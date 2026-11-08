"""Microphone capture with silence detection -> 16 kHz mono WAV bytes."""
from __future__ import annotations

import io
import threading
import time
import wave
from typing import Callable

import numpy as np

from undo.log import get_logger

log = get_logger("mic")

SAMPLE_RATE = 16000


def pcm_to_wav(pcm: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.astype(np.int16).tobytes())
    return buf.getvalue()


class SilenceDetector:
    """Stops once we've heard speech and then `silence_seconds` of quiet (or max duration)."""

    def __init__(self, silence_seconds: float = 2.0, max_seconds: float = 30.0, threshold: float = 0.012, sample_rate: int = SAMPLE_RATE):
        self.silence_seconds = silence_seconds
        self.max_seconds = max_seconds
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.heard_speech = False
        self._quiet_samples = 0
        self._total_samples = 0

    def feed(self, chunk: np.ndarray) -> bool:
        """Return True when recording should stop."""
        self._total_samples += len(chunk)
        rms = float(np.sqrt(np.mean(np.square(chunk.astype(np.float32))))) if len(chunk) else 0.0
        if rms > self.threshold:
            self.heard_speech = True
            self._quiet_samples = 0
        else:
            self._quiet_samples += len(chunk)
        if self._total_samples >= self.max_seconds * self.sample_rate:
            return True
        return self.heard_speech and self._quiet_samples >= self.silence_seconds * self.sample_rate


class MicRecorder:
    def __init__(self, silence_seconds: float = 2.0, max_seconds: float = 30.0, sample_rate: int = SAMPLE_RATE):
        self.silence_seconds = silence_seconds
        self.max_seconds = max_seconds
        self.sample_rate = sample_rate
        self._stop = threading.Event()
        self.on_chunk: Callable[[np.ndarray], None] | None = None  # live audio tap (level meter, streaming STT)

    def request_stop(self) -> None:
        self._stop.set()

    def available(self) -> bool:
        try:
            import sounddevice as sd

            return any(d["max_input_channels"] > 0 for d in sd.query_devices())
        except Exception:
            return False

    def record(self) -> bytes:
        """Blocks until silence / stop / max duration. Returns WAV bytes (may be empty if nothing heard)."""
        import sounddevice as sd

        self._stop.clear()
        detector = SilenceDetector(self.silence_seconds, self.max_seconds, sample_rate=self.sample_rate)
        chunks: list[np.ndarray] = []
        done = threading.Event()

        def callback(indata, frames, time_info, status):
            mono = indata[:, 0].copy()
            chunks.append(mono)
            if self.on_chunk:
                try:
                    self.on_chunk(mono)
                except Exception:
                    pass
            if detector.feed(mono) or self._stop.is_set():
                done.set()

        t0 = time.time()
        with sd.InputStream(samplerate=self.sample_rate, channels=1, dtype="float32", blocksize=1024, callback=callback):
            while not done.is_set() and not self._stop.is_set():
                time.sleep(0.05)
        if not chunks or not detector.heard_speech:
            log.info("no speech detected (%.1fs)", time.time() - t0)
            return b""
        pcm = np.concatenate(chunks)
        log.info("recorded %.1fs of audio", len(pcm) / self.sample_rate)
        return pcm_to_wav((pcm * 32767).clip(-32768, 32767), self.sample_rate)
