"""The Recorder daemon: capture -> dedup -> save JPEG -> index -> async OCR, with a rolling disk buffer."""
from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path

from PIL import Image

from undo.config import Settings
from undo.images import downscale
from undo.interfaces import ForegroundProvider, OCREngine
from undo.log import get_logger
from undo.models import Frame
from undo.recorder.capture import Capturer, Deduplicator, MSSCapturer
from undo.recorder.index import FrameIndex
from undo.recorder.ocr import build_ocr
from undo.recorder.platform import build_foreground

log = get_logger("recorder")


class Recorder:
    def __init__(
        self,
        settings: Settings,
        capturer: Capturer | None = None,
        ocr: OCREngine | None = None,
        foreground: ForegroundProvider | None = None,
        index: FrameIndex | None = None,
    ):
        self.settings = settings
        settings.ensure_dirs()
        self.capturer = capturer or MSSCapturer()
        self.ocr = ocr or build_ocr(settings.ocr_enabled)
        self.foreground = foreground or build_foreground()
        self.index = index or FrameIndex(settings.db_path)
        self.dedup = Deduplicator(settings.phash_threshold)
        self._ocr_queue: queue.Queue[tuple[int, Image.Image] | None] = queue.Queue(maxsize=50)
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._thread: threading.Thread | None = None
        self._ocr_thread: threading.Thread | None = None
        self.frames_captured = 0
        self.frames_skipped = 0
        self.last_frame: Frame | None = None
        self._pause_reasons: set[str] = set()
        self._tick_lock = threading.Lock()
        self._lock = threading.Lock()

    # -- lifecycle -----------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._ocr_thread = threading.Thread(target=self._ocr_loop, name="undo-ocr", daemon=True)
        self._ocr_thread.start()
        self._thread = threading.Thread(target=self._loop, name="undo-recorder", daemon=True)
        self._thread.start()
        self.inputs = None
        if self.settings.input_log:
            try:
                from undo.recorder.inputs import InputLogger

                self.inputs = InputLogger(self.index.add_input, self.foreground, self._is_excluded, lambda: self.paused)
                self.inputs.start()
            except Exception as exc:
                log.warning("input log unavailable (%s) — on macOS allow Input Monitoring", exc)
        log.info("recorder started: every %.1fs, buffer %d min, ocr=%s, data=%s", self.settings.capture_interval, self.settings.buffer_minutes, getattr(self.ocr, "name", "?"), self.settings.data_dir)

    def stop(self) -> None:
        self._stop.set()
        if getattr(self, "inputs", None):
            self.inputs.stop()
        if self._thread:
            self._thread.join(timeout=5)
        self._ocr_queue.put(None)
        if self._ocr_thread:
            self._ocr_thread.join(timeout=5)

    def pause(self, reason: str = "user") -> None:
        with self._lock:
            self._pause_reasons.add(reason)
            self._paused.set()
        log.info("recorder paused (%s)", reason)

    def resume(self, reason: str = "user") -> None:
        with self._lock:
            self._pause_reasons.discard(reason)
            if not self._pause_reasons:
                self._paused.clear()
                self.dedup.reset()
                log.info("recorder resumed")

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    # -- one tick (public so tests can drive it synchronously) --------------
    def tick(self, now: float | None = None) -> Frame | None:
        with self._tick_lock:
            return self._tick(now)

    def snapshot_now(self) -> None:
        """Capture the screen right away (e.g. just before the prompt opens and recording pauses)."""
        try:
            self.tick()
        except Exception as exc:
            log.warning("snapshot failed: %s", exc)

    def _tick(self, now: float | None = None) -> Frame | None:
        now = now if now is not None else time.time()
        app, title = self.foreground.foreground()
        if self._is_excluded(app, title):
            self.frames_skipped += 1
            return None
        image = self.capturer.grab()
        ax_text = None
        if self.settings.ax:
            from undo import ax

            ax_text = ax.form_state(ax.snapshot(app, budget=0.5))
        dup, phash = self.dedup.is_duplicate(image)
        # a ticked box barely changes the pixels: keep the frame anyway when the form values changed
        if dup and not (ax_text and ax_text != getattr(self.last_frame, "ax_text", None)):
            self.frames_skipped += 1
            return None
        stored = downscale(image, self.settings.frame_max_width)
        path = self.settings.frames_dir / f"{int(now * 1000)}.jpg"
        stored.convert("RGB").save(path, "JPEG", quality=self.settings.jpeg_quality, optimize=True)
        frame = Frame(ts=now, app=app, window_title=title, path=str(path), width=stored.width, height=stored.height, phash=phash)
        bounds = getattr(self.foreground, "last_bounds", None)
        if bounds:
            frame.win_x, frame.win_y, frame.win_w, frame.win_h = bounds
        if ax_text is not None:
            frame.ax_text = ax_text
        self.index.add(frame)
        self.frames_captured += 1
        self.last_frame = frame
        try:
            self._ocr_queue.put_nowait((frame.id, stored))
        except queue.Full:
            log.warning("OCR queue full, skipping OCR for frame %s", frame.id)
        return frame

    def purge(self, now: float | None = None) -> int:
        now = now if now is not None else time.time()
        cutoff = now - self.settings.buffer_minutes * 60
        paths = self.index.purge_older_than(cutoff)
        for p in paths:
            try:
                Path(p).unlink(missing_ok=True)
            except OSError:
                pass
        return len(paths)

    # -- internals -------------------------------------------------------------
    def _is_excluded(self, app: str, title: str) -> bool:
        hay = f"{app} {title}".lower()
        return any(x.lower() in hay for x in self.settings.excluded_apps if x)

    def _loop(self) -> None:
        last_purge = 0.0
        last_control = 0.0
        while not self._stop.is_set():
            t0 = time.time()
            if t0 - last_control > 2:
                self._apply_control_file()
                last_control = t0
            if not self._paused.is_set():
                try:
                    self.tick(t0)
                except Exception as exc:
                    log.exception("capture failed: %s", exc)
            if t0 - last_purge > 30:
                n = self.purge(t0)
                if n:
                    log.debug("purged %d old frames", n)
                last_purge = t0
            elapsed = time.time() - t0
            self._stop.wait(max(0.1, self.settings.capture_interval - elapsed))

    def _ocr_loop(self) -> None:
        while True:
            item = self._ocr_queue.get()
            if item is None:
                return
            frame_id, image = item
            try:
                text = self.ocr.recognize(image)
                if text:
                    self.index.set_ocr(frame_id, text)
            except Exception as exc:
                log.debug("ocr failed for %s: %s", frame_id, exc)

    def _apply_control_file(self) -> None:
        """Menu bar app (separate process) writes {"paused": bool, "buffer_minutes": int} here."""
        path = self.settings.control_path
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text() or "{}")
        except (OSError, json.JSONDecodeError):
            return
        if "paused" in data:
            if data["paused"] and "menubar" not in self._pause_reasons:
                self.pause("menubar")
            elif not data["paused"] and "menubar" in self._pause_reasons:
                self.resume("menubar")
        if "buffer_minutes" in data and int(data["buffer_minutes"]) != self.settings.buffer_minutes:
            self.settings.buffer_minutes = int(data["buffer_minutes"])
            log.info("buffer set to %d min", self.settings.buffer_minutes)

    def wait_for_ocr(self, timeout: float = 5.0) -> None:
        deadline = time.time() + timeout
        while not self._ocr_queue.empty() and time.time() < deadline:
            time.sleep(0.05)
        time.sleep(0.05)

    def stats(self) -> dict:
        return {"captured": self.frames_captured, "skipped": self.frames_skipped, "indexed": self.index.count(), "paused": self.paused}
