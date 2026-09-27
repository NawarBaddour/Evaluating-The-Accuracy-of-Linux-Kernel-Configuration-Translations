import plotnine as p9


class PlotTheme(p9.theme_gray):
    DARK_COLOR = "#5B4F41"
    LIGHT_COLOR = "#FCF9F4"

    PALETTE = {
        "enabled": "#1f77b4",
        "added": "#2ca02c",
        "removed": "#d62728",
        "changed": "#ff7f0e",
    }

    def __init__(self, figure_size, base_size):
        super().__init__(base_size=base_size)
        self += p9.theme(
            figure_size=figure_size,
            text=p9.element_text(color=self.DARK_COLOR),
            legend_key=p9.element_blank(),
            panel_background=p9.element_rect(fill=self.LIGHT_COLOR),
            panel_grid_major=p9.element_line(
                color=self.DARK_COLOR, linetype="dashdot", alpha=0.1
            ),
            panel_grid_minor=p9.element_blank(),
            panel_border=p9.element_rect(color=self.DARK_COLOR),
            strip_background=p9.element_blank(),
        )
