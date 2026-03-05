# settings_ui.py

from __future__ import annotations

import os

try:
    from PySide2 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide6 import QtWidgets, QtCore, QtGui

import settings


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
    font-weight: 600;
}
QLineEdit {
    padding: 6px 8px;
    border-radius: 8px;
    background: #262626;
}
QPushButton {
    padding: 7px 10px;
    border-radius: 8px;
    background: #2a2a2a;
}
QPushButton:hover { background: #333333; }
QPushButton:pressed { background: #262626; }
QLabel#Hint { color: #a8a8a8; }
QLabel#HeaderBanner { background: transparent; }
"""


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(SettingsDialog, self).__init__(parent)
        self.setWindowTitle("TimeTracker Settings")
        self.setMinimumWidth(620)
        self.setStyleSheet(_QSS)

        st = settings.load_settings()

        # Header banner
        self._banner_pix = None
        self.bannerLabel = QtWidgets.QLabel()
        self.bannerLabel.setObjectName("HeaderBanner")
        self.bannerLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.bannerLabel.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.bannerLabel.setFixedHeight(0)
        self._load_banner()

        title = QtWidgets.QLabel("Settings")
        title.setObjectName("Title")

        self.pathEdit = QtWidgets.QLineEdit(st.get("ttk_dir", ""))
        self.alwaysOnTopCheck = QtWidgets.QCheckBox("Keep main window always on top")
        self.alwaysOnTopCheck.setChecked(st.get("always_on_top", False))        
        self.btnBrowse = QtWidgets.QPushButton("Choose…")
        self.btnSave = QtWidgets.QPushButton("Save")
        self.btnClose = QtWidgets.QPushButton("Close")

        hint = QtWidgets.QLabel(
            "Folder where TimeTracker stores encrypted .enc files (inside .ttk).\n"
            "Tip: default is ~/.nuke/.ttk"
        )
        hint.setObjectName("Hint")

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel(".ttk folder:"))
        row.addWidget(self.pathEdit, 1)
        row.addWidget(self.btnBrowse)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self.btnSave)
        btns.addWidget(self.btnClose)

        # Outer layout (no margins) so banner can sit nicely on top
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        outer.addWidget(self.bannerLabel)

        # Body layout (original margins)
        body = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(body)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.alwaysOnTopCheck)
        layout.addLayout(row)
        layout.addStretch(1)
        layout.addLayout(btns)

        outer.addWidget(body, 1)

        self.btnBrowse.clicked.connect(self.choose_folder)
        self.btnSave.clicked.connect(self.save)
        self.btnClose.clicked.connect(self.close)

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
        return super().resizeEvent(event)

    def choose_folder(self):
        start = self.pathEdit.text().strip() or os.path.expanduser("~")
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose .ttk folder", start)
        if d:
            self.pathEdit.setText(d)

    def save(self):
        d = self.pathEdit.text().strip()
        if not d:
            QtWidgets.QMessageBox.warning(self, "Error", "Folder path is empty")
            return
        st = settings.load_settings()
        st["ttk_dir"] = os.path.normpath(d)
        st["always_on_top"] = self.alwaysOnTopCheck.isChecked()
        settings.save_settings(st)
        QtWidgets.QMessageBox.information(self, "Saved", "Settings saved")


def show_settings(parent=None):
    dlg = SettingsDialog(parent)
    dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()