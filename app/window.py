
import json
import math
import time
from datetime import datetime
from pathlib import Path

import psutil
from PyQt5.QtCore import QEvent, QLocale, QPointF, QRectF, QSettings, Qt, QTimer, QUrl
from PyQt5.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient,
)
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QProgressBar,
    QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from .i18n import DEFAULTS, LANGS, get_lang, set_lang, tr, wmo

try:
    from PyQt5.QtMultimedia import QCamera, QCameraInfo, QCameraViewfinderSettings
    from PyQt5.QtMultimediaWidgets import QCameraViewfinder
except ImportError:  
    QCamera = None

BG, PANEL, PANEL2, LINE = "#050a10", "#0a1520", "#0d1c2a", "#12354a"
CYAN, CYAN2, TEXT, MUTE = "#00b4d8", "#48cae4", "#e6f1f7", "#6f8ea3"
OK, BAD = "#22c55e", "#ef4444"
MONO = "Consolas, 'JetBrains Mono', 'DejaVu Sans Mono', monospace"
SANS = "'Segoe UI', 'Outfit', 'Noto Sans', 'Helvetica Neue', Arial, sans-serif"

MAX_MSGS = 150  

QSS = f"""
QMainWindow, QDialog {{ background:{BG}; }}
QWidget {{ color:{TEXT}; font-family:{SANS}; font-size:13px; }}
#header {{ border-bottom:1px solid {LINE}; }}
#brand {{ color:{CYAN2}; font:700 20px {MONO}; letter-spacing:3px; }}
#badge {{ padding:3px 10px; border-radius:11px; background:#0b2a1c; color:{OK}; border:1px solid #14532d; font-size:12px; }}
#badge[off="true"] {{ background:#2a0e0e; color:{BAD}; border-color:#5b1b1b; }}
#pill, #gear {{ background:{PANEL}; border:1px solid {LINE}; border-radius:12px; padding:8px 16px; font:500 14px {MONO}; }}
#gear {{ font-size:18px; padding:0; color:{CYAN2}; }}
#card {{ background:{PANEL}; border:1px solid {LINE}; border-radius:16px; }}
#cardHead {{ background:{PANEL2}; border-bottom:1px solid {LINE}; border-top-left-radius:16px; border-top-right-radius:16px; }}
#cardTitle {{ color:{CYAN2}; font-weight:600; font-size:14px; }}
#tile {{ background:#08121b; border-radius:10px; }}
#tileKey {{ color:{CYAN2}; font-size:11px; }}
#tileVal {{ font:500 13px {MONO}; }}
#mute {{ color:{MUTE}; font-size:12px; }}
#temp {{ font:500 28px {MONO}; }}
#cityName {{ color:{CYAN2}; }}
#upTime {{ font:12px {MONO}; }}
QProgressBar {{ background:#1b2a36; border:0; border-radius:2px; max-height:5px; min-height:5px; }}
QProgressBar::chunk {{ background:{CYAN}; border-radius:2px; }}
#tool {{ background:transparent; border:0; color:{MUTE}; font-size:15px; padding:2px 6px; }}
#tool:hover {{ color:{CYAN2}; }}
#chip {{ background:{PANEL2}; border:1px solid {LINE}; border-radius:12px; padding:4px 12px; font-size:12px; }}
#chip:hover {{ border-color:{CYAN}; }}
#status {{ background:#0a2030; color:{CYAN2}; border-radius:10px; padding:8px 18px; font-weight:500; }}
#title {{ font:700 28px {MONO}; letter-spacing:4px; }}
#chatTitle {{ font:600 17px {SANS}; }}
#bubble {{ background:{PANEL2}; border:1px solid {LINE}; border-radius:16px; padding:12px 16px; font-weight:500; }}
#bubble[role="user"] {{ background:#0c3a50; border-color:#14607f; }}
#bubble[role="err"] {{ background:#1d0d0d; border-color:#5b1b1b; color:#fca5a5; }}
#stamp {{ color:{MUTE}; font-size:10px; }}
#cam {{ background:#07111a; border:1px solid {LINE}; border-radius:12px; color:{MUTE}; }}
#sep {{ background:{LINE}; }}
#host {{ background:transparent; }}
QLineEdit {{ background:#07111a; border:1px solid {LINE}; border-radius:10px; padding:9px 12px; selection-background-color:{CYAN}; }}
#input {{ border:1px solid {CYAN}; border-top-right-radius:0; border-bottom-right-radius:0; }}
#send {{ background:#0e5a75; border:0; border-top-right-radius:10px; border-bottom-right-radius:10px; padding:0 18px; color:white; font-size:16px; }}
#send:hover {{ background:{CYAN}; }}
#send:disabled, #input:disabled {{ background:#0a1f2b; color:{MUTE}; }}
QScrollArea {{ border:0; background:transparent; }}
QScrollBar:vertical {{ width:8px; background:transparent; }}
QScrollBar::handle:vertical {{ background:{LINE}; border-radius:4px; min-height:24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height:0; }}
QPushButton {{ background:{PANEL2}; border:1px solid {LINE}; border-radius:10px; padding:7px 18px; }}
QPushButton:hover {{ border-color:{CYAN}; }}
QComboBox {{ background:#07111a; border:1px solid {LINE}; border-radius:10px; padding:8px 12px; }}
QComboBox QAbstractItemView {{ background:{PANEL}; selection-background-color:#0e5a75; }}
"""


def font(size=13, weight=QFont.Normal, mono=False):
    f = QFont("Consolas" if mono else "Segoe UI", size)
    f.setWeight(weight)
    return f


def _ring(p: QPainter, c: QPointF, r: float, k: float, color: str,
          width: float = 1.5, fill: str | None = None, alpha: int = 255) -> None:
    col = QColor(color)
    col.setAlpha(alpha)
    p.setPen(QPen(col, width))
    p.setBrush(QBrush(QColor(fill)) if fill else Qt.NoBrush)
    p.drawEllipse(c, r * k, r * k)


class Orb(QWidget):

    def __init__(self) -> None:
        super().__init__()
        self.state = "idle"
        self._t0 = time.monotonic()
        self._paused = False
        self._bg: QPixmap | None = None
        self._bg_key = None
        self.setMinimumSize(240, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._timer = QTimer(self)
        self._timer.setInterval(40)  # 25 к/с
        self._timer.timeout.connect(self.update)

    def set_state(self, state: str) -> None:
        if state == self.state:
            return
        self.state = state
        self._sync()
        self.update()

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        self._sync()

    def _sync(self) -> None:
        run = self.state != "idle" and not self._paused and self.isVisible()
        if run and not self._timer.isActive():
            self._timer.start()
        elif not run and self._timer.isActive():
            self._timer.stop()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._sync()

    def hideEvent(self, e) -> None:
        super().hideEvent(e)
        self._sync()

    def _geom(self):
        c = QPointF(self.width() / 2, self.height() / 2)
        r = min(self.width(), self.height()) / 2 - 6
        return c, r

    def _render_bg(self) -> None:
        dpr = self.devicePixelRatioF()
        pm = QPixmap(max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        c, r = self._geom()
        _ring(p, c, r, 1.0, "#14506a")
        _ring(p, c, r, 0.93, "#14506a", alpha=180)
        _ring(p, c, r, 0.86, "#14506a", alpha=120)
        _ring(p, c, r, 0.75, "#1a6f8f", fill="#0a2536")
        rc = r * 0.4
        g = QRadialGradient(QPointF(c.x() - rc * 0.2, c.y() - rc * 0.3), rc * 1.4)
        g.setColorAt(0, QColor("#1c5a73"))
        g.setColorAt(1, QColor("#0d3347"))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(c, rc, rc)
        p.end()
        self._bg = pm
        self._bg_key = (self.width(), self.height(), dpr)

    def paintEvent(self, _e) -> None:
        key = (self.width(), self.height(), self.devicePixelRatioF())
        if self._bg is None or self._bg_key != key:
            self._render_bg()
        t = time.monotonic() - self._t0
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(0, 0, self._bg)
        c, r = self._geom()

        if self.state == "listening":
            ph = (t % 2.4) / 2.4
            _ring(p, c, r, 0.92 + 0.2 * ph, CYAN, 2, alpha=int(200 * (1 - ph)))

        p.setPen(Qt.NoPen)
        glow = 1.0 if self.state in ("listening", "speaking") else 0.0
        for i in range(5):
            x = c.x() + (i - 2) * 14
            if self.state == "speaking":
                h = 5 + 26 * abs(math.sin(t * 7 + i * 0.9))
                p.setBrush(QColor(CYAN))
                p.drawRoundedRect(QRectF(x - 3, c.y() - h / 2, 6, h), 3, 3)
            else:
                dy = -9 * max(0, math.sin(t * 6 - i * 0.7)) if self.state == "thinking" else 0
                p.setBrush(QColor("#ffffff" if dy < -6 else CYAN))
                p.drawEllipse(QPointF(x, c.y() + dy), 3.2 + glow * 0.6, 3.2 + glow * 0.6)


class IconButton(QPushButton):

    def __init__(self, kind: str) -> None:
        super().__init__()
        self.kind = kind
        self.setCheckable(True)
        self.setFixedSize(64, 64)
        self.setCursor(Qt.PointingHandCursor)

    def set_tip(self, tip: str) -> None:
        self.setToolTip(tip)
        self.setAccessibleName(tip)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        active = self.isChecked() or self.underMouse()
        p.setPen(QPen(QColor(CYAN if active else LINE), 1.5))
        p.setBrush(QColor(PANEL2 if self.isChecked() else PANEL))
        p.drawRoundedRect(QRectF(1, 1, 62, 62), 16, 16)
        p.setPen(QPen(QColor(CYAN2 if self.isChecked() or self.kind != "speaker" else MUTE), 2.2,
                      Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.translate(32, 32)
        if self.kind == "camera":
            p.drawRoundedRect(QRectF(-13, -8, 26, 19), 4, 4)
            p.drawLine(-6, -8, -4, -12); p.drawLine(-4, -12, 4, -12); p.drawLine(4, -12, 6, -8)
            p.drawEllipse(QPointF(0, 2), 5, 5)
        elif self.kind == "mic":
            p.drawRoundedRect(QRectF(-4.5, -13, 9, 17), 4.5, 4.5)
            path = QPainterPath(); path.moveTo(-10, -2); path.arcTo(QRectF(-10, -6, 20, 20), 180, 180)
            p.drawPath(path); p.drawLine(0, 14, 0, 18)
        else:
            poly = QPainterPath(); poly.moveTo(-14, -4); poly.lineTo(-8, -4); poly.lineTo(-1, -10)
            poly.lineTo(-1, 10); poly.lineTo(-8, 4); poly.lineTo(-14, 4); poly.closeSubpath()
            p.drawPath(poly)
            if self.isChecked():
                p.drawArc(QRectF(-4, -6, 12, 12), -50 * 16, 100 * 16)
                p.drawArc(QRectF(-4, -12, 24, 24), -50 * 16, 100 * 16)
            else:
                p.drawLine(4, -6, 14, 6); p.drawLine(14, -6, 4, 6)


def tool_btn(text: str) -> QPushButton:
    b = QPushButton(text, objectName="tool")
    b.setCursor(Qt.PointingHandCursor)
    return b


class Tiles(QWidget):

    def __init__(self, ids: list[str]) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(8)
        self.keys: dict[str, QLabel] = {}
        self.vals: dict[str, QLabel] = {}
        for k in ids:
            t = QFrame(objectName="tile")
            tl = QVBoxLayout(t)
            tl.setContentsMargins(6, 8, 6, 8)
            tl.setSpacing(2)
            key = QLabel(objectName="tileKey", alignment=Qt.AlignCenter)
            val = QLabel("--", objectName="tileVal", alignment=Qt.AlignCenter)
            tl.addWidget(key)
            tl.addWidget(val)
            lay.addWidget(t)
            self.keys[k] = key
            self.vals[k] = val
        self.retranslate()

    def retranslate(self) -> None:
        for k, lab in self.keys.items():
            lab.setText(tr("tile_" + k))

    def set(self, key: str, text: str) -> None:
        self.vals[key].setText(text) 


class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent=None) -> None:
        super().__init__(parent)
        self._lang0 = cfg["lang"]
        self.setWindowTitle(tr("settings"))
        self.setMinimumWidth(380)
        form = QFormLayout(self)
        self.lang = QComboBox()
        for code, name in LANGS.items():
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(self.lang.findData(cfg["lang"]))
        self.city = QLineEdit(cfg["city"])
        self.wake = QLineEdit(cfg["wake"])
        self.model = QLineEdit(cfg["model"])
        self.mode = QComboBox()
        self.mode.addItems(["hybrid", "llm", "actions"])
        self.mode.setCurrentText(cfg["mode"])
        self.tts = QCheckBox(tr("s_tts"))
        self.tts.setChecked(cfg["tts"])
        form.addRow(tr("s_lang"), self.lang)
        form.addRow(tr("s_city"), self.city)
        form.addRow(tr("s_wake"), self.wake)
        form.addRow(tr("s_model"), self.model)
        form.addRow(tr("s_mode"), self.mode)
        form.addRow("", self.tts)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self) -> dict:
        lang = self.lang.currentData()
        city = self.city.text().strip()
        wake = self.wake.text().strip().lower()
        if lang != self._lang0:
            if wake == DEFAULTS[self._lang0]["wake"]:
                wake = ""
            if city == DEFAULTS[self._lang0]["city"]:
                city = ""
        return {
            "lang": lang,
            "city": city or DEFAULTS[lang]["city"],
            "wake": wake or DEFAULTS[lang]["wake"],
            "model": self.model.text().strip() or "llama3.2",
            "mode": self.mode.currentText(),
            "tts": self.tts.isChecked(),
        }


class MainWindow(QMainWindow):
    def __init__(self, worker_cls) -> None:
        super().__init__()
        self.setStyleSheet(QSS)
        self.qs = QSettings("voice_assistant", "gui")

        lang = str(self.qs.value("lang", "") or "")
        if lang not in LANGS:
            lang = "ru" if QLocale.system().name().startswith("ru") else "en"
        set_lang(lang)
        d = DEFAULTS[lang]
        self.cfg = {
            "lang": lang,
            "city": str(self.qs.value("city", d["city"])),
            "wake": str(self.qs.value("wake", d["wake"])),
            "model": str(self.qs.value("model", "llama3.2")),
            "mode": str(self.qs.value("mode", "hybrid")),
            "tts": self.qs.value("tts", True, type=bool),
        }

        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1480, screen.width() - 40), min(880, screen.height() - 60))
        self.setMinimumSize(1100, 640)

        self.history: list[tuple[str, str, str]] = []
        self.started = time.monotonic()
        self.n_msgs = 0
        self.net = QNetworkAccessManager(self)
        self.camera = None
        self.viewfinder = None
        self._tr: list = []           
        self._online = False
        self._state = ("thinking", "st_loading")
        self._lat: float | None = None
        self._wx: dict | None = None
        self._city_name = ""
        self._wx_busy = False
        self._stick = True            
        self._disk = None
        self._disk_ts = 0.0
        self._root_path = Path.home().anchor or "/"

        self._build()
        self.retranslate()

        self.worker = worker_cls(self.cfg)
        self.worker.state.connect(self.on_state)
        self.worker.message.connect(self.add_message)
        self.worker.error.connect(self.on_error)
        self.worker.latency.connect(self.on_latency)
        self.worker.ready.connect(lambda: self.set_online(True))
        self.worker.loading.connect(lambda: self.set_online(False))
        self.worker.listening_changed.connect(self.b_mic.setChecked)
        self.set_online(False)
        self.worker.start()

        self._ui_timers = []
        for ms, fn in ((1000, self.tick), (3000, self.update_stats)):
            t = QTimer(self)
            t.setInterval(ms)
            t.timeout.connect(fn)
            t.start()
            self._ui_timers.append(t)
        wx_timer = QTimer(self)
        wx_timer.setInterval(600_000)
        wx_timer.timeout.connect(self.fetch_weather)
        wx_timer.start()

        psutil.cpu_percent(None)  
        self.tick()
        self.update_stats()
        self.fetch_weather()
        self.add_message("assistant", tr("greeting"), log=False)

    def _bind(self, setter, key: str) -> None:
        self._tr.append((setter, key))

    def _bind_tip(self, w, key: str) -> None:
        def setter(text, w=w):
            w.setToolTip(text)
            w.setAccessibleName(text)
        self._tr.append((setter, key))

    def retranslate(self) -> None:
        self.setWindowTitle(tr("title"))
        for setter, key in self._tr:
            setter(tr(key))
        for tiles in (self.sys_tiles, self.w_tiles, self.up_tiles):
            tiles.retranslate()
        self.set_online(self._online)
        self.on_state(*self._state)
        self._render_latency()
        self._render_weather()
        self.update_stats()

    def _card(self, title_key: str, tool=None, extra=None):
        card = QFrame(objectName="card")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        head = QFrame(objectName="cardHead")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(14, 8, 10, 8)
        title = QLabel(objectName="cardTitle")
        self._bind(title.setText, title_key)
        hl.addWidget(title)
        hl.addStretch()
        for w in (extra, tool):
            if w:
                hl.addWidget(w)
        outer.addWidget(head)
        body = QVBoxLayout()
        body.setContentsMargins(12, 12, 12, 12)
        body.setSpacing(6)
        outer.addLayout(body)
        return card, body

    def _bar(self, key: str):
        row = QHBoxLayout()
        name = QLabel(objectName="mute")
        self._bind(name.setText, key)
        val = QLabel("--", objectName="mute", alignment=Qt.AlignRight)
        row.addWidget(name)
        row.addWidget(val)
        bar = QProgressBar(textVisible=False, maximum=100)
        return row, val, bar

    def _build(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QFrame(objectName="header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 12, 20, 12)
        brand = QLabel(objectName="brand")
        self._bind(brand.setText, "brand")
        hl.addWidget(brand)
        self.badge = QLabel(objectName="badge")
        hl.addWidget(self.badge)
        hl.addStretch()
        self.clock = QLabel(objectName="pill")
        hl.addWidget(self.clock)
        hl.addStretch()
        self.h_weather = QLabel("--", objectName="pill")
        hl.addWidget(self.h_weather)
        gear = QPushButton("⚙", objectName="gear", cursor=Qt.PointingHandCursor)
        self._bind_tip(gear, "settings")
        gear.setFixedSize(42, 42)
        gear.clicked.connect(self.open_settings)
        hl.addWidget(gear)
        outer.addWidget(header)

        main = QHBoxLayout()
        main.setContentsMargins(20, 20, 20, 20)
        main.setSpacing(20)
        outer.addLayout(main, 1)

        left_w = QWidget()
        left = QVBoxLayout(left_w)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(14)

        r = tool_btn("⟳")
        r.clicked.connect(self.update_stats)
        self._bind_tip(r, "refresh")
        card, b = self._card("system", r)
        row, self.cpu_t, self.cpu_b = self._bar("cpu_name")
        row2, self.ram_t, self.ram_b = self._bar("mem_name")
        b.addLayout(row); b.addWidget(self.cpu_b)
        b.addLayout(row2); b.addWidget(self.ram_b)
        self.sys_tiles = Tiles(["cpu", "ram", "disk"])
        b.addWidget(self.sys_tiles)
        left.addWidget(card)

        r = tool_btn("⟳")
        r.clicked.connect(self.fetch_weather)
        self._bind_tip(r, "refresh")
        card, b = self._card("weather", r)
        self.w_temp = QLabel("--", objectName="temp")
        self.w_city = QLabel("—", objectName="cityName")
        self.w_desc = QLabel("", objectName="mute")
        for w in (self.w_temp, self.w_city, self.w_desc):
            b.addWidget(w)
        self.w_tiles = Tiles(["hum", "wind", "feels"])
        b.addWidget(self.w_tiles)
        left.addWidget(card)

        self.cam_btn = tool_btn("⏻")
        self.cam_btn.clicked.connect(self.toggle_camera)
        self._bind_tip(self.cam_btn, "cam_toggle")
        card, b = self._card("camera", self.cam_btn)
        self.cam_stack = QStackedWidget(objectName="cam")
        self.cam_stack.setFixedHeight(190)
        self.cam_off = QLabel(alignment=Qt.AlignCenter)
        self._bind(self.cam_off.setText, "cam_off")
        self.cam_stack.addWidget(self.cam_off)
        b.addWidget(self.cam_stack)
        left.addWidget(card)

        self.up_t = QLabel("00:00:00", objectName="upTime")
        card, b = self._card("uptime", extra=self.up_t)
        self.up_tiles = Tiles(["msgs", "lat"])
        b.addWidget(self.up_tiles)
        row3, self.load_t, self.load_b = self._bar("load")
        b.addLayout(row3); b.addWidget(self.load_b)
        left.addWidget(card)
        left.addStretch()
        left_w.setFixedWidth(360)
        main.addWidget(left_w)

        center = QVBoxLayout()
        center.addStretch()
        self.orb = Orb()
        center.addWidget(self.orb, 3)
        title = QLabel(objectName="title", alignment=Qt.AlignCenter)
        self._bind(title.setText, "brand")
        center.addWidget(title)
        self.status = QLabel(objectName="status")
        sr = QHBoxLayout(); sr.addStretch(); sr.addWidget(self.status); sr.addStretch()
        center.addLayout(sr)
        ctr = QHBoxLayout(); ctr.setSpacing(40); ctr.addStretch()
        self.b_cam = IconButton("camera")
        self.b_mic = IconButton("mic")
        self.b_tts = IconButton("speaker")
        self._bind(self.b_cam.set_tip, "camera")
        self._bind(self.b_mic.set_tip, "mic_tip")
        self._bind(self.b_tts.set_tip, "tts_tip")
        self.b_tts.setChecked(self.cfg["tts"])
        self.b_cam.clicked.connect(self.toggle_camera)
        self.b_mic.clicked.connect(self.toggle_mic)
        self.b_tts.clicked.connect(self.toggle_tts)
        for w in (self.b_cam, self.b_mic, self.b_tts):
            ctr.addWidget(w)
        ctr.addStretch()
        center.addSpacing(18); center.addLayout(ctr); center.addStretch()
        main.addLayout(center, 1)

        # чат
        chat = QFrame(objectName="card")
        chat.setFixedWidth(420)
        cl = QVBoxLayout(chat)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        ch = QHBoxLayout(); ch.setContentsMargins(16, 12, 14, 12)
        chat_title = QLabel(objectName="chatTitle")
        self._bind(chat_title.setText, "chat")
        ch.addWidget(chat_title); ch.addStretch()
        for key, fn in (("clear", self.clear_chat), ("export", self.export_chat)):
            btn = QPushButton(objectName="chip", cursor=Qt.PointingHandCursor)
            self._bind(btn.setText, key)
            btn.clicked.connect(fn)
            ch.addWidget(btn)
        cl.addLayout(ch)
        sep = QFrame(objectName="sep"); sep.setFixedHeight(1)
        cl.addWidget(sep)
        self.scroll = QScrollArea(widgetResizable=True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget(objectName="host")
        self.msgs = QVBoxLayout(host)
        self.msgs.setContentsMargins(16, 16, 16, 16); self.msgs.setSpacing(12)
        self.msgs.addStretch()
        self.scroll.setWidget(host)
        sb = self.scroll.verticalScrollBar()
        sb.rangeChanged.connect(lambda _lo, hi: self._stick and sb.setValue(hi))
        sb.valueChanged.connect(lambda v: setattr(self, "_stick", v >= sb.maximum() - 8))
        cl.addWidget(self.scroll, 1)
        inp = QHBoxLayout(); inp.setContentsMargins(14, 12, 14, 14); inp.setSpacing(0)
        self.input = QLineEdit(objectName="input")
        self._bind(self.input.setPlaceholderText, "placeholder")
        self.input.returnPressed.connect(self.send_text)
        self.send_btn = QPushButton("➤", objectName="send", cursor=Qt.PointingHandCursor)
        self._bind_tip(self.send_btn, "send")
        self.send_btn.clicked.connect(self.send_text)
        self.input.setMinimumHeight(42)
        self.send_btn.setFixedSize(54, 42)
        inp.addWidget(self.input); inp.addWidget(self.send_btn)
        cl.addLayout(inp)
        main.addWidget(chat)

    def changeEvent(self, e) -> None:
        if e.type() == QEvent.WindowStateChange and hasattr(self, "_ui_timers"):
            active = not self.isMinimized()
            for t in self._ui_timers:
                t.start() if active else t.stop()
            self.orb.set_paused(not active)
            if active:
                self.tick()
                self.update_stats()
        super().changeEvent(e)

    def set_online(self, ok: bool) -> None:
        self._online = ok
        self.badge.setText(tr("online" if ok else "loading"))
        self.badge.setProperty("off", not ok)
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)
        for w in (self.input, self.send_btn, self.b_mic):
            w.setEnabled(ok)

    def on_state(self, state: str, key: str) -> None:
        self._state = (state, key)
        self.orb.set_state(state)
        self.status.setText(tr(key, self.cfg["wake"]))

    def on_error(self, key: str, detail: str) -> None:
        self.add_message("err", tr(key, detail))

    def on_latency(self, secs: float) -> None:
        self._lat = secs
        self._render_latency()

    def _render_latency(self) -> None:
        if self._lat is not None:
            self.up_tiles.set("lat", f"{self._lat:.1f} {tr('sec')}")

    def tick(self) -> None:
        self.clock.setText(datetime.now().strftime("%H:%M:%S   |   %d.%m.%Y"))
        s = int(time.monotonic() - self.started)
        self.up_t.setText(f"{s // 3600:02}:{s // 60 % 60:02}:{s % 60:02}")

    def update_stats(self) -> None:
        cpu = psutil.cpu_percent(None)
        ram = psutil.virtual_memory()
        now = time.monotonic()
        if self._disk is None or now - self._disk_ts > 30:  
            try:
                self._disk = psutil.disk_usage(self._root_path)
            except OSError:
                pass
            self._disk_ts = now
        gb = 1024 ** 3
        unit = tr("gb")
        self.cpu_b.setValue(int(cpu)); self.cpu_t.setText(f"{cpu:.0f}%")
        self.ram_b.setValue(int(ram.percent)); self.ram_t.setText(f"{ram.used / gb:.1f} {unit}")
        self.sys_tiles.set("cpu", f"{cpu:.0f}%")
        self.sys_tiles.set("ram", f"{ram.percent:.0f}%")
        if self._disk:
            self.sys_tiles.set("disk", f"{self._disk.used // gb}/{self._disk.total // gb} {unit}")
        load = int((cpu + ram.percent) / 2)
        self.load_b.setValue(load)
        level = "load_low" if load < 40 else "load_mid" if load < 75 else "load_high"
        self.load_t.setText(f"{tr(level)} · {load}%")

    def _get_json(self, url: str, cb) -> None:
        req = QNetworkRequest(QUrl(url))
        if hasattr(req, "setTransferTimeout"):
            req.setTransferTimeout(8000)
        reply = self.net.get(req)

        def done():
            try:
                if reply.error():
                    raise RuntimeError(reply.errorString())
                cb(json.loads(bytes(reply.readAll()).decode("utf-8")))
            except Exception:  # noqa: BLE001
                self._wx_busy = False
                self.w_desc.setText(tr("wx_fail"))
            finally:
                reply.deleteLater()

        reply.finished.connect(done)

    def fetch_weather(self) -> None:
        if self._wx_busy:
            return
        self._wx_busy = True
        q = QUrl.toPercentEncoding(self.cfg["city"]).data().decode()
        self._get_json(
            f"https://geocoding-api.open-meteo.com/v1/search?count=1&language={get_lang()}&name={q}",
            self._on_geo,
        )

    def _on_geo(self, data: dict) -> None:
        p = data["results"][0]
        self._city_name = p["name"]
        self._get_json(
            "https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&wind_speed_unit=ms"
            "&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code"
            % (p["latitude"], p["longitude"]),
            self._on_weather,
        )

    def _on_weather(self, data: dict) -> None:
        self._wx = data["current"]
        self._wx_busy = False
        self._render_weather()

    def _render_weather(self) -> None:
        w = self._wx
        if not w:
            return
        t = f"{w['temperature_2m']:.1f}°C"
        self.w_temp.setText(t)
        self.w_city.setText(self._city_name)
        self.h_weather.setText(f"{t}   {self._city_name}")
        self.w_desc.setText(wmo(w["weather_code"]))
        self.w_tiles.set("hum", f"{w['relative_humidity_2m']}%")
        self.w_tiles.set("wind", f"{w['wind_speed_10m']} {tr('ms')}")
        self.w_tiles.set("feels", f"{w['apparent_temperature']:.1f}°C")

    def toggle_camera(self) -> None:
        if not QCamera:
            self.add_message("err", tr("cam_missing"))
            self.b_cam.setChecked(False)
            return
        if self.camera:
            self._stop_camera()
        else:
            info = QCameraInfo.defaultCamera()
            if info.isNull():
                self.add_message("err", tr("cam_none"))
                self.b_cam.setChecked(False)
                return
            if self.viewfinder is None: 
                self.viewfinder = QCameraViewfinder()
                self.cam_stack.addWidget(self.viewfinder)
            cam = QCamera(info)
            cam.setViewfinder(self.viewfinder)
            try: 
                s = QCameraViewfinderSettings()
                s.setResolution(640, 480)
                s.setMaximumFrameRate(20)
                cam.setViewfinderSettings(s)
            except Exception:  # noqa: BLE001
                pass
            try:
                cam.error.connect(lambda *_: self._camera_failed())
            except Exception:  # noqa: BLE001
                pass
            cam.start()
            self.camera = cam
            self.cam_stack.setCurrentIndex(1)
        self.b_cam.setChecked(self.camera is not None)

    def _stop_camera(self) -> None:
        if self.camera:
            self.camera.stop()
            self.camera.deleteLater()
            self.camera = None
        self.cam_stack.setCurrentIndex(0)

    def _camera_failed(self) -> None:
        self._stop_camera()
        self.b_cam.setChecked(False)
        self.add_message("err", tr("cam_error"))

    def toggle_mic(self) -> None:
        self.worker.submit("listen", self.b_mic.isChecked())

    def toggle_tts(self) -> None:
        self.cfg["tts"] = self.b_tts.isChecked()
        self.worker.submit("cfg", {"tts": self.cfg["tts"]})
        self.qs.setValue("tts", self.cfg["tts"])

    def send_text(self) -> None:
        text = self.input.text().strip()
        if text:
            self.input.clear()
            self.worker.submit("text", text)

    def add_message(self, role: str, text: str, log: bool = True) -> None:
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        box = QVBoxLayout()
        box.setSpacing(6)
        label = QLabel(text, objectName="bubble", wordWrap=True,
                       textInteractionFlags=Qt.TextSelectableByMouse)
        label.setProperty("role", {"user": "user", "err": "err"}.get(role, "assistant"))
        label.setMaximumWidth(340)
        stamp = QLabel(datetime.now().strftime("%H:%M"), objectName="stamp")
        box.addWidget(label)
        box.addWidget(stamp)
        if role == "user":
            wl.addStretch(); wl.addLayout(box)
            stamp.setAlignment(Qt.AlignRight)
            self._stick = True
        else:
            wl.addLayout(box); wl.addStretch()
        self.msgs.insertWidget(self.msgs.count() - 1, wrap)
        while self.msgs.count() - 1 > MAX_MSGS:  
            item = self.msgs.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if role != "err" and log:
            self.history.append((datetime.now().isoformat(timespec="seconds"), role, text))
        if role == "user":
            self.n_msgs += 1
            self.up_tiles.set("msgs", str(self.n_msgs))

    def clear_chat(self) -> None:
        while self.msgs.count() > 1:
            item = self.msgs.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.history.clear()
        self.n_msgs = 0
        self.up_tiles.set("msgs", "0")

    def export_chat(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, tr("export_title"), "dialog.txt", tr("export_filter"))
        if path:
            names = {"user": tr("you"), "assistant": tr("assistant")}
            Path(path).write_text(
                "\n".join(f"[{t}] {names[r]}: {m}" for t, r, m in self.history), encoding="utf-8")

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.cfg, self)
        if not dlg.exec_():
            return
        old = dict(self.cfg)
        self.cfg.update(dlg.values())
        for k, v in self.cfg.items():
            self.qs.setValue(k, v)
        self.b_tts.setChecked(self.cfg["tts"])
        self.worker.submit("cfg", dict(self.cfg)) 
        if old["lang"] != self.cfg["lang"]:
            set_lang(self.cfg["lang"])
            self.retranslate()
            self._wx = None
            self.fetch_weather()
        elif old["city"] != self.cfg["city"]:
            self.fetch_weather()

    def closeEvent(self, e) -> None:
        self._stop_camera()
        self.hide() 
        self.worker.submit("stop")
        if not self.worker.wait(8000):
            self.worker.terminate()
            self.worker.wait(1000)
        super().closeEvent(e)
