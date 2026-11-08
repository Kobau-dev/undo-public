from undo.config import Settings
from undo.trigger.hotkey import DoubleTap, hotkey_label


def tap(dt: DoubleTap, t: float) -> bool:
    dt.press(True, t)
    return dt.release(True, t + 0.05)


def test_double_tap_fires_within_window():
    dt = DoubleTap(window=0.4)
    assert not tap(dt, 0.0)
    assert tap(dt, 0.25)


def test_slow_taps_do_not_fire():
    dt = DoubleTap(window=0.4)
    assert not tap(dt, 0.0)
    assert not tap(dt, 1.0)
    assert tap(dt, 1.2)  # the slow tap counts as a new first tap


def test_option_used_with_another_key_is_ignored():
    dt = DoubleTap(window=0.4)
    assert not tap(dt, 0.0)
    dt.press(True, 0.1)
    dt.press(False, 0.12)  # ⌥+key, e.g. typing a special character
    assert not dt.release(True, 0.15)
    assert not tap(dt, 0.2)


def test_other_key_between_taps_resets():
    dt = DoubleTap(window=0.4)
    assert not tap(dt, 0.0)
    dt.press(False, 0.1)
    assert not tap(dt, 0.2)


def test_key_repeat_while_held_counts_once():
    dt = DoubleTap(window=0.4)
    dt.press(True, 0.0)
    dt.press(True, 0.03)  # auto-repeat
    assert not dt.release(True, 0.08)
    assert tap(dt, 0.2)


def test_labels_and_default(monkeypatch):
    monkeypatch.delenv("UNDO_HOTKEY", raising=False)
    assert Settings().hotkey == "double:shift"
    assert hotkey_label("double:shift") == "⇧ ⇧"
    assert hotkey_label("double:alt") == "⌥ ⌥"
    assert hotkey_label("double:alt_r") == "⌥ ⌥ droite"
    assert hotkey_label("<cmd>+<shift>+<alt>+z") == "⌘⇧⌥Z"
