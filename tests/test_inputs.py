from undo.recorder.index import FrameIndex
from undo.recorder.inputs import TypedBuffer, format_inputs


def test_typed_buffer():
    b = TypedBuffer()
    for i, c in enumerate("Dupomt"):
        b.char(c, 10 + i)
    b.backspace(20); b.backspace(20)
    b.char("n", 21); b.char("t", 22)
    assert b.take() == (10, "Dupont")
    assert b.text == ""


def test_inputs_stored_purged_and_formatted(tmp_path):
    idx = FrameIndex(tmp_path / "f.db")
    idx.add_input(100.0, "Brave Browser", "Formulaire", "typed", "Déclaration de perte\n")
    idx.add_input(101.0, "Brave Browser", "Formulaire", "shortcut", "cmd+w")
    idx.add_input(102.0, "Brave Browser", "Formulaire", "click", "10,20 left")
    rows = idx.inputs_between(0, 200)
    assert [r["kind"] for r in rows] == ["typed", "shortcut", "click"]
    text = format_inputs(rows, now=160.0)
    assert "typed «Déclaration de perte»" in text and "shortcut cmd+w" in text and "10,20" not in text
    idx.purge_older_than(101.5)
    assert [r["kind"] for r in idx.inputs_between(0, 200)] == ["click"]


def test_nothing_logged_in_password_fields_without_secure_input(monkeypatch):
    from undo import ax
    from undo.recorder import inputs

    log = inputs.InputLogger.__new__(inputs.InputLogger)
    log.is_paused = lambda: False
    monkeypatch.setattr(inputs, "secure_input_enabled", lambda: False)
    monkeypatch.setattr(ax, "focused_is_password", lambda: True)
    assert log._blocked()
    monkeypatch.setattr(ax, "focused_is_password", lambda: False)
    assert not log._blocked()
