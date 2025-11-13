#!/usr/bin/env python3
"""
STL Slicer – CNC Suite Edition (Restored 3D Preview)
---------------------------------------------------
Brian Wilson (Grump) and AI. Inspired by scorchworks
"""

import sys, os
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QProgressBar, QDoubleSpinBox,
    QSplitter, QMessageBox
)
from PyQt6.QtCore import Qt

import matplotlib
matplotlib.use("qtagg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# --- shared theming ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from themes.theme_utils import apply_theme

# --- optional STL support ---
try:
    from stl import mesh
    HAS_STL = True
except Exception:
    mesh = None
    HAS_STL = False


class SliceCanvas(FigureCanvas):
    def __init__(self):
        self.fig = Figure(figsize=(5, 5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self._reset()

    def _reset(self):
        self.ax.clear()
        self.ax.set_title("Slice Preview")
        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.draw()

    def plot_slice(self, points):
        self.ax.clear()
        if len(points) == 0:
            self.ax.text(0.5, 0.5, "No slice data",
                         transform=self.ax.transAxes,
                         ha="center", va="center", color="gray")
        else:
            xs, ys = points[:, 0], points[:, 1]
            self.ax.plot(xs, ys, "k-", linewidth=0.6)
            self.ax.set_aspect("equal", "box")
        self.draw()


class MeshCanvas3D(FigureCanvas):
    def __init__(self):
        self.fig = Figure(figsize=(5, 5), dpi=100)
        self.ax = self.fig.add_subplot(111, projection="3d")
        super().__init__(self.fig)
        self._reset()

    def _reset(self):
        self.ax.clear()
        self.ax.set_title("3D Model Preview")
        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.set_zlabel("Z")
        self.ax.view_init(30, 45)
        self.draw()

    def plot_mesh(self, mesh_data):
        self.ax.clear()
        self.ax.set_title("3D Model Preview")
        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.set_zlabel("Z")
        if mesh_data is not None and len(mesh_data.vectors) > 0:
            for v in mesh_data.vectors:
                x, y, z = v[:, 0], v[:, 1], v[:, 2]
                self.ax.plot_trisurf(x, y, z, color='lightsteelblue', linewidth=0.2, alpha=0.9)
            self.ax.auto_scale_xyz(
                [mesh_data.x.min(), mesh_data.x.max()],
                [mesh_data.y.min(), mesh_data.y.max()],
                [mesh_data.z.min(), mesh_data.z.max()]
            )
        else:
            self.ax.text2D(0.5, 0.5, "No model loaded", transform=self.ax.transAxes, ha='center', va='center', color='gray')
        self.ax.view_init(30, 45)
        self.draw()


class SlicerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("STL Slicer – CNC Suite")
        self.resize(1200, 800)
        self.mesh_data = None
        self.slice_height = 1.0
        self.slices = []
        self._init_ui()

    def _init_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        left = QWidget()
        lv = QVBoxLayout(left)

        self.load_btn = QPushButton("Load STL File")
        self.load_btn.clicked.connect(self.load_stl)
        lv.addWidget(self.load_btn)

        lv.addWidget(QLabel("Slice Height (mm):"))
        self.slice_spin = QDoubleSpinBox()
        self.slice_spin.setRange(0.1, 10.0)
        self.slice_spin.setValue(1.0)
        self.slice_spin.setSingleStep(0.1)
        lv.addWidget(self.slice_spin)

        self.slice_btn = QPushButton("Slice Model")
        self.slice_btn.clicked.connect(self.slice_model)
        lv.addWidget(self.slice_btn)

        self.export_btn = QPushButton("Export G-code…")
        self.export_btn.clicked.connect(self.export_gcode)
        self.export_btn.setEnabled(False)
        lv.addWidget(self.export_btn)

        self.progress = QProgressBar(); lv.addWidget(self.progress)
        lv.addStretch()

        splitter.addWidget(left)

        # --- Right panel: vertical split for 3D (top) + 2D (bottom) ---
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.canvas3d = MeshCanvas3D()
        self.canvas2d = SliceCanvas()
        right_splitter.addWidget(self.canvas3d)
        right_splitter.addWidget(self.canvas2d)
        right_splitter.setSizes([600, 400])
        splitter.addWidget(right_splitter)
        splitter.setSizes([250, 950])

        self.statusBar().showMessage("Ready")

    def load_stl(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open STL File", "", "STL Files (*.stl);;All Files (*)"
        )
        if not path:
            return
        if not HAS_STL:
            QMessageBox.critical(self, "Error", "numpy-stl not available.")
            return
        try:
            self.mesh_data = mesh.Mesh.from_file(path)
            self.canvas3d.plot_mesh(self.mesh_data)
            self.statusBar().showMessage(f"Loaded {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load STL: {e}")

    def slice_model(self):
        if self.mesh_data is None:
            QMessageBox.warning(self, "Warning", "Load an STL file first.")
            return

        h = self.slice_spin.value()
        z_min, z_max = np.min(self.mesh_data.z), np.max(self.mesh_data.z)
        z_levels = np.arange(z_min, z_max, h)
        self.slices.clear()
        self.progress.setRange(0, len(z_levels))
        self.statusBar().showMessage("Slicing model...")

        try:
            for i, z in enumerate(z_levels):
                mask = (self.mesh_data.z >= z) & (self.mesh_data.z < z + h)
                pts = self.mesh_data.points[mask.any(axis=1)]
                if pts.size > 0:
                    pts2d = pts[:, [0, 1, 2]]
                    self.slices.append((z, pts2d))
                self.progress.setValue(i + 1)

            if self.slices:
                z0, pts = self.slices[0]
                self.canvas2d.plot_slice(pts)
                self.statusBar().showMessage(f"Sliced into {len(self.slices)} layers.")
                self.export_btn.setEnabled(True)
            else:
                self.canvas2d._reset()
                QMessageBox.information(self, "Info", "No slices generated.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Slicing failed: {e}")

    def export_gcode(self):
        if not self.slices:
            QMessageBox.warning(self, "Warning", "No slices to export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save G-code", "", "G-code Files (*.gcode *.nc *.ngc *.txt)"
        )
        if not path:
            return

        try:
            gcode = []
            gcode.append("; Generated by CNC Suite Slicer")
            gcode.append("G90 ; absolute positioning")
            gcode.append("G21 ; millimeters")

            feed = 800
            rapid = 1200
            for z, pts in self.slices:
                if len(pts) == 0:
                    continue
                gcode.append(f"(Layer Z={z:.3f})")
                x0, y0, _ = pts[0]
                gcode.append(f"G0 X{x0:.3f} Y{y0:.3f} Z{z:.3f} F{rapid}")
                for (x, y, _) in pts[1:]:
                    gcode.append(f"G1 X{x:.3f} Y{y:.3f} Z{z:.3f} F{feed}")
                gcode.append("")

            gcode.append("G0 Z10.000")
            gcode.append("M2 ; end of program")

            with open(path, "w") as f:
                f.write("\n".join(gcode))

            self.statusBar().showMessage(f"G-code saved: {os.path.basename(path)}")
            print(f"[Slicer] G-code exported to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"G-code export failed: {e}")


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
    win = SlicerApp()
    win.show()
    sys.exit(app.exec())
