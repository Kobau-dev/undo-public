"""`undo run` with the microphone chosen by name, so a take does not depend on the Mac's default input (AirPods, iPhone...).

With UNDO_TAKE_FEED set, the audio input is replaced: the line named in that control file goes straight into Undo's audio input in
real time, over a quiet room tone, instead of being played through the speakers. Everything after the input is the normal voice flow:
level meter, live transcription, silence detection. Only the takes use this: Undo itself is unchanged."""
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

sd.default.device = (os.environ.get("UNDO_TAKE_MIC", "Micro MacBook Air"), None)


class FeedStream:
    """Stands in for sd.InputStream: calls back in real time with room tone, or with the line asked for in the control file."""

    def __init__(self, samplerate=16000, channels=1, dtype="float32", blocksize=1024, callback=None, **_):
        self.rate, self.block, self.callback = samplerate, blocksize, callback
        self.control = Path(os.environ["UNDO_TAKE_FEED"])
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        voice = np.zeros(0, dtype=np.float32)
        rng = np.random.default_rng()
        next_at = time.monotonic()
        while not self._stop.is_set():
            if self.control.exists():
                voice = np.fromfile(self.control.read_text().strip(), dtype=np.float32)
                self.control.unlink()
            chunk = rng.normal(0, 0.0005, self.block).astype(np.float32)
            n = min(self.block, len(voice))
            chunk[:n] += voice[:n]
            voice = voice[n:]
            self.callback(chunk.reshape(-1, 1), self.block, None, None)
            next_at += self.block / self.rate
            time.sleep(max(0.0, next_at - time.monotonic()))

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join(timeout=1)


if os.environ.get("UNDO_TAKE_FEED"):
    sd.InputStream = FeedStream

from undo.__main__ import main  # noqa: E402

sys.exit(main(["run", "-v"]))
