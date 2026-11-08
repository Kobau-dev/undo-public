"""Current-screen capture + coordinate mapping (model [0,1000] -> screenshot px -> screen points)."""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from undo.images import downscale
from undo.recorder.capture import MSSCapturer


@dataclass
class Screenshot:
    image: Image.Image  # what we send to the model (possibly downscaled)
    screen_w: int  # logical screen size in points (what pyautogui uses)
    screen_h: int

    def to_screen(self, nx: int, ny: int) -> tuple[int, int]:
        """Normalized [0,1000] coordinates on `image` -> screen points. Handles Retina since we scale by logical size."""
        x = round(nx / 1000 * self.screen_w)
        y = round(ny / 1000 * self.screen_h)
        return max(0, min(self.screen_w - 1, x)), max(0, min(self.screen_h - 1, y))


class ScreenSource:
    def __init__(self, max_width: int = 1440, capturer: MSSCapturer | None = None, logical_size: tuple[int, int] | None = None):
        self.max_width = max_width
        self.capturer = capturer or MSSCapturer()
        self._logical = logical_size

    def logical_size(self) -> tuple[int, int]:
        if self._logical:
            return self._logical
        try:
            import pyautogui

            w, h = pyautogui.size()
            return int(w), int(h)
        except Exception:
            return self.capturer.screen_size()

    def grab(self) -> Screenshot:
        raw = self.capturer.grab()
        w, h = self.logical_size()
        return Screenshot(image=downscale(raw, self.max_width), screen_w=w, screen_h=h)
