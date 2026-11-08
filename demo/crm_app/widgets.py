"""Interface building blocks shared by the screens."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QPoint, QRegularExpression, QStringListModel, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QAbstractItemView, QCalendarWidget, QCompleter, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def long_date(d: date) -> str:
    return f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {d.year}"


def label(text: str, name: str | None = None, wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


class Card(QFrame):
    def __init__(self, title: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 14, 18, 16)
        self.body.setSpacing(10)
        if title:
            self.body.addWidget(label(title, "SectionTitle"))


class Field(QWidget):
    """Visible label (buddy) above an input; the label is also the input's accessible name."""

    def __init__(self, text: str, widget: QWidget, required: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        self.caption = QLabel(f"{text} <span style='color:#c0392b'>*</span>" if required else text)
        self.caption.setObjectName("FieldLabel")
        self.caption.setTextFormat(Qt.RichText)
        self.caption.setBuddy(widget)
        lay.addWidget(self.caption)
        lay.addWidget(widget)
        widget.setAccessibleName(text)
        self.widget = widget


class DateField(QLineEdit):
    """jj/mm/aaaa text field with a calendar popup — a plain text field for the accessibility API."""

    def __init__(self, icon_factory, parent: QWidget | None = None):
        super().__init__(parent)
        self.setValidator(QRegularExpressionValidator(QRegularExpression(r"[0-9]{0,2}/?[0-9]{0,2}/?[0-9]{0,4}"), self))
        self.setMaxLength(10)
        self._action = QAction(icon_factory("calendar"), "Pick a date", self)
        self._action.triggered.connect(self._popup)
        self.addAction(self._action, QLineEdit.TrailingPosition)
        self.editingFinished.connect(self._check)

    def set_icon(self, ic) -> None:
        self._action.setIcon(ic)

    def set_date(self, d: date | None) -> None:
        self.setText(d.strftime("%d/%m/%Y") if d else "")

    def qdate(self) -> QDate:
        return QDate.fromString(self.text(), "dd/MM/yyyy")

    def _check(self) -> None:
        bad = bool(self.text()) and not self.qdate().isValid()
        self.setProperty("invalid", bad)
        self.style().unpolish(self)
        self.style().polish(self)

    def _popup(self) -> None:
        cal = QCalendarWidget()
        cal.setWindowFlags(Qt.Popup)
        cal.setGridVisible(False)
        cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        cal.setFirstDayOfWeek(Qt.Monday)
        if self.qdate().isValid():
            cal.setSelectedDate(self.qdate())

        def pick(d: QDate) -> None:
            self.setText(d.toString("dd/MM/yyyy"))
            self._check()
            cal.close()

        cal.clicked.connect(pick)
        cal.activated.connect(pick)
        cal.adjustSize()
        cal.move(self.mapToGlobal(QPoint(self.width() - cal.sizeHint().width(), self.height() + 4)))
        cal.show()
        self._cal = cal


class LookupField(QLineEdit):
    """Text field with suggestions (type to filter, chevron to list them all).
    A plain text field for the accessibility API, named after its label (Qt names combo boxes after their value)."""

    def __init__(self, items: list[str], icon_factory, parent: QWidget | None = None):
        super().__init__(parent)
        self._model = QStringListModel(items, self)
        comp = QCompleter(self._model, self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        comp.setCompletionMode(QCompleter.PopupCompletion)
        comp.setMaxVisibleItems(10)
        comp.popup().setProperty("completer", True)
        self.setCompleter(comp)
        self._action = QAction(icon_factory("chevron"), "Show the list", self)
        self._action.triggered.connect(self.show_all)
        self.addAction(self._action, QLineEdit.TrailingPosition)

    def set_icon(self, ic) -> None:
        self._action.setIcon(ic)

    def set_items(self, items: list[str]) -> None:
        self._model.setStringList(items)

    def items(self) -> list[str]:
        return self._model.stringList()

    def show_all(self) -> None:
        self.setFocus()
        self.completer().setCompletionPrefix("")
        self.completer().complete()


def table(headers: list[str], rows: list[list[str]], stretch: int = 0, data: list | None = None) -> QTableWidget:
    t = QTableWidget(len(rows), len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(38)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setAlternatingRowColors(False)
    t.setShowGrid(False)
    t.setFocusPolicy(Qt.NoFocus)
    t.setWordWrap(False)
    hh = t.horizontalHeader()
    hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    hh.setHighlightSections(False)
    fill_table(t, rows, data)
    hh.setSectionResizeMode(QHeaderView.ResizeToContents)
    hh.setSectionResizeMode(stretch, QHeaderView.Stretch)
    return t


def fill_table(t: QTableWidget, rows: list[list[str]], data: list | None = None) -> None:
    t.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            it = QTableWidgetItem(val)
            if data is not None:
                it.setData(Qt.UserRole, data[r])
            t.setItem(r, c, it)


class Kpi(Card):
    def __init__(self, title: str, value: str, delta: str = "", parent: QWidget | None = None):
        super().__init__(None, parent)
        self.body.setSpacing(4)
        self.body.addWidget(label(title, "KpiLabel"))
        self.value = label(value, "KpiValue")
        self.body.addWidget(self.value)
        if delta:
            self.body.addWidget(label(delta, "KpiDelta"))


def info_grid(pairs: list[tuple[str, str]], columns: int = 3) -> QWidget:
    w = QWidget()
    g = QGridLayout(w)
    g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(28)
    g.setVerticalSpacing(12)
    for i, (k, v) in enumerate(pairs):
        box = QVBoxLayout()
        box.setSpacing(2)
        box.addWidget(label(k, "FieldLabel"))
        val = label(v or "—", "Value", wrap=True)
        val.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(val)
        g.addLayout(box, i // columns, i % columns)
    for c in range(columns):
        g.setColumnStretch(c, 1)
    return w


def hrow(*widgets, spacing: int = 10, stretch_before: bool = False) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    if stretch_before:
        lay.addStretch(1)
    for w in widgets:
        if w is None:
            lay.addStretch(1)
        elif isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    return lay


class Toast(QLabel):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.hide()
        self._timer = QTimer(self, singleShot=True, interval=3200, timeout=self.hide)

    def show_message(self, text: str) -> None:
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - 48)
        self.raise_()
        self.show()
        self._timer.start()


class Avatar(QLabel):
    def __init__(self, initials: str, size: int = 32, parent: QWidget | None = None):
        super().__init__(initials, parent)
        self.setObjectName("Avatar" if size <= 32 else "AvatarLarge")
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)


class Clickable(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        self.clicked.emit()
        super().mouseReleaseEvent(ev)
