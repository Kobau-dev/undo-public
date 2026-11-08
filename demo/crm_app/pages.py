"""CRM screens: dashboard, lists, contact record, visit report."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QGridLayout, QHBoxLayout, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QRadioButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from . import data
from .widgets import Avatar, Card, DateField, Field, Kpi, LookupField, fill_table, hrow, info_grid, label, long_date, table


def page_header(title: str, subtitle: str = "", breadcrumb: str = "", actions: list[QWidget] | None = None) -> QVBoxLayout:
    box = QVBoxLayout()
    box.setSpacing(4)
    if breadcrumb:
        box.addWidget(label(breadcrumb, "Breadcrumb"))
    row = QHBoxLayout()
    texts = QVBoxLayout()
    texts.setSpacing(3)
    texts.addWidget(label(title, "PageTitle"))
    if subtitle:
        texts.addWidget(label(subtitle, "PageSubtitle"))
    row.addLayout(texts, 1)
    for a in actions or []:
        row.addWidget(a, 0, Qt.AlignBottom)
    box.addLayout(row)
    return box


def button(text: str, primary: bool = False) -> QPushButton:
    b = QPushButton(text)
    if primary:
        b.setProperty("kind", "primary")
    b.setCursor(Qt.PointingHandCursor)
    return b


def scrolled(inner: QWidget) -> QScrollArea:
    inner.setObjectName("ScrollContent")
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setWidget(inner)
    sa.setFrameShape(QScrollArea.NoFrame)
    return sa


class Page(QWidget):
    open_contact = Signal(int)
    new_report = Signal(object)  # Contact | None

    def __init__(self):
        super().__init__()
        self.inner = QWidget()
        self.lay = QVBoxLayout(self.inner)
        self.lay.setContentsMargins(28, 22, 28, 24)
        self.lay.setSpacing(18)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = scrolled(self.inner)
        outer.addWidget(self.scroll)

    def refresh(self) -> None:
        pass

    def _contact_table(self, t) -> None:
        t.cellDoubleClicked.connect(lambda r, _c: self._open_row(t, r))
        t.setCursor(Qt.PointingHandCursor)

    def _open_row(self, t, r: int) -> None:
        cid = t.item(r, 0).data(Qt.UserRole)
        if cid:
            self.open_contact.emit(cid)


def all_visits() -> list[tuple[data.Visit, data.Contact]]:
    out = [(v, c) for c in data.CONTACTS for v in c.visits]
    return sorted(out, key=lambda vc: vc[0].days_ago)


class Dashboard(Page):
    def __init__(self):
        super().__init__()
        first = data.USER_NAME.split()[0]
        self.lay.addLayout(page_header(f"Hello {first}", long_date(date.today()).capitalize() + " · " + data.USER_ROLE))

        kpis = QHBoxLayout()
        kpis.setSpacing(14)
        self.visits_kpi = Kpi("Visits this month", "", "+12% vs October")
        open_amount = sum(o.amount for o in data.OPPORTUNITIES)
        for k in (
            self.visits_kpi,
            Kpi("Appointments today", str(len(data.TODAY_AGENDA)), "First at 09:00"),
            Kpi("Open opportunities", str(len(data.OPPORTUNITIES)), data.euros(open_amount)),
            Kpi("Target A coverage", "68 %", "+5 pts this quarter"),
        ):
            kpis.addWidget(k)
        self.lay.addLayout(kpis)

        row = QHBoxLayout()
        row.setSpacing(14)
        agenda = Card("Today's appointments")
        rows, ids = [], []
        for hour, cid, obj in data.TODAY_AGENDA:
            c = next(x for x in data.CONTACTS if x.id == cid)
            rows.append([hour, c.name, data.account(c.account_id).name, obj])
            ids.append(cid)
        self.agenda = table(["Time", "Contact", "Account", "Objective"], rows, stretch=2, data=ids)
        self.agenda.setMinimumHeight(5 * 38 + 36)
        self._contact_table(self.agenda)
        agenda.body.addWidget(self.agenda)
        row.addWidget(agenda, 3)

        opps = Card("Opportunities due soon")
        top = sorted(data.OPPORTUNITIES, key=lambda o: o.close_in_days)[:5]
        t = table(["Opportunity", "Stage", "Amount"],
                  [[o.title, o.stage, data.euros(o.amount)] for o in top], stretch=0)
        t.setMinimumHeight(5 * 38 + 36)
        opps.body.addWidget(t)
        row.addWidget(opps, 2)
        self.lay.addLayout(row)

        recent = Card("Latest activity")
        self.recent = table(["Date", "Type", "Contact", "Account", "Objective"], [], stretch=3)
        self._contact_table(self.recent)
        recent.body.addWidget(self.recent)
        self.lay.addWidget(recent)
        self.refresh()

    def refresh(self) -> None:
        today = date.today()
        visits_month = sum(1 for v, _ in all_visits() if (v.day.year, v.day.month) == (today.year, today.month))
        self.visits_kpi.value.setText(f"{visits_month + 11} / 42")
        items = all_visits()[:6]
        fill_table(self.recent, [[data.fr_date(v.day), v.kind, c.name, data.account(c.account_id).name, v.objective] for v, c in items],
                   [c.id for _, c in items])
        self.recent.setMinimumHeight(len(items) * 38 + 36)


class ContactsPage(Page):
    def __init__(self):
        super().__init__()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter by name, specialty, city…")
        self.filter.setAccessibleName("Filter contacts")
        self.filter.setFixedWidth(280)
        self.filter.textChanged.connect(self.refresh)
        self.lay.addLayout(page_header("Contacts", f"{len(data.CONTACTS)} healthcare professionals · Paris East sector",
                                       actions=[self.filter, button("New contact", primary=True)]))
        card = Card()
        self.table = table(["Name", "Specialty", "Account", "City", "Segment", "Last visit", "Next visit"], [], stretch=2)
        self._contact_table(self.table)
        card.body.addWidget(self.table)
        self.lay.addWidget(card, 1)
        self.refresh()

    def refresh(self) -> None:
        q = self.filter.text().strip().lower()
        rows, ids = [], []
        for c in sorted(data.CONTACTS, key=lambda c: c.last):
            a = data.account(c.account_id)
            hay = f"{c.name} {c.specialty} {a.name} {a.city}".lower()
            if q and q not in hay:
                continue
            nxt = data.fr_date(date.today() + timedelta(days=c.next_visit_in)) if c.next_visit_in is not None else "—"
            rows.append([c.name, c.specialty, a.name, a.city.split(" ", 1)[1], c.segment,
                         data.fr_date(c.last_visit) if c.last_visit else "—", nxt])
            ids.append(c.id)
        fill_table(self.table, rows, ids)
        self.table.setMinimumHeight(len(rows) * 38 + 40)


class AccountsPage(Page):
    def __init__(self):
        super().__init__()
        self.lay.addLayout(page_header("Accounts", f"{len(data.ACCOUNTS)} facilities · Owner: {data.USER_NAME}",
                                       actions=[button("Export"), button("New account", primary=True)]))
        card = Card()
        rows = [[a.name, a.kind, a.address, a.city, a.segment, a.potential, str(len(data.contacts_of(a.id))), a.phone] for a in data.ACCOUNTS]
        t = table(["Company name", "Type", "Address", "City", "Segment", "Potential", "Contacts", "Switchboard"], rows, stretch=0)
        t.setMinimumHeight(len(rows) * 38 + 40)
        card.body.addWidget(t)
        self.lay.addWidget(card, 1)


class OpportunitiesPage(Page):
    def __init__(self):
        super().__init__()
        total = sum(o.amount for o in data.OPPORTUNITIES)
        weighted = sum(o.amount * o.probability // 100 for o in data.OPPORTUNITIES)
        self.lay.addLayout(page_header("Opportunities", f"{data.euros(total)} open · {data.euros(weighted)} weighted",
                                       actions=[button("New opportunity", primary=True)]))
        card = Card()
        rows = [[o.title, data.account(o.account_id).name, o.stage, data.euros(o.amount), f"{o.probability} %",
                 data.fr_date(date.today() + timedelta(days=o.close_in_days))] for o in data.OPPORTUNITIES]
        t = table(["Opportunity", "Account", "Stage", "Amount", "Probability", "Expected close"], rows, stretch=0)
        t.setMinimumHeight(len(rows) * 38 + 40)
        card.body.addWidget(t)
        self.lay.addWidget(card, 1)


class ActivitiesPage(Page):
    def __init__(self):
        super().__init__()
        new = button("New visit report", primary=True)
        new.clicked.connect(lambda: self.new_report.emit(None))
        self.lay.addLayout(page_header("Activities", "Visits and reports in your sector", actions=[new]))
        card = Card()
        self.table = table(["Date", "Type", "Contact", "Account", "Objective", "Products presented", "Author"], [], stretch=5)
        self._contact_table(self.table)
        card.body.addWidget(self.table)
        self.lay.addWidget(card, 1)
        self.refresh()

    def refresh(self) -> None:
        items = all_visits()
        fill_table(self.table, [[data.fr_date(v.day), v.kind, c.name, data.account(c.account_id).name, v.objective,
                                 ", ".join(v.products) or "—", v.author] for v, c in items], [c.id for _, c in items])
        self.table.setMinimumHeight(len(items) * 38 + 40)


class BarChart(QWidget):
    def __init__(self, values: list[tuple[str, int]], target: int):
        super().__init__()
        self.values, self.target = values, target
        self.setMinimumHeight(220)

    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        text, accent, mid = pal.windowText().color(), pal.highlight().color(), pal.mid().color()
        w, h = self.width(), self.height()
        top, bottom, left = 12, 28, 34
        peak = max(max(v for _, v in self.values), self.target) * 1.15
        p.setPen(mid)
        for i in range(5):
            y = top + (h - top - bottom) * i / 4
            p.drawLine(left, int(y), w, int(y))
            p.setPen(text)
            p.drawText(QRectF(0, y - 8, left - 6, 16), Qt.AlignRight | Qt.AlignVCenter, str(round(peak * (4 - i) / 4)))
            p.setPen(mid)
        n = len(self.values)
        slot = (w - left) / n
        for i, (lab, v) in enumerate(self.values):
            bh = (h - top - bottom) * v / peak
            x = left + i * slot + slot * 0.25
            color = QColor(accent)
            if i < n - 1:
                color.setAlpha(150)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, h - bottom - bh, slot * 0.5, bh), 3, 3)
            p.setPen(text)
            p.drawText(QRectF(left + i * slot, h - bottom + 6, slot, 18), Qt.AlignCenter, lab)
        ty = top + (h - top - bottom) * (1 - self.target / peak)
        pen = p.pen()
        pen.setColor(QColor("#d9822b"))
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.drawLine(left, int(ty), w, int(ty))


class ReportsPage(Page):
    def __init__(self):
        super().__init__()
        self.lay.addLayout(page_header("Reports", "Paris East sector activity · last 6 months", actions=[button("Export to PDF")]))
        kpis = QHBoxLayout()
        kpis.setSpacing(14)
        for k in (Kpi("Visits (6 months)", "231", "Target 240"), Kpi("Contacts seen", "58 / 71", "82% of the portfolio"),
                  Kpi("Average visit length", "17 min", "+2 min"), Kpi("Reports filed within 24 h", "91 %", "+4 pts")):
            kpis.addWidget(k)
        self.lay.addLayout(kpis)
        row = QHBoxLayout()
        row.setSpacing(14)
        chart = Card("Visits per month")
        today = date.today()
        names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        series = [(names[(today.month - 6 + i) % 12], v) for i, v in enumerate([38, 41, 29, 44, 47, 32])]
        chart.body.addWidget(BarChart(series, 40))
        row.addWidget(chart, 3)
        seg = Card("Coverage by segment")
        t = table(["Segment", "Contacts", "Seen", "Target frequency", "Coverage"],
                  [["Target A", "24", "19", "1 visit / month", "79 %"], ["Target B", "31", "26", "1 visit / 2 months", "84 %"],
                   ["Target C", "16", "13", "1 visit / quarter", "81 %"]], stretch=3)
        t.setMinimumHeight(3 * 38 + 40)
        seg.body.addWidget(t)
        seg.body.addStretch(1)
        row.addWidget(seg, 2)
        self.lay.addLayout(row)
        self.lay.addStretch(1)


class ContactRecord(Page):
    def __init__(self):
        super().__init__()
        self.contact: data.Contact | None = None

    def set_contact(self, c: data.Contact) -> None:
        self.contact = c
        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                _clear(item.layout())
        a = data.account(c.account_id)
        self.lay.addWidget(label(f"Contacts  ›  {c.name}", "Breadcrumb"))

        head = Card()
        top = QHBoxLayout()
        top.setSpacing(16)
        top.addWidget(Avatar(c.initials, 56), 0, Qt.AlignTop)
        names = QVBoxLayout()
        names.setSpacing(4)
        names.addWidget(label(c.name, "ContactName"))
        names.addWidget(label(f"{c.specialty} · {a.name}", "Muted"))
        badges = QHBoxLayout()
        badges.setSpacing(6)
        badges.addWidget(label(c.segment, "Badge"))
        badges.addWidget(label("GDPR consent up to date", "BadgeSuccess"))
        if c.next_visit_in is not None and c.next_visit_in <= 5:
            badges.addWidget(label("Visit to schedule", "BadgeWarning"))
        badges.addStretch(1)
        names.addLayout(badges)
        top.addLayout(names, 1)
        plan = button("Schedule a visit")
        new = button("New visit report", primary=True)
        new.clicked.connect(lambda: self.new_report.emit(self.contact))
        top.addWidget(plan, 0, Qt.AlignTop)
        top.addWidget(new, 0, Qt.AlignTop)
        head.body.addLayout(top)
        nxt = date.today() + timedelta(days=c.next_visit_in) if c.next_visit_in is not None else None
        head.body.addSpacing(6)
        head.body.addWidget(info_grid([
            ("Phone", c.phone), ("Email", c.email), ("Licence no.", c.rpps),
            ("Address", f"{a.address}, {a.city}"), ("Availability", c.availability), ("Account switchboard", a.phone),
            ("Last visit", data.fr_date(c.last_visit) if c.last_visit else "Never visited"),
            ("Next visit", data.fr_date(nxt) if nxt else "Not scheduled"), ("Owner", a.owner),
        ]))
        self.lay.addWidget(head)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        hist = table(["Date", "Type", "Objective", "Products presented", "Summary", "Author"],
                     [[data.fr_date(v.day), v.kind, v.objective, ", ".join(v.products) or "—", v.summary, v.author]
                      for v in sorted(c.visits, key=lambda v: v.days_ago)], stretch=4)
        hist.setMinimumHeight(max(3, len(c.visits)) * 38 + 40)
        tabs.addTab(_wrap(hist), f"Visit history ({len(c.visits)})")
        opps = [o for o in data.OPPORTUNITIES if o.account_id == a.id]
        ot = table(["Opportunity", "Stage", "Amount", "Probability"],
                   [[o.title, o.stage, data.euros(o.amount), f"{o.probability} %"] for o in opps], stretch=0)
        ot.setMinimumHeight(max(3, len(opps)) * 38 + 40)
        tabs.addTab(_wrap(ot), f"Account opportunities ({len(opps)})")
        others = [x for x in data.contacts_of(a.id) if x.id != c.id]
        ct = table(["Name", "Role", "Phone", "Email"], [[x.name, x.specialty, x.phone, x.email] for x in others], stretch=0,
                   data=[x.id for x in others])
        ct.setMinimumHeight(max(3, len(others)) * 38 + 40)
        self._contact_table(ct)
        tabs.addTab(_wrap(ct), f"Other contacts at this account ({len(others)})")
        card = Card()
        card.body.setContentsMargins(6, 4, 6, 6)
        card.body.addWidget(tabs)
        self.lay.addWidget(card)
        self.lay.addStretch(1)


def _wrap(w: QWidget) -> QWidget:
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 8, 0, 0)
    lay.addWidget(w)
    return box


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear(item.layout())


class VisitReportForm(Page):
    """« New visit report ». Nothing is kept until « Enregistrer » is pressed."""

    saved = Signal(object, object)  # Contact, Visit
    cancelled = Signal(object)  # Contact | None

    def __init__(self, icon_factory, context: data.Contact | None = None):
        super().__init__()
        self.context = context
        self.lay.setSpacing(12)
        self.lay.setContentsMargins(28, 16, 28, 16)
        self.lay.addLayout(page_header("New visit report", f"Entered by {data.USER_NAME} · {data.COMPANY}",
                                       breadcrumb="Activities  ›  New visit report"))

        # Visit details
        info = Card("Visit details")
        g = QGridLayout()
        g.setHorizontalSpacing(16)
        g.setVerticalSpacing(12)
        self.account = LookupField([a.name for a in data.ACCOUNTS], icon_factory)
        self.contact = LookupField([], icon_factory)
        self._account_changed("")
        self.visit_date = DateField(icon_factory)
        self.visit_date.set_date(date.today())
        self.visit_time = QLineEdit()
        self.visit_time.setMaxLength(5)
        self.duration = LookupField(data.DURATIONS, icon_factory)
        self.objective = LookupField(data.OBJECTIVES, icon_factory)
        g.addWidget(Field("Account", self.account, required=True), 0, 0)
        g.addWidget(Field("Contact met", self.contact, required=True), 0, 1)
        g.addWidget(Field("Visit date", self.visit_date, required=True), 0, 2)
        g.addWidget(Field("Time", self.visit_time), 0, 3)
        g.addWidget(Field("Duration", self.duration), 0, 4)

        types = QWidget()
        tl = QVBoxLayout(types)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(7)
        cap = label("Visit type", "FieldLabel")
        tl.addWidget(cap)
        radios = QHBoxLayout()
        radios.setSpacing(18)
        self.type_group = QButtonGroup(self)
        self.type_buttons: list[QRadioButton] = []
        for t in data.VISIT_TYPES:
            rb = QRadioButton(t)
            rb.setAccessibleName(t)
            self.type_group.addButton(rb)
            self.type_buttons.append(rb)
            radios.addWidget(rb)
        radios.addStretch(1)
        tl.addLayout(radios)
        g.addWidget(types, 1, 0, 1, 2)
        g.addWidget(Field("Main objective", self.objective), 1, 2, 1, 3)
        for col, st in enumerate((5, 5, 2, 1, 2)):
            g.setColumnStretch(col, st)
        info.body.addLayout(g)
        self.lay.addWidget(info)

        row = QHBoxLayout()
        row.setSpacing(14)

        report = Card("Visit notes")
        self.report = QPlainTextEdit()
        self.report.setTabChangesFocus(True)
        self.report.setMinimumHeight(128)
        self.objections = QPlainTextEdit()
        self.objections.setTabChangesFocus(True)
        self.objections.setFixedHeight(60)
        report.body.addWidget(Field("Visit report", self.report, required=True), 1)
        report.body.addWidget(Field("Doctor's needs and objections", self.objections))
        row.addWidget(report, 3)

        side = QVBoxLayout()
        side.setSpacing(14)
        prods = Card("Products presented")
        prods.body.setSpacing(8)
        self.products: list[QCheckBox] = []
        for p in data.PRODUCTS:
            cb = QCheckBox(f"{p.name} — {p.detail}")
            cb.setAccessibleName(p.name)
            self.products.append(cb)
            prods.body.addWidget(cb)
        self.docs = QLineEdit()
        prods.body.addSpacing(4)
        prods.body.addWidget(Field("Documents handed over", self.docs))
        side.addWidget(prods)

        follow = Card("Follow-up")
        self.next_step = QLineEdit()
        self.follow_up = DateField(icon_factory)
        self.reminder = QCheckBox("Add a reminder to my calendar")
        follow.body.addWidget(Field("Next step", self.next_step))
        follow.body.addLayout(hrow(Field("Follow-up date", self.follow_up), None))
        follow.body.addWidget(self.reminder)
        side.addWidget(follow)
        side.addStretch(1)
        row.addLayout(side, 2)
        self.lay.addLayout(row)

        self.error = label("", "LoginError")
        self.error.hide()
        cancel = button("Cancel")
        cancel.clicked.connect(self._cancel)
        self.save_btn = button("Save report", primary=True)
        self.save_btn.clicked.connect(self._save)
        self.lay.addLayout(hrow(self.error, None, cancel, self.save_btn))
        self.lay.addStretch(1)

        self.account.textChanged.connect(self._account_changed)
        if context:
            self.account.setText(data.account(context.account_id).name)
            self.contact.setText(context.name)

    def _account_changed(self, text: str) -> None:
        acc = next((a for a in data.ACCOUNTS if a.name.lower() == text.strip().lower()), None)
        people = data.contacts_of(acc.id) if acc else sorted(data.CONTACTS, key=lambda c: c.last)
        names = [c.name for c in people]
        self.contact.set_items(names)
        if acc and self.contact.text().strip().lower() not in {n.lower() for n in names}:
            self.contact.clear()

    def ensure_visible(self, w: QWidget) -> None:
        if self.inner.isAncestorOf(w):
            self.scroll.ensureWidgetVisible(w, 40, 40)

    def is_dirty(self) -> bool:
        texts = [self.visit_time.text(), self.duration.text(), self.objective.text(), self.report.toPlainText(),
                 self.objections.toPlainText(), self.docs.text(), self.next_step.text(), self.follow_up.text()]
        return (any(t.strip() for t in texts) or self.type_group.checkedButton() is not None
                or any(cb.isChecked() for cb in self.products))

    def confirm_discard(self) -> bool:
        if not self.is_dirty():
            return True
        box = QMessageBox(QMessageBox.Warning, "Discard report",
                          "Discard this report?", QMessageBox.NoButton, self)
        box.setInformativeText("What you entered will not be saved.")
        discard = box.addButton("Discard", QMessageBox.DestructiveRole)
        box.addButton("Keep editing", QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() is discard

    def _cancel(self) -> None:
        if self.confirm_discard():
            self.cancelled.emit(self.context)

    def _save(self) -> None:
        acc = next((a for a in data.ACCOUNTS if a.name.lower() == self.account.text().strip().lower()), None)
        people = data.contacts_of(acc.id) if acc else data.CONTACTS
        contact = next((c for c in people if c.name.lower() == self.contact.text().strip().lower()), None)
        missing = []
        if not self.account.text().strip():
            missing.append("compte")
        if contact is None:
            missing.append("contact")
        if not self.visit_date.qdate().isValid():
            missing.append("visit date")
        if not self.report.toPlainText().strip():
            missing.append("report")
        if missing:
            self.error.setText("Required fields to fill in: " + ", ".join(missing) + ".")
            self.error.show()
            return
        d = self.visit_date.qdate().toPython()
        rb = self.type_group.checkedButton()
        first_line = self.report.toPlainText().strip().splitlines()[0]
        visit = data.Visit((date.today() - d).days, rb.text() if rb else "In person", self.objective.text() or "—",
                           [p.name for p, cb in zip(data.PRODUCTS, self.products) if cb.isChecked()],
                           first_line[:160])
        contact.visits.append(visit)
        self.saved.emit(contact, visit)


def now_hhmm() -> str:
    return datetime.now().strftime("%H:%M")
