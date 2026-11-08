"""Deterministic providers for tests, --dry-run and offline demos."""
from __future__ import annotations

import json
from collections import deque
from typing import Any

from PIL import Image

from undo.interfaces import ModelResponse, ToolCall, Transcriber, VisionModel


class ScriptedVisionModel(VisionModel):
    """Returns pre-scripted responses in order. Each item is a str (content) or a (tool_name, args) tuple."""

    name = "scripted"

    def __init__(self, script: list[Any]):
        self.script = deque(script)
        self.requests: list[dict[str, Any]] = []

    def complete(self, messages, *, json_schema=None, tools=None, temperature=0.0, thinking=True, max_tokens=2048) -> ModelResponse:
        self.requests.append({"messages": messages, "json_schema": json_schema, "tools": tools})
        if not self.script:
            raise RuntimeError("ScriptedVisionModel ran out of responses")
        item = self.script.popleft()
        if isinstance(item, list) and item and all(isinstance(i, tuple) for i in item):
            return ModelResponse(tool_calls=[ToolCall(name=n, arguments=a) for n, a in item])
        if isinstance(item, tuple):
            name, args = item
            return ModelResponse(tool_calls=[ToolCall(name=name, arguments=args)])
        if isinstance(item, dict):
            return ModelResponse(content=json.dumps(item))
        return ModelResponse(content=str(item))

    def locate(self, image: Image.Image, target: str) -> tuple[int, int]:
        return image.width // 2, image.height // 2


class FakeTranscriber(Transcriber):
    name = "fake"

    def __init__(self, text: str = ""):
        self.text = text

    def transcribe(self, wav_bytes: bytes, languages=None) -> str:
        return self.text
