"""Blur sensitive text (card numbers, IBANs, long secrets) in screenshots before they leave the machine.
Opt-in (UNDO_REDACT=1): it costs one OCR pass per image sent to H."""
from __future__ import annotations

import re

from PIL import Image, ImageFilter

from undo.log import get_logger

log = get_logger("redact")

_DIGITS = re.compile(r"(?:\d[ -]?){13,19}")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){3,7}(?:[ ]?[A-Z0-9]{1,4})?\b")
_SECRET = re.compile(r"\b(?:sk|pk|ghp|gho|xox[bp]|AKIA)[-_A-Za-z0-9]{12,}\b")


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total, alt = total + d, not alt
    return total % 10 == 0


def is_sensitive(text: str) -> bool:
    for m in _DIGITS.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn(digits):
            return True
    return bool(_IBAN.search(text.upper().replace("\u00a0", " ")) or _SECRET.search(text))


def blur_boxes(image: Image.Image, boxes: list[tuple[int, int, int, int]], pad: int = 4) -> Image.Image:
    if not boxes:
        return image
    out = image.copy()
    for x0, y0, x1, y1 in boxes:
        box = (max(0, x0 - pad), max(0, y0 - pad), min(out.width, x1 + pad), min(out.height, y1 + pad))
        if box[2] > box[0] and box[3] > box[1]:
            out.paste(out.crop(box).filter(ImageFilter.GaussianBlur(12)), box)
    return out


class Redactor:
    def __init__(self, ocr):
        self.ocr = ocr

    def __call__(self, image: Image.Image) -> Image.Image:
        boxes_fn = getattr(self.ocr, "boxes", None)
        if boxes_fn is None:
            return image
        try:
            hits = [b for text, b in boxes_fn(image) if is_sensitive(text)]
        except Exception as exc:  # never block a restoration on redaction
            log.warning("redaction skipped: %s", exc)
            return image
        if hits:
            log.info("blurred %d sensitive region(s)", len(hits))
        return blur_boxes(image, hits)


def build_redactor(settings):
    if not getattr(settings, "redact", False):
        return None
    from undo.recorder.ocr import build_ocr

    return Redactor(build_ocr(True))
