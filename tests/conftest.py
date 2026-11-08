from __future__ import annotations

import time
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from undo.config import Settings
from undo.recorder.daemon import Recorder
from undo.recorder.index import FrameIndex


def render_text_image(lines: list[str], size=(800, 500), bg="white") -> Image.Image:
    img = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    y = 20
    for line in lines:
        d.text((20, y), line, fill="black")
        y += 24
    return img


class FakeCapturer:
    def __init__(self):
        self.image = render_text_image(["blank"])

    def set(self, lines: list[str], bg="white"):
        self.image = render_text_image(lines, bg=bg)

    def grab(self):
        return self.image.copy()


class FakeOCR:
    """Pretend OCR: the capturer attaches the text it rendered."""

    name = "fake"

    def __init__(self):
        self.texts: dict[int, str] = {}
        self.current = ""

    def recognize(self, image):
        return self.current


class FakeForeground:
    def __init__(self):
        self.value = ("Safari", "Dossier administratif")

    def foreground(self):
        return self.value


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings(data_dir=tmp_path / "data", buffer_minutes=30, ocr_enabled=False, h_api_key="test", gladia_api_key=None, timeline_selection=False)
    s.ensure_dirs()
    return s


@pytest.fixture
def recorder(settings):
    cap, ocr, fg = FakeCapturer(), FakeOCR(), FakeForeground()
    rec = Recorder(settings, capturer=cap, ocr=ocr, foreground=fg, index=FrameIndex(settings.db_path))
    rec.fake = (cap, ocr, fg)  # type: ignore[attr-defined]
    yield rec
    rec.index.close()


def record_scene(rec: Recorder, scenes: list[tuple[float, list[str], tuple[str, str] | None]]):
    """scenes: (seconds_ago, text_lines, (app, title)) -> frames written synchronously with OCR."""
    cap, ocr, fg = rec.fake  # type: ignore[attr-defined]
    now = time.time()
    frames = []
    for ago, lines, fgv in scenes:
        if fgv:
            fg.value = fgv
        cap.set(lines)
        rec.dedup.reset()  # scenes are distinct moments even if they look alike
        ocr.current = "\n".join(lines)
        f = rec.tick(now - ago)
        if f is not None:
            rec.index.set_ocr(f.id, ocr.current)
            f.ocr_text = ocr.current
            frames.append(f)
    return frames
