__all__ = ["cli"]


import argparse
import logging
import os
import sys
import warnings
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Type

import kmax.arch
from kmax.arch import Arch
from kmax.klocalizer import Klocalizer
from plotnine.exceptions import PlotnineWarning
from rich import traceback
from rich.markdown import Markdown
from rich.rule import Rule

from evaluate.config_to_model import ConfigToModel

from .logger import Header, Logger
from .model_to_config import ModelToConfig
from .utils import run_command


class _CLI:
    def __init__(self):
        self._patch_logging()
        self._parse_args()

    def run(self):
        run_start_date = datetime.now()

        run_date = run_start_date.strftime("%Y-%m-%d_%H-%M-%S")
        run_name = f"run_{run_date}"
        self._run_output_dir = self._output_dir / run_name
        self._run_output_dir.mkdir(parents=True)

        self.logger = Logger(self.logging_level)
        self.logger.push(self._run_output_dir / f"{run_name}.log")

        self.logger.push(self._run_output_dir / "initializing.log")
        self.logger.info(Header(run_name, 1))
        self.logger.debug(Markdown(f"Running: `{' '.join(sys.argv)}`"))
        self.logger.info(Header("Initializing...", 2))
        self.logger.info(f"Created output directory: '{self._run_output_dir}'")
        self._init_constraints()
        self.logger.pop()

        if self._EvalModes.M2C in self._eval_modes:
            self.logger.info(Rule(self._EvalModes.M2C.value))

            eval_dir = self._run_output_dir / "model_to_config"
            ModelToConfig(
                eval_dir,
                self._linux_ksrc,
                self._kernel_version,
                self._arch,
                self._constraints,
                self._seed,
                self.logger,
            ).evaluate(self._num_configs)
            if self._round_trip:
                self.logger.info(
                    Rule(f"{self._EvalModes.M2C.value} Round-Trip")
                )

                ConfigToModel(
                    Path(f"{eval_dir}_round_trip"),
                    self._linux_ksrc,
                    self._kernel_version,
                    self._arch,
                    self._constraints,
                    self._seed,
                    self.logger,
                ).evaluate(self._num_configs, True, eval_dir)

        if self._EvalModes.C2M in self._eval_modes:
            self.logger.info(Rule(self._EvalModes.C2M.value))

            eval_dir = self._run_output_dir / "config_to_model"
            ConfigToModel(
                eval_dir,
                self._linux_ksrc,
                self._kernel_version,
                self._arch,
                self._constraints,
                self._seed,
                self.logger,
            ).evaluate(self._num_configs)
            if self._round_trip:
                self.logger.info(
                    Rule(f"{self._EvalModes.C2M.value} Round-Trip")
                )

                ModelToConfig(
                    Path(f"{eval_dir}_round_trip"),
                    self._linux_ksrc,
                    self._kernel_version,
                    self._arch,
                    self._constraints,
                    self._seed,
                    self.logger,
                ).evaluate(self._num_configs, True, eval_dir)

        self.logger.info(Rule("Finalizing"))
        self.logger.push(self._run_output_dir / "finalizing.log")
        self.logger.info(Header("Finalizing...", 2))
        elapsed = datetime.now() - run_start_date
        elapsed = elapsed - timedelta(microseconds=elapsed.microseconds)
        self.logger.debug(f"Total elapsed time: {elapsed} (HH:MM:SS)")
        self.logger.pop()
        self.logger.pop()

    def _patch_logging(self):
        traceback.install()

        # Monkey-patch getLogger for inhanced logging in kmax.arch
        kmax.arch.getLogger = lambda *args, **kwargs: self.logger

        warnings.filterwarnings(
            "ignore",
            "To compute the density of a group with only one value set the bandwidth manually. e.g `bw=0.1`",
            PlotnineWarning,
        )
        warnings.filterwarnings(
            "ignore",
            "Groups with fewer than 2 data points have been removed.",
            PlotnineWarning,
        )

    def _parse_args(self):
        def existing_writable_dir(path_str):
            path = Path(path_str)
            if not path.is_dir():
                raise argparse.ArgumentTypeError(
                    f"'{path}' is not a valid directory"
                )
            if not os.access(path, os.W_OK):
                raise argparse.ArgumentTypeError(
                    f"no write permission in directory '{path}'"
                )
            return path

        def creatable_dir(path_str):
            path = Path(path_str)
            existing = next(
                (
                    parent
                    for parent in [path] + list(path.parents)
                    if parent.exists()
                )
            )
            if not existing.is_dir():
                raise argparse.ArgumentTypeError(
                    f"'{existing}' exists and is not a directory"
                )
            if not os.access(existing, os.W_OK):
                raise argparse.ArgumentTypeError(
                    f"no write permission in directory '{existing}'"
                )
            return path

        def positive_int(value):
            value = int(value)
            if value <= 0:
                raise argparse.ArgumentTypeError(
                    f"invalid int value: '{value}'; must be at least 1"
                )
            return value

        def eval_mode(value):
            try:
                return self._EvalModes[value.upper()]
            except KeyError:
                return value

        parser = argparse.ArgumentParser(
            description="Evaluating The Accuracy of Linux Kernel Configuration Translations",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
        parser.register("action", "append unique", self._AppendUnique)
        parser.register("type", "existing writable dir", existing_writable_dir)
        parser.register("type", "creatable dir", creatable_dir)
        parser.register("type", "positive int", positive_int)
        parser.register("type", "eval mode", eval_mode)

        parser.add_argument(
            "-o",
            "--output-dir",
            type="creatable dir",
            default="./results",
            help="path to the output directory",
        )
        parser.add_argument(
            "-l",
            "--linux-ksrc",
            type="existing writable dir",
            default=".",
            help="path to the Linux kernel source directory",
        )
        parser.add_argument(
            "-c",
            "--cache-dir",
            type="creatable dir",
            default="./kmax.cache",
            help="path to the cache directory. Load existing files or write new ones",
        )
        parser.add_argument(
            "-a",
            "--arch",
            nargs="+",
            choices=Arch.ARCHS,
            metavar="ARCH",
            default=["x86_64"],
            help=f"architecture to evaluate. Available architectures: {Arch.ARCHS}",
        )
        parser.add_argument(
            "-e",
            "--eval",
            nargs="+",
            type="eval mode",
            choices=self._EvalModes,
            action="append unique",
            metavar="EVAL",
            default=argparse.SUPPRESS,
            help=f"what to evaluate. Available evaluations: { {mode.name: mode.value for mode in self._EvalModes} } (default: all)",
        )
        parser.add_argument(
            "--roundtrip",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="enable or disable round-trip for evaluations",
        )
        parser.add_argument(
            "-n",
            "--num-configs",
            type="positive int",
            default=1,
            help="generate the given number of configurations",
        )
        parser.add_argument(
            "-s",
            "--seed",
            type=int,
            default=0,
            help="random seed for the solver's model generation and for `make randconfig`",
        )

        parser.set_defaults(logging_level=logging.INFO)
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "-q",
            "--quiet",
            action="store_const",
            const=logging.WARNING,
            dest="logging_level",
            help="quiet mode prints no messages to stdout",
        )
        group.add_argument(
            "-v",
            "--verbose",
            action="store_const",
            const=logging.DEBUG,
            dest="logging_level",
            help="verbose mode prints additional messages to stdout",
        )

        args = parser.parse_args()
        if "eval" not in args:
            args.eval = [mode for mode in self._EvalModes]

        self._output_dir = args.output_dir
        self._linux_ksrc = args.linux_ksrc
        self._cache_dir = args.cache_dir
        self._arch_name = args.arch[0]
        self._eval_modes = args.eval
        self._round_trip = args.roundtrip
        self._num_configs = args.num_configs
        self._seed = args.seed
        self.logging_level = args.logging_level

    def _init_constraints(self):
        self.logger.info("Getting kernel version...")
        self._kernel_version = run_command(
            ["make", "kernelversion"], self.logger, self._linux_ksrc
        ).strip()

        self.logger.info(
            f"Computing constraints for architecture '{self._arch_name}'..."
        )

        arch_dir = self._cache_dir / self._kernel_version / self._arch_name
        self._arch = Arch(
            self._arch_name,
            self._linux_ksrc,
            arch_dir,
            False,
            False,
            None,
            self.logger.level,
            ["--disable-tristate-support"],
        )

        klocalizer = Klocalizer()
        klocalizer.set_logger(self.logger)
        klocalizer.set_linux_krsc(self._linux_ksrc)
        self._constraints = klocalizer.compile_constraints(self._arch)

    class _EvalModes(str, Enum):
        klass: Type

        M2C = ("Model to Config", ModelToConfig)
        C2M = ("Config to Model", ConfigToModel)

        def __new__(cls, value, klass):
            obj = str.__new__(cls, value)
            obj._value_ = value
            obj.klass = klass
            return obj

        def __str__(self):
            return self.name

    class _AppendUnique(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            existing = getattr(namespace, self.dest, None)
            if existing is None:
                existing = []

            values = values if isinstance(values, list) else [values]
            for value in values:
                if value in existing:
                    existing.remove(value)
                existing.append(value)
            setattr(namespace, self.dest, existing)


cli = _CLI()
