"""Terminal status sink (used with --no-ui, in tests, and as fallback when tkinter is missing)."""
from __future__ import annotations

from rich.panel import Panel

from undo.log import console, get_logger
from undo.i18n import t

log = get_logger("ui")

STATE_LABELS = {
    "idle": "Ready",
    "listening": "Listening…",
    "transcribing": "Transcribing…",
    "heard": "Heard",
    "analyzing": "Going through the recording…",
    "understood": "Understood",
    "executing": "Taking over",
    "done": "Done",
    "failed": "Failed",
    "stopped": "Stopped",
}


class ConsoleUI:
    def __init__(self, auto_confirm: bool = False, default_answer: str | None = None):
        self.auto_confirm = auto_confirm
        self.default_answer = default_answer
        self.state = "idle"

    def set_state(self, state: str, text: str = "") -> None:
        self.state = state
        console.print(Panel(text or "", title=f"Undo — {t(STATE_LABELS.get(state, state))}", border_style="cyan" if state not in {"failed", "stopped"} else "red"))

    def add_step(self, text: str) -> None:
        console.print(f"  [bold cyan]→[/] {text}")

    def confirm(self, question: str) -> bool:
        if self.auto_confirm:
            console.print(f"[yellow]{question}[/] → auto-confirm")
            return True
        try:
            return console.input(f"[yellow]{question}[/] [y/N] ").strip().lower() in {"o", "oui", "y", "yes"}
        except EOFError:
            console.print(f"[red]{t('no terminal to confirm → refused')}[/]")
            return False

    def ask(self, question: str) -> str:
        if self.default_answer is not None:
            return self.default_answer
        try:
            return console.input(f"[yellow]{question}[/] ")
        except EOFError:
            console.print(f"[red]{t('no terminal to answer')}[/]")
            return "(no answer available: the user cannot be reached; use the recovered content from the analysis or call done)"

    def start(self, worker) -> None:
        """Run `worker()` on the main thread (no event loop needed)."""
        worker()

    def quit(self) -> None:
        pass
