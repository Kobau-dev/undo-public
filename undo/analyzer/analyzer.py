"""Analyzer: keyframes + request -> validated Analysis JSON from the vision model."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from pydantic import ValidationError

from undo.analyzer.prompts import ANALYZER_SYSTEM, RETRY_HINT, analyzer_user_text, frame_caption
from undo.analyzer.search import Keyframe, relative_time, select_keyframes
from undo.config import Settings
from undo.images import crop_to_window, image_part, load, text_part
from undo.interfaces import VisionModel
from undo.log import get_logger
from undo.models import Analysis
from undo.recorder.index import FrameIndex
from undo.recovery import recovery_hints

log = get_logger("analyzer")


class Analyzer:
    def __init__(self, settings: Settings, vision: VisionModel, index: FrameIndex, max_retries: int = 3, base_dir: Path | None = None, fallback: VisionModel | None = None):
        self.settings = settings
        self.vision = vision
        self.index = index
        self.max_retries = max_retries
        self.base_dir = base_dir  # resolves relative frame paths (exported recordings)
        from undo.redact import build_redactor

        self.redactor = build_redactor(settings)
        self.fallback = fallback  # e.g. the executor's fast Holo model when the analyzer model keeps failing
        self.last_keyframes: list[Keyframe] = []

    def analyze(self, request: str, *, now: float | None = None, app: str | None = None) -> Analysis:
        now = now if now is not None else time.time()
        keyframes = []
        if self.settings.timeline_selection and app is None:
            try:
                from undo.analyzer.timeline import pick_keyframes

                keyframes = pick_keyframes(self.vision, self.index, request, now=now, buffer_minutes=self.settings.buffer_minutes, max_frames=self.settings.max_keyframes)
            except Exception as exc:
                log.warning("timeline selection failed (%s), using heuristics", " ".join(str(exc).split())[:200])
        if not keyframes:
            keyframes = select_keyframes(
                self.index, request, now=now, lookback_minutes=self.settings.lookback_minutes, max_frames=self.settings.max_keyframes, search_minutes=self.settings.buffer_minutes, app=app
            )
        if not keyframes:
            raise RuntimeError("No frames recorded in the lookback window — is the recorder running?")
        self.last_keyframes = keyframes
        for k in keyframes:
            log.info("keyframe %s %s %s — %s", relative_time(k.ts, now), k.frame.app, k.role, k.reason)
        return self.analyze_keyframes(request, keyframes, now=now)

    def _keyboard_log(self, now: float) -> str:
        try:
            from undo.recorder.inputs import format_inputs

            rows = self.index.inputs_between(now - self.settings.lookback_minutes * 60, now + 1)
            return format_inputs(rows, now)
        except Exception as exc:
            log.debug("keyboard log unavailable: %s", exc)
            return ""

    def analyze_keyframes(self, request: str, keyframes: list[Keyframe], *, now: float | None = None) -> Analysis:
        now = now if now is not None else time.time()
        hints = recovery_hints([(k.frame.app, k.frame.window_title) for k in keyframes])
        content = [text_part(analyzer_user_text(request, hints))]
        typed = self._keyboard_log(now)
        if typed:
            content.append(text_part(typed))
        total = len(keyframes)
        for i, k in enumerate(keyframes, 1):
            content.append(text_part(frame_caption(i, total, relative_time(k.ts, now), k.frame.app, k.frame.window_title, k.role, k.frame.ocr_text, ax=k.frame.ax_text)))
            f = k.frame
            img = crop_to_window(load(self._resolve(f.path)), f.win_x, f.win_y, f.win_w, f.win_h)
            content.append(image_part(self.redactor(img) if self.redactor else img, quality=75))
        messages = [{"role": "system", "content": ANALYZER_SYSTEM}, {"role": "user", "content": content}]
        schema = Analysis.model_json_schema()

        last_error = ""
        for attempt in range(1, self.max_retries + 1):
            t0 = time.time()
            resp = self.vision.complete(messages, json_schema=schema, temperature=0.2, thinking=True, max_tokens=8000)
            raw = (resp.content or "").strip()
            try:
                analysis = Analysis.model_validate(_normalize(json.loads(_extract_json(raw))))
                log.info("analysis ok in %.1fs (attempt %d): strategy=%s confidence=%.2f", time.time() - t0, attempt, analysis.strategy, analysis.confidence)
                return analysis
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                last_error = " ".join(str(exc).split())[:300]
                log.warning("invalid analysis JSON (attempt %d): %s | raw: %s", attempt, last_error, " ".join(raw.split())[:300])
                messages = messages + [
                    {"role": "assistant", "content": raw[:4000]},
                    {"role": "user", "content": RETRY_HINT.format(error=last_error)},
                ]
        if self.fallback is not None and self.fallback is not self.vision:
            log.warning("analyzer model failed %d times, falling back to %s", self.max_retries, getattr(self.fallback, "model", "executor model"))
            primary, self.vision = self.vision, self.fallback
            try:
                return self.analyze_keyframes(request, keyframes, now=now)
            finally:
                self.vision = primary
        raise RuntimeError(f"Analyzer: model never returned valid JSON ({last_error})")


    def _resolve(self, path: str) -> str:
        p = Path(path)
        if self.base_dir and not p.is_absolute():
            return str(self.base_dir / p)
        return path


STRATEGIES = ("native_undo", "version_history", "trash", "manual_redo")


def _normalize(data):
    """Forgive the usual model slips before strict validation: confidence as a percentage, strategy casing or
    synonyms, plan as one string, recovered_content as an object/list."""
    if not isinstance(data, dict):
        return data
    c = data.get("confidence")
    if isinstance(c, str):
        try:
            c = float(c.strip().rstrip("%"))
        except ValueError:
            c = 0.5
    if isinstance(c, (int, float)):
        data["confidence"] = min(1.0, max(0.0, c / 100 if c > 1 else c))
    st = str(data.get("strategy", "")).strip().lower().replace(" ", "_").replace("-", "_")
    data["strategy"] = st if st in STRATEGIES else next((x for x in STRATEGIES if x in st), "manual_redo")
    plan = data.get("plan")
    if isinstance(plan, str):
        data["plan"] = [line.strip(" -•\t") for line in plan.splitlines() if line.strip(" -•\t")]
    rc = data.get("recovered_content")
    if isinstance(rc, dict):
        data["recovered_content"] = "\n".join(f"{k}: {v}" for k, v in rc.items())
    elif isinstance(rc, list):
        data["recovered_content"] = "\n".join(map(str, rc))
    elif rc is None:
        data["recovered_content"] = ""
    for k in ("summary", "before_state", "target_app"):
        if data.get(k) is None:
            data[k] = ""
    return data


_ODD_SPACES = re.compile("[\u00a0\u1680\u2000-\u200b\u202f\u205f\u3000\ufeff]")


def _extract_json(text: str) -> str:
    """Tolerate code fences / prose around the object, and the non-breaking spaces holo4-27b sometimes puts between
    tokens (invalid JSON whitespace)."""
    text = _ODD_SPACES.sub(" ", text).strip()
    if text.startswith("{"):
        return text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in response")
    return text[start : end + 1]
