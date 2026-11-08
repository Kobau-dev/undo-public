"""Wires recorder + trigger + analyzer + executor + UI into the Undo application."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from undo.analyzer import Analyzer
from undo.config import Settings
from undo.interfaces import StatusSink, Transcriber, VisionModel
from undo.log import get_logger
from undo.models import Analysis, ExecutionResult
from undo.recorder import FrameIndex, Recorder
from undo.trigger import Trigger
from undo.trigger.hotkey import EscapeListener, hotkey_label
from undo.i18n import t

log = get_logger("app")


class UndoApp:
    def __init__(self, settings: Settings, ui: StatusSink, vision: VisionModel | None = None, transcriber: Transcriber | None = None, recorder: Recorder | None = None):
        self.settings = settings
        self.ui = ui
        self._vision = vision
        self.transcriber = transcriber
        self.index = recorder.index if recorder else FrameIndex(settings.db_path)
        self.recorder = recorder or Recorder(settings, index=self.index)
        self._analyzer_vision: VisionModel | None = None
        self.analyzer = Analyzer(settings, vision, self.index) if vision else None
        self.executor = None
        self.trigger = Trigger(settings, transcriber, ui, self.handle_request,
                               on_open=self._prompt_opened, on_close=lambda: self.recorder.resume("prompt"))
        self._escape = EscapeListener(self.emergency_stop)
        self._busy = threading.Lock()
        self._stop = threading.Event()
        self._cancel = threading.Event()
        if hasattr(ui, "on_escape"):
            ui.on_escape = self.emergency_stop  # Esc caught by the bubble itself while it has the keyboard

    def _prompt_opened(self) -> None:
        snap = getattr(self.recorder, "snapshot_now", None)
        if snap:
            snap()  # the screen the user is looking at when asking, even if the periodic capture has not caught it yet
        self.recorder.pause("prompt")

    # -- providers are built lazily so `record` / dry runs work without keys -------------
    @property
    def vision_lazy(self) -> VisionModel:
        if self._vision is None:
            from undo.providers import build_vision

            self._vision = build_vision(self.settings)
        return self._vision

    @property
    def analyzer_vision_lazy(self) -> VisionModel:
        if self._analyzer_vision is None:
            from undo.providers import build_vision

            self._analyzer_vision = build_vision(self.settings, role="analyzer")
        return self._analyzer_vision

    def _build_executor(self):
        if self.executor is not None:
            return self.executor
        pause = lambda: self.recorder.pause("executor")
        resume = lambda: self.recorder.resume("executor")
        if self.settings.executor_backend == "holo-agent":
            from undo.executor.holo_agent import HoloAgentExecutor

            self.executor = HoloAgentExecutor(self.settings, self.ui, on_start=pause, on_finish=resume)
        else:
            from undo.executor import AgentExecutor

            self.executor = AgentExecutor(self.settings, self.vision_lazy, ui=self.ui, on_start=pause, on_finish=resume)
        return self.executor

    # -- lifecycle -------------------------------------------------------------------
    def start(self) -> None:
        self.recorder.start()
        try:
            self.trigger.start()
            self._escape.start()
        except Exception as exc:
            log.warning("global hotkey unavailable (%s). Use --request or the text prompt.", exc)
        self.ui.set_state("idle", t("Recording ({minutes} min). Press {hotkey} and say what you want back.", minutes=self.settings.buffer_minutes, hotkey=hotkey_label(self.settings.hotkey)))

    def run_forever(self) -> None:
        self.start()
        try:
            while not self._stop.is_set():
                self._stop.wait(1.0)
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self._stop.set()
        self.trigger.stop()
        self._escape.stop()
        self.recorder.stop()

    def emergency_stop(self) -> None:
        """Esc, at any stage: drops the request being captured, abandons the analysis, or stops the agent."""
        from undo.executor.control import self_esc_recent

        if self_esc_recent():  # the agent pressed Esc itself (closing a menu), not the user
            log.debug("Esc sent by the agent, kill switch ignored")
            return
        if self.trigger.cancel():
            return
        if not self._busy.locked() or self._cancel.is_set():
            return
        log.warning("ESC pressed — stopping")
        self._cancel.set()
        if self.executor is not None:
            self.executor.stop()
        cancel_input = getattr(self.ui, "cancel_input", None)
        if cancel_input:
            cancel_input()
        self.ui.set_state("stopped", t("Emergency stop (Esc)."))

    def _cancellable(self, fn):
        """Run fn in a thread so that Esc returns at once (None) instead of waiting for a slow model call."""
        box: dict = {}

        def work() -> None:
            try:
                box["value"] = fn()
            except BaseException as exc:
                box["error"] = exc

        t = threading.Thread(target=work, name="undo-analyze", daemon=True)
        t.start()
        while t.is_alive():
            if self._cancel.is_set():
                return None
            t.join(0.05)
        if "error" in box:
            raise box["error"]
        return None if self._cancel.is_set() else box["value"]

    # -- the core flow -------------------------------------------------------------------
    def handle_request(self, request: str) -> ExecutionResult | None:
        request = " ".join((request or "").split())
        if not self._busy.acquire(blocking=False):
            log.info("request ignored, already working")
            return None
        self._cancel.clear()
        t0 = time.time()
        run_log: dict = {"request": request, "started": t0}
        try:
            self.ui.set_state("analyzing", f"“{request}”\n" + t("Going through the last {minutes} minutes…", minutes=self.settings.lookback_minutes))
            analyzer = self.analyzer or Analyzer(self.settings, self.analyzer_vision_lazy, self.index, fallback=self.vision_lazy)
            analysis = self._cancellable(lambda: analyzer.analyze(request))
            if analysis is None:
                run_log["cancelled"] = True
                return None
            run_log["analysis"] = analysis.model_dump()
            run_log["keyframes"] = [{"ts": k.ts, "role": k.role, "path": k.frame.path} for k in analyzer.last_keyframes]
            self.ui.set_state("understood", self.describe(analysis))
            if analysis.confidence < 0.4 and not self.ui.confirm(t("I'm only {confidence} sure. Try anyway?", confidence=f"{analysis.confidence:.0%}")):
                self.ui.set_state("stopped", t("Cancelled."))
                return None
            executor = self._build_executor()
            if hasattr(executor, "cancel_event"):
                executor.cancel_event = self._cancel
            if self._cancel.is_set():
                run_log["cancelled"] = True
                return None
            if hasattr(executor, "replay_form"):
                executor.replay_form = self._recorded_form(analyzer.last_keyframes)
            result = executor.run(analysis, request)
            run_log["result"] = result.model_dump()
            return result
        except Exception as exc:
            log.exception("undo failed: %s", exc)
            self.ui.set_state("failed", str(exc)[:300])
            run_log["error"] = str(exc)
            return None
        finally:
            run_log["duration"] = time.time() - t0
            self._save_run(run_log)
            self._busy.release()

    @staticmethod
    def _recorded_form(keyframes) -> str:
        """The richest accessibility form state among the moments picked from history (not the current screen)."""
        past = [k.frame for k in keyframes if k.role != "current" and (k.frame.ax_text or "").strip()]
        best = max(past, key=lambda f: (len(f.ax_text.splitlines()), f.ts), default=None)
        return best.ax_text if best else ""

    @staticmethod
    def describe(a: Analysis) -> str:
        plan = "\n".join(f"{i}. {s}" for i, s in enumerate(a.plan[:4], 1))
        more = f"\n… (+{len(a.plan) - 4})" if len(a.plan) > 4 else ""
        strategy = t("Strategy: {strategy} · confidence {confidence}", strategy=a.strategy, confidence=f"{a.confidence:.0%}")
        return f"{a.summary}\n{strategy}\n{plan}{more}"

    def _save_run(self, data: dict) -> None:
        try:
            runs = self.settings.data_dir / "runs"
            runs.mkdir(parents=True, exist_ok=True)
            path = runs / f"{int(data['started'])}.json"
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))
            log.info("run log: %s", path)
        except OSError as exc:
            log.debug("could not save run log: %s", exc)


def export_recording(settings: Settings, out_dir: Path, minutes: int | None = None) -> Path:
    """Copy the last N minutes of the recording into a self-contained folder for --replay."""
    import shutil

    src = FrameIndex(settings.db_path)
    now = time.time()
    frames = src.between(now - (minutes or settings.buffer_minutes) * 60, now + 1)
    out_dir = Path(out_dir)
    (out_dir / "frames").mkdir(parents=True, exist_ok=True)
    if (out_dir / "frames.db").exists():
        (out_dir / "frames.db").unlink()
    dst = FrameIndex(out_dir / "frames.db")
    for f in frames:
        name = Path(f.path).name
        try:
            shutil.copy2(f.path, out_dir / "frames" / name)
        except OSError:
            continue
        f.id = None
        f.path = f"frames/{name}"
        dst.add(f)
    dst.close()
    (out_dir / "meta.json").write_text(json.dumps({"exported": now, "frames": len(frames), "last_ts": frames[-1].ts if frames else None}, indent=2))
    return out_dir
