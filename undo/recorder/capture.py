"""Screen capture with perceptual-hash deduplication."""
from __future__ import annotations

import os
import platform
import subprocess
import tempfile

from typing import Protocol

import imagehash
import mss
from PIL import Image, ImageChops

from undo.images import downscale


class Capturer(Protocol):
    def grab(self) -> Image.Image: ...


class MSSCapturer:
    """Primary monitor capture. On Retina displays the image is in device pixels.

    Some X11 setups (VMs) break mss/XShm; we then switch permanently to PIL's ImageGrab (never retrying mss,
    since each failed mss() leaks an X connection and the server eventually refuses clients).
    """

    def __init__(self, monitor: int = 1):
        self.monitor = monitor
        self._sct: mss.base.MSSBase | None = None
        self._fallback = False

    def _ensure(self):
        if self._sct is None:
            try:
                self._sct = mss.mss()
            except mss.exception.ScreenShotError:
                self._fallback = True
                raise
        return self._sct

    def grab(self) -> Image.Image:
        if platform.system() == "Darwin":
            return self._grab_macos()
        if not self._fallback:
            try:
                sct = self._ensure()
                mon = sct.monitors[self.monitor] if len(sct.monitors) > self.monitor else sct.monitors[0]
                shot = sct.grab(mon)
                return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            except mss.exception.ScreenShotError:
                self._fallback = True
                self.close()
        from PIL import ImageGrab

        return ImageGrab.grab().convert("RGB")

    def _grab_macos(self) -> Image.Image:
        """mss takes ~30 s per frame on macOS 26 (ScreenCaptureKit); `screencapture` takes 0.15 s."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            path = tmp.name
        try:
            subprocess.run(["screencapture", "-x", "-t", "png", path], check=True, timeout=10)
            with Image.open(path) as im:
                return im.convert("RGB")
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def screen_size(self) -> tuple[int, int]:
        """Logical (point) size of the monitor as reported by mss (or the fallback grab's size)."""
        if not self._fallback:
            try:
                sct = self._ensure()
                mon = sct.monitors[self.monitor] if len(sct.monitors) > self.monitor else sct.monitors[0]
                return mon["width"], mon["height"]
            except mss.exception.ScreenShotError:
                self._fallback = True
        return self.grab().size

    def close(self) -> None:
        if self._sct is not None:
            try:
                self._sct.close()
            finally:
                self._sct = None


class Deduplicator:
    """Drops frames that show (almost) nothing new.

    A frame is a duplicate when fewer than `changed_ratio` of the pixels moved (grayscale, 640 px wide, |delta| > 32).
    One extra line of typed text changes ~0.2 % of the pixels, the clock or a blinking caret < 0.05 %.
    A perceptual hash alone (the previous approach) misses a single new line on a Retina screen.
    `threshold` (bits) is kept for the phash shortcut: identical hashes within it AND few changed pixels -> duplicate.
    """

    def __init__(self, threshold: int = 4, changed_ratio: float = 0.001):
        self.threshold = threshold
        self.changed_ratio = changed_ratio
        self.last_hash: imagehash.ImageHash | None = None
        self._last_small: Image.Image | None = None

    def is_duplicate(self, image: Image.Image) -> tuple[bool, str]:
        small = downscale(image, 640).convert("L")
        h = imagehash.phash(small)
        dup = False
        if self._last_small is not None and self._last_small.size == small.size:
            diff = ImageChops.difference(small, self._last_small).point(lambda v: 255 if v > 32 else 0)
            changed = diff.histogram()[255] / (small.width * small.height)
            dup = changed < self.changed_ratio and (h - self.last_hash) <= self.threshold
        if not dup:
            self.last_hash, self._last_small = h, small
        return dup, str(h)

    def reset(self) -> None:
        self.last_hash = None
        self._last_small = None
