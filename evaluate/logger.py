import logging
import sys
from functools import partialmethod

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.terminal_theme import MONOKAI
from rich.text import Text


class Logger:
    _FILE_LINE_WIDTH = 180
    _LEVEL_WIDTH = 8
    _STACK_OFFSET = 2

    def __init__(self, level=logging.NOTSET, files=[]):
        self.level = level
        self._file_consoles = []

        width = None
        if not sys.stdout.isatty():
            width = self._FILE_LINE_WIDTH
        self._console = Console(width=width)

        files = files if isinstance(files, list) else [files]
        for file in files:
            self.push(file)

    def push(self, file, record=True):
        self._file_consoles.append(
            Console(
                file=open(file, "a"),
                width=Logger._FILE_LINE_WIDTH,
                record=record,
            )
        )

    def pop(self):
        file_console = self._file_consoles.pop()
        if file_console.record:
            file_console.save_html(
                f"{file_console.file.name}.html", theme=MONOKAI
            )
        return file_console.file.name

    @classmethod
    def _get_level_text(cls, level: int):
        level_name = logging.getLevelName(level)
        level_text = Text.styled(
            level_name.ljust(cls._LEVEL_WIDTH),
            f"logging.level.{level_name.lower()}",
        )
        return level_text

    def _log(self, level, message, show_level=True):
        output = message
        if show_level:
            output = Table.grid(padding=(0, 1), expand=True)
            output.add_column(style="log.level", width=self._LEVEL_WIDTH)
            output.add_column(
                ratio=1, highlight=True, style="log.message", overflow="fold"
            )
            output.add_row(self._get_level_text(level), message)

        if level >= self.level:
            self._console.log(output, _stack_offset=self._STACK_OFFSET)

        for file_console in self._file_consoles:
            file_console.log(output, _stack_offset=self._STACK_OFFSET)

    debug = partialmethod(_log, logging.DEBUG)
    info = partialmethod(_log, logging.INFO)
    warning = partialmethod(_log, logging.WARNING)
    error = partialmethod(_log, logging.ERROR)
    critical = partialmethod(_log, logging.CRITICAL)


class Header:
    def __init__(self, text: str, level=1):
        self.text = text
        self.level = max(1, min(level, 6))

    def __rich_console__(self, console, options):
        header_text = f"{'#' * self.level} {self.text}"
        yield Markdown(header_text)


class CommandOutput:
    def __init__(self, output: str, title):
        self.output = output
        self.title = title

    def __rich_console__(self, console, options):
        output = Syntax(
            "\n".join("    " + line for line in self.output.splitlines()),
            "console",
            line_numbers=True,
            word_wrap=True,
            padding=(1, 0),
        )
        yield Panel(output, title=self.title)
