# timeTracker_ui.py

from __future__ import annotations

import os
import subprocess
import sys

import nuke

import timeTracker
import settings
import settings_ui

try:
    from PySide2 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide6 import QtWidgets, QtCore, QtGui

_window = None

# =========================
# Header banner
# =========================
HEADER_BANNER_FILE = "timeTracker.png"


def _here_dir() -> str:
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return os.getcwd()


def _banner_path() -> str:
    return os.path.join(_here_dir(), HEADER_BANNER_FILE)



_QSS = """
QDialog {
    background: #1f1f1f;
    color: #e8e8e8;
    font-size: 12px;
}
QLabel#Title {
    font-size: 16px;
    font-weight: 700;
    color: #fbbf24; /* yellow */
}
QLabel#TimeMain {
    font-size: 22px;
    font-weight: 700;
    font-family: Consolas, Menlo, Monaco, "Courier New", monospace;
}
QLabel#TimeSub {
    font-size: 16px;
    font-weight: 600;
    font-family: Consolas, Menlo, Monaco, "Courier New", monospace;
    color: #d6d6d6;
}
QLabel#Hint { color: #a8a8a8; }
QLabel#HeaderBanner { background: transparent; }
QLabel#Badge {
    padding: 3px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 700;
}
QPushButton {
    padding: 7px 10px;
    border-radius: 8px;
    background: #2a2a2a;
}
QPushButton:hover { background: #333333; }
QPushButton:pressed { background: #262626; }
QFrame#Card {
    background: #262626;
    border-radius: 12px;
}
"""


def _open_folder(folder: str):
    try:
        if os.name == "nt":
            os.startfile(folder)  # noqa
        elif sys.platform == "darwin":
            subprocess.check_call(["open", folder])
        else:
            subprocess.check_call(["xdg-open", folder])
    except Exception:
        nuke.message(folder)


def _make_badge(text: str, bg: str, fg: str = "#111111"):
    lbl = QtWidgets.QLabel(text)
    lbl.setObjectName("Badge")
    lbl.setStyleSheet(f"QLabel#Badge {{ background: {bg}; color: {fg}; }}")
    return lbl


class ClickableFooter(QtWidgets.QLabel):
    clicked = QtCore.Signal() if hasattr(QtCore, "Signal") else QtCore.pyqtSignal()  # type: ignore

    def mousePressEvent(self, event):
        try:
            self.clicked.emit()
        except Exception:
            pass
        return super(ClickableFooter, self).mousePressEvent(event)


class TimeTrackerWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(TimeTrackerWindow, self).__init__(parent)

        try:
            import settings
            st = settings.load_settings()
            try:
                st = settings.load_settings()
                flags = self.windowFlags()
                if st.get("always_on_top", False):
                    flags |= QtCore.Qt.WindowStaysOnTopHint
                else:
                    flags &= ~QtCore.Qt.WindowStaysOnTopHint
                self.setWindowFlags(flags)
            except Exception:
                pass
        except Exception:
            pass

 
        self.setWindowTitle("TimeTracker")
        self.setMinimumWidth(560)
        self.setStyleSheet(_QSS)

        self._footer_clicks = 0


        # ---------- Header banner ----------
        self._banner_pix = None
        self.bannerLabel = QtWidgets.QLabel()
        self.bannerLabel.setObjectName("HeaderBanner")
        self.bannerLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.bannerLabel.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.bannerLabel.setFixedHeight(0)
        self._load_banner()

        # Top: Shot
        self.title = QtWidgets.QLabel("Shot: —")
        self.title.setObjectName("Title")

        # Badges row
        self.badgeWork = _make_badge("WORK", "#34d399")
        self.badgeIdle = _make_badge("IDLE", "#fbbf24")
        self.badgeRender = _make_badge("RENDERING", "#60a5fa")
        self.badgeBg = _make_badge("BACKGROUND", "#9ca3af")

        self.badgeRow = QtWidgets.QHBoxLayout()
        self.badgeRow.setSpacing(8)
        self.badgeRow.addWidget(self.badgeWork)
        self.badgeRow.addWidget(self.badgeIdle)
        self.badgeRow.addWidget(self.badgeRender)
        self.badgeRow.addWidget(self.badgeBg)
        self.badgeRow.addStretch(1)

        # Times
        self.workLabel = QtWidgets.QLabel("00:00:00")
        self.workLabel.setObjectName("TimeMain")

        self.renderLabel = QtWidgets.QLabel("00:00:00")
        self.renderLabel.setObjectName("TimeSub")

        self.hintLabel = QtWidgets.QLabel("Work counts when Nuke is active + you do something. Render counted separately.")
        self.hintLabel.setObjectName("Hint")

        # Buttons
        self.btnCopy = QtWidgets.QPushButton("Copy data file path")
        self.btnOpen = QtWidgets.QPushButton("Open .ttk folder")
        self.btnSettings = QtWidgets.QPushButton("Settings")
        self.btnClose = QtWidgets.QPushButton("Close")

        self.btnCopy.clicked.connect(self.copy_path)
        self.btnOpen.clicked.connect(self.open_docs_folder)
        self.btnSettings.clicked.connect(self.open_settings)
        self.btnClose.clicked.connect(self.close)

        btnRow1 = QtWidgets.QHBoxLayout()
        btnRow1.addWidget(self.btnCopy)
        btnRow1.addWidget(self.btnOpen)

        btnRow2 = QtWidgets.QHBoxLayout()
        btnRow2.addWidget(self.btnSettings)
        btnRow2.addStretch(1)
        btnRow2.addWidget(self.btnClose)

        # Card layout
        card = QtWidgets.QFrame()
        card.setObjectName("Card")
        cardLayout = QtWidgets.QVBoxLayout(card)
        cardLayout.setContentsMargins(14, 14, 14, 14)
        cardLayout.setSpacing(8)

        line1 = QtWidgets.QHBoxLayout()
        line1.addWidget(QtWidgets.QLabel("Work:"))
        line1.addStretch(1)
        line1.addWidget(self.workLabel)

        line2 = QtWidgets.QHBoxLayout()
        line2.addWidget(QtWidgets.QLabel("Render:"))
        line2.addStretch(1)
        line2.addWidget(self.renderLabel)

        cardLayout.addLayout(line1)
        cardLayout.addLayout(line2)
        cardLayout.addWidget(self.hintLabel)

        # Footer (backdoor)
        self.versionLabel = QtWidgets.QLabel(getattr(timeTracker, "__version__", ""))
        self.versionLabel.setObjectName("Hint")
        self.versionLabel.setAlignment(QtCore.Qt.AlignLeft)

        self.footer = ClickableFooter("© Aleš Ushakou, 2026")
        self.footer.setObjectName("Hint")
        self.footer.setAlignment(QtCore.Qt.AlignRight)
        self.footer.clicked.connect(self._on_footer_click)
        self._apply_footer_color()

        # Main layout
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        outer.addWidget(self.bannerLabel)

        body = QtWidgets.QWidget(self)
        top = QtWidgets.QVBoxLayout(body)
        top.setContentsMargins(14, 14, 14, 10)
        top.setSpacing(10)

        top.addWidget(self.title)
        top.addLayout(self.badgeRow)
        top.addWidget(card)
        top.addLayout(btnRow1)
        top.addLayout(btnRow2)
        footerRow = QtWidgets.QHBoxLayout()
        footerRow.addWidget(self.versionLabel)
        footerRow.addStretch(1)
        footerRow.addWidget(self.footer)
        top.addLayout(footerRow)

        outer.addWidget(body, 1)

        # Mark UI open for backdoor mode
        timeTracker.set_ui_open(True)

        # Timer update
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

        self.refresh()

    def closeEvent(self, event):
        try:
            timeTracker.set_ui_open(False)
        except Exception:
            pass
        return super(TimeTrackerWindow, self).closeEvent(event)


    # -------------------------
    # Banner
    # -------------------------
    def _load_banner(self):
        p = _banner_path()
        if os.path.isfile(p):
            try:
                self._banner_pix = QtGui.QPixmap(p)
            except Exception:
                self._banner_pix = None
        else:
            self._banner_pix = None
        self._update_banner()

    def _update_banner(self):
        if not self._banner_pix or self._banner_pix.isNull():
            self.bannerLabel.clear()
            self.bannerLabel.setFixedHeight(0)
            return

        # растягиваем по всей ширине центрального виджета
        w = max(1, int(self.contentsRect().width()))

        # если НЕ хотим апскейл выше оригинала (чтобы не мылить)
        w = min(w, int(self._banner_pix.width()))

        scaled = self._banner_pix.scaledToWidth(
            w,
            QtCore.Qt.SmoothTransformation
        )

        self.bannerLabel.setPixmap(scaled)
        self.bannerLabel.setFixedHeight(scaled.height())

    def resizeEvent(self, event):
        try:
            self._update_banner()
        except Exception:
            pass
        return super(TimeTrackerWindow, self).resizeEvent(event)

    def _apply_footer_color(self):
        if settings.is_ales_on():
            self.footer.setStyleSheet("color: #fbbf24;")
        else:
            self.footer.setStyleSheet("color: #a8a8a8;")

    def _on_footer_click(self):
        self._footer_clicks += 1
        if self._footer_clicks >= 6:
            self._footer_clicks = 0
            # toggle ales mode
            new_state = not settings.is_ales_on()
            settings.set_ales(new_state)
            self._apply_footer_color()

    def _set_badges(self, app_active: bool, rendering: bool, user_active: bool):
        self.badgeRender.setVisible(bool(rendering))
        self.badgeBg.setVisible(not app_active)

        if rendering:
            self.badgeWork.setVisible(False)
            self.badgeIdle.setVisible(False)
        else:
            self.badgeWork.setVisible(bool(app_active and user_active))
            self.badgeIdle.setVisible(bool(app_active and not user_active))

    def refresh(self):
        shot = timeTracker.get_shot_name()
        self.title.setText(f"Shot: {shot}")

        work = timeTracker.human_time(timeTracker.get_live_work_seconds())
        rend = timeTracker.human_time(timeTracker.get_live_render_seconds())
        self.workLabel.setText(work)
        self.renderLabel.setText(rend)

        try:
            st = timeTracker._get_state()  # convenience
            app_active = bool(st.get("app_active", True))
            rendering = bool(st.get("rendering", False))

            if settings.is_ales_on():
                user_active = True
            else:
                now = timeTracker._now()
                user_active = (now - float(st.get("last_activity", 0.0) or 0.0)) <= float(getattr(timeTracker, "IDLE_TIMEOUT_SEC", 20))

            self._set_badges(app_active, rendering, user_active)
        except Exception:
            self.badgeWork.setVisible(False)
            self.badgeIdle.setVisible(False)
            self.badgeRender.setVisible(False)
            self.badgeBg.setVisible(False)

    def copy_path(self):
        p = timeTracker.get_data_file_path()
        if not p:
            nuke.message("Script is not saved yet.")
            return
        QtWidgets.QApplication.clipboard().setText(os.path.normpath(p))

    def open_docs_folder(self):
        d = settings.get_ttk_dir()
        if not d:
            nuke.message("No .ttk folder in settings.")
            return
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        _open_folder(d)

    def open_settings(self):
        settings_ui.show_settings(self)


def show_window():
    global _window
    if _window is None or not _window.isVisible():
        _window = TimeTrackerWindow()
        _window.show()
        _window.raise_()
        _window.activateWindow()
    else:
        _window.raise_()
        _window.activateWindow()
