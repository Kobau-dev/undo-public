"""Colours, style sheet and vector icons (light / dark)."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap


@dataclass(frozen=True)
class Colors:
    dark: bool
    window: str
    sidebar: str
    surface: str
    raised: str
    border: str
    border_strong: str
    text: str
    muted: str
    faint: str
    accent: str
    accent_hover: str
    accent_soft: str
    accent_text: str
    input: str
    danger: str
    danger_soft: str
    success: str
    success_soft: str
    warning: str
    warning_soft: str


LIGHT = Colors(
    dark=False, window="#f3f5f8", sidebar="#eceff4", surface="#ffffff", raised="#f8f9fb", border="#e1e5eb",
    border_strong="#c9d0da", text="#1b2330", muted="#5f6b7a", faint="#8a95a3", accent="#1a5fb4", accent_hover="#164f97",
    accent_soft="#e3edfa", accent_text="#ffffff", input="#ffffff", danger="#c0392b", danger_soft="#fbe9e7",
    success="#1e7f4f", success_soft="#e3f4ea", warning="#a15c00", warning_soft="#fdf0dc",
)
DARK = Colors(
    dark=True, window="#1c1e22", sidebar="#24272c", surface="#26292e", raised="#2c3036", border="#363a41",
    border_strong="#4a4f58", text="#e8eaed", muted="#a2a9b4", faint="#7c8490", accent="#4f8fe6", accent_hover="#6aa2ee",
    accent_soft="#263a55", accent_text="#ffffff", input="#1f2226", danger="#ef6b5b", danger_soft="#45282a",
    success="#4cc38a", success_soft="#1f3a2e", warning="#f0b35a", warning_soft="#3d3121",
)


def palette(c: Colors) -> QPalette:
    p = QPalette()
    roles = {
        QPalette.Window: c.window, QPalette.WindowText: c.text, QPalette.Base: c.input, QPalette.AlternateBase: c.raised,
        QPalette.Text: c.text, QPalette.Button: c.surface, QPalette.ButtonText: c.text, QPalette.Highlight: c.accent,
        QPalette.HighlightedText: c.accent_text, QPalette.ToolTipBase: c.surface, QPalette.ToolTipText: c.text,
        QPalette.PlaceholderText: c.faint, QPalette.Mid: c.border, QPalette.Midlight: c.border, QPalette.Light: c.surface,
        QPalette.Dark: c.border_strong, QPalette.Shadow: c.border_strong, QPalette.Link: c.accent,
    }
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(c.faint))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(c.faint))
    return p


_ASSETS: Path | None = None


def _assets(c: Colors) -> dict[str, str]:
    """Chevron / check / dot images for the style sheet (QSS can only draw these from files)."""
    global _ASSETS
    if _ASSETS is None:
        _ASSETS = Path(tempfile.mkdtemp(prefix="sillage-crm-"))
    tag = "dark" if c.dark else "light"
    out = {}
    for name, color in (("chevron", c.muted), ("check", c.accent_text), ("dot", c.accent_text)):
        path = _ASSETS / f"{name}-{tag}.png"
        if not path.exists():
            pm = QPixmap(32, 32)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            if name == "dot":
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(color))
                p.drawEllipse(QRectF(10, 10, 12, 12))
            else:
                p.setPen(_pen(QColor(color), 3.6 if name == "check" else 3.0))
                pts = ((8, 16.5), (13.5, 22), (24, 10)) if name == "check" else ((9, 12.5), (16, 19.5), (23, 12.5))
                path_ = QPainterPath(QPointF(*pts[0]))
                for pt in pts[1:]:
                    path_.lineTo(QPointF(*pt))
                p.drawPath(path_)
            p.end()
            pm.save(str(path))
        out[name] = path.as_posix()
    return out


def stylesheet(c: Colors) -> str:
    a = _assets(c)
    return f"""
QMainWindow, #Central {{ background: {c.window}; }}
QWidget {{ color: {c.text}; }}
QToolTip {{ background: {c.surface}; color: {c.text}; border: 1px solid {c.border}; padding: 4px 6px; }}

#TopBar {{ background: {c.surface}; border-bottom: 1px solid {c.border}; }}
#Brand {{ font-size: 15px; font-weight: 700; color: {c.text}; }}
#Tenant {{ color: {c.muted}; font-size: 12px; }}
#UserName {{ font-weight: 600; }}
#UserRole, #SyncLabel {{ color: {c.muted}; font-size: 11px; }}
#Avatar {{ background: {c.accent_soft}; color: {c.accent}; border-radius: 16px; font-weight: 700; }}
#AvatarLarge {{ background: {c.accent_soft}; color: {c.accent}; border-radius: 28px; font-weight: 700; font-size: 20px; }}
#GlobalSearch {{ background: {c.raised}; border: 1px solid {c.border}; border-radius: 7px; padding: 5px 10px; min-width: 300px; }}
#GlobalSearch:focus {{ border-color: {c.accent}; background: {c.input}; }}

#Sidebar {{ background: {c.sidebar}; border: none; border-right: 1px solid {c.border}; outline: 0; padding: 10px 8px; }}
#Sidebar::item {{ padding: 8px 10px; margin: 1px 0; border-radius: 7px; color: {c.text}; }}
#Sidebar::item:hover {{ background: {c.raised}; }}
#Sidebar::item:selected {{ background: {c.accent_soft}; color: {c.accent}; font-weight: 600; }}
#SidebarFooter {{ background: {c.sidebar}; border-right: 1px solid {c.border}; }}
#SidebarFooter QLabel {{ color: {c.muted}; font-size: 11px; }}

#PageTitle {{ font-size: 21px; font-weight: 700; }}
#PageSubtitle, #Muted {{ color: {c.muted}; }}
#Breadcrumb {{ color: {c.muted}; font-size: 12px; }}
#SectionTitle {{ font-size: 14px; font-weight: 700; }}
#FieldLabel {{ color: {c.muted}; font-size: 12px; font-weight: 600; }}
#Required {{ color: {c.danger}; }}
#Value {{ font-size: 13px; }}
#KpiValue {{ font-size: 24px; font-weight: 700; }}
#KpiLabel {{ color: {c.muted}; font-size: 12px; }}
#KpiDelta {{ color: {c.success}; font-size: 12px; font-weight: 600; }}
#ContactName {{ font-size: 22px; font-weight: 700; }}

#Card {{ background: {c.surface}; border: 1px solid {c.border}; border-radius: 10px; }}
#Badge {{ background: {c.accent_soft}; color: {c.accent}; border-radius: 9px; padding: 2px 9px; font-size: 11px; font-weight: 700; }}
#BadgeSuccess {{ background: {c.success_soft}; color: {c.success}; border-radius: 9px; padding: 2px 9px; font-size: 11px; font-weight: 700; }}
#BadgeWarning {{ background: {c.warning_soft}; color: {c.warning}; border-radius: 9px; padding: 2px 9px; font-size: 11px; font-weight: 700; }}
#Banner {{ background: {c.success_soft}; color: {c.success}; border-radius: 8px; padding: 8px 12px; font-weight: 600; }}

QLineEdit, QPlainTextEdit, QComboBox {{
    background: {c.input}; border: 1px solid {c.border_strong}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {c.accent}; selection-color: {c.accent_text};
}}
QPlainTextEdit {{ padding: 6px 8px; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 1px solid {c.accent}; }}
QLineEdit[invalid="true"] {{ border: 1px solid {c.danger}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url({a["chevron"]}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {c.surface}; border: 1px solid {c.border}; selection-background-color: {c.accent_soft}; selection-color: {c.text}; outline: 0; }}
QListView#qt_completer, QCompleter QAbstractItemView, QAbstractItemView[completer="true"] {{ background: {c.surface}; border: 1px solid {c.border_strong};
    padding: 4px; selection-background-color: {c.accent_soft}; selection-color: {c.text}; outline: 0; }}
QAbstractItemView[completer="true"]::item {{ padding: 6px 8px; border-radius: 5px; }}
QComboBox QLineEdit {{ border: none; padding: 0; background: transparent; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; border: 1px solid {c.border_strong}; background: {c.input}; }}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {c.accent}; }}
QCheckBox::indicator:checked {{ background: {c.accent}; border-color: {c.accent}; image: url({a["check"]}); }}
QRadioButton::indicator:checked {{ background: {c.accent}; border-color: {c.accent}; image: url({a["dot"]}); }}

QPushButton {{ background: {c.surface}; border: 1px solid {c.border_strong}; border-radius: 6px; padding: 6px 14px; font-weight: 600; }}
QPushButton:hover {{ background: {c.raised}; }}
QPushButton:pressed {{ background: {c.border}; }}
QPushButton[kind="primary"] {{ background: {c.accent}; border: 1px solid {c.accent}; color: {c.accent_text}; }}
QPushButton[kind="primary"]:hover {{ background: {c.accent_hover}; border-color: {c.accent_hover}; }}
QPushButton[kind="primary"]:disabled {{ background: {c.border_strong}; border-color: {c.border_strong}; }}
QPushButton[kind="link"] {{ background: transparent; border: none; color: {c.accent}; padding: 2px 0; text-align: left; }}
QPushButton[kind="link"]:hover {{ text-decoration: underline; }}

QTableWidget {{ background: {c.surface}; alternate-background-color: {c.raised}; border: none; gridline-color: transparent;
    selection-background-color: {c.accent_soft}; selection-color: {c.text}; outline: 0; }}
QTableWidget::item {{ padding: 6px 8px; border-bottom: 1px solid {c.border}; }}
QHeaderView::section {{ background: {c.surface}; color: {c.muted}; border: none; border-bottom: 1px solid {c.border_strong};
    padding: 7px 8px; font-size: 12px; font-weight: 600; }}
QTabWidget::pane {{ border: none; border-top: 1px solid {c.border}; }}
QTabBar::tab {{ background: transparent; padding: 8px 14px; color: {c.muted}; border-bottom: 2px solid transparent; font-weight: 600; }}
QTabBar::tab:selected {{ color: {c.accent}; border-bottom: 2px solid {c.accent}; }}
QScrollArea {{ border: none; background: transparent; }}
#ScrollContent {{ background: {c.window}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c.border_strong}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QCalendarWidget QWidget {{ alternate-background-color: {c.raised}; }}
QStatusBar {{ background: {c.surface}; border-top: 1px solid {c.border}; color: {c.muted}; font-size: 11px; }}

#LoginSheet {{ background: {c.surface}; }}
#LoginTitle {{ font-size: 17px; font-weight: 700; }}
#LoginError {{ color: {c.danger}; font-size: 12px; }}
#ExpiredNotice {{ background: {c.warning_soft}; color: {c.warning}; border-radius: 8px; padding: 9px 12px; }}
#Toast {{ background: {c.text}; color: {c.window}; border-radius: 8px; padding: 9px 16px; font-weight: 600; }}
"""


def _pen(color: QColor, w: float = 1.6) -> QPen:
    pen = QPen(color, w)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def icon(name: str, color: str, size: int = 18) -> QIcon:
    """Small line icons drawn at runtime (no image assets to ship)."""
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    col = QColor(color)
    p.setPen(_pen(col))
    p.setBrush(Qt.NoBrush)
    if name == "dashboard":
        for x, y, w, h in ((2.5, 2.5, 5.5, 7), (10, 2.5, 5.5, 4), (2.5, 11.5, 5.5, 4), (10, 8.5, 5.5, 7)):
            p.drawRoundedRect(QRectF(x, y, w, h), 1.5, 1.5)
    elif name == "contacts":
        p.drawEllipse(QRectF(6, 2.5, 6, 6))
        path = QPainterPath(QPointF(3, 15.5))
        path.cubicTo(3.5, 10.5, 14.5, 10.5, 15, 15.5)
        p.drawPath(path)
    elif name == "accounts":
        p.drawRect(QRectF(3, 3, 8, 12.5))
        p.drawRect(QRectF(11, 7.5, 4.5, 8))
        for y in (6, 9, 12):
            p.drawLine(QPointF(5.5, y), QPointF(8.5, y))
    elif name == "opportunities":
        p.drawEllipse(QRectF(2.5, 2.5, 13, 13))
        p.drawEllipse(QRectF(6, 6, 6, 6))
        p.setBrush(col)
        p.drawEllipse(QRectF(8.2, 8.2, 1.6, 1.6))
    elif name == "activities":
        p.drawRoundedRect(QRectF(2.5, 3.5, 13, 12), 2, 2)
        p.drawLine(QPointF(2.5, 7.5), QPointF(15.5, 7.5))
        p.drawLine(QPointF(6, 2), QPointF(6, 5))
        p.drawLine(QPointF(12, 2), QPointF(12, 5))
    elif name == "reports":
        p.drawLine(QPointF(3, 15.5), QPointF(15.5, 15.5))
        for x, top in ((4.5, 9), (8.5, 4), (12.5, 7)):
            p.drawRoundedRect(QRectF(x, top, 2.5, 15.5 - top - 1.5), 0.8, 0.8)
    elif name == "calendar":
        p.drawRoundedRect(QRectF(2.5, 3.5, 13, 12), 2, 2)
        p.drawLine(QPointF(2.5, 7.5), QPointF(15.5, 7.5))
        p.setBrush(col)
        for x in (5.5, 8.5, 11.5):
            p.drawEllipse(QRectF(x, 10, 1.4, 1.4))
    elif name == "chevron":
        path = QPainterPath(QPointF(5, 7.5))
        path.lineTo(QPointF(9, 11.5))
        path.lineTo(QPointF(13, 7.5))
        p.drawPath(path)
    elif name == "search":
        p.drawEllipse(QRectF(3, 3, 9, 9))
        p.drawLine(QPointF(10.8, 10.8), QPointF(15, 15))
    elif name == "bell":
        path = QPainterPath(QPointF(4, 13))
        path.cubicTo(5.5, 11, 4.5, 4, 9, 4)
        path.cubicTo(13.5, 4, 12.5, 11, 14, 13)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(7.5, 15.3), QPointF(10.5, 15.3))
    elif name == "sync":
        p.drawArc(QRectF(3, 3, 12, 12), 30 * 16, 150 * 16)
        p.drawArc(QRectF(3, 3, 12, 12), 210 * 16, 150 * 16)
    elif name == "lock":
        p.drawRoundedRect(QRectF(4, 8, 10, 7.5), 1.5, 1.5)
        p.drawArc(QRectF(6, 3, 6, 9), 0, 180 * 16)
    p.end()
    return QIcon(pm)


def app_icon(size: int = 256) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#1a5fb4"))
    m = size * 0.08
    p.drawRoundedRect(QRectF(m, m, size - 2 * m, size - 2 * m), size * 0.22, size * 0.22)
    p.setPen(_pen(QColor("white"), size * 0.075))
    for i, y in enumerate((0.38, 0.52, 0.66)):
        path = QPainterPath(QPointF(size * 0.24, size * y))
        path.cubicTo(size * 0.40, size * (y - 0.09), size * 0.56, size * (y + 0.09), size * 0.76, size * y)
        p.setOpacity(1.0 - i * 0.25)
        p.drawPath(path)
    p.end()
    return QIcon(pm)
