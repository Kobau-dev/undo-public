"""Model-picked keyframes: the whole buffer is summarised as a text timeline (one line per stretch of time spent in
one window), the model reads it and names the moments relevant to the request; only those images are then sent."""
from __future__ import annotations

import json
import time

from undo.analyzer.search import Keyframe, parse_time_hint, relative_time
from undo.interfaces import VisionModel
from undo.log import get_logger
from undo.models import Frame
from undo.recorder.index import FrameIndex

log = get_logger("timeline")

MAX_SEGMENTS = 250
EXCERPT = 160
RECENT_SEGMENTS = 60
SAME_CONTENT = 0.45  # word-set Jaccard under which the same window shows something else (another mail, another page)
NEW_CONTENT = 25  # or this many words appeared and a third as many vanished: another mail in a list+preview layout

PICK_SYSTEM = """You are the memory of Undo, a "Ctrl+Z for the whole computer". You get the user's request and a text
timeline of their screen (oldest first). Each line is a segment: id | time range (relative to now) | app | window |
OCR excerpt. Pick the segments whose screenshots are needed to understand and restore what the user asks for: the
state BEFORE the mistake (richest content), the moment it broke, and any segment in ANOTHER app/window holding
information the user refers to (an email, a document...). Do not pick the current screen, it is always included.
Output only JSON: {"segments": ["S12", ...], "reason": "short"} with at most {n} ids, most useful first."""


def _words(text: str) -> list[str]:
    return (text or "").split()


def _similar(a: Frame, b: Frame) -> bool:
    wa, wb = set(_words(a.ocr_text)), set(_words(b.ocr_text))
    if not wa or not wb:
        return True
    if len(wb - wa) >= NEW_CONTENT and len(wa - wb) >= NEW_CONTENT // 3:
        return False
    return len(wa & wb) / len(wa | wb) >= SAME_CONTENT


def _segments(frames: list[Frame]) -> list[list[Frame]]:
    """Stretches of time in one window showing the same content; a new mail or page in the same window starts a new one."""
    segs: list[list[Frame]] = []
    for f in frames:
        if segs and (segs[-1][-1].app, segs[-1][-1].window_title) == (f.app, f.window_title) and _similar(segs[-1][0], f):
            segs[-1].append(f)
        else:
            segs.append([f])
    return segs


def _richest(seg: list[Frame], current_words: set[str]) -> Frame:
    """The frame of the segment holding the most text absent from the current screen (what may have been lost)."""
    return max(seg, key=lambda f: (len({w for w in _words(f.ocr_text) if w not in current_words}), len(f.ocr_text or ""), f.ts))


def _excerpt(text: str, current_words: set[str] | None = None) -> str:
    words = _words(text)
    if current_words is not None:
        new = [w for w in words if w not in current_words]
        if len(new) >= 3:  # what differs from the current screen first: menu bars and unchanged text are noise
            words = new
    return " ".join(words)[:EXCERPT]


def build_timeline(index: FrameIndex, request: str, now: float, buffer_minutes: int) -> tuple[str, dict[str, Frame], Frame | None]:
    """Returns (timeline text, segment id -> representative frame, current frame)."""
    start = now - buffer_minutes * 60
    hint = parse_time_hint(request, now)
    frames = index.between(start, now + 1)
    if not frames:
        return "", {}, None
    current = frames[-1]
    current_words = set(_words(current.ocr_text))
    segs = _segments(frames[:-1])
    if len(segs) > MAX_SEGMENTS:
        keep = set(range(max(0, len(segs) - RECENT_SEGMENTS), len(segs)))
        hit_ids = {f.id for f, _ in index.search(request, start_ts=start, end_ts=now + 1, limit=40)}
        for i, seg in enumerate(segs):
            if any(f.id in hit_ids for f in seg) or (hint and seg[-1].ts >= hint[0] and seg[0].ts <= hint[1]):
                keep.add(i)
        rest = [i for i in range(len(segs)) if i not in keep]
        room = max(0, MAX_SEGMENTS - len(keep))
        if rest and room:
            step = max(1, len(rest) // room)
            keep.update(rest[::step][:room])
        segs = [segs[i] for i in sorted(keep)]
    ids: dict[str, Frame] = {}
    lines = []
    for i, seg in enumerate(segs, 1):
        rep = _richest(seg, current_words)
        sid = f"S{i}"
        ids[sid] = rep
        span = relative_time(seg[0].ts, now) + ("" if len(seg) == 1 else f"→{relative_time(seg[-1].ts, now)}")
        lines.append(f"{sid} | {span} | {rep.app or '?'} | {(rep.window_title or '?')[:60]} | {_excerpt(rep.ocr_text, current_words)}")
    lines.append(f"CURRENT | {relative_time(current.ts, now)} | {current.app or '?'} | {(current.window_title or '?')[:60]} | {_excerpt(current.ocr_text)}")
    return "\n".join(lines), ids, current


def pick_keyframes(vision: VisionModel, index: FrameIndex, request: str, *, now: float | None = None, buffer_minutes: int = 480, max_frames: int = 5) -> list[Keyframe]:
    """Keyframes chosen by the model from the text timeline; [] when it cannot decide (caller falls back to heuristics)."""
    from undo.analyzer.analyzer import _extract_json

    now = now if now is not None else time.time()
    text, ids, current = build_timeline(index, request, now, buffer_minutes)
    if current is None:
        return []
    chosen = [Keyframe(current, "current", "latest frame")]
    if not ids:
        return chosen
    n = max_frames - 1
    hint = parse_time_hint(request, now)
    when = f"\nThe user points at this time: {relative_time(hint[0], now)} to {relative_time(hint[1], now)}." if hint else ""
    messages = [
        {"role": "system", "content": PICK_SYSTEM.replace("{n}", str(n))},
        {"role": "user", "content": f"USER REQUEST: «{request}»{when}\n\nTIMELINE:\n{text}"},
    ]
    t0 = time.time()
    resp = vision.complete(messages, temperature=0.0, thinking=False, max_tokens=400)
    data = json.loads(_extract_json((resp.content or "").strip()))
    picked = [s.strip() for s in data.get("segments", []) if isinstance(s, str)]
    for sid in picked:
        f = ids.get(sid)
        if f is not None and all(k.frame.id != f.id for k in chosen) and len(chosen) < max_frames:
            chosen.append(Keyframe(f, "picked", f"{sid} chosen by the model"))
    log.info("timeline: %d segments, model picked %s in %.1fs (%s)", len(ids), picked, time.time() - t0, str(data.get("reason", ""))[:120])
    return sorted(chosen, key=lambda k: k.ts) if len(chosen) > 1 else []
