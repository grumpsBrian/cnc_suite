#!/usr/bin/env python3
"""
G-code Sender – CNC Suite Edition
---------------------------------
Brian Wilson (Grump) and AI. Inspired by scorchworks
"""

import sys, os, time, re, queue
from dataclasses import dataclass
from typing import List, Optional
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QProgressBar, QTextEdit, QSplitter, QFileDialog,
    QMessageBox
)

import matplotlib
matplotlib.use("qtagg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# --- theme import ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from themes.theme_utils import apply_theme

# --- optional serial ---
try:
    import serial
    import serial.tools.list_ports as list_ports
    HAS_SERIAL = True
except Exception:
    serial = None
    list_ports = None
    HAS_SERIAL = False

# ---------- utilities ----------
GCODE_LINE_RE = re.compile(r"^\s*([GMT]\d+|;|#|\()")
COMMENT_RE = re.compile(r"\s*(;.*|\(.*\))\s*$")


def is_gcode_line(line: str) -> bool:
    ln = line.strip()
    return bool(ln and not ln.startswith((';', '(')) and GCODE_LINE_RE.match(ln))


def strip_comment(line: str) -> str:
    return COMMENT_RE.sub("", line).strip()


# ---------- serial worker ----------
class SerialWorker(QThread):
    line_received = pyqtSignal(str)
    connected = pyqtSignal(bool)
    error = pyqtSignal(str)

    def __init__(self, port: str, baud: int):
        super().__init__()
        self._port = port
        self._baud = baud
        self._ser = None
        self._running = False
        self._tx = queue.Queue()

    def run(self):
        if not HAS_SERIAL:
            self._running = True
            self.connected.emit(True)
            while self._running:
                try:
                    _ = self._tx.get(timeout=0.1)
                    time.sleep(0.02)
                    self.line_received.emit("ok")
                except queue.Empty:
                    pass
            self.connected.emit(False)
            return

        try:
            self._ser = serial.Serial(self._port, self._baud, timeout=0.05)
            self._running = True
            self.connected.emit(True)
            while self._running:
                try:
                    raw = self._ser.readline()
                    if raw:
                        self.line_received.emit(raw.decode(errors="ignore").strip())
                except Exception:
                    pass
                try:
                    to_send = self._tx.get_nowait()
                    self._ser.write((to_send + "\n").encode())
                except queue.Empty:
                    pass
        except Exception as e:
            self.error.emit(f"Serial open failed: {e}")
            self.connected.emit(False)
        finally:
            if self._ser:
                try: self._ser.close()
                except Exception: pass
            self.connected.emit(False)

    def stop(self):
        self._running = False

    def send_line(self, line: str):
        self._tx.put(line)

    @property
    def is_connected(self):
        return self._running


# ---------- preview ----------
class Preview3D(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111, projection="3d")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.canvas)
        self.tool_marker = None
        self._message("Load a G-code file to view toolpath")

    def _message(self, text, color="gray"):
        self.ax.clear()
        self.ax.text2D(0.5, 0.5, text,
                       transform=self.ax.transAxes,
                       ha="center", va="center", fontsize=10, color=color)
        self.canvas.draw_idle()

    def plot_gcode(self, lines: List[str]):
        """Draw 3-D path and reset tool marker."""
        import numpy as np
        self.ax.clear()
        print(f"[Sender] plot_gcode called with {len(lines) if lines else 0} lines")

        x = y = z = 0.0
        xs, ys, zs = [], [], []

        for ln in lines or []:
            s = strip_comment(ln).upper()
            if not is_gcode_line(s):
                continue
            if s.startswith(("G0", "G1")):
                def get(axis, default):
                    m = re.search(rf"{axis}(-?\d+(\.\d+)?)", s)
                    return float(m.group(1)) if m else default
                nx, ny, nz = get("X", x), get("Y", y), get("Z", z)
                xs += [x, nx, np.nan]
                ys += [y, ny, np.nan]
                zs += [z, nz, np.nan]
                x, y, z = nx, ny, nz

        allx = np.array([v for v in xs if not np.isnan(v)])
        ally = np.array([v for v in ys if not np.isnan(v)])
        allz = np.array([v for v in zs if not np.isnan(v)])

        if len(allx) > 1 and len(ally) > 1 and len(allz) > 1:
            self.ax.plot(xs, ys, zs, linewidth=0.8, color="orange")
            self.ax.set_xlim(float(allx.min()), float(allx.max()))
            self.ax.set_ylim(float(ally.min()), float(ally.max()))
            self.ax.set_zlim(float(allz.min()), float(allz.max()))
            self.ax.set_xlabel("X"); self.ax.set_ylabel("Y"); self.ax.set_zlabel("Z")
            self.ax.set_title("Toolpath Preview")
            self.ax.view_init(35, 45)
            self.ax.grid(True)
        else:
            self._message("No valid toolpath in file")

        # Reset tool marker to origin
        self.tool_marker = self.ax.plot([0], [0], [0],
                                        marker="o", markersize=6,
                                        color="red")[0]
        self.canvas.draw_idle()
        print("[Sender] plot_gcode finished drawing")

    def update_tool(self, x, y, z):
        """Move the red marker to a new position."""
        if self.tool_marker:
            self.tool_marker.remove()
        self.tool_marker = self.ax.plot([x], [y], [z],
                                        marker="o", markersize=6,
                                        color="red")[0]
        self.canvas.draw_idle()


# ---------- state ----------
@dataclass
class SenderState:
    gcode_lines: List[str]
    index: int = 0
    running: bool = False
    paused: bool = False
    ok_to_send: bool = True


# ---------- main window ----------
class GCodeSenderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("G-code Sender – CNC Suite")
        self.resize(1100, 700)
        self.state = SenderState(gcode_lines=[])
        self.worker: Optional[SerialWorker] = None
        self.preview = Preview3D()
        self.log = QTextEdit(readOnly=True)
        self.progress = QProgressBar()
        self.port = QComboBox()
        self.baud = QComboBox(); self.baud.addItems(["115200", "250000", "57600", "9600"])
        self.refresh_btn = QPushButton("Refresh Ports")
        self.connect_btn = QPushButton("Connect")
        self.disconnect_btn = QPushButton("Disconnect"); self.disconnect_btn.setEnabled(False)
        self.open_btn = QPushButton("Open G-code…")
        self.start_btn = QPushButton("Start")
        self.pause_btn = QPushButton("Pause")
        self.stop_btn = QPushButton("Stop")
        self.feed_hold_btn = QPushButton("Feed Hold (!)")
        self.resume_btn = QPushButton("Resume (~)")
        self.unlock_btn = QPushButton("Unlock ($X)")
        self.home_btn = QPushButton("Home ($H)")

        self._build_ui()
        self._connect_signals()
        self.refresh_ports()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def _build_ui(self):
        left = QWidget(); left_layout = QVBoxLayout(left)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Port:")); bar.addWidget(self.port)
        bar.addWidget(QLabel("Baud:")); bar.addWidget(self.baud)
        bar.addWidget(self.refresh_btn)
        bar.addWidget(self.connect_btn); bar.addWidget(self.disconnect_btn)
        bar.addStretch(1); bar.addWidget(self.open_btn)
        left_layout.addLayout(bar)
        left_layout.addWidget(self.preview)

        right = QWidget(); rv = QVBoxLayout(right)
        rv.addWidget(QLabel("Log:")); rv.addWidget(self.log)
        ctrl = QHBoxLayout()
        for w in (
            self.start_btn, self.pause_btn, self.stop_btn,
            self.feed_hold_btn, self.resume_btn, self.unlock_btn, self.home_btn
        ):
            ctrl.addWidget(w)
        rv.addLayout(ctrl); rv.addWidget(self.progress)

        splitter = QSplitter(); splitter.addWidget(left); splitter.addWidget(right)
        splitter.setStretchFactor(0, 3); splitter.setStretchFactor(1, 2)
        self.setCentralWidget(splitter)

    def _connect_signals(self):
        self.refresh_btn.clicked.connect(self.refresh_ports)
        self.connect_btn.clicked.connect(self.connect_serial)
        self.disconnect_btn.clicked.connect(self.disconnect_serial)
        self.open_btn.clicked.connect(self.open_gcode)
        self.start_btn.clicked.connect(self.start_sending)
        self.pause_btn.clicked.connect(self.pause_sending)
        self.stop_btn.clicked.connect(self.stop_sending)
        self.feed_hold_btn.clicked.connect(lambda: self.send_immediate("!"))
        self.resume_btn.clicked.connect(lambda: self.send_immediate("~"))
        self.unlock_btn.clicked.connect(lambda: self.send_immediate("$X"))
        self.home_btn.clicked.connect(lambda: self.send_immediate("$H"))

    # --- serial ---
    def connect_serial(self):
        port = self.port.currentText() or "SIMULATED"
        baud = int(self.baud.currentText())
        if not self.worker or not self.worker.isRunning():
            self.worker = SerialWorker(port, baud)
            self.worker.line_received.connect(self.on_line_received)
            self.worker.connected.connect(self.on_connected)
            self.worker.error.connect(lambda e: self.log.append(f"ERROR: {e}"))
            self.worker.start()
            self.log.append(f"Connecting to {port} @ {baud}…")
        self.connect_btn.setEnabled(False); self.disconnect_btn.setEnabled(True)

    def disconnect_serial(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop(); self.log.append("Serial disconnected.")
        self.connect_btn.setEnabled(True); self.disconnect_btn.setEnabled(False)

    def on_connected(self, ok: bool):
        self.log.append("Connected." if ok else "Disconnected.")

    # --- ports ---
    def refresh_ports(self):
        self.port.clear()
        ports = []
        if HAS_SERIAL and list_ports:
            try: ports = [p.device for p in list_ports.comports()]
            except Exception: ports = []
        if not ports: ports = ["SIMULATED"]
        self.port.addItems(ports)

    # --- gcode file ---
    def open_gcode(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open G-code", "", "G-code (*.gcode *.nc *.ngc *.txt);;All files (*)"
        )
        if not path: return
        try:
            with open(path, "r", errors="ignore") as f:
                raw = f.read().splitlines()
            lines = [strip_comment(l) for l in raw if is_gcode_line(l)]
            self.state = SenderState(gcode_lines=lines)
            self.preview.plot_gcode(lines)
            self.log.clear()
            self.log.append(f"Loaded {len(lines)} G-code lines from {os.path.basename(path)}")
            self.progress.setRange(0, len(lines)); self.progress.setValue(0)
            self._update_buttons()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load G-code: {e}")

    # --- controls ---
    def start_sending(self):
        if not self.worker or not self.worker.is_connected:
            QMessageBox.warning(self, "Not connected", "Connect to a port first."); return
        if not self.state.gcode_lines:
            QMessageBox.warning(self, "No G-code", "Load a G-code file first."); return
        self.state.running = True; self.state.paused = False; self.state.ok_to_send = True
        self.timer.start(1); self._update_buttons()

    def pause_sending(self):
        if not self.state.running: return
        self.state.paused = not self.state.paused; self._update_buttons()

    def stop_sending(self):
        self.state.running = False; self.state.paused = False; self.state.ok_to_send = True
        if self.worker: self.worker.stop()
        self.timer.stop(); self._update_buttons()

    def send_immediate(self, cmd: str):
        if self.worker and self.worker.is_connected:
            self.worker.send_line(cmd); self.log.append(f"Sent immediate: {cmd}")
        else:
            self.log.append(f"(sim) Sent immediate: {cmd}")

    # --- tick loop with moving tool ---
    def _tick(self):
        if not self.state.running or self.state.paused: return
        if not self.state.ok_to_send: return
        if self.state.index >= len(self.state.gcode_lines):
            self.log.append("Completed."); self.stop_sending(); return

        line = self.state.gcode_lines[self.state.index]
        if self.worker and self.worker.is_connected:
            self.worker.send_line(line)
        self.log.append(f"→ {line}")

        # --- tool marker update ---
        m = re.findall(r"[XYZ]-?\d+\.?\d*", line.upper())
        coords = {c[0]: float(c[1:]) for c in m}
        x = coords.get("X", 0.0)
        y = coords.get("Y", 0.0)
        z = coords.get("Z", 0.0)
        if hasattr(self.preview, "update_tool"):
            self.preview.update_tool(x, y, z)

        self.state.ok_to_send = False
        self.state.index += 1
        self.progress.setValue(self.state.index)
        if not self.worker or not self.worker.is_connected:
            QTimer.singleShot(20, lambda: self.on_line_received("ok"))

    def on_line_received(self, line: str):
        self.log.append(f"← {line}")
        if line.strip().lower().startswith("ok"):
            self.state.ok_to_send = True

    def _update_buttons(self):
        running, paused = self.state.running, self.state.paused
        self.start_btn.setEnabled(not running and bool(self.state.gcode_lines))
        self.pause_btn.setEnabled(running)
        self.pause_btn.setText("Resume" if paused else "Pause")
        self.stop_btn.setEnabled(running)


# ---------- entry ----------
if __name__ == "__main__":
    theme, color = "dark", "grey"
    if "--theme" in sys.argv:
        i = sys.argv.index("--theme")
        if i + 1 < len(sys.argv): theme = sys.argv[i + 1].lower()
    if "--color" in sys.argv:
        i = sys.argv.index("--color")
        if i + 1 < len(sys.argv): color = sys.argv[i + 1].lower()

    app = QApplication(sys.argv)
    apply_theme(app, theme, color)
    win = GCodeSenderWindow()
    win.show()
    sys.exit(app.exec())
