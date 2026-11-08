"""Image helpers shared by recorder, analyzer and executor."""
from __future__ import annotations

import base64
import io

from PIL import Image


def downscale(image: Image.Image, max_width: int) -> Image.Image:
    if max_width <= 0 or image.width <= max_width:
        return image
    ratio = max_width / image.width
    return image.resize((max_width, max(1, round(image.height * ratio))), Image.LANCZOS)


def to_jpeg_bytes(image: Image.Image, quality: int = 75) -> bytes:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def crop_to_window(image: Image.Image, x: float, y: float, w: float, h: float, pad: float = 0.01) -> Image.Image:
    """Crop to the foreground window (fractions of the screen) so the model reads it at a higher resolution.
    Unknown, tiny or (almost) full-screen bounds -> image unchanged."""
    if w <= 0 or h <= 0 or w * h < 0.08 or w * h > 0.92:
        return image
    W, H = image.size
    box = (max(0, int((x - pad) * W)), max(0, int((y - pad) * H)), min(W, int((x + w + pad) * W)), min(H, int((y + h + pad) * H)))
    return image.crop(box)


def to_data_uri(image: Image.Image, quality: int = 75) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(to_jpeg_bytes(image, quality)).decode()


def image_part(image: Image.Image, quality: int = 75) -> dict:
    return {"type": "image_url", "image_url": {"url": to_data_uri(image, quality)}}


def text_part(text: str) -> dict:
    return {"type": "text", "text": text}


def load(path: str) -> Image.Image:
    with Image.open(path) as im:
        return im.convert("RGB")
