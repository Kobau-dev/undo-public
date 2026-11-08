"""Main window, navigation, menus, session expiry and launch options."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QFontDatabase, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from . import data, theme
from .pages import (
    AccountsPage, ActivitiesPage, ContactRecord, ContactsPage, Dashboard, OpportunitiesPage, Page, ReportsPage,
    VisitReportForm,
)
from .session import LoginSheet, SessionManager
from .widgets import Avatar, DateField, LookupField, Toast, label

NAV = [
    ("dashboard", "Dashboard", "dashboard"),
    ("contacts", "Contacts", "contacts"),
    ("accounts", "Accounts", "accounts"),
    ("opportunities", "Opportunities", "opportunities"),
    ("activities", "Activities", "activities"),
    ("reports", "Reports", "reports"),
]


class MainWindow(QMainWindow):
    def __init__(self, session: SessionManager, theme_mode: str = "auto"):
        super().__init__()
        self.session = session
        self.theme_mode = theme_mode
        self.colors = theme.LIGHT
        self.setWindowTitle(data.APP_NAME)
        self.setMinimumSize(QSize(1100, 720))

        central = QWidget()
        central.setObjectName("Central")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._top_bar())

        body = QHBoxLayout()
        body.setSpacing(0)
        side = QVBoxLayout()
        side.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("Sidebar")
        self.nav.setAccessibleName("Navigation")
        self.nav.setFixedWidth(220)
        self.nav.setIconSize(QSize(18, 18))
        self.nav.setFocusPolicy(Qt.NoFocus)
        for key, text, _ic in NAV:
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, key)
            it.setSizeHint(QSize(200, 38))
            self.nav.addItem(it)
        self.nav.currentRowChanged.connect(self._nav_changed)
        side.addWidget(self.nav, 1)
        foot = QFrame()
        foot.setObjectName("SidebarFooter")
        foot.setFixedWidth(220)
        fl = QVBoxLayout(foot)
        fl.setContentsMargins(18, 10, 12, 14)
        fl.addWidget(QLabel(f"{data.COMPANY}\nParis East sector · v4.12.2"))
        side.addWidget(foot)
        body.addLayout(side)

        self.stack = QStackedWidget()
        self.pages: dict[str, Page] = {
            "dashboard": Dashboard(), "contacts": ContactsPage(), "accounts": AccountsPage(),
            "opportunities": OpportunitiesPage(), "activities": ActivitiesPage(), "reports": ReportsPage(),
        }
        self.record = ContactRecord()
        self.pages["fiche"] = self.record
        for p in self.pages.values():
            self.stack.addWidget(p)
            p.open_contact.connect(self.show_contact)
            p.new_report.connect(self.new_report)
        self.form: VisitReportForm | None = None
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        self.setCentralWidget(central)

        self.statusBar().addWidget(QLabel(f"Signed in: {data.USER_LOGIN}"))
        self.sync_label = QLabel()
        self.statusBar().addPermanentWidget(self.sync_label)
        self._mark_synced()
        self.toast = Toast(self)
        self._menus()

        for seq in ("Meta+Shift+E", "Ctrl+Shift+E"):
            QShortcut(QKeySequence(seq), self, activated=self.session.expire, context=Qt.ApplicationShortcut)
        self.session.expired.connect(self._on_expired)
        QApplication.instance().focusChanged.connect(self._focus_changed)
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda _s: self.apply_theme())
        self.apply_theme()
        self.nav.setCurrentRow(0)

    # ---- chrome -------------------------------------------------------------------------------------------------
    def _top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(58)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 0, 18, 0)
        lay.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(theme.app_icon().pixmap(30, 30))
        lay.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addStretch(1)
        names.addWidget(label(data.APP_NAME, "Brand"))
        names.addWidget(label(data.COMPANY, "Tenant"))
        names.addStretch(1)
        lay.addLayout(names)
        lay.addSpacing(60)
        self.search = QLineEdit()
        self.search.setObjectName("GlobalSearch")
        self.search.setPlaceholderText("Search for a contact or an account…")
        self.search.setAccessibleName("Global search")
        self.search_action = self.search.addAction(theme.icon("search", "#8a95a3"), QLineEdit.LeadingPosition)
        self.search.returnPressed.connect(self._search)
        lay.addWidget(self.search, 1)
        lay.addStretch(1)
        self.sync_btn = QToolButton()
        self.sync_btn.setToolTip("Sync")
        self.sync_btn.setAccessibleName("Sync")
        self.sync_btn.setAutoRaise(True)
        self.sync_btn.clicked.connect(self._sync)
        self.bell = QToolButton()
        self.bell.setToolTip("Notifications")
        self.bell.setAccessibleName("Notifications")
        self.bell.setAutoRaise(True)
        lay.addWidget(self.sync_btn)
        lay.addWidget(self.bell)
        lay.addSpacing(6)
        who = QVBoxLayout()
        who.setSpacing(0)
        who.addStretch(1)
        who.addWidget(label(data.USER_NAME, "UserName"), 0, Qt.AlignRight)
        who.addWidget(label(data.USER_ROLE, "UserRole"), 0, Qt.AlignRight)
        who.addStretch(1)
        lay.addLayout(who)
        lay.addWidget(Avatar("".join(w[0] for w in data.USER_NAME.split())))
        return bar

    def _menus(self) -> None:
        mb = self.menuBar()
        f = mb.addMenu("File")
        a = QAction("New visit report", self, shortcut=QKeySequence.New)
        a.triggered.connect(lambda: self.new_report(self.record.contact if self.stack.currentWidget() is self.record else None))
        f.addAction(a)
        s = QAction("Sync now", self, shortcut=QKeySequence("Ctrl+R"))
        s.triggered.connect(self._sync)
        f.addAction(s)
        f.addSeparator()
        close = QAction("Close window", self, shortcut=QKeySequence.Close)
        close.triggered.connect(self.close)
        f.addAction(close)
        q = QAction("Quit Sillage CRM", self, shortcut=QKeySequence.Quit, menuRole=QAction.QuitRole)
        q.triggered.connect(QApplication.instance().quit)
        f.addAction(q)
        v = mb.addMenu("View")
        for i, (key, text, _ic) in enumerate(NAV):
            act = QAction(text, self, shortcut=QKeySequence(f"Ctrl+{i + 1}"))
            act.triggered.connect(lambda _=False, k=key: self.go(k))
            v.addAction(act)
        h = mb.addMenu("Help")
        h.addAction("Sillage Help Center")
        about = QAction("About Sillage CRM", self, menuRole=QAction.AboutRole)
        about.triggered.connect(lambda: QMessageBox.about(
            self, "About Sillage CRM",
            f"<b>{data.APP_NAME}</b> 4.12.2<br>Healthcare Edition — {data.COMPANY}<br><br>© 2026 Sillage Software SAS"))
        h.addAction(about)

    def apply_theme(self) -> None:
        mode = self.theme_mode
        if mode == "auto":
            hints = QGuiApplication.styleHints()
            dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark
        else:
            dark = mode == "dark"
        c = theme.DARK if dark else theme.LIGHT
        self.colors = c
        app = QApplication.instance()
        app.setPalette(theme.palette(c))
        app.setStyleSheet(theme.stylesheet(c))
        for i, (_k, _t, ic) in enumerate(NAV):
            self.nav.item(i).setIcon(theme.icon(ic, c.muted))
        self.sync_btn.setIcon(theme.icon("sync", c.muted))
        self.bell.setIcon(theme.icon("bell", c.muted))
        self.search_action.setIcon(theme.icon("search", c.faint))
        if self.form:
            for f in self.form.findChildren(DateField):
                f.set_icon(theme.icon("calendar", c.muted))
            for f in self.form.findChildren(LookupField):
                f.set_icon(theme.icon("chevron", c.muted))

    def icon_factory(self, name: str):
        return theme.icon(name, self.colors.muted)

    # ---- navigation ---------------------------------------------------------------------------------------------
    def _nav_changed(self, row: int) -> None:
        if row < 0:
            return
        key = NAV[row][0]
        page = self.pages[key]
        page.refresh()
        self.stack.setCurrentWidget(page)
        self.setWindowTitle(f"{NAV[row][1]} — {data.APP_NAME}")

    def go(self, key: str) -> None:
        row = next(i for i, n in enumerate(NAV) if n[0] == key)
        if self.nav.currentRow() == row:
            self._nav_changed(row)
        self.nav.setCurrentRow(row)

    def _select_nav(self, key: str) -> None:
        self.nav.blockSignals(True)
        self.nav.setCurrentRow(next(i for i, n in enumerate(NAV) if n[0] == key))
        self.nav.blockSignals(False)

    def show_contact(self, contact_id: int) -> None:
        c = next(x for x in data.CONTACTS if x.id == contact_id)
        self.record.set_contact(c)
        self.stack.setCurrentWidget(self.record)
        self._select_nav("contacts")
        self.setWindowTitle(f"{c.name} — {data.APP_NAME}")

    def new_report(self, contact: data.Contact | None = None) -> None:
        if self.form is not None and not self.form.confirm_discard():
            self.stack.setCurrentWidget(self.form)
            self._select_nav("activities")
            return
        self._replace_form(contact)
        self.stack.setCurrentWidget(self.form)
        self._select_nav("activities")
        self.setWindowTitle(f"New visit report — {data.APP_NAME}")
        self.form.report.setFocus() if contact else self.form.account.setFocus()

    def _drop_form(self) -> None:
        if self.form is not None:
            self.stack.removeWidget(self.form)
            self.form.deleteLater()
            self.form = None

    def _replace_form(self, contact: data.Contact | None) -> None:
        self._drop_form()
        self.form = VisitReportForm(self.icon_factory, contact)
        self.form.saved.connect(self._report_saved)
        self.form.cancelled.connect(self._report_cancelled)
        self.stack.addWidget(self.form)

    def _report_saved(self, contact: data.Contact, _visit) -> None:
        self.show_contact(contact.id)
        self._drop_form()
        self._mark_synced()
        self.toast.show_message("Report saved and synced")

    def _report_cancelled(self, contact: data.Contact | None) -> None:
        self._drop_form()
        if contact:
            self.show_contact(contact.id)
        else:
            self.go("activities")

    def _search(self) -> None:
        c = data.find_contact(self.search.text())
        if c:
            self.search.clear()
            self.show_contact(c.id)
        else:
            self.toast.show_message("No results")

    def _focus_changed(self, _old, new) -> None:
        if new is not None and self.form is not None:
            self.form.ensure_visible(new)

    def _mark_synced(self) -> None:
        self.sync_label.setText(f"Synced at {datetime.now():%H:%M}")

    def _sync(self) -> None:
        self.sync_label.setText("Syncing…")
        QTimer.singleShot(900, self._mark_synced)

    # ---- session ------------------------------------------------------------------------------------------------
    def _on_expired(self) -> None:
        app = QApplication.instance()
        while (w := app.activePopupWidget()) is not None:
            w.close()
        for w in app.topLevelWidgets():
            if isinstance(w, QMessageBox) and w.isVisible():
                w.reject()
        on_form = self.form is not None and self.stack.currentWidget() is self.form
        if self.form is not None:
            context = self.form.context
            self._replace_form(context)
            if on_form:
                self.stack.setCurrentWidget(self.form)
        self.sync_label.setText("Signed out")
        sheet = LoginSheet(self, self.session.minutes_label(), theme.app_icon())
        sheet.accepted.connect(self._relogged)
        sheet.rejected.connect(app.quit)
        sheet.open()
        self._sheet = sheet

    def _relogged(self) -> None:
        self._mark_synced()
        self.session.start()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m demo.crm_app", description="Sillage CRM (desktop app)")
    p.add_argument("--session-timeout", type=float, default=_env_float("SILLAGE_SESSION_TIMEOUT", 300),
                   help="seconds of inactivity before expiry (0 = never; default 300, or $SILLAGE_SESSION_TIMEOUT)")
    p.add_argument("--session-absolute", action="store_true", default=os.environ.get("SILLAGE_SESSION_ABSOLUTE") == "1",
                   help="count the time from sign-in, even if the user is typing")
    p.add_argument("--page", choices=[k for k, _t, _i in NAV], help="screen shown at launch")
    p.add_argument("--contact", help="open a contact's record (partial name or id, e.g. \"marchand\")")
    p.add_argument("--new-report", action="store_true", help="open \"New visit report\" directly")
    p.add_argument("--theme", choices=["auto", "light", "dark"], default="auto")
    p.add_argument("--size", default="1360x860", help="window size, e.g. 1440x900")
    return p.parse_args(argv)


def _rename_process_on_macos() -> None:
    """Menu bar and Dock show « Sillage CRM » instead of « Python »."""
    if sys.platform != "darwin":
        return
    try:
        from Foundation import NSBundle

        info = NSBundle.mainBundle().localizedInfoDictionary() or NSBundle.mainBundle().infoDictionary()
        if info is not None:
            info["CFBundleName"] = data.APP_NAME
    except Exception:
        pass


def build(argv: list[str] | None = None) -> tuple[QApplication, MainWindow, argparse.Namespace]:
    args = parse_args(argv)
    _rename_process_on_macos()
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(data.APP_NAME)
    app.setApplicationDisplayName(data.APP_NAME)
    app.setOrganizationName("Sillage Software")
    app.setWindowIcon(theme.app_icon())
    if sys.platform != "darwin":
        app.setStyle("Fusion")
        fams = set(QFontDatabase.families())
        for fam in ("Inter", "Noto Sans", "DejaVu Sans"):
            if fam in fams:
                app.setFont(QFont(fam, 10))
                break
    session = SessionManager(args.session_timeout, args.session_absolute)
    app.installEventFilter(session)
    win = MainWindow(session, args.theme)
    try:
        w, h = (int(x) for x in args.size.lower().split("x"))
        win.resize(w, h)
    except ValueError:
        win.resize(1360, 860)
    contact = data.find_contact(args.contact) if args.contact else None
    if args.contact and contact is None:
        print(f"contact not found: {args.contact}", file=sys.stderr)
    if args.page:
        win.go(args.page)
    if contact:
        win.show_contact(contact.id)
    if args.new_report:
        win.new_report(contact)
    win.stack.setFocus()
    session.start()
    return app, win, args


def main(argv: list[str] | None = None) -> int:
    app, win, _args = build(argv)
    win.show()
    win.raise_()
    return app.exec()
