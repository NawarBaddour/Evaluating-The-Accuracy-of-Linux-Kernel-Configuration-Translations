import shutil
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import plotnine as p9
import regex
import z3
from kmax.klocalizer import Klocalizer
from rich.rule import Rule
from rich.table import Table

from .evaluator import Categories, Evaluator, HasStats, HasTypes, Types
from .logger import Header
from .model_to_config import ModelToConfig
from .plot_theme import PlotTheme
from .utils import format_percent, run_command


class ConfigToModel(Evaluator):
    def __init__(
        self,
        output_dir,
        linux_ksrc,
        kernel_version,
        arch,
        constraints,
        seed,
        logger,
    ):
        super().__init__(
            output_dir, linux_ksrc, kernel_version, arch, seed, logger
        )

        self._constraints = constraints

    def gen_config_in(self, seed):
        run_command(
            [
                "make",
                f"ARCH={self._arch.name}",
                f"KCONFIG_SEED={seed}",
                "randconfig",
            ],
            self.logger,
            self._linux_ksrc,
        )

        randconfig_file = self._linux_ksrc / ".config"
        return randconfig_file.read_text()

    def evaluate(self, num_configs, round_trip=False, prev_eval_dir=None):
        self.logger.push(self._output_dir / "configs.log")

        configs_dir = self._output_dir / "configs"
        configs_dir.mkdir(parents=True)
        self.logger.debug(f"Created configurations directory: '{configs_dir}'")

        width = len(str(num_configs))

        kconfig_types = self._arch.get_kconfig_types()
        freq = (
            ModelToConfig._Freq(self.logger)
            if round_trip
            else self._Freq(self.logger)
        )
        total = ModelToConfig._Stats() if round_trip else self._Stats()
        for i in range(1, num_configs + 1):
            config_seed = self._seed + i

            config_num = f"{i:0{width}d}"
            self.logger.info(Header(f"Configuration {config_num}", 2))

            config_name = f"{config_num}.config"
            config_dir = configs_dir / config_name
            config_dir.mkdir(parents=True)
            self.logger.debug(
                f"Created configuration directory: '{config_dir}'"
            )
            config_file = config_dir / config_name

            config_in_file = Path(f"{config_file}.in")
            if round_trip:
                prev_config_file = (
                    prev_eval_dir / configs_dir.name / config_name / config_name
                )
                shutil.copy(Path(f"{prev_config_file}.in"), config_in_file)
                config = Path(f"{prev_config_file}.out").read_text()
            else:
                self.logger.info(
                    f"Generating configuration '{config_in_file}'..."
                )
                config = self.gen_config_in(config_seed)
                config_in_file.write_text(config)

            config_diff_file = Path(f"{config_file}.diff")
            config_out_file = Path(f"{config_file}.out")
            if round_trip:
                self.logger.info(
                    f"Generating configuration '{config_out_file}'..."
                )
            else:
                self.logger.info(f"Generating diff '{config_diff_file}'...")

            result = self._EvaluationResult(
                config_num,
                config,
                self._constraints,
                Klocalizer.get_config_file_constraints(config_in_file),
                config_seed,
                kconfig_types,
                self.logger,
            )

            if not round_trip:
                self.logger.push(config_diff_file)
                result.log_diffs()
                result.log_result()
                self.logger.pop()

                self.logger.info(
                    f"Generating configuration '{config_out_file}'..."
                )
            new_config = result.gen_config_out()
            config_out_file.write_text(new_config)

            if round_trip:
                self.logger.info(f"Generating diff '{config_diff_file}'...")
                result = ModelToConfig._EvaluationResult(
                    config_num,
                    config_in_file.read_text(),
                    new_config,
                    kconfig_types,
                    self.logger,
                )
                self.logger.push(config_diff_file)
                result.log_diffs()
                result.log_result()
                self.logger.pop()

            total += result.stats

            self.logger.info("Updating frequencies...")
            freq.update(result)

        self.logger.pop()

        header_text = (
            "Model to Config Round-Trip" if round_trip else "Config to Model"
        )
        self.logger.info(Rule(f"{header_text} Frequencies"))
        self.logger.info(Header("Frequencies", 2))
        self.logger.info("Generating frequencies...")
        self.logger.push(self._output_dir / "frequencies.log")
        freq.log()
        self.logger.pop()

        self.logger.info(Rule(f"{header_text} Results"))
        self.logger.info(Header("Results", 2))
        self.logger.info("Generating results...")
        self.logger.push(self._output_dir / "results.log")
        total_table = total.get_table("Total")
        self.logger.info(total_table)
        self.logger.pop()

        plots_dir = self._output_dir / "plots"
        plots_dir.mkdir(parents=True)
        self.logger.info(Header("Plots", 2))
        self.logger.debug(f"Created plots directory: '{plots_dir}'")
        self.logger.info("Generating plots...")
        random_state = np.random.RandomState(self._seed)
        freq.plot(plots_dir, random_state)

    class _Freq(HasStats):
        def __init__(self, logger):
            self.logger = logger
            super().__init__(dict)

        def update(self, result):
            for cat in Categories:
                freq_cat_obj = getattr(self, cat.value)
                res_cat_obj = (
                    result.config_types
                    if cat == Categories.ENABLED
                    else getattr(result, cat.value)
                )
                for t in Types:
                    freq_cat_type_obj = getattr(freq_cat_obj, t.value)
                    res_cat_type_obj = getattr(res_cat_obj, t.value)
                    for name in res_cat_type_obj:
                        freq_cat_type_obj[name] = (
                            freq_cat_type_obj.get(name, 0) + 1
                        )
                        freq_cat_obj.all[name] = (
                            freq_cat_obj.all.get(name, 0) + 1
                        )

        def log(self):
            for t in Types:
                table = Table(
                    title=f"Frequency of Type: '{t.value}'", expand=True
                )

                columns = {}
                for cat in Categories:
                    table.add_column(
                        cat.value.title(),
                        header_style=cat.color,
                        style=cat.color,
                        overflow="fold",
                    )

                    self_cat_obj = getattr(self, cat.value)
                    self_cat_type_obj = getattr(self_cat_obj, t.value)
                    columns[cat.value] = sorted(
                        self_cat_type_obj.items(),
                        key=lambda x: x[1],
                        reverse=True,
                    )

                for i in range(len(getattr(self.enabled, t.value))):
                    cells = []
                    for cat in Categories:
                        if i < len(columns[cat.value]):
                            cell = columns[cat.value][i]
                            cells.append(f"{cell[0]}: {cell[1]}")
                        else:
                            cells.append("")
                    table.add_row(*cells)
                self.logger.debug(table)

        def _to_dataframe(self):
            rows = []
            for cat in Categories:
                self_cat_obj = getattr(self, cat.value)
                for t in Types:
                    self_cat_type_obj = getattr(self_cat_obj, t.value)
                    for name, freq in self_cat_type_obj.items():
                        rows.append([name, t.value, cat.value, freq])

            df = pd.DataFrame(
                rows, columns=["Feature", "Type", "Category", "Frequency"]
            )
            df["Category"] = pd.Categorical(
                df["Category"],
                categories=[c.value for c in reversed(Categories)],
                ordered=True,
            )
            df["Type"] = pd.Categorical(
                df["Type"],
                categories=[t.value for t in reversed(Types)],
                ordered=True,
            )

            return df

        def plot(self, output_dir, random_state):
            width = 15
            base_size = width
            big_theme = PlotTheme((width, width * 2 / 3), base_size)
            small_theme = PlotTheme((width, width / 3), base_size)

            df = self._to_dataframe()

            df["Group"] = df["Category"].apply(
                lambda x: "Enabled" if x == "enabled" else "Diff"
            )
            pl1 = (
                p9.ggplot(df, p9.aes("Type", "Frequency", color="Category"))
                + p9.geom_jitter(
                    width=0.25, size=0.5, alpha=0.6, random_state=random_state
                )
                + p9.stat_summary(
                    fun_y=np.mean, geom="point", size=3, color="black"
                )
                + p9.facet_wrap("Group")
                + p9.labs(title="Data Points")
                + p9.scale_color_manual(values=PlotTheme.PALETTE)
                + big_theme
            )
            pl1.save(output_dir / "data_points.svg", verbose=False)

            pl2 = (
                p9.ggplot(df, p9.aes("Type", "Frequency", fill="Category"))
                + p9.geom_boxplot(alpha=0.7)
                + p9.labs(title="Boxplot")
                + p9.scale_fill_manual(values=PlotTheme.PALETTE)
                + small_theme
            )
            pl2.save(output_dir / "boxplot.svg", verbose=False)

            pl3 = (
                p9.ggplot(df, p9.aes("Type", "Frequency", fill="Category"))
                + p9.geom_violin(alpha=0.7)
                + p9.labs(title="Distribution by Type")
                + p9.scale_fill_manual(values=PlotTheme.PALETTE)
                + small_theme
            )
            pl3.save(output_dir / "distribution_by_type.svg", verbose=False)

            pl4 = (
                p9.ggplot(df, p9.aes("Frequency", color="Category"))
                + p9.stat_ecdf()
                + p9.facet_wrap("Type")
                + p9.labs(
                    title="Cumulative Relative Frequency Graph",
                    y="Cumulative Relative Proportion",
                )
                + p9.scale_color_manual(values=PlotTheme.PALETTE)
                + big_theme
            )
            pl4.save(
                output_dir / "cumulative_relative_frequency_graph.svg",
                verbose=False,
            )

            df_sum = df.groupby(["Category", "Type"], as_index=False)[
                "Frequency"
            ].sum()
            df_diff = df_sum[df_sum["Category"] != "enabled"]
            df_enabled = df_sum[df_sum["Category"] == "enabled"]
            pl5_diff = (
                p9.ggplot(df_diff, p9.aes("Type", "Frequency", fill="Category"))
                + p9.geom_col(position="dodge", alpha=0.7)
                + p9.labs(title="Diff")
                + p9.scale_fill_manual(values=PlotTheme.PALETTE)
                + small_theme
                + p9.theme(legend_position="none")
            )
            pl5_enabled = (
                p9.ggplot(
                    df_enabled, p9.aes("Type", "Frequency", fill="Category")
                )
                + p9.geom_col(alpha=0.7)
                + p9.labs(title="Enabled")
                + p9.scale_fill_manual(values=PlotTheme.PALETTE)
                + small_theme
            )
            pl5 = pl5_diff | pl5_enabled
            pl5.save(output_dir / "total_per_type.svg", verbose=False)

    class _Stats(HasStats):
        def __init__(self):
            super().__init__(int)

        def __add__(self, other):
            result = ConfigToModel._Stats()
            for cat in Categories:
                self_cat_obj = getattr(self, cat.value)
                other_cat_obj = getattr(other, cat.value)
                result_cat_obj = getattr(result, cat.value)
                result_cat_obj.all = self_cat_obj.all + other_cat_obj.all
                for t in Types:
                    self_cat_type_count = getattr(self_cat_obj, t.value)
                    other_cat_type_count = getattr(other_cat_obj, t.value)
                    setattr(
                        result_cat_obj,
                        t.value,
                        self_cat_type_count + other_cat_type_count,
                    )
            return result

        def get_table(self, title):
            table = Table(
                title=title,
                caption=f"Percentages are relative to the row total ('{list(Categories)[-1].title()}')",
                expand=True,
                show_footer=True,
            )

            table.add_column(
                "Type",
                "All",
                ratio=1,
                overflow="fold",
            )
            for cat in Categories:
                self_cat_obj = getattr(self, cat.value)
                self_cat_all_count = self_cat_obj.all
                self_enabled_all_count = self.enabled.all
                table.add_column(
                    cat.value.title(),
                    f"{self_cat_all_count} ({format_percent(self_cat_all_count, self_enabled_all_count)})",
                    ratio=1,
                    justify="center",
                    header_style=cat.color,
                    footer_style=cat.color,
                    style=cat.color,
                    overflow="fold",
                )

            for t in Types:
                cells = [t.value]
                self_enabled_type_count = getattr(self.enabled, t.value)
                for cat in Categories:
                    self_cat_obj = getattr(self, cat.value)
                    self_cat_type_count = getattr(self_cat_obj, t.value)
                    cells.append(
                        f"{self_cat_type_count} ({format_percent(self_cat_type_count, self_enabled_type_count)})",
                    )
                table.add_row(*cells)
            return table

    class _EvaluationResult:
        class _ConfigTypes(HasTypes):
            def __init__(self, config=None, kconfig_types=None):
                super().__init__(dict)

                if config and kconfig_types:
                    pattern_on = regex.compile("^(CONFIG_[A-Za-z0-9_]+)=(.*)$")
                    for line in config.splitlines():
                        pattern_on_match = pattern_on.match(line)
                        if pattern_on_match:
                            name = pattern_on_match.group(1)
                            value = pattern_on_match.group(2)
                            getattr(self, kconfig_types[name])[name] = value
                        elif line.strip() and not line.startswith("#"):
                            raise RuntimeError(f"Invalid config line: `{line}`")

        @dataclass
        class _Removed:
            old: str
            reason: str

        @dataclass
        class _Changed:
            old: str
            new: str

        def __init__(
            self,
            num,
            config,
            constraints,
            assumptions,
            seed,
            kconfig_types,
            logger,
        ):
            self.num = num
            self.config = config
            self.config_types = self._ConfigTypes(config, kconfig_types)
            self.new_config_types = self._ConfigTypes()
            self.new_config_types.bool = deepcopy(self.config_types.bool)
            self.new_config_types.tristate = deepcopy(
                self.config_types.tristate
            )
            self.changed = HasTypes()
            self.removed = HasTypes()
            self.removed.number = deepcopy(self.config_types.number)
            self.removed.string = deepcopy(self.config_types.string)
            self.added = HasTypes()
            self.logger = logger

            solver = z3.Solver()
            solver.set(unsat_core=True)
            solver.set(random_seed=seed)
            solver.add(constraints)

            is_sat = solver.check(assumptions) == z3.sat
            if is_sat:
                self.logger.info("Already satisfiable")
            else:
                self.logger.info("Removing unsatisfiable constraints...")
                while not is_sat:
                    core = sorted(solver.unsat_core(), key=str)
                    var = core[0]

                    removed = True
                    res_cat_obj = self.removed
                    if z3.is_not(var):
                        removed = False
                        res_cat_obj = self.added
                        var = var.children()[0]

                    name = var.decl().name()
                    t = kconfig_types[name]

                    new_config_type_obj = getattr(self.new_config_types, t)
                    res_cat_type_obj = getattr(res_cat_obj, t)
                    res_cat_type_obj[name] = self._Removed(
                        "y", str(core).replace("\n", " ")
                    )

                    if removed:
                        del new_config_type_obj[name]
                    else:
                        new_config_type_obj[name] = "y"
                    assumptions.remove(core[0])

                    is_sat = solver.check(assumptions) == z3.sat

            pattern_m = regex.compile("^(CONFIG_[A-Za-z0-9_]+)=m$")
            for line in self.config.splitlines():
                pattern_on_match = pattern_m.match(line)
                if pattern_on_match:
                    name = pattern_on_match.group(1)
                    if name not in self.removed.tristate:
                        self.changed.tristate[name] = self._Changed("m", "y")
                    else:
                        self.removed.tristate[name].old = "m"

            self.stats = self._get_stats()

        def _get_stats(self):
            ret = ConfigToModel._Stats()
            for cat in Categories:
                ret_cat_obj = getattr(ret, cat.value)
                res_cat_obj = (
                    self.config_types
                    if cat == Categories.ENABLED
                    else getattr(self, cat.value)
                )
                for t in Types:
                    res_cat_type_count = len(getattr(res_cat_obj, t.value))
                    setattr(ret_cat_obj, t.value, res_cat_type_count)
                    ret_cat_obj.all += getattr(ret_cat_obj, t.value)
            return ret

        def gen_config_out(self):
            ret = ""
            pattern_on = regex.compile("^(CONFIG_[A-Za-z0-9_]+)=(.*)$")
            pattern_off = regex.compile("^# (CONFIG_[A-Za-z0-9_]+) is not set")
            for line in self.config.splitlines():
                pattern_on_match = pattern_on.match(line)
                pattern_off_match = pattern_off.match(line)
                if pattern_on_match:
                    name = pattern_on_match.group(1)
                    removed = False
                    for t in Types:
                        if name in getattr(self.removed, t.value):
                            removed = True
                            break
                    if not removed:
                        ret += f"{name}=y\n"
                elif pattern_off_match:
                    name = pattern_off_match.group(1)
                    added = False
                    for t in Types:
                        if name in getattr(self.added, t.value):
                            added = True
                            break
                    if added:
                        ret += f"{name}=y\n"
                    else:
                        ret += f"{line}\n"
                elif not line.strip() or line.startswith("#"):
                    ret += f"{line}\n"
                else:
                    raise RuntimeError(f"Invalid config line: `{line}`")
            return ret

        def log_diffs(self):
            for t in Types:
                changed_dict = getattr(self.changed, t.value)
                removed_dict = getattr(self.removed, t.value)
                added_dict = getattr(self.added, t.value)

                table = Table(title=f"Diff of Type: '{t.value}'")
                table.add_column(
                    "Removed",
                    header_style="red",
                    style="red",
                    overflow="fold",
                )
                table.add_column(
                    "Added",
                    header_style="green",
                    style="green",
                    overflow="fold",
                )

                if t in ["bool", "tristate"]:
                    table.add_column(
                        "Reason",
                        header_style="blue",
                        style="blue",
                        overflow="fold",
                    )

                    for name, value in removed_dict.items():
                        table.add_row(f"{name}={value.old}", "", value.reason)

                    for name, value in added_dict.items():
                        table.add_row("", f"{name}={value.old}", value.reason)

                    for name, value in changed_dict.items():
                        table.add_row(
                            f"{name}={value.old}", f"{name}={value.new}"
                        )
                else:
                    for name, value in removed_dict.items():
                        table.add_row(f"{name}={value}", "")

                    for name, value in added_dict.items():
                        table.add_row("", f"{name}={value}")

                self.logger.debug(table)

        def log_result(self):
            table = self.stats.get_table(f"Configuration {self.num}")
            self.logger.debug(table)
