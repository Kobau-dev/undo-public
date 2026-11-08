"""Pluggable providers. Build them from Settings with `build_vision` / `build_transcriber`."""
from __future__ import annotations

from undo.config import Settings
from undo.interfaces import Transcriber, VisionModel


class MissingHKey(RuntimeError):
    pass


def build_vision(settings: Settings, role: str = "executor") -> VisionModel:
    """role="executor": Holo (grounding + actions, `UNDO_MODEL`).
    role="analyzer": the "brain" that reads the keyframes and plans: Holo `UNDO_ANALYZER_MODEL` (default holo4-35b-a3b)."""
    if not settings.h_api_key:
        raise MissingHKey("H_API_KEY is not set (see .env.example)")
    from undo.providers.holo import HoloVisionModel

    if role == "analyzer":
        return HoloVisionModel(api_key=settings.h_api_key, base_url=settings.h_base_url, model=settings.analyzer_model, reasoning_effort=settings.analyzer_effort)
    return HoloVisionModel(api_key=settings.h_api_key, base_url=settings.h_base_url, model=settings.model)


def build_transcriber(settings: Settings) -> Transcriber | None:
    if not settings.gladia_api_key:
        return None
    from undo.providers.gladia import GladiaTranscriber

    return GladiaTranscriber(api_key=settings.gladia_api_key)
