"""Desktop CRM used in the demo video (demo/crm_app): the report form, its accessible labels and the session expiry."""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QAccessible  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from demo.crm_app.app import build  # noqa: E402


@pytest.fixture
def win():
    _app, w, _args = build(["--session-timeout", "0", "--contact", "marchand", "--new-report"])
    yield w
    w.close()
    w.deleteLater()
    QApplication.processEvents()


def _name(widget) -> str:
    return QAccessible.queryAccessibleInterface(widget).text(QAccessible.Name)


def test_form_inputs_have_accessible_labels(win):
    f = win.form
    assert _name(f.report) == "Visit report"
    assert _name(f.visit_date) == "Visit date"
    assert _name(f.next_step) == "Next step"
    assert _name(f.account) == "Account"
    assert _name(f.contact) == "Contact met"
    assert _name(f.objective) == "Main objective"
    assert [_name(b) for b in f.type_buttons][0] == "In person"
    assert _name(f.products[0]) == "Tensiora 5/10 mg"


def test_session_expiry_loses_unsaved_report(win):
    f = win.form
    assert f.contact.text() == "Dr Hélène Marchand"
    f.report.setPlainText("Long report")
    f.products[1].setChecked(True)
    f.type_buttons[2].setChecked(True)
    assert f.is_dirty()

    win.session.expire()
    sheet = win._sheet
    assert sheet.isVisible() and sheet.password.echoMode() == sheet.password.EchoMode.Password
    assert win.form is not f and not win.form.is_dirty()
    assert win.stack.currentWidget() is win.form

    sheet._submit()
    assert sheet.error.isVisible()  # empty password refused
    sheet.password.setText("secret")
    sheet._submit()
    sheet.accept()
    assert win.session.active and not win.form.report.toPlainText()


def test_save_adds_visit_to_contact(win):
    f = win.form
    contact = f.context
    before = len(contact.visits)
    f.report.setPlainText("Glycalm XR presentation.\nMore at the next visit.")
    f._save()
    assert len(contact.visits) == before + 1
    assert contact.visits[-1].summary == "Glycalm XR presentation."
    assert win.stack.currentWidget() is win.record
    contact.visits.pop()


def test_contact_suggestions_follow_account(win):
    f = win.form
    assert set(f.contact.items()) == {"Dr Hélène Marchand", "Dr Mehdi Ouali"}
    f.account.setText("Coteaux Clinic")
    assert set(f.contact.items()) == {"Dr Isabelle Moreau", "Dr François Garnier"}



def test_contact_cleared_when_account_changes_and_empty_search(win):
    from demo.crm_app import data

    c = data.find_contact("marchand")
    win.new_report(c)
    other = next(a for a in data.ACCOUNTS if a.id != c.account_id)
    win.form.account.setText(other.name)
    assert win.form.contact.text() == ""
    assert data.find_contact("   ") is None


def test_new_report_after_save_starts_empty(win):
    from demo.crm_app import data

    c = data.find_contact("marchand")
    win.form.report.setPlainText("Follow-up visit.")
    win.form.save_btn.click()
    win.new_report(c)
    assert win.form.report.toPlainText() == ""
    c.visits.pop()
