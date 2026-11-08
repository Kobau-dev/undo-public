"""Shared pydantic models: recorded frames, analysis output, executor actions."""
from __future__ import annotations

import re

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Frame(BaseModel):
    id: int | None = None
    ts: float
    app: str = ""
    window_title: str = ""
    ocr_text: str = ""
    path: str
    width: int = 0
    height: int = 0
    phash: str = ""
    # foreground window bounds as fractions of the screen (0..1); 0,0,0,0 = unknown -> full screen
    win_x: float = 0.0
    win_y: float = 0.0
    win_w: float = 0.0
    win_h: float = 0.0
    ax_text: str = ""  # form state read from the accessibility tree (exact values), when available


Strategy = Literal["native_undo", "version_history", "trash", "manual_redo"]


class Analysis(BaseModel):
    """Strict JSON contract returned by the Analyzer."""

    summary: str = Field(description="What was lost or broken, one or two sentences")
    before_state: str = Field(description="Precise description of the state to restore")
    recovered_content: str = Field(default="", description="Exact text to retype if applicable (from OCR + vision)")
    strategy: Strategy = Field(description="native_undo | version_history | trash | manual_redo")
    plan: list[str] = Field(default_factory=list, description="Ordered concrete steps the agent will execute")
    confidence: float = Field(ge=0.0, le=1.0)
    target_app: str = Field(default="", description="Application where the restoration happens")

    @field_validator("plan")
    @classmethod
    def _non_empty_plan(cls, v: list[str]) -> list[str]:
        v = [s.strip() for s in v if s and s.strip()]
        if not v:
            raise ValueError("plan must contain at least one step")
        return v


ActionType = Literal[
    "click",
    "move",
    "double_click",
    "right_click",
    "type",
    "key",
    "scroll",
    "open_app",
    "wait",
    "done",
    "ask_user",
    "set_text",
    "press",
]

DESTRUCTIVE_HINTS = (
    "delete",
    "supprim",
    "remove",
    "send",
    "envoy",
    "pay",
    "paie",
    "payer",
    "submit",
    "soumettre",
    "valider",
    "validate",
    "confirm",
    "purchase",
    "achet",
    "order",
    "commander",
    "publish",
    "publier",
    "empty trash",
    "vider la corbeille",
)
# verb at a word start, not its past participle: "Supprimer" asks, "la note supprimée" / "deleted" do not
_DESTRUCTIVE_RE = re.compile(r"\b(?:" + "|".join(map(re.escape, DESTRUCTIVE_HINTS)) + r")(?!é|d\b)", re.IGNORECASE)


class Action(BaseModel):
    """One step decided by the executor model. Coordinates are normalized [0, 1000] on the screenshot sent."""

    type: ActionType
    x: int | None = Field(default=None, ge=0, le=1000)
    y: int | None = Field(default=None, ge=0, le=1000)
    text: str | None = None  # type / open_app / done / ask_user
    keys: str | None = None  # key combo e.g. "cmd+z"
    id: int | None = None  # set_text / press: control id from the accessibility list
    dx: int = 0
    dy: int = 0
    seconds: float = 1.0
    target: str = Field(default="", description="What is being acted on, e.g. 'Save button'")
    destructive: bool = False
    is_password_field: bool = False
    reason: str = ""

    @property
    def needs_confirmation(self) -> bool:
        if self.destructive:
            return True
        hay = f"{self.target} {self.reason} {self.text or ''} {self.keys or ''}"
        return self.type in {"click", "double_click", "key", "press"} and bool(_DESTRUCTIVE_RE.search(hay))

    def describe(self) -> str:
        t = self.type
        if t in {"click", "double_click", "right_click", "move"}:
            return f"{t} ({self.x},{self.y}) {self.target}".strip()
        if t == "type":
            preview = (self.text or "")[:60].replace("\n", "⏎")
            return f"type “{preview}{'…' if len(self.text or '') > 60 else ''}” {self.target}".strip()
        if t == "key":
            return f"key {self.keys}"
        if t == "set_text":
            preview = (self.text or "")[:60].replace("\n", "⏎")
            return f"set_text #{self.id} “{preview}{'…' if len(self.text or '') > 60 else ''}” {self.target}".strip()
        if t == "press":
            return f"press #{self.id} {self.target}".strip()
        if t == "scroll":
            return f"scroll dx={self.dx} dy={self.dy} {self.target}".strip()
        if t == "open_app":
            return f"open_app {self.text}"
        if t == "wait":
            return f"wait {self.seconds}s"
        if t == "done":
            return f"done: {self.text or ''}"
        if t == "ask_user":
            return f"ask_user: {self.text or ''}"
        return t


class ExecutionResult(BaseModel):
    success: bool
    steps: int
    message: str = ""
    actions: list[str] = Field(default_factory=list)
