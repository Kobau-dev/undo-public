from PIL import Image

from undo.images import crop_to_window
from undo.models import Frame
from undo.recorder.index import FrameIndex
from undo.recorder.platform import _fraction_of


def test_crop_to_window():
    im = Image.new("RGB", (1000, 500))
    assert crop_to_window(im, 0.2, 0.1, 0.5, 0.6).size == (520, 310)
    assert crop_to_window(im, 0, 0, 0, 0) is im  # unknown
    assert crop_to_window(im, 0, 0, 1, 1) is im  # full screen
    assert crop_to_window(im, 0.1, 0.1, 0.1, 0.1) is im  # tiny popup


def test_fraction_of_clamps():
    import pytest

    assert _fraction_of({"X": -10, "Y": 25, "Width": 760, "Height": 400}, 1500, 1000) == pytest.approx((0.0, 0.025, 0.5, 0.4))
    assert _fraction_of({"X": 0, "Y": 0, "Width": 0, "Height": 10}, 1500, 1000) is None


def test_index_stores_bounds_and_migrates(tmp_path):
    import sqlite3

    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE frames (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, app TEXT NOT NULL DEFAULT '', window_title TEXT NOT NULL DEFAULT '', ocr_text TEXT NOT NULL DEFAULT '', path TEXT NOT NULL, width INTEGER NOT NULL DEFAULT 0, height INTEGER NOT NULL DEFAULT 0, phash TEXT NOT NULL DEFAULT '')")
    con.commit(); con.close()
    idx = FrameIndex(db)
    idx.add(Frame(ts=1.0, path="a.jpg", win_x=0.1, win_y=0.2, win_w=0.5, win_h=0.6))
    f = idx.latest(1)[0]
    assert (f.win_x, f.win_y, f.win_w, f.win_h) == (0.1, 0.2, 0.5, 0.6)
