"""Hotkey -> listen (voice, or a text box typed in parallel) -> request text. Falls back to a typed request when there is\nno mic / no Gladia."""
from __future__ import annotations

import threading
import time
from typing import Callable

import numpy as np

from undo.config import Settings
from undo.interfaces import StatusSink, Transcriber
from undo.log import get_logger
from undo.trigger.hotkey import HotkeyListener
from undo.trigger.mic import MicRecorder
from undo.i18n import t

log = get_logger("trigger")



def one_line(text: str | None) -> str:
    """A transcript or pasted request can span several lines (one per utterance): keep it as one clean line."""
    return " ".join((text or "").split())

class Trigger:
    def __init__(self, settings: Settings, transcriber: Transcriber | None, ui: StatusSink, on_request: Callable[[str], None], mic: MicRecorder | None = None,
                 on_open: Callable[[], None] | None = None, on_close: Callable[[], None] | None = None):
        self.settings = settings
        self.on_open, self.on_close = on_open, on_close  # e.g. pause the recorder: the prompt and the request must not enter history
        self.transcriber = transcriber
        self.ui = ui
        self.on_request = on_request
        self.mic = mic or MicRecorder(settings.silence_seconds, settings.max_record_seconds)
        self._listening = threading.Event()
        self._listen_t0 = 0.0
        self._busy = threading.Lock()
        self._capturing = threading.Event()
        self._cancelled = threading.Event()
        self.review_timeout = 180.0  # a transcript left unsent in the text box is dropped after this long
        self._hotkey = HotkeyListener(settings.hotkey, self.fire)

    def start(self) -> None:
        self._hotkey.start()

    def stop(self) -> None:
        self._hotkey.stop()

    def cancel(self) -> bool:
        """Esc while the request is being captured (listening, typing, transcribing): drop it. False if not capturing."""
        if not self._capturing.is_set():
            return False
        self._cancelled.set()
        self.mic.request_stop()
        cancel_input = getattr(self.ui, "cancel_input", None)
        if cancel_input:
            cancel_input()
        return True

    def fire(self) -> None:
        """Called on hotkey. Second press while listening stops the recording early."""
        if self._listening.is_set():
            # ignore extra taps right after opening (a triple tap must not end the recording before it starts)
            if time.time() - self._listen_t0 >= 1.5:
                log.info("recording stopped by hotkey")
                self.mic.request_stop()
            return
        if not self._busy.acquire(blocking=False):
            log.info("hotkey ignored: Undo is busy")
            return
        self._cancelled.clear()
        if self.on_open:
            self.on_open()
        try:
            self._capturing.set()
            try:
                request = one_line(self.capture_request())
            finally:
                self._capturing.clear()
            if self._cancelled.is_set():
                log.info("request cancelled (Esc)")
                self.ui.set_state("stopped", t("Cancelled."))
            elif request:
                self.on_request(request)
            else:
                self.ui.set_state("idle", t("Nothing heard."))
        finally:
            if self.on_close:
                self.on_close()
            self._busy.release()

    def _start_live(self):
        make = getattr(self.transcriber, "live_session", None)
        if not (make and self.settings.live_transcription):
            return None
        set_transcript = getattr(self.ui, "set_transcript", None)
        try:
            live = make(self.settings.gladia_languages, set_transcript or (lambda _t: None))
            live.start()
            return live
        except Exception as exc:
            log.warning("live transcription unavailable (%s), using pre-recorded", exc)
            return None

    def capture_request(self) -> str:
        can_voice = self.settings.voice and self.transcriber is not None and self.mic.available()
        if not can_voice:
            why = "voice off" if not self.settings.voice else "no Gladia key" if self.transcriber is None else "no microphone"
            log.info("voice unavailable (%s), asking for text", why)
            self.ui.set_state("listening", t("What do you want back?"))
            return self.ui.ask(t("What do you want back?")).strip()

        self.ui.set_state("listening", t("Speak now: say what you want back, then press Enter to send."))
        typed: list[str] = []
        submitted = threading.Event()
        edited = threading.Event()
        close_box = None
        if hasattr(self.ui, "prompt_input"):
            def on_typed(text: str) -> None:
                log.info("typed request received")
                typed.append(text)
                submitted.set()
                self.mic.request_stop()

            def on_edited() -> None:
                log.info("typing in the text box: microphone off")
                edited.set()
                self.mic.request_stop()

            close_box = self.ui.prompt_input(t("Say what you want back… or type it here and press Enter"), on_typed)
            self.ui.on_input_edited = on_edited
        live = self._start_live()
        set_level = getattr(self.ui, "set_level", None)

        def on_chunk(mono: np.ndarray) -> None:
            if set_level:
                set_level(float(np.sqrt(np.mean(mono * mono))))
            if live:
                live.send((mono * 32767).clip(-32768, 32767).astype("<i2").tobytes())

        self.mic.on_chunk = on_chunk
        self._listen_t0 = time.time()
        self._listening.set()
        try:
            wav = b"" if self._cancelled.is_set() else self.mic.record()
        finally:
            self.mic.on_chunk = None
            self._listening.clear()
        try:
            return self._after_listening(live, wav, typed, submitted, edited)
        finally:
            if close_box:
                close_box()

    def _after_listening(self, live, wav: bytes, typed: list[str], submitted: threading.Event, edited: threading.Event) -> str:
        """The microphone is off: get the transcript, put it in the text box and wait for Enter."""
        if self._cancelled.is_set() or typed or edited.is_set() or not wav:
            if live:
                live.close()
            spoken = ""
            if not (self._cancelled.is_set() or typed or edited.is_set()):
                return self.ui.ask(t("I didn't hear anything. What do you want back?")).strip()
        else:
            try:
                spoken = one_line(self._transcribe(live, wav))
            except Exception as exc:
                log.exception("transcription failed: %s", exc)
                return self.ui.ask(t("Couldn't transcribe that. What do you want back?")).strip()
        if self._cancelled.is_set():
            return ""
        # Only Enter sends: the transcript can be read and corrected first. Without a text box (console), it goes straight on.
        fill = getattr(self.ui, "fill_input", None)
        if not typed and fill and (spoken or edited.is_set()) and fill(None if edited.is_set() else spoken):
            log.info("request in the text box, waiting for Enter")
            spoken = self._wait_for_enter(typed, submitted)
        request = typed[0] if typed else spoken
        if request:
            self.ui.set_state("heard", f"“{one_line(request)}”")
        return request

    def _transcribe(self, live, wav: bytes) -> str:
        if live:
            self.ui.set_state("transcribing", t("Transcribing…"))
            text = live.finish()
            if text or self._cancelled.is_set():
                log.info("live transcript: %s", text)
                return text
            log.info("live transcript empty, falling back to pre-recorded")
        self.ui.set_state("transcribing", t("Transcribing (Gladia)…"))
        return self.transcriber.transcribe(wav, self.settings.gladia_languages)

    def _wait_for_enter(self, typed: list[str], submitted: threading.Event) -> str:
        deadline = time.time() + self.review_timeout
        while not submitted.wait(0.05):
            if self._cancelled.is_set():
                return ""
            if time.time() > deadline:
                log.info("request left in the text box, dropped")
                self._cancelled.set()
                return ""
        return typed[0]
