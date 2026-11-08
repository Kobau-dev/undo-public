"""SQLite index of recorded frames with FTS5 full-text search on OCR text."""
from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path

from undo.models import Frame

SCHEMA = """
CREATE TABLE IF NOT EXISTS frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    app TEXT NOT NULL DEFAULT '',
    window_title TEXT NOT NULL DEFAULT '',
    ocr_text TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    phash TEXT NOT NULL DEFAULT '',
    win_x REAL NOT NULL DEFAULT 0, win_y REAL NOT NULL DEFAULT 0,
    win_w REAL NOT NULL DEFAULT 0, win_h REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_frames_ts ON frames(ts);
CREATE TABLE IF NOT EXISTS inputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    app TEXT NOT NULL DEFAULT '',
    window_title TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,  -- typed | shortcut | click
    text TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_inputs_ts ON inputs(ts);
CREATE VIRTUAL TABLE IF NOT EXISTS frames_fts USING fts5(
    ocr_text, app, window_title, content='frames', content_rowid='id', tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS frames_ai AFTER INSERT ON frames BEGIN
    INSERT INTO frames_fts(rowid, ocr_text, app, window_title) VALUES (new.id, new.ocr_text, new.app, new.window_title);
END;
CREATE TRIGGER IF NOT EXISTS frames_ad AFTER DELETE ON frames BEGIN
    INSERT INTO frames_fts(frames_fts, rowid, ocr_text, app, window_title) VALUES ('delete', old.id, old.ocr_text, old.app, old.window_title);
END;
CREATE TRIGGER IF NOT EXISTS frames_au AFTER UPDATE ON frames BEGIN
    INSERT INTO frames_fts(frames_fts, rowid, ocr_text, app, window_title) VALUES ('delete', old.id, old.ocr_text, old.app, old.window_title);
    INSERT INTO frames_fts(rowid, ocr_text, app, window_title) VALUES (new.id, new.ocr_text, new.app, new.window_title);
END;
"""

_TOKEN_RE = re.compile(r"[\w'’-]{2,}", re.UNICODE)


def fts_query_from_text(text: str, max_terms: int = 12) -> str:
    """Turn a free-form request into a lenient FTS5 OR-query of prefix terms."""
    terms = []
    for tok in _TOKEN_RE.findall(text.lower()):
        tok = tok.strip("'’-")
        if len(tok) < 3 or tok in STOPWORDS:
            continue
        if tok not in terms:
            terms.append(tok)
    terms = terms[:max_terms]
    return " OR ".join(f'"{t}"*' for t in terms)


class FrameIndex:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(frames)")}
        for c in ("win_x", "win_y", "win_w", "win_h"):
            if c not in cols:  # databases created before window bounds were recorded
                self._conn.execute(f"ALTER TABLE frames ADD COLUMN {c} REAL NOT NULL DEFAULT 0")
        if "ax_text" not in cols:
            self._conn.execute("ALTER TABLE frames ADD COLUMN ax_text TEXT NOT NULL DEFAULT ''")

    # -- write -------------------------------------------------------------
    def add(self, frame: Frame) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO frames(ts, app, window_title, ocr_text, path, width, height, phash, win_x, win_y, win_w, win_h, ax_text)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (frame.ts, frame.app, frame.window_title, frame.ocr_text, frame.path, frame.width, frame.height, frame.phash,
                 frame.win_x, frame.win_y, frame.win_w, frame.win_h, frame.ax_text),
            )
            frame.id = int(cur.lastrowid)
            return frame.id

    def add_input(self, ts: float, app: str, title: str, kind: str, text: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO inputs(ts, app, window_title, kind, text) VALUES (?,?,?,?,?)", (ts, app, title, kind, text))

    def inputs_between(self, start_ts: float, end_ts: float) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT ts, app, window_title, kind, text FROM inputs WHERE ts BETWEEN ? AND ? ORDER BY ts", (start_ts, end_ts)).fetchall()
        return [dict(r) for r in rows]

    def set_ocr(self, frame_id: int, text: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE frames SET ocr_text=? WHERE id=?", (text, frame_id))

    def purge_older_than(self, ts: float) -> list[str]:
        """Delete frames older than ts; return their file paths so the caller can unlink them."""
        with self._lock, self._conn:
            rows = self._conn.execute("SELECT path FROM frames WHERE ts < ?", (ts,)).fetchall()
            self._conn.execute("DELETE FROM frames WHERE ts < ?", (ts,))
            self._conn.execute("DELETE FROM inputs WHERE ts < ?", (ts,))
        return [r["path"] for r in rows]

    # -- read --------------------------------------------------------------
    def _rows_to_frames(self, rows) -> list[Frame]:
        return [Frame(**{k: r[k] for k in r.keys() if k in Frame.model_fields}) for r in rows]

    def count(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM frames").fetchone()[0])

    def latest(self, n: int = 1) -> list[Frame]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM frames ORDER BY ts DESC LIMIT ?", (n,)).fetchall()
        return self._rows_to_frames(rows)

    def get(self, frame_id: int) -> Frame | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM frames WHERE id=?", (frame_id,)).fetchone()
        return self._rows_to_frames([row])[0] if row else None

    def between(self, start_ts: float, end_ts: float | None = None, app: str | None = None) -> list[Frame]:
        end_ts = end_ts if end_ts is not None else time.time() + 1
        sql = "SELECT * FROM frames WHERE ts BETWEEN ? AND ?"
        params: list = [start_ts, end_ts]
        if app:
            sql += " AND app LIKE ?"
            params.append(f"%{app}%")
        sql += " ORDER BY ts ASC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return self._rows_to_frames(rows)

    def search(self, query: str, start_ts: float | None = None, end_ts: float | None = None, app: str | None = None, limit: int = 30) -> list[tuple[Frame, float]]:
        """FTS search. Returns (frame, score) with lower bm25 score = better match."""
        fts = fts_query_from_text(query) if not query.startswith('"') else query
        if not fts:
            return []
        sql = (
            "SELECT f.*, bm25(frames_fts, 5.0, 1.0, 2.0) AS score FROM frames_fts "
            "JOIN frames f ON f.id = frames_fts.rowid WHERE frames_fts MATCH ?"
        )
        params: list = [fts]
        if start_ts is not None:
            sql += " AND f.ts >= ?"
            params.append(start_ts)
        if end_ts is not None:
            sql += " AND f.ts <= ?"
            params.append(end_ts)
        if app:
            sql += " AND f.app LIKE ?"
            params.append(f"%{app}%")
        sql += " ORDER BY score ASC LIMIT ?"
        params.append(limit)
        with self._lock:
            try:
                rows = self._conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                return []
        return [(f, float(r["score"])) for f, r in zip(self._rows_to_frames(rows), rows)]

    def apps(self, start_ts: float | None = None) -> list[str]:
        sql = "SELECT DISTINCT app FROM frames"
        params: list = []
        if start_ts is not None:
            sql += " WHERE ts >= ?"
            params.append(start_ts)
        with self._lock:
            return [r[0] for r in self._conn.execute(sql, params).fetchall() if r[0]]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


STOPWORDS = set(
    """
    the and for with that this from what have was were are you your les des une dans pour que qui est sur avec
    mon mes ses son sa leur nous vous ils elles elle lui pas plus tout tous toute cela ceci comme mais donc car
    aussi avant après apres puis quand alors j'ai jai ai été ete etre être fait faire faut veux voudrais peux
    recuperer récupérer retrouver remettre revenir perdu perdue perdus supprimé supprime efface effacé undo
    just want need back get got lost deleted removed restore recover please stp svp
    """.split()
)
