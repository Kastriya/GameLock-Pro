import sys
import os
import json
import hashlib
import subprocess
from datetime import datetime, time as dtime
from pathlib import Path

import psutil
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QFileDialog, QSystemTrayIcon,
    QMenu, QDialog, QLineEdit, QMessageBox, QFrame, QListWidgetItem,
    QTimeEdit, QInputDialog
)
from PyQt6.QtCore import QTimer, Qt, QTime, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QFont, QColor, QPalette, QPixmap, QPainter


# ── Constants ──────────────────────────────────────────────────────────────────
CONFIG_FILE = Path.home() / ".gamelock_config.json"
DEFAULT_PASSWORD = hashlib.sha256(b"gamelock123").hexdigest()
UNLOCK_DEFAULT = dtime(20, 0)   # 8:00 PM
LOCK_DEFAULT   = dtime(6, 0)    # 6:00 AM


# ── Config I/O ─────────────────────────────────────────────────────────────────
def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {
        "games": [],
        "unlock_hour": 20, "unlock_minute": 0,
        "lock_hour": 6,   "lock_minute": 0,
        "password": DEFAULT_PASSWORD,
        "autostart": False,
    }

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# ── Worker thread: kills games outside allowed window ─────────────────────────
class LockWorker(QThread):
    status_signal = pyqtSignal(str)   # "locked" | "unlocked"

    def __init__(self, cfg_getter):
        super().__init__()
        self.cfg_getter = cfg_getter
        self._running = True

    def is_allowed(self, cfg) -> bool:
        now = datetime.now().time().replace(second=0, microsecond=0)
        unlock = dtime(cfg["unlock_hour"], cfg["unlock_minute"])
        lock   = dtime(cfg["lock_hour"],   cfg["lock_minute"])
        if unlock > lock:          # spans midnight (e.g. 20:00 → 06:00)
            return now >= unlock or now < lock
        return unlock <= now < lock

    def run(self):
        while self._running:
            cfg = self.cfg_getter()
            allowed = self.is_allowed(cfg)
            self.status_signal.emit("unlocked" if allowed else "locked")
            if not allowed:
                for game_path in cfg["games"]:
                    exe_name = Path(game_path).name.lower()
                    for proc in psutil.process_iter(["name", "exe"]):
                        try:
                            pname = (proc.info["name"] or "").lower()
                            pexe  = (proc.info["exe"]  or "").lower()
                            if pname == exe_name or pexe == game_path.lower():
                                proc.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
            self.msleep(5000)   # check every 5 s

    def stop(self):
        self._running = False
        self.quit()


# ── Password dialog ────────────────────────────────────────────────────────────
class PasswordDialog(QDialog):
    def __init__(self, parent=None, title="Enter Password", prompt="Password:"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(320, 150)
        self.setStyleSheet(parent.styleSheet() if parent else "")
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(QLabel(prompt))
        self.pw_edit = QLineEdit()
        self.pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw_edit.setPlaceholderText("••••••••")
        lay.addWidget(self.pw_edit)
        btns = QHBoxLayout()
        ok = QPushButton("OK");     ok.clicked.connect(self.accept)
        ca = QPushButton("Cancel"); ca.clicked.connect(self.reject)
        btns.addWidget(ok); btns.addWidget(ca)
        lay.addLayout(btns)

    def value(self):
        return self.pw_edit.text()


# ── Main window ────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    STYLESHEET = """
    QMainWindow, QDialog { background: #0f1117; }
    QWidget { background: #0f1117; color: #e2e8f0; font-family: 'Segoe UI'; font-size: 13px; }

    /* Cards */
    QFrame#card {
        background: #1a1d27;
        border: 1px solid #2d3148;
        border-radius: 12px;
    }

    /* Buttons */
    QPushButton {
        background: #6c63ff;
        color: #fff;
        border: none;
        border-radius: 8px;
        padding: 8px 18px;
        font-weight: 600;
    }
    QPushButton:hover   { background: #7d75ff; }
    QPushButton:pressed { background: #5a52e0; }
    QPushButton#danger  { background: #e05252; }
    QPushButton#danger:hover { background: #f06060; }
    QPushButton#outline {
        background: transparent;
        border: 1px solid #2d3148;
        color: #94a3b8;
    }
    QPushButton#outline:hover { border-color: #6c63ff; color: #e2e8f0; }

    /* List */
    QListWidget {
        background: #12141e;
        border: 1px solid #2d3148;
        border-radius: 8px;
        padding: 4px;
    }
    QListWidget::item { padding: 8px 10px; border-radius: 6px; }
    QListWidget::item:selected { background: #6c63ff22; color: #a89dff; }
    QListWidget::item:hover    { background: #1e2130; }

    /* Inputs */
    QLineEdit, QTimeEdit {
        background: #12141e;
        border: 1px solid #2d3148;
        border-radius: 8px;
        padding: 6px 10px;
        color: #e2e8f0;
    }
    QLineEdit:focus, QTimeEdit:focus { border-color: #6c63ff; }

    /* Labels */
    QLabel#title  { font-size: 22px; font-weight: 700; color: #fff; }
    QLabel#sub    { font-size: 12px; color: #64748b; }
    QLabel#badge  { font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 20px; }
    QLabel#timer  { font-size: 28px; font-weight: 700; color: #a89dff; }
    QLabel#section{ font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 1px; }
    """

    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.setWindowTitle("GameLock Pro")
        self.setMinimumSize(520, 640)
        self.setStyleSheet(self.STYLESHEET)

        self._build_ui()
        self._build_tray()

        self.worker = LockWorker(lambda: self.cfg)
        self.worker.status_signal.connect(self._on_status)
        self.worker.start()

        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self._refresh_timer)
        self.clock_timer.start(1000)
        self._refresh_timer()

    # ── UI ─────────────────────────────────────────────────────────────────────
    def _card(self) -> QFrame:
        f = QFrame(); f.setObjectName("card")
        return f

    def _section_label(self, text: str) -> QLabel:
        l = QLabel(text.upper()); l.setObjectName("section"); return l

    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        main = QVBoxLayout(root); main.setContentsMargins(24, 24, 24, 24); main.setSpacing(16)

        # ── Header ──
        hdr = QHBoxLayout()
        left = QVBoxLayout(); left.setSpacing(2)
        t = QLabel("GameLock Pro"); t.setObjectName("title"); left.addWidget(t)
        s = QLabel("Schedule & enforce your gaming hours"); s.setObjectName("sub"); left.addWidget(s)
        hdr.addLayout(left)
        hdr.addStretch()
        self.badge = QLabel("● LOCKED"); self.badge.setObjectName("badge")
        self._set_badge("locked")
        hdr.addWidget(self.badge)
        main.addLayout(hdr)

        # ── Status card ──
        sc = self._card(); sl = QVBoxLayout(sc); sl.setContentsMargins(20,16,20,16); sl.setSpacing(4)
        sl.addWidget(self._section_label("Next Event"))
        self.timer_label = QLabel("--:--:--"); self.timer_label.setObjectName("timer")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(self.timer_label)
        self.next_event_label = QLabel(""); self.next_event_label.setObjectName("sub")
        self.next_event_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(self.next_event_label)
        main.addWidget(sc)

        # ── Schedule card ──
        sched_card = self._card(); scl = QVBoxLayout(sched_card)
        scl.setContentsMargins(20,16,20,16); scl.setSpacing(10)
        scl.addWidget(self._section_label("Schedule"))

        row = QHBoxLayout(); row.setSpacing(16)

        ul = QVBoxLayout(); ul.setSpacing(4)
        ul.addWidget(QLabel("🔓  Unlock Time"))
        self.unlock_edit = QTimeEdit()
        self.unlock_edit.setTime(QTime(self.cfg["unlock_hour"], self.cfg["unlock_minute"]))
        self.unlock_edit.setDisplayFormat("HH:mm")
        ul.addWidget(self.unlock_edit)
        row.addLayout(ul)

        ll = QVBoxLayout(); ll.setSpacing(4)
        ll.addWidget(QLabel("🔒  Lock Time"))
        self.lock_edit = QTimeEdit()
        self.lock_edit.setTime(QTime(self.cfg["lock_hour"], self.cfg["lock_minute"]))
        self.lock_edit.setDisplayFormat("HH:mm")
        ll.addWidget(self.lock_edit)
        row.addLayout(ll)
        scl.addLayout(row)

        save_btn = QPushButton("Save Schedule")
        save_btn.clicked.connect(self._save_schedule)
        scl.addWidget(save_btn)
        main.addWidget(sched_card)

        # ── Games card ──
        gc = self._card(); gl = QVBoxLayout(gc); gl.setContentsMargins(20,16,20,16); gl.setSpacing(10)
        gl.addWidget(self._section_label("Monitored Games"))

        self.game_list = QListWidget()
        self.game_list.setMinimumHeight(130)
        for g in self.cfg["games"]:
            self.game_list.addItem(QListWidgetItem(Path(g).name + f"  —  {g}"))
        gl.addWidget(self.game_list)

        gbtn = QHBoxLayout(); gbtn.setSpacing(8)
        add_btn = QPushButton("+ Add Game"); add_btn.clicked.connect(self._add_game)
        rem_btn = QPushButton("Remove"); rem_btn.setObjectName("danger"); rem_btn.clicked.connect(self._remove_game)
        gbtn.addWidget(add_btn); gbtn.addWidget(rem_btn); gbtn.addStretch()
        gl.addLayout(gbtn)
        main.addWidget(gc)

        # ── Settings card ──
        setc = self._card(); setl = QHBoxLayout(setc)
        setc.setContentsMargins(20,14,20,14)
        pw_btn = QPushButton("Change Password"); pw_btn.setObjectName("outline"); pw_btn.clicked.connect(self._change_password)
        setl.addWidget(pw_btn)
        setl.addStretch()
        info = QLabel("Default pw: gamelock123"); info.setObjectName("sub")
        setl.addWidget(info)
        main.addWidget(setc)

        main.addStretch()

    # ── Tray ───────────────────────────────────────────────────────────────────
    def _build_tray(self):
        # Create a simple colored icon
        pix = QPixmap(16, 16); pix.fill(QColor("#6c63ff"))
        self.tray = QSystemTrayIcon(QIcon(pix), self)
        menu = QMenu()
        menu.addAction("Show", self.show)
        menu.addAction("Quit", self._quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.show() if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _set_badge(self, status: str):
        if status == "unlocked":
            self.badge.setText("● UNLOCKED")
            self.badge.setStyleSheet("background:#1a3a2a; color:#4ade80; border-radius:20px; padding:3px 10px;")
        else:
            self.badge.setText("● LOCKED")
            self.badge.setStyleSheet("background:#3a1a1a; color:#f87171; border-radius:20px; padding:3px 10px;")

    def _on_status(self, status: str):
        self._set_badge(status)

    def _refresh_timer(self):
        now = datetime.now()
        unlock = now.replace(hour=self.cfg["unlock_hour"], minute=self.cfg["unlock_minute"], second=0, microsecond=0)
        lock   = now.replace(hour=self.cfg["lock_hour"],   minute=self.cfg["lock_minute"],   second=0, microsecond=0)

        # Determine which event is next
        candidates = []
        for t, label in [(unlock, "Unlocks"), (lock, "Locks")]:
            if t <= now: t = t.replace(day=t.day+1)   # push to tomorrow if passed
            candidates.append((t, label))
        candidates.sort()
        nxt, lbl = candidates[0]
        delta = nxt - now
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s   = divmod(rem, 60)
        self.timer_label.setText(f"{h:02d}:{m:02d}:{s:02d}")
        self.next_event_label.setText(f"{lbl} at {nxt.strftime('%I:%M %p')}")

    # ── Actions ────────────────────────────────────────────────────────────────
    def _save_schedule(self):
        dlg = PasswordDialog(self, prompt="Enter password to change schedule:")
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        if hash_pw(dlg.value()) != self.cfg["password"]:
            QMessageBox.warning(self, "Wrong Password", "Incorrect password."); return
        ut = self.unlock_edit.time(); lt = self.lock_edit.time()
        self.cfg["unlock_hour"] = ut.hour(); self.cfg["unlock_minute"] = ut.minute()
        self.cfg["lock_hour"]   = lt.hour(); self.cfg["lock_minute"]   = lt.minute()
        save_config(self.cfg)
        QMessageBox.information(self, "Saved", "Schedule updated successfully!")

    def _add_game(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Game EXE", "", "Executable (*.exe)")
        if path and path not in self.cfg["games"]:
            self.cfg["games"].append(path)
            save_config(self.cfg)
            self.game_list.addItem(QListWidgetItem(Path(path).name + f"  —  {path}"))

    def _remove_game(self):
        row = self.game_list.currentRow()
        if row < 0: return
        dlg = PasswordDialog(self, prompt="Enter password to remove a game:")
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        if hash_pw(dlg.value()) != self.cfg["password"]:
            QMessageBox.warning(self, "Wrong Password", "Incorrect password."); return
        self.cfg["games"].pop(row)
        save_config(self.cfg)
        self.game_list.takeItem(row)

    def _change_password(self):
        dlg = PasswordDialog(self, prompt="Current password:")
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        if hash_pw(dlg.value()) != self.cfg["password"]:
            QMessageBox.warning(self, "Wrong Password", "Incorrect password."); return
        dlg2 = PasswordDialog(self, title="New Password", prompt="New password (min 6 chars):")
        if dlg2.exec() != QDialog.DialogCode.Accepted: return
        if len(dlg2.value()) < 6:
            QMessageBox.warning(self, "Too Short", "Password must be at least 6 characters."); return
        self.cfg["password"] = hash_pw(dlg2.value())
        save_config(self.cfg)
        QMessageBox.information(self, "Done", "Password changed!")

    def _quit(self):
        dlg = PasswordDialog(self, prompt="Enter password to quit GameLock:")
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        if hash_pw(dlg.value()) != self.cfg["password"]:
            QMessageBox.warning(self, "Wrong Password", "Cannot quit without correct password."); return
        self.worker.stop()
        QApplication.quit()

    def closeEvent(self, event):
        event.ignore()   # minimize to tray instead of closing
        self.hide()
        self.tray.showMessage("GameLock Pro", "Running in background. Right-click tray to quit.", QSystemTrayIcon.MessageIcon.Information, 2000)


# ── Entry ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())