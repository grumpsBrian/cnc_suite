#!/usr/bin/env python3
"""
G-code Viewer — CNC Suite Edition
Brian Wilson (Grump) and AI. Inspired by scorchworks
"""
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import sys, os
import matplotlib
matplotlib.use("qtagg")

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QFileDialog, QLabel, QSplitter, QStatusBar
)
from PyQt6.QtCore import Qt

# 🔸 unified theme import
from themes.theme_utils import apply_theme

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class GcodeCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure()
        self.ax = self.fig.add_subplot(111, projection="3d")
        super().__init__(self.fig)
        self.setParent(parent)
        self._reset_axes()

    def _reset_axes(self):
        self.ax.clear()
        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.set_zlabel("Z")
        self.ax.set_title("G-code Toolpath Viewer")
        self.ax.view_init(45, 45)
        self.draw()

    def load_gcode(self, filepath):
        if not os.path.isfile(filepath):
            raise FileNotFoundError(filepath)
        x, y, z = [], [], []
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith(("G0", "G1")):
                    gx = gy = gz = None
                    for p in line.split():
                        if p.startswith("X"): gx = float(p[1:])
                        elif p.startswith("Y"): gy = float(p[1:])
                        elif p.startswith("Z"): gz = float(p[1:])
                    if gx is not None and gy is not None:
                        x.append(gx)
                        y.append(gy)
                        z.append(gz if gz is not None else (z[-1] if z else 0))
        self._reset_axes()
        if x:
            self.ax.plot(x, y, z, linewidth=0.9)
            self.ax.auto_scale_xyz([min(x), max(x)], [min(y), max(y)], [min(z), max(z)])
        self.draw()

    def zoom(self, factor):
        cur = self.fig.get_size_inches()
        self.fig.set_size_inches(cur * factor, forward=True)
        self.draw()

    def rotate(self, de=0, da=0):
        self.ax.view_init(self.ax.elev + de, self.ax.azim + da)
        self.draw()


class GcodeViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("G-code Viewer – CNC Suite")
        self.resize(1400, 900)
        self._init_ui()

    def _init_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        self.canvas = GcodeCanvas()
        splitter.addWidget(self.canvas)

        controls = QWidget()
        v = QVBoxLayout(controls)

        open_btn = QPushButton("Open G-code File")
        open_btn.clicked.connect(self.open_file)
        v.addWidget(open_btn)

        self.path_label = QLabel("No file loaded.")
        v.addWidget(self.path_label)

        for txt, fn in [
            ("Zoom +", lambda: self.canvas.zoom(1.1)),
            ("Zoom –", lambda: self.canvas.zoom(0.9)),
            ("Rotate ◄", lambda: self.canvas.rotate(0, -10)),
            ("Rotate ►", lambda: self.canvas.rotate(0, 10)),
            ("Reset View", self.canvas._reset_axes),
            ("Clear View", self.canvas._reset_axes),
        ]:
            b = QPushButton(txt)
            b.clicked.connect(fn)
            v.addWidget(b)

        v.addStretch()
        splitter.insertWidget(0, controls)
        splitter.setSizes([250, 1150])

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready – Load a G-code file to view toolpath")

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select G-code File",
            "", "G-code Files (*.gcode *.nc *.tap *.txt);;All Files (*)"
        )
        if path:
            self.path_label.setText(os.path.basename(path))
            self.status.showMessage(f"Loading {path}…")
            try:
                self.canvas.load_gcode(path)
                self.status.showMessage("File loaded and displayed.")
            except Exception as e:
                self.status.showMessage(f"Error: {e}")


# ---------- Entry ----------
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
    win = GcodeViewer()
    win.show()
    sys.exit(app.exec())
