import logging
import os

from rich.console import Console
from rich.logging import RichHandler

console = Console(stderr=True)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose or os.environ.get("UNDO_DEBUG") else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="%H:%M:%S",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False, markup=True)],
        force=True,
    )
    logging.getLogger().handlers[0].addFilter(_OnlyUndoBelowWarning())


class _OnlyUndoBelowWarning(logging.Filter):
    """Third-party libraries (httpx/httpcore/openai/urllib3/PIL...) only get through at WARNING+."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.WARNING or record.name.startswith("undo")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"undo.{name}")
