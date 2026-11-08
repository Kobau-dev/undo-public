import json
import os
import subprocess
import sys

from undo.app import UndoApp, export_recording
from undo.analyzer import Analyzer
from undo.executor import AgentExecutor
from undo.executor.control import DryRunController
from undo.executor.screen import ScreenSource
from undo.providers.mock import ScriptedVisionModel
from undo.ui.console import ConsoleUI
from tests.conftest import record_scene
from tests.test_analyzer import GOOD, _scenes
from tests.test_executor import FakeCap


def test_end_to_end_dry_run_pauses_recorder(recorder, settings, tmp_path):
    record_scene(recorder, _scenes())
    settings.dry_run = True
    settings.step_delay = 0
    model = ScriptedVisionModel([GOOD, ("click", {"x": 300, "y": 300, "target": "Nom"}), ("type", {"text": "Dupont"}), ("done", {"text": "Formulaire restauré"})])
    ui = ConsoleUI(auto_confirm=True)
    app = UndoApp(settings, ui, vision=model, recorder=recorder)
    pauses = []
    ctrl = DryRunController()
    app.executor = AgentExecutor(
        settings, model, controller=ctrl, screen=ScreenSource(1440, capturer=FakeCap(), logical_size=(1440, 900)), ui=ui,
        on_start=lambda: (recorder.pause("executor"), pauses.append(recorder.paused)), on_finish=lambda: (recorder.resume("executor"), pauses.append(recorder.paused)),
    )
    result = app.handle_request("remets le formulaire")
    assert result and result.success
    assert pauses == [True, False]
    assert ctrl.log == ["left_click(432, 270)", "type('Dupont')"]
    runs = list((settings.data_dir / "runs").glob("*.json"))
    assert len(runs) == 1
    data = json.loads(runs[0].read_text())
    assert data["analysis"]["strategy"] == "manual_redo" and data["result"]["success"]


def test_low_confidence_asks_before_acting(recorder, settings):
    record_scene(recorder, _scenes())
    low = dict(GOOD, confidence=0.2)

    class NoUI(ConsoleUI):
        def confirm(self, q):
            return False

    app = UndoApp(settings, NoUI(), vision=ScriptedVisionModel([low]), recorder=recorder)
    assert app.handle_request("formulaire") is None


def test_export_and_replay(recorder, settings, tmp_path, monkeypatch):
    monkeypatch.setenv("UNDO_TIMELINE", "0")
    record_scene(recorder, _scenes())
    out = export_recording(settings, tmp_path / "export", minutes=30)
    assert (out / "frames.db").exists() and (out / "meta.json").exists()
    assert len(list((out / "frames").glob("*.jpg"))) == 5
    from undo.recorder import FrameIndex

    idx = FrameIndex(out / "frames.db")
    frames = idx.latest(10)
    assert len(frames) == 5 and all(f.path.startswith("frames/") for f in frames)
    assert idx.search("Lilas")
    # replay through the CLI path with a scripted model
    import undo.__main__ as cli
    import undo.providers as providers

    orig = providers.build_vision
    providers.build_vision = lambda s, role="executor": ScriptedVisionModel([GOOD])
    try:
        rc = cli.main(["analyze", "--replay", str(out), "formulaire perdu", "--data-dir", str(settings.data_dir)])
    finally:
        providers.build_vision = orig
    assert rc == 0


def test_cli_status(settings, recorder):
    import undo.__main__ as cli

    assert cli.main(["status", "--data-dir", str(settings.data_dir)]) == 0


class _StatesUI(ConsoleUI):
    def __init__(self):
        super().__init__(auto_confirm=True)
        self.states = []

    def set_state(self, state, text=""):
        self.states.append(state)


def test_esc_during_analysis_returns_at_once(recorder, settings):
    import threading
    import time

    release = threading.Event()
    ui = _StatesUI()
    app = UndoApp(settings, ui, vision=ScriptedVisionModel([]), recorder=recorder)

    class SlowAnalyzer:
        last_keyframes = []

        def analyze(self, request):
            app.emergency_stop()
            release.wait(5)
            raise AssertionError("must have been abandoned")

    app.analyzer = SlowAnalyzer()
    t0 = time.time()
    assert app.handle_request("remets le formulaire") is None
    assert time.time() - t0 < 2
    release.set()
    assert app.executor is None and ui.states[-1] == "stopped"
    assert not app._busy.locked()


def test_esc_during_execution_stops_agent(recorder, settings):
    record_scene(recorder, _scenes())
    settings.dry_run = True
    settings.step_delay = 0
    model = ScriptedVisionModel([GOOD] + [("wait", {"seconds": 0})] * 8)
    ui = _StatesUI()
    app = UndoApp(settings, ui, vision=model, recorder=recorder)

    class EscOnWait(DryRunController):
        def wait(self, seconds):
            super().wait(seconds)
            app.emergency_stop()

    app.executor = AgentExecutor(settings, model, controller=EscOnWait(), screen=ScreenSource(1440, capturer=FakeCap(), logical_size=(1440, 900)), ui=ui)
    result = app.handle_request("remets le formulaire")
    assert result and not result.success and result.message.startswith("Stopped") and result.steps == 1
    assert "stopped" in ui.states


def test_missing_h_key_gives_a_readable_message(monkeypatch, capsys):
    from undo.__main__ import main

    monkeypatch.delenv("H_API_KEY", raising=False)
    monkeypatch.delenv("HAI_API_KEY", raising=False)
    for argv in (["run", "--dry-run"], ["models"], ["analyze", "x"]):
        assert main(argv) == 2
        assert "H_API_KEY is missing" in capsys.readouterr().err


def test_ui_works_without_tkinter():
    """Homebrew Python has no tkinter: `make run` must not crash on import."""
    code = (
        "import sys; sys.modules['tkinter'] = None\n"
        "import platform\n"
        "from undo.ui import overlay\n"
        "platform.system = lambda: 'Linux'\n"
        "assert type(overlay.build_ui()).__name__ == 'ConsoleUI'\n"
        "platform.system = lambda: 'Darwin'\n"
        "assert type(overlay.build_ui()).__name__ == 'MacHudUI'\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True, timeout=30)
