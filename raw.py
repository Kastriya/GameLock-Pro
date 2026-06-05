import sys
import os
import json
import hashlib
from datetime import datetime, time as dtime
from pathlib import Path

import psutil
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QFileDialog, QSystemTrayIcon,
    QMenu, QDialog, QLineEdit, QMessageBox, QFrame, QListWidgetItem,
    QTimeEdit, QGraphicsDropShadowEffect, QScrollArea, QSizePolicy
)
from PyQt6.QtCore import QTimer, Qt, QTime, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve, QRect, QSize
from PyQt6.QtGui import (
    QIcon, QFont, QColor, QPalette, QPixmap, QPainter,
    QLinearGradient, QBrush, QPen, QFontDatabase, QPainterPath, QRegion
)


CONFIG_FILE = Path.home() / ".gamelock_config.json"
DEFAULT_PASSWORD = hashlib.sha256(b"gamelock123").hexdigest()


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {
        "games": [],
        "unlock_hour": 20, "unlock_minute": 0,
        "lock_hour": 6,   "lock_minute": 0,
        "password": DEFAULT_PASSWORD,
    }

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()


# ── Lock Worker ────────────────────────────────────────────────────────────────
class LockWorker(QThread):
    status_signal = pyqtSignal(bool)  # True = allowed

    def __init__(self, cfg_getter):
        super().__init__()
        self.cfg_getter = cfg_getter
        self._running = True

    def is_allowed(self, cfg):
        now = datetime.now().time().replace(second=0, microsecond=0)
        unlock = dtime(cfg["unlock_hour"], cfg["unlock_minute"])
        lock   = dtime(cfg["lock_hour"],   cfg["lock_minute"])
        if unlock > lock:
            return now >= unlock or now < lock
        return unlock <= now < lock

    def run(self):
        while self._running:
            cfg = self.cfg_getter()
            allowed = self.is_allowed(cfg)
            self.status_signal.emit(allowed)
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
            self.msleep(5000)

    def stop(self):
        self._running = False
        self.quit()


# ── Material Elevated Card ─────────────────────────────────────────────────────
class Card(QFrame):
    def __init__(self, parent=None, elevated=False):
        super().__init__(parent)
        self.setObjectName("card")
        if elevated:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(24)
            shadow.setXOffset(0)
            shadow.setYOffset(4)
            shadow.setColor(QColor(0, 0, 0, 60))
            self.setGraphicsEffect(shadow)


# ── Material Button ────────────────────────────────────────────────────────────
class FilledButton(QPushButton):
    def __init__(self, text, color="#1a73e8", parent=None):
        super().__init__(text, parent)
        self.color = color
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {color};
                color: white;
                border: none;
                border-radius: 20px;
                padding: 0 24px;
                font-size: 13px;
                font-weight: 600;
                letter-spacing: 0.3px;
            }}
            QPushButton:hover {{ background: {color}dd; }}
            QPushButton:pressed {{ background: {color}aa; }}
        """)

class TonalButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                background: #e8f0fe;
                color: #1a73e8;
                border: none;
                border-radius: 20px;
                padding: 0 24px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover { background: #d2e3fc; }
            QPushButton:pressed { background: #b6ccfe; }
        """)

class OutlinedButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #5f6368;
                border: 1.5px solid #dadce0;
                border-radius: 20px;
                padding: 0 24px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover { background: #f1f3f4; color: #1a73e8; border-color: #1a73e8; }
            QPushButton:pressed { background: #e8f0fe; }
        """)


# ── Password Dialog ────────────────────────────────────────────────────────────
class PasswordDialog(QDialog):
    def __init__(self, parent=None, title="Verify Identity", prompt="Enter your password to continue"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(380, 220)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: white;
                border-radius: 16px;
            }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0,0,0,80))
        shadow.setOffset(0, 8)
        card.setGraphicsEffect(shadow)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(28, 28, 28, 24)
        lay.setSpacing(16)

        icon_row = QHBoxLayout()
        icon_lbl = QLabel("🔐")
        icon_lbl.setStyleSheet("font-size: 28px; background: transparent;")
        icon_row.addWidget(icon_lbl)
        icon_row.addStretch()
        lay.addLayout(icon_row)

        t = QLabel(title)
        t.setStyleSheet("font-size: 16px; font-weight: 700; color: #202124; background: transparent;")
        lay.addWidget(t)

        p = QLabel(prompt)
        p.setStyleSheet("font-size: 12px; color: #5f6368; background: transparent;")
        p.setWordWrap(True)
        lay.addWidget(p)

        self.pw_edit = QLineEdit()
        self.pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw_edit.setPlaceholderText("Password")
        self.pw_edit.setStyleSheet("""
            QLineEdit {
                background: #f1f3f4;
                border: 2px solid transparent;
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 13px;
                color: #202124;
            }
            QLineEdit:focus { border-color: #1a73e8; background: white; }
        """)
        self.pw_edit.returnPressed.connect(self.accept)
        lay.addWidget(self.pw_edit)

        btns = QHBoxLayout(); btns.setSpacing(8)
        btns.addStretch()
        ca = OutlinedButton("Cancel"); ca.clicked.connect(self.reject); ca.setFixedWidth(90)
        ok = FilledButton("Confirm");  ok.clicked.connect(self.accept); ok.setFixedWidth(100)
        btns.addWidget(ca); btns.addWidget(ok)
        lay.addLayout(btns)

        outer.addWidget(card)

    def value(self): return self.pw_edit.text()


# ── Circular Status Widget ─────────────────────────────────────────────────────
class StatusRing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(160, 160)
        self._locked = True
        self._angle = 0
        self._timer_text = "--:--:--"
        self._event_text = ""

    def set_status(self, locked):
        self._locked = locked
        self.update()

    def set_timer(self, text, event):
        self._timer_text = text
        self._event_text = event
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, r = 80, 80, 64

        # Background ring
        p.setPen(QPen(QColor("#f1f3f4"), 10))
        p.drawEllipse(cx-r, cy-r, r*2, r*2)

        # Colored arc
        color = QColor("#34a853") if not self._locked else QColor("#ea4335")
        p.setPen(QPen(color, 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(cx-r, cy-r, r*2, r*2, 90*16, -270*16)

        # Center icon
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#f8f9fa"))
        p.drawEllipse(cx-44, cy-44, 88, 88)

        icon = "🟢" if not self._locked else "🔴"
        p.setFont(QFont("Segoe UI Emoji", 22))
        p.setPen(QColor("#202124"))
        p.drawText(QRect(cx-22, cy-22, 44, 44), Qt.AlignmentFlag.AlignCenter, icon)
        p.end()


# ── Time Picker Card ───────────────────────────────────────────────────────────
class TimeCard(QFrame):
    def __init__(self, label, icon, color, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {color};
                border-radius: 16px;
                border: none;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)

        top = QHBoxLayout()
        ic = QLabel(icon); ic.setStyleSheet("font-size:18px; background:transparent;")
        lbl = QLabel(label); lbl.setStyleSheet("font-size:11px; font-weight:700; color:#5f6368; letter-spacing:0.5px; background:transparent;")
        top.addWidget(ic); top.addWidget(lbl); top.addStretch()
        lay.addLayout(top)

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH : mm")
        self.time_edit.setButtonSymbols(QTimeEdit.ButtonSymbols.NoButtons)
        self.time_edit.setStyleSheet("""
            QTimeEdit {
                background: transparent;
                border: none;
                font-size: 26px;
                font-weight: 700;
                color: #202124;
                padding: 0;
            }
        """)
        lay.addWidget(self.time_edit)

    def get_time(self): return self.time_edit.time()
    def set_time(self, h, m): self.time_edit.setTime(QTime(h, m))


# ── Game List Item ─────────────────────────────────────────────────────────────
class GameItemWidget(QWidget):
    def __init__(self, name, path, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(12)

        icon = QLabel("🎮")
        icon.setStyleSheet("font-size:20px; background:transparent;")
        icon.setFixedWidth(28)
        lay.addWidget(icon)

        info = QVBoxLayout(); info.setSpacing(1)
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet("font-size:13px; font-weight:600; color:#202124; background:transparent;")
        path_lbl = QLabel(path)
        path_lbl.setStyleSheet("font-size:11px; color:#9aa0a6; background:transparent;")
        path_lbl.setMaximumWidth(300)
        info.addWidget(name_lbl)
        info.addWidget(path_lbl)
        lay.addLayout(info)
        lay.addStretch()


# ── Main Window ────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.setWindowTitle("GameLock Pro")
        self.setMinimumSize(560, 720)
        self.setStyleSheet("""
            QMainWindow { background: #f8f9fa; }
            QWidget#root { background: #f8f9fa; }
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent; width: 6px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #dadce0; border-radius: 3px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        self._build_ui()
        self._build_tray()

        self.worker = LockWorker(lambda: self.cfg)
        self.worker.status_signal.connect(self._on_status)
        self.worker.start()

        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self._refresh_timer)
        self.clock_timer.start(1000)
        self._refresh_timer()

    def _build_ui(self):
        root = QWidget(); root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)

        # ── Top App Bar ──
        bar = QFrame()
        bar.setFixedHeight(64)
        bar.setStyleSheet("background: white; border-bottom: 1px solid #e8eaed;")
        bar_lay = QHBoxLayout(bar); bar_lay.setContentsMargins(24, 0, 24, 0)

        logo = QLabel("🎯")
        logo.setStyleSheet("font-size:22px;")
        title = QLabel("GameLock Pro")
        title.setStyleSheet("font-size:18px; font-weight:700; color:#202124;")
        bar_lay.addWidget(logo); bar_lay.addWidget(title); bar_lay.addStretch()

        self.status_chip = QLabel("● LOCKED")
        self.status_chip.setFixedHeight(32)
        self.status_chip.setStyleSheet("""
            background: #fce8e6; color: #c5221f;
            border-radius: 16px; padding: 0 14px;
            font-size: 12px; font-weight: 700;
        """)
        bar_lay.addWidget(self.status_chip)
        outer.addWidget(bar)

        # ── Scrollable body ──
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        body = QWidget(); body.setStyleSheet("background: #f8f9fa;")
        lay = QVBoxLayout(body); lay.setContentsMargins(20, 20, 20, 20); lay.setSpacing(16)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        # ── Status Hero Card ──
        hero = Card(elevated=True)
        hero.setStyleSheet("""
            QFrame#card {
                background: white;
                border-radius: 20px;
                border: none;
            }
        """)
        hero_lay = QHBoxLayout(hero); hero_lay.setContentsMargins(24,24,24,24); hero_lay.setSpacing(20)

        self.status_ring = StatusRing()
        hero_lay.addWidget(self.status_ring)

        info_col = QVBoxLayout(); info_col.setSpacing(4)
        next_lbl = QLabel("NEXT EVENT")
        next_lbl.setStyleSheet("font-size:10px; font-weight:700; color:#9aa0a6; letter-spacing:1px;")
        self.timer_label = QLabel("--:--:--")
        self.timer_label.setStyleSheet("font-size:32px; font-weight:700; color:#202124; font-family: 'Consolas';")
        self.event_label = QLabel("Calculating...")
        self.event_label.setStyleSheet("font-size:13px; color:#5f6368;")

        self.unlock_info = QLabel()
        self.unlock_info.setStyleSheet("font-size:12px; color:#9aa0a6; margin-top:8px;")
        self._update_schedule_info()

        info_col.addWidget(next_lbl)
        info_col.addWidget(self.timer_label)
        info_col.addWidget(self.event_label)
        info_col.addStretch()
        info_col.addWidget(self.unlock_info)
        hero_lay.addLayout(info_col)
        lay.addWidget(hero)

        # ── Schedule Card ──
        sched = Card(elevated=True)
        sched.setStyleSheet("QFrame#card { background: white; border-radius: 20px; border: none; }")
        sl = QVBoxLayout(sched); sl.setContentsMargins(24,20,24,24); sl.setSpacing(16)

        sh = QHBoxLayout()
        stitle = QLabel("Schedule")
        stitle.setStyleSheet("font-size:15px; font-weight:700; color:#202124;")
        sh.addWidget(stitle); sh.addStretch()
        sl.addLayout(sh)

        times_row = QHBoxLayout(); times_row.setSpacing(12)
        self.unlock_card = TimeCard("UNLOCK TIME", "🔓", "#e6f4ea")
        self.unlock_card.set_time(self.cfg["unlock_hour"], self.cfg["unlock_minute"])
        self.lock_card   = TimeCard("LOCK TIME",   "🔒", "#fce8e6")
        self.lock_card.set_time(self.cfg["lock_hour"], self.cfg["lock_minute"])
        times_row.addWidget(self.unlock_card)
        times_row.addWidget(self.lock_card)
        sl.addLayout(times_row)

        save_btn = FilledButton("Save Schedule", "#1a73e8")
        save_btn.setFixedWidth(160)
        save_btn.clicked.connect(self._save_schedule)
        sl.addWidget(save_btn)
        lay.addWidget(sched)

        # ── Games Card ──
        gc = Card(elevated=True)
        gc.setStyleSheet("QFrame#card { background: white; border-radius: 20px; border: none; }")
        gl = QVBoxLayout(gc); gl.setContentsMargins(24,20,24,20); gl.setSpacing(14)

        gh = QHBoxLayout()
        gtitle = QLabel("Monitored Games")
        gtitle.setStyleSheet("font-size:15px; font-weight:700; color:#202124;")
        self.game_count = QLabel(f"{len(self.cfg['games'])} games")
        self.game_count.setStyleSheet("font-size:12px; color:#9aa0a6; background:#f1f3f4; padding:2px 10px; border-radius:10px;")
        gh.addWidget(gtitle); gh.addStretch(); gh.addWidget(self.game_count)
        gl.addLayout(gh)

        self.game_list = QListWidget()
        self.game_list.setSpacing(2)
        self.game_list.setMinimumHeight(140)
        self.game_list.setStyleSheet("""
            QListWidget {
                background: #f8f9fa;
                border: 1.5px solid #e8eaed;
                border-radius: 12px;
                padding: 4px;
                outline: none;
            }
            QListWidget::item {
                border-radius: 8px;
                border: none;
            }
            QListWidget::item:selected {
                background: #e8f0fe;
            }
            QListWidget::item:hover {
                background: #f1f3f4;
            }
        """)
        self._reload_game_list()
        gl.addWidget(self.game_list)

        gbtn = QHBoxLayout(); gbtn.setSpacing(8)
        add_btn = FilledButton("+ Add Game", "#1a73e8")
        add_btn.setFixedWidth(130); add_btn.clicked.connect(self._add_game)
        rem_btn = FilledButton("Remove", "#ea4335")
        rem_btn.setFixedWidth(110); rem_btn.clicked.connect(self._remove_game)
        gbtn.addWidget(add_btn); gbtn.addWidget(rem_btn); gbtn.addStretch()
        gl.addLayout(gbtn)
        lay.addWidget(gc)

        # ── Settings Row ──
        settings_row = QHBoxLayout(); settings_row.setSpacing(12)
        pw_btn = OutlinedButton("🔑  Change Password")
        pw_btn.clicked.connect(self._change_password)
        quit_btn = OutlinedButton("⏹  Quit App")
        quit_btn.clicked.connect(self._quit)
        settings_row.addWidget(pw_btn); settings_row.addWidget(quit_btn); settings_row.addStretch()
        lay.addLayout(settings_row)

        # ── Footer ──
        footer = QLabel("GameLock Pro  •  Checks every 5 seconds  •  Default password: gamelock123")
        footer.setStyleSheet("font-size:11px; color:#bdc1c6; text-align:center;")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(footer)
        lay.addStretch()

    def _build_tray(self):
        pix = QPixmap(16, 16); pix.fill(QColor("#1a73e8"))
        self.tray = QSystemTrayIcon(QIcon(pix), self)
        menu = QMenu()
        menu.addAction("Show GameLock", self.show)
        menu.addSeparator()
        menu.addAction("Quit", self._quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self.show() if r == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        self.tray.show()

    def _reload_game_list(self):
        self.game_list.clear()
        for g in self.cfg["games"]:
            item = QListWidgetItem(self.game_list)
            w = GameItemWidget(Path(g).name, g)
            item.setSizeHint(w.sizeHint())
            self.game_list.addItem(item)
            self.game_list.setItemWidget(item, w)
        if hasattr(self, "game_count"):
            self.game_count.setText(f"{len(self.cfg['games'])} games")

    def _update_schedule_info(self):
        uh, um = self.cfg["unlock_hour"], self.cfg["unlock_minute"]
        lh, lm = self.cfg["lock_hour"],   self.cfg["lock_minute"]
        txt = f"Unlocks {uh:02d}:{um:02d}  →  Locks {lh:02d}:{lm:02d}"
        if hasattr(self, "unlock_info"):
            self.unlock_info.setText(txt)

    def _on_status(self, allowed):
        if allowed:
            self.status_chip.setText("● UNLOCKED")
            self.status_chip.setStyleSheet("background:#e6f4ea; color:#137333; border-radius:16px; padding:0 14px; font-size:12px; font-weight:700;")
        else:
            self.status_chip.setText("● LOCKED")
            self.status_chip.setStyleSheet("background:#fce8e6; color:#c5221f; border-radius:16px; padding:0 14px; font-size:12px; font-weight:700;")
        self.status_ring.set_status(not allowed)

    def _refresh_timer(self):
        now = datetime.now()
        unlock = now.replace(hour=self.cfg["unlock_hour"], minute=self.cfg["unlock_minute"], second=0, microsecond=0)
        lock   = now.replace(hour=self.cfg["lock_hour"],   minute=self.cfg["lock_minute"],   second=0, microsecond=0)
        candidates = []
        for t, label in [(unlock, "Unlocks at"), (lock, "Locks at")]:
            if t <= now:
                from datetime import timedelta
                t = t + timedelta(days=1)
            candidates.append((t, label))
        candidates.sort()
        nxt, lbl = candidates[0]
        delta = nxt - now
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m, s   = divmod(rem, 60)
        self.timer_label.setText(f"{h:02d}:{m:02d}:{s:02d}")
        self.event_label.setText(f"{lbl} {nxt.strftime('%I:%M %p')}")
        self.status_ring.set_timer(f"{h:02d}:{m:02d}:{s:02d}", lbl)

    def _require_password(self, prompt="Enter your password to continue"):
        dlg = PasswordDialog(self, prompt=prompt)
        if dlg.exec() != QDialog.DialogCode.Accepted: return False
        if hash_pw(dlg.value()) != self.cfg["password"]:
            QMessageBox.warning(self, "Wrong Password", "Incorrect password. Please try again.")
            return False
        return True

    def _save_schedule(self):
        if not self._require_password("Enter password to change the schedule:"): return
        ut = self.unlock_card.get_time()
        lt = self.lock_card.get_time()
        self.cfg["unlock_hour"] = ut.hour(); self.cfg["unlock_minute"] = ut.minute()
        self.cfg["lock_hour"]   = lt.hour(); self.cfg["lock_minute"]   = lt.minute()
        save_config(self.cfg)
        self._update_schedule_info()
        QMessageBox.information(self, "Saved", "✅  Schedule updated successfully!")

    def _add_game(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Game Executable", "", "Executable Files (*.exe)")
        if path and path not in self.cfg["games"]:
            self.cfg["games"].append(path)
            save_config(self.cfg)
            self._reload_game_list()

    def _remove_game(self):
        row = self.game_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select a Game", "Please select a game from the list first.")
            return
        if not self._require_password("Enter password to remove this game:"): return
        self.cfg["games"].pop(row)
        save_config(self.cfg)
        self._reload_game_list()

    def _change_password(self):
        if not self._require_password("Enter your current password:"): return
        dlg2 = PasswordDialog(self, title="New Password", prompt="Choose a new password (min 6 characters):")
        if dlg2.exec() != QDialog.DialogCode.Accepted: return
        if len(dlg2.value()) < 6:
            QMessageBox.warning(self, "Too Short", "Password must be at least 6 characters."); return
        self.cfg["password"] = hash_pw(dlg2.value())
        save_config(self.cfg)
        QMessageBox.information(self, "Done", "✅  Password changed successfully!")

    def _quit(self):
        if not self._require_password("Enter password to quit GameLock Pro:"): return
        self.worker.stop()
        QApplication.quit()

    def closeEvent(self, e):
        e.ignore()
        self.hide()
        self.tray.showMessage(
            "GameLock Pro",
            "Still running in the background. Right-click the tray icon to quit.",
            QSystemTrayIcon.MessageIcon.Information, 2500
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
