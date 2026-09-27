import subprocess

from rich.columns import Columns
from rich.markdown import Markdown

from .logger import CommandOutput


def run_command(command, logger, cwd=None):
    logger.debug(
        Columns(
            [
                Markdown(f"`{' '.join(command)}`", justify="center"),
            ],
            title="[bold green]Running command...",
        )
    )
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)

    title = "[bold black on "
    if result.stdout:
        logger.debug(CommandOutput(result.stdout, title + "green]STDOUT"))

    if result.stderr:
        if result.returncode != 0:
            logger.error(CommandOutput(result.stderr, title + "red]STDERR"))
            raise subprocess.CalledProcessError(
                result.returncode,
                command,
                result.stdout,
                result.stderr,
            )
        else:
            logger.warning(
                CommandOutput(result.stderr, title + "yellow]STDERR")
            )

    return result.stdout


def format_percent(numerator, denominator, precision=3):
    if denominator == 0:
        return "N/A"
    percent = numerator * 100 / denominator
    formatted = f"{percent:.{precision}f}".rstrip("0").rstrip(".")
    return f"{formatted}%"
