"""Find the moments that matter: before the mistake, the mistake itself, and now."""
from __future__ import annotations

import re

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from undo.models import Frame
from undo.recorder.index import FrameIndex


@dataclass
class Keyframe:
    frame: Frame
    role: str  # before | error | current | context | match
    reason: str = ""

    @property
    def ts(self) -> float:
        return self.frame.ts


def _jpeg_size(frame: Frame) -> int:
    try:
        return Path(frame.path).stat().st_size
    except OSError:
        return 0


def _content_drops(frames: list[Frame]) -> list[tuple[int, int, str]]:
    """(index, drop) where the amount of content shrinks sharply vs the previous frame -> likely 'the mistake'.

    Content is measured by OCR text length; without OCR (Linux dev box, OCR disabled) the JPEG size is a decent
    proxy (a filled form compresses ~20% worse than an empty one), with a tighter threshold.
    """
    if any(f.ocr_text for f in frames):
        measure, min_prev, ratio, unit = (lambda f: len(f.ocr_text)), 40, 0.6, "chars"
    else:
        measure, min_prev, ratio, unit = _jpeg_size, 20_000, 0.9, "bytes (no OCR)"
    drops = []
    for i in range(1, len(frames)):
        if frames[i - 1].app and frames[i].app and frames[i - 1].app != frames[i].app:
            continue  # switching apps is not a mistake
        prev, cur = measure(frames[i - 1]), measure(frames[i])
        if prev >= min_prev and cur < prev * ratio:
            drops.append((i, prev - cur, unit))
    drops.sort(key=lambda d: -d[1])
    return drops


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w{3,}", text.lower())}


def _most_lost_content(window: list[Frame], current: Frame) -> tuple[Frame | None, int]:
    """Frame (same app as `current`) whose OCR text has the most words absent from the current screen: that is
    where the lost content is most visible. Robust where a raw length drop is not (values are small vs labels)."""
    now_words = _words(current.ocr_text)
    scored = [
        (len(_words(f.ocr_text) - now_words), f)
        for f in window[:-1]
        if f.ocr_text and not (f.app and current.app and f.app != current.app)
    ]
    if not scored:
        return None, 0
    top = max(n for n, _ in scored)
    # among the richest frames (within 15 %), take the most recent one: the last complete state before the loss
    n, f = max(((n, f) for n, f in scored if n >= top * 0.85), key=lambda x: x[1].ts)
    return f, n


OLD_MATCH_CONTEXT_S = 600
_AGO = re.compile(r"(?:il y a|ago|y a)\s*(\d+)\s*(min|minutes?|h|heures?|hours?)\b|(\d+)\s*(min|minutes?|h|heures?|hours?)\s+ago", re.I)
_AT = re.compile(r"\b(?:vers|à|a|at|around)\s+(\d{1,2})\s*(?:h|:)\s*(\d{2})?", re.I)
_PERIODS = {"ce matin": (6, 12), "this morning": (6, 12), "à midi": (11, 14), "cet après-midi": (12, 18), "cet apres-midi": (12, 18), "this afternoon": (12, 18), "ce soir": (18, 24), "tonight": (18, 24)}


def parse_time_hint(request: str, now: float) -> tuple[float, float] | None:
    """Time window named in the request ("il y a 2 h", "vers 14h30", "ce matin"), or None."""
    m = _AGO.search(request)
    if m:
        n, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        secs = int(n) * (3600 if unit.lower().startswith("h") else 60)
        margin = max(600, secs * 0.25)
        return now - secs - margin, now - secs + margin
    day = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0)
    m = _AT.search(request)
    if m and int(m.group(1)) < 24:
        t = day.replace(hour=int(m.group(1)), minute=int(m.group(2) or 0)).timestamp()
        if t > now:
            t -= 86400
        return t - 900, t + 900
    low = request.lower()
    for words, (h0, h1) in _PERIODS.items():
        if words in low:
            return day.timestamp() + h0 * 3600, min(now, day.timestamp() + h1 * 3600)
    return None



def select_keyframes(
    index: FrameIndex,
    request: str,
    *,
    now: float | None = None,
    lookback_minutes: int = 15,
    max_frames: int = 5,
    app: str | None = None,
    search_minutes: int | None = None,
) -> list[Keyframe]:
    """Heuristics run on the recent window; the OCR search covers the whole buffer (`search_minutes`) and, when the
    best match is older than the window, the frames around it are added so hours-old states can be found."""
    now = now if now is not None else time.time()
    start = now - lookback_minutes * 60
    window = index.between(start, now + 1, app=app)
    if not window:
        return []
    search_start, search_end = now - max(lookback_minutes, search_minutes or 0) * 60, now + 1
    hint = parse_time_hint(request, now)
    if hint:
        search_start, search_end = hint

    chosen: dict[int, Keyframe] = {}

    def add(frame: Frame, role: str, reason: str = "") -> None:
        if frame.id in chosen or len(chosen) >= max_frames:
            return
        chosen[frame.id] = Keyframe(frame, role, reason)

    current = window[-1]
    add(current, "current", "latest frame")

    hits = index.search(request, start_ts=search_start, end_ts=search_end, app=app, limit=10)
    hits = [(f, s) for f, s in hits if f.id != current.id]
    extra: tuple[float, float] | None = None
    if hint and hint[0] < start:
        extra = hint
    elif hits and hits[0][0].ts < start:
        extra = (hits[0][0].ts - OLD_MATCH_CONTEXT_S, hits[0][0].ts + OLD_MATCH_CONTEXT_S)
    if extra:
        seen = {f.id for f in window}
        around = [f for f in index.between(extra[0], extra[1], app=app) if f.id not in seen]
        window = sorted(around + window, key=lambda f: f.ts)
    # the user asks for help from the app they are in: prefer matches there (a chat window quoting the request
    # must not win over the real "before" screen)
    hits.sort(key=lambda h: 0 if (not current.app or h[0].app == current.app) else 1)
    if hits:
        best, score = hits[0]
        add(best, "before", f"best OCR match (bm25 {score:.1f})")

    lost, n_lost = _most_lost_content(window, current)
    if lost is not None and n_lost >= 5:
        add(lost, "before", f"most content missing from the current screen ({n_lost} words)")

    drops = _content_drops(window)
    if drops:
        i, drop, unit = drops[0]
        if i >= 1:
            add(window[i - 1], "before", f"richest content before a drop of {drop} {unit}")
        add(window[i], "error", f"content dropped by {drop} {unit}")

    # fill with a second OCR match, then evenly spaced context frames
    for f, s in hits[1:2]:
        add(f, "match", f"OCR match (bm25 {s:.1f})")
    if len(chosen) < max_frames:
        remaining = [f for f in window if f.id not in chosen]
        slots = max_frames - len(chosen)
        if remaining and slots:
            step = max(1, len(remaining) // slots)
            for f in remaining[::step][:slots]:
                add(f, "context", "evenly spaced")

    # info the user saw in another window (other app / tab) must reach the model even when every slot is taken
    if not any((k.frame.app, k.frame.window_title) != (current.app, current.window_title) for k in chosen.values()):
        other = next((f for f, _ in hits if (f.app, f.window_title) != (current.app, current.window_title)), None)
        if other is None:
            others = [f for f in window if (f.app, f.window_title) != (current.app, current.window_title)]
            other = max(others, key=lambda f: len(f.ocr_text or ""), default=None)
        if other is not None and other.id not in chosen:
            chosen[other.id] = Keyframe(other, "other_window", f"seen in another window ({other.app})")

    return sorted(chosen.values(), key=lambda k: k.ts)


def relative_time(ts: float, now: float) -> str:
    delta = max(0, int(now - ts))
    m, s = divmod(delta, 60)
    return f"-{m}m{s:02d}s" if m else f"-{s}s"
