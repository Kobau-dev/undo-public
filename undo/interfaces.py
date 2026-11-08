"""Provider-agnostic interfaces. Swap implementations in undo/providers and undo/executor."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from PIL import Image


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class ModelResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    reasoning: str | None = None
    raw: Any = None


class VisionModel(ABC):
    """A multimodal model that sees screenshots and returns text / JSON / tool calls."""

    name: str = "vision"

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        json_schema: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        thinking: bool = True,
        max_tokens: int = 2048,
    ) -> ModelResponse:
        """OpenAI-style chat completion. `messages` may contain image_url parts (data URIs)."""

    @abstractmethod
    def locate(self, image: Image.Image, target: str) -> tuple[int, int]:
        """Return pixel coordinates of `target` in `image` (grounding)."""


class Transcriber(ABC):
    """Speech-to-text on a finished audio clip."""

    name: str = "transcriber"

    @abstractmethod
    def transcribe(self, wav_bytes: bytes, languages: list[str] | None = None) -> str: ...


class Executor(ABC):
    """Takes an analysis and restores the 'before' state by driving the computer."""

    name: str = "executor"

    @abstractmethod
    def run(self, analysis: Any, request: str) -> Any: ...

    def stop(self) -> None:  # pragma: no cover - default no-op
        pass


@runtime_checkable
class OCREngine(Protocol):
    def recognize(self, image: Image.Image) -> str: ...


@runtime_checkable
class ForegroundProvider(Protocol):
    def foreground(self) -> tuple[str, str]:
        """(app_name, window_title) of the frontmost window."""


@runtime_checkable
class StatusSink(Protocol):
    """Where the UI overlay / console gets its updates."""

    def set_state(self, state: str, text: str = "") -> None: ...

    def add_step(self, text: str) -> None: ...

    def confirm(self, question: str) -> bool: ...

    def ask(self, question: str) -> str: ...
