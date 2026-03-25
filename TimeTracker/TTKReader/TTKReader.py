import os
import sys
import json
import base64
import hashlib
import hmac
import subprocess
import shutil
from datetime import datetime

# ---- Qt ----
try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui


TTK_VERSION = "1.1"
_TIMETRACKER_KEY = "Ales_Ushakou_Internal_Key_2026"
_TIMETRACKER_SALT = "Ales_Ushakou_Salt_2026"


def _salt():
    return _TIMETRACKER_SALT.encode("utf-8")


def _passphrase():
    return _TIMETRACKER_KEY


def _derive_key(passphrase: str) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8", "ignore"),
        _salt(),
        120_000,
        dklen=32,
    )


def _keystream(key: bytes, nbytes: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < nbytes:
        block = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:nbytes])


def decrypt_json(token: str, passphrase: str) -> dict:
    enc = base64.urlsafe_b64decode(token.encode("ascii"))
    key = _derive_key(passphrase)
    ks = _keystream(key, len(enc))
    raw = bytes([a ^ b for a, b in zip(enc, ks)])
    return json.loads(raw.decode("utf-8"))


# =========================
# Helpers
# =========================

def human_time(seconds) -> str:
    try:
        s = int(float(seconds))
    except Exception:
        return ""
    h = s // 3600
    m = (s % 3600) // 60
    ss = s % 60
    return f"{h:02d}:{m:02d}:{ss:02d}"


def fmt_ts(ts) -> str:
    try:
        ts = float(ts)
        if ts <= 0:
            return ""
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def _fallback_ttk_dir() -> str:
    # same idea as timeTracker.py default: ~/.nuke/.ttk
    return os.path.join(os.path.expanduser("~"), ".nuke", ".ttk")


def default_root_folder() -> str:
    # read from settings if possible, otherwise fallback
    try:
        if settings and hasattr(settings, "get_ttk_dir"):
            p = settings.get_ttk_dir()
            if p:
                return str(p)
    except Exception:
        pass
    return _fallback_ttk_dir()


def find_tracker_files(root_dir: str):
    out = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if os.path.basename(dirpath).lower() != ".ttk":
            continue
        for fn in filenames:
            if fn.startswith("timetracker_") and fn.endswith(".enc"):
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def read_one_file(fp: str):
    token = open(fp, "r", encoding="utf-8").read().strip()
    data = decrypt_json(token, _passphrase())

    computer = data.get("computer", "")
    shot = data.get("shot", "")

    work_s = float(data.get("work_seconds", 0.0) or 0.0)
    rend_s = float(data.get("render_seconds", 0.0) or 0.0)

    created = float(data.get("created_at", 0.0) or 0.0)
    updated = float(data.get("updated_at", 0.0) or 0.0)

    return {
        "computer": computer,
        "shot": shot,
        "work": human_time(work_s),
        "render": human_time(rend_s),
        "started_at": fmt_ts(created),
        "finished_at": fmt_ts(updated),
        "file": os.path.basename(fp),
        "_file_path": fp,
        "_work_s_raw": work_s,
        "_render_s_raw": rend_s,
        "_created_at_raw": created,
        "_updated_at_raw": updated,
    }


# =========================
# Header banner
# =========================

# Put your banner image next to this script (same folder).
# Expected size: 1400x300.
HEADER_BANNER_FILE = "TTKReader.png"


def _here_dir() -> str:
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return os.getcwd()


def _banner_path() -> str:
    return os.path.join(_here_dir(), HEADER_BANNER_FILE)


# =========================
# UI
# =========================

COLS = ["Computer", "Shot", "Work", "Render", "Started", "Finished", "File"]


class ReaderWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TimeTracker Reader")
        self.resize(1250, 650)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        # ---------- Header banner ----------
        self._banner_pix = None
        self.bannerLabel = QtWidgets.QLabel()
        self.bannerLabel.setObjectName("HeaderBanner")
        self.bannerLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.bannerLabel.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.bannerLabel.setFixedHeight(0)  # will be set after pixmap load
        self._load_banner()

        # ---------- Controls ----------
        self.pathEdit = QtWidgets.QLineEdit()
        self.btnBrowse = QtWidgets.QPushButton("Choose folder…")
        self.btnScan = QtWidgets.QPushButton("Scan")
        self.btnExportExcel = QtWidgets.QPushButton("Export Excel…")
        self.btnExportPDF = QtWidgets.QPushButton("Export PDF…")
        self.btnCopyReportPath = QtWidgets.QPushButton("Copy report path")
        self.btnOpenReportFile = QtWidgets.QPushButton("Open report file")
        self.status = QtWidgets.QLabel("")
        self.last_report_path = ""

        # ---- Version label (dynamic, safe) ----

        version_text = f"TimeTracker Reader v{TTK_VERSION}"
        self.versionLabel = QtWidgets.QLabel(version_text)
        self.versionLabel.setObjectName("Hint")
        self.versionLabel.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        self.copyrightLabel = QtWidgets.QLabel(
            '<span style="color:#888888;">© Aleš Ushakou, 2026</span>'
        )
        self.copyrightLabel.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.copyrightLabel.setObjectName("Hint")
        self.copyrightLabel.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.copyrightLabel.setToolTip("Open LinkedIn profile")

        ORANGE = "#FFC266"  # 🔥 наш любимый оранж

        def _open_linkedin(event):
            QtGui.QDesktopServices.openUrl(
                QtCore.QUrl("https://www.linkedin.com/in/ales-ushakou/")
            )

        def _copyright_enter(event):
            self.copyrightLabel.setText(
                f'<span style="color:{ORANGE};">© Aleš Ushakou, 2026</span>'
            )

        def _copyright_leave(event):
            self.copyrightLabel.setText(
                '<span style="color:#888888;">© Aleš Ushakou, 2026</span>'
            )

        self.copyrightLabel.mousePressEvent = _open_linkedin
        self.copyrightLabel.enterEvent = _copyright_enter
        self.copyrightLabel.leaveEvent = _copyright_leave

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Root folder:"))
        top.addWidget(self.pathEdit, 1)
        top.addWidget(self.btnBrowse)
        top.addWidget(self.btnScan)

        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(self.btnExportExcel)
        btns.addWidget(self.btnExportPDF)
        btns.addWidget(self.btnCopyReportPath)
        btns.addWidget(self.btnOpenReportFile)
        btns.addStretch(1)
        btns.addWidget(self.status)

        self.table = QtWidgets.QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)

        # zebra rows
        self.table.setAlternatingRowColors(True)

        # sorting
        self.table.setSortingEnabled(True)

        footer = QtWidgets.QHBoxLayout()
        footer.addWidget(self.versionLabel)
        footer.addStretch(1)
        footer.addWidget(self.copyrightLabel)

        layout = QtWidgets.QVBoxLayout(central)
        layout.addWidget(self.bannerLabel)   # <-- banner сверху
        layout.addLayout(top)
        layout.addLayout(btns)
        layout.addWidget(self.table, 1)
        layout.addLayout(footer)

        # subtle hint styling (works for both dark/light)
        self.setStyleSheet(
            """
            QLabel#Hint { color: rgba(200,200,200,140); }
            QTableWidget::item:selected { background: rgba(80,120,200,120); }
            """
        )

        self.rows = []

        self.btnBrowse.clicked.connect(self.choose_folder)
        self.btnScan.clicked.connect(self.scan)
        self.btnExportExcel.clicked.connect(self.export_excel)
        self.btnExportPDF.clicked.connect(self.export_pdf)
        self.btnCopyReportPath.clicked.connect(self.copy_report_path)
        self.btnOpenReportFile.clicked.connect(self.open_report_file)

        # initial folder from settings (or fallback)
        try:
            self.pathEdit.setText(default_root_folder())
        except Exception:
            self.pathEdit.setText(_fallback_ttk_dir())

    # ---------- Banner helpers ----------
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


        cw = max(1, int(self.centralWidget().width()))
        target_w = max(1, int(cw * 0.8))


        target_w = min(target_w, int(self._banner_pix.width()))

        scaled = self._banner_pix.scaledToWidth(target_w, QtCore.Qt.SmoothTransformation)
        self.bannerLabel.setPixmap(scaled)
        self.bannerLabel.setFixedHeight(scaled.height())

    def resizeEvent(self, event):
        try:
            self._update_banner()
        except Exception:
            pass
        return super().resizeEvent(event)

    # ---------- UI logic ----------
    def choose_folder(self):
        start_dir = self.pathEdit.text().strip() or default_root_folder()
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose folder", start_dir)
        if d:
            self.pathEdit.setText(d)

    def set_status(self, text):
        self.status.setText(text)

    def scan(self):
        root = self.pathEdit.text().strip()
        if not root or not os.path.isdir(root):
            QtWidgets.QMessageBox.warning(self, "Error", "Choose a valid folder.")
            return

        self.set_status("Scanning…")
        QtWidgets.QApplication.processEvents()

        files = find_tracker_files(root)
        rows = []
        errors = 0

        for fp in files:
            try:
                rows.append(read_one_file(fp))
            except Exception:
                errors += 1

        # default sort: computer -> shot -> finished desc
        rows.sort(
            key=lambda r: (
                r.get("computer", ""),
                r.get("shot", ""),
                -float(r.get("_updated_at_raw", 0.0) or 0.0),
            )
        )

        self.rows = rows
        self.populate_table()
        self.set_status(f"Rows: {len(rows)} | Files: {len(files)} | Errors: {errors}")

    def populate_table(self):
        # preserve sorting usability by disabling during fill
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for r in self.rows:
            row_idx = self.table.rowCount()
            self.table.insertRow(row_idx)

            values = [
                r.get("computer", ""),
                r.get("shot", ""),
                r.get("work", ""),
                r.get("render", ""),
                r.get("started_at", ""),
                r.get("finished_at", ""),
                r.get("file", ""),
            ]

            for c, v in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(v))
                item.setTextAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)

                # Sorting: QTableWidget uses EditRole for comparisons.
                if c == 2:  # Work
                    item.setData(QtCore.Qt.EditRole, float(r.get("_work_s_raw", 0.0) or 0.0))
                    item.setText(r.get("work", ""))
                elif c == 3:  # Render
                    item.setData(QtCore.Qt.EditRole, float(r.get("_render_s_raw", 0.0) or 0.0))
                    item.setText(r.get("render", ""))
                elif c == 4:  # Started
                    item.setData(QtCore.Qt.EditRole, float(r.get("_created_at_raw", 0.0) or 0.0))
                    item.setText(r.get("started_at", ""))
                elif c == 5:  # Finished
                    item.setData(QtCore.Qt.EditRole, float(r.get("_updated_at_raw", 0.0) or 0.0))
                    item.setText(r.get("finished_at", ""))
                elif c == 6:  # File
                    # store full path so Copy works even with sorting enabled
                    item.setData(QtCore.Qt.UserRole, r.get("_file_path", ""))

                self.table.setItem(row_idx, c, item)

        self.table.setSortingEnabled(True)

    def _suggest_report_name(self, ext: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"timetracker_report_{stamp}.{ext}"

    def _set_last_report_path(self, path: str):
        self.last_report_path = os.path.normpath(path) if path else ""
        if self.last_report_path:
            self.set_status(f"Report: {self.last_report_path}")

    def export_excel(self):
        if not self.rows:
            QtWidgets.QMessageBox.information(self, "Info", "Nothing to export. Scan first.")
            return

        try:
            from openpyxl import Workbook
        except Exception:
            QtWidgets.QMessageBox.warning(
                self,
                "Missing dependency",
                "openpyxl is not installed.\nInstall it with: pip install openpyxl",
            )
            return

        out, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export Excel",
            self._suggest_report_name("xlsx"),
            "Excel (*.xlsx)",
        )
        if not out:
            return
        if not out.lower().endswith(".xlsx"):
            out += ".xlsx"

        wb = Workbook()
        ws = wb.active
        ws.title = "TimeTracker Report"
        ws.append(COLS)

        for r in self.rows:
            ws.append([
                r.get("computer", ""),
                r.get("shot", ""),
                r.get("work", ""),
                r.get("render", ""),
                r.get("started_at", ""),
                r.get("finished_at", ""),
                r.get("file", ""),
            ])

        # auto column width
        for col_cells in ws.columns:
            max_len = 0
            col_letter = col_cells[0].column_letter
            for cell in col_cells:
                try:
                    val = "" if cell.value is None else str(cell.value)
                except Exception:
                    val = ""
                max_len = max(max_len, len(val))
            ws.column_dimensions[col_letter].width = min(max(max_len + 2, 10), 60)

        wb.save(out)
        self._set_last_report_path(out)
        QtWidgets.QMessageBox.information(self, "Done", f"Saved:\n{out}")

    def export_pdf(self):
        if not self.rows:
            QtWidgets.QMessageBox.information(self, "Info", "Nothing to export. Scan first.")
            return

        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.enums import TA_LEFT
            from reportlab.lib.units import mm
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
        except Exception:
            QtWidgets.QMessageBox.warning(
                self,
                "Missing dependency",
                "reportlab is not installed.\nInstall it with: pip install reportlab",
            )
            return

        out, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export PDF",
            self._suggest_report_name("pdf"),
            "PDF (*.pdf)",
        )
        if not out:
            return
        if not out.lower().endswith(".pdf"):
            out += ".pdf"

        doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=10 * mm, bottomMargin=10 * mm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("TTKTitle", parent=styles["Title"], alignment=TA_LEFT, textColor=colors.HexColor("#ff8a00"), fontSize=18, leading=22, spaceAfter=4)
        subtitle_style = ParagraphStyle("TTKSubtitle", parent=styles["Normal"], alignment=TA_LEFT, fontSize=9, textColor=colors.HexColor("#666666"), leading=11, spaceAfter=10)

        elements = []

        banner = _banner_path()
        if os.path.isfile(banner):
            try:
                img = Image(banner)
                max_w = doc.width
                iw = float(getattr(img, 'imageWidth', 1) or 1)
                ih = float(getattr(img, 'imageHeight', 1) or 1)
                scale = min(max_w / iw, 1.0)
                img.drawWidth = iw * scale
                img.drawHeight = ih * scale
                elements.append(img)
                elements.append(Spacer(1, 6))
            except Exception:
                pass

        elements.append(Paragraph("TimeTracker Report", title_style))
        elements.append(Paragraph("from TTKReader", subtitle_style))

        data = [COLS]
        for r in self.rows:
            data.append([
                r.get("computer", ""),
                r.get("shot", ""),
                r.get("work", ""),
                r.get("render", ""),
                r.get("started_at", ""),
                r.get("finished_at", ""),
                r.get("file", ""),
            ])

        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ff8a00")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("LEADING", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.HexColor("#f7f7f7")]),
            ("ALIGN", (2, 1), (3, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(table)

        doc.build(elements)
        self._set_last_report_path(out)
        QtWidgets.QMessageBox.information(self, "Done", f"Saved:\n{out}")

    def copy_report_path(self):
        if not self.last_report_path:
            QtWidgets.QMessageBox.information(self, "Info", "No report file yet. Export Excel or PDF first.")
            return
        QtWidgets.QApplication.clipboard().setText(self.last_report_path)
        self.set_status(f"Copied report path: {self.last_report_path}")

    def open_report_file(self):
        if not self.last_report_path:
            QtWidgets.QMessageBox.information(self, "Info", "No report file yet. Export Excel or PDF first.")
            return
        path = self.last_report_path
        if not os.path.isfile(path):
            QtWidgets.QMessageBox.warning(self, "Error", f"File not found:\n{path}")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                opener = shutil.which("xdg-open")
                if opener:
                    subprocess.Popen([opener, path])
                else:
                    raise RuntimeError("xdg-open not found")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Could not open file:\n{e}")


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    w = ReaderWindow()
    w.show()

    # PySide6: exec(); PySide2: exec_()
    if hasattr(app, "exec"):
        sys.exit(app.exec())
    else:
        sys.exit(app.exec_())


if __name__ == "__main__":
    main()