"""Session expiry: inactivity timer and sign-in sheet."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from . import data
from .widgets import Field


class SessionManager(QObject):
    """Expires after `timeout` seconds without keyboard/mouse input (or since login when `absolute`)."""

    expired = Signal()
    _ACTIVITY = {QEvent.KeyPress, QEvent.MouseButtonPress, QEvent.Wheel}

    def __init__(self, timeout: float, absolute: bool = False, parent: QObject | None = None):
        super().__init__(parent)
        self.timeout = timeout
        self.absolute = absolute
        self.active = False
        self._timer = QTimer(self, singleShot=True, timeout=self.expire)

    def start(self) -> None:
        self.active = True
        if self.timeout > 0:
            self._timer.start(int(self.timeout * 1000))

    def expire(self) -> None:
        if not self.active:
            return
        self.active = False
        self._timer.stop()
        self.expired.emit()

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802
        if self.active and not self.absolute and self.timeout > 0 and ev.type() in self._ACTIVITY:
            self._timer.start(int(self.timeout * 1000))
        return False

    def minutes_label(self) -> str:
        m = max(1, round(self.timeout / 60)) if self.timeout > 0 else 15
        return f"{m} minute" + ("s" if m > 1 else "")


class LoginSheet(QDialog):
    def __init__(self, parent: QWidget, minutes: str, app_icon):
        super().__init__(parent, Qt.Sheet)
        self.setObjectName("LoginSheet")
        self.setWindowTitle("Session expired")
        self.setWindowModality(Qt.WindowModal)
        self.setFixedWidth(440)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 26, 28, 22)
        lay.setSpacing(14)

        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(app_icon.pixmap(44, 44))
        head.addWidget(logo, 0, Qt.AlignTop)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        title = QLabel("Your session has expired")
        title.setObjectName("LoginTitle")
        sub = QLabel("Please sign in again to continue.")
        sub.setObjectName("Muted")
        titles.addWidget(title)
        titles.addWidget(sub)
        head.addLayout(titles, 1)
        head.setSpacing(14)
        lay.addLayout(head)

        notice = QLabel(f"For security reasons, you were signed out after {minutes} of inactivity. "
                        "Unsaved changes have been lost.")
        notice.setObjectName("ExpiredNotice")
        notice.setWordWrap(True)
        lay.addWidget(notice)

        self.login = QLineEdit(data.USER_LOGIN)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        lay.addWidget(Field("Username", self.login))
        lay.addWidget(Field("Password", self.password))

        self.error = QLabel("")
        self.error.setObjectName("LoginError")
        self.error.hide()
        lay.addWidget(self.error)

        forgot = QPushButton("Forgot password?")
        forgot.setProperty("kind", "link")
        forgot.setCursor(Qt.PointingHandCursor)
        lay.addWidget(forgot, 0, Qt.AlignLeft)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.quit_btn = QPushButton("Quit")
        self.quit_btn.clicked.connect(self.reject)
        self.ok_btn = QPushButton("Sign in")
        self.ok_btn.setProperty("kind", "primary")
        self.ok_btn.setDefault(True)
        self.ok_btn.clicked.connect(self._submit)
        buttons.addWidget(self.quit_btn)
        buttons.addWidget(self.ok_btn)
        lay.addLayout(buttons)
        self.password.setFocus()

    def _submit(self) -> None:
        if not self.login.text().strip() or not self.password.text():
            self.error.setText("Enter your username and password.")
            self.error.show()
            return
        self.error.hide()
        self.ok_btn.setEnabled(False)
        self.ok_btn.setText("Signing in…")
        QTimer.singleShot(700, self.accept)

    def keyPressEvent(self, ev) -> None:  # noqa: N802
        if ev.key() == Qt.Key_Escape:  # no way around the sign-in
            return
        super().keyPressEvent(ev)
