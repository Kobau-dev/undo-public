"""OCR engines. macOS: Apple Vision via ocrmac. Elsewhere: tesseract if present. Else: no-op."""
from __future__ import annotations

import platform
import shutil
import tempfile
from pathlib import Path

from PIL import Image

from undo.log import get_logger

log = get_logger("ocr")


class NoopOCR:
    name = "noop"

    def recognize(self, image: Image.Image) -> str:
        return ""


class AppleVisionOCR:
    """Apple Vision framework through `ocrmac` (pip install ocrmac)."""

    name = "apple-vision"

    def __init__(self, languages: list[str] | None = None):
        from ocrmac import ocrmac  # type: ignore

        self._ocrmac = ocrmac
        self.languages = languages or ["en-US", "fr-FR"]

    def _results(self, image: Image.Image):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
            image.save(tmp.name)
            try:
                results = self._ocrmac.OCR(tmp.name, language_preference=self.languages, recognition_level="accurate").recognize()
            except TypeError:  # older ocrmac signature
                results = self._ocrmac.OCR(tmp.name, language_preference=self.languages).recognize()
        return results

    def boxes(self, image: Image.Image) -> list[tuple[str, tuple[int, int, int, int]]]:
        """(text, pixel box) per line; Vision boxes are normalized with y from the bottom."""
        w, h = image.size
        return [(t, (int(x * w), int((1 - y - bh) * h), int((x + bw) * w), int((1 - y) * h))) for t, c, (x, y, bw, bh) in self._results(image) if c >= 0.3]

    def recognize(self, image: Image.Image) -> str:
        results = self._results(image)
        # results: list of (text, confidence, (x, y, w, h)) with y from bottom; sort top-to-bottom, left-to-right
        lines = sorted(results, key=lambda r: (-round(r[2][1], 2), r[2][0]))
        return "\n".join(r[0] for r in lines if r[1] >= 0.3)


class TesseractOCR:
    name = "tesseract"

    def __init__(self, languages: list[str] | None = None):
        import pytesseract  # type: ignore

        self._pt = pytesseract
        self.lang = "+".join(languages or ["fra", "eng"])

    def boxes(self, image: Image.Image) -> list[tuple[str, tuple[int, int, int, int]]]:
        d = self._pt.image_to_data(image, output_type=self._pt.Output.DICT)
        lines: dict = {}
        for i, word in enumerate(d["text"]):
            if word.strip():
                key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
                x0, y0, x1, y1 = d["left"][i], d["top"][i], d["left"][i] + d["width"][i], d["top"][i] + d["height"][i]
                t, b = lines.get(key, ("", (x0, y0, x1, y1)))
                lines[key] = ((t + " " + word).strip(), (min(b[0], x0), min(b[1], y0), max(b[2], x1), max(b[3], y1)))
        return list(lines.values())

    def recognize(self, image: Image.Image) -> str:
        try:
            return self._pt.image_to_string(image, lang=self.lang)
        except Exception:  # missing language pack
            return self._pt.image_to_string(image)


def build_ocr(enabled: bool = True):
    if not enabled:
        return NoopOCR()
    if platform.system() == "Darwin":
        try:
            return AppleVisionOCR()
        except Exception as exc:  # pragma: no cover
            log.warning("ocrmac unavailable (%s); OCR disabled. pip install ocrmac", exc)
            return NoopOCR()
    if shutil.which("tesseract"):
        try:
            return TesseractOCR()
        except Exception as exc:  # pragma: no cover
            log.warning("pytesseract unavailable (%s)", exc)
    log.warning("no OCR engine available; text search will be limited to app/window titles")
    return NoopOCR()
