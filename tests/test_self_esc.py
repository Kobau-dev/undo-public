"""The agent's own Esc (closing a menu) must not trip the Esc kill switch; a real one later must."""
import time

from undo.executor import control


def test_self_esc_window(monkeypatch):
    monkeypatch.setattr(control, "_last_self_esc", 0.0)
    assert not control.self_esc_recent()
    monkeypatch.setattr(control, "_last_self_esc", time.time())
    assert control.self_esc_recent()
    monkeypatch.setattr(control, "_last_self_esc", time.time() - control.SELF_ESC_WINDOW - 0.1)
    assert not control.self_esc_recent()

