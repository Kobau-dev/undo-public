"""macOS menu bar icon (rumps). Runs as its own process and talks to the daemon through ~/.undo/control.json."""
from __future__ import annotations

import json
import subprocess
import sys

from undo.config import Settings
from undo.i18n import t


def _write(settings: Settings, **changes) -> dict:
    path = settings.control_path
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text() or "{}")
        except json.JSONDecodeError:
            data = {}
    data.update(changes)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data


def main(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    try:
        import rumps  # type: ignore
    except ImportError:
        print("rumps is macOS-only: pip install rumps", file=sys.stderr)
        sys.exit(1)

    BUFFER_CHOICES = (30, 120, 480, 1440)

    def _label(minutes: int) -> str:
        return f"{minutes} min" if minutes < 60 else f"{minutes // 60} h"

    class UndoBar(rumps.App):
        def __init__(self):
            super().__init__("↶", quit_button=None)
            self.proc: subprocess.Popen | None = None
            self.pause_item = rumps.MenuItem(t("Pause recording"), callback=self.toggle_pause)
            self.run_item = rumps.MenuItem(t("Start Undo"), callback=self.toggle_run)
            buffer_menu = rumps.MenuItem(t("Buffer length"))
            for minutes in BUFFER_CHOICES:
                item = rumps.MenuItem(_label(minutes), callback=self.set_buffer)
                item.state = minutes == settings.buffer_minutes
                buffer_menu.add(item)
            self.menu = [self.run_item, self.pause_item, buffer_menu, None, rumps.MenuItem(t("Quit"), callback=self.quit_all)]

        def toggle_run(self, sender):
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
                self.proc = None
                sender.title = t("Start Undo")
                self.title = "↶"
            else:
                self.proc = subprocess.Popen([sys.executable, "-m", "undo", "run"])
                sender.title = t("Stop Undo")
                self.title = "↶●"

        def toggle_pause(self, sender):
            sender.state = not sender.state
            _write(settings, paused=bool(sender.state))
            self.title = "↶⏸" if sender.state else ("↶●" if self.proc else "↶")

        def set_buffer(self, sender):
            minutes = next(m for m in BUFFER_CHOICES if _label(m) == sender.title)
            for item in self.menu[t("Buffer length")].values():
                item.state = item.title == sender.title
            _write(settings, buffer_minutes=minutes)

        def quit_all(self, sender):
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
            rumps.quit_application()

    UndoBar().run()


if __name__ == "__main__":
    main()
