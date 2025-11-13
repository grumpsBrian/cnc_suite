#!/usr/bin/env python3
"""
Pic23D – Image to 3D Mesh Generator (CNC Suite Edition, XY Enhanced)
Brian Wilson (Grump) and AI. Inspired by scorchworks
"""

import sys, os
import numpy as np
from PIL import Image

try:
    from stl import mesh
except Exception:
    mesh = None

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QDoubleSpinBox, QFileDialog, QMessageBox,
    QSplitter, QGroupBox, QProgressBar
)
from PyQt6.QtCore import Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# 🔸 unified theme import
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from themes.theme_utils import apply_theme


class MeshCanvas(FigureCanvas):
    def __init__(self):
        self.fig = Figure()
        self.ax = self.fig.add_subplot(111, projection="3d")
        super().__init__(self.fig)
        self._reset()

    def _reset(self):
        self.ax.clear()
        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.set_zlabel("Z")
        self.ax.set_title("3D Heightmap Preview")
        self.ax.view_init(45, 45)
        self.draw()

    def plot_heightmap(self, X, Y, Z):
        self.ax.clear()
        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.set_zlabel("Z")
        self.ax.set_title("3D Heightmap Preview")
        self.ax.plot_surface(X, Y, Z, cmap="viridis", linewidth=0, antialiased=False)

        zmin, zmax = float(np.min(Z)), float(np.max(Z))
        self.ax.set_zlim(zmin, zmax)
        self.ax.set_box_aspect((1, 1, 10 * (zmax - zmin or 1.0) / max(Z.shape)))
        self.ax.view_init(45, 45)
        self.draw()


class Pic23DApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pic23D – Image to 3D Mesh Generator")
        self.resize(1400, 900)
        self.Z = None
        self.image_path = None
        self._init_ui()

    def _init_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        left = QWidget()
        v = QVBoxLayout(left)

        self.load_btn = QPushButton("Load Image")
        self.load_btn.clicked.connect(self.load_image)
        v.addWidget(self.load_btn)

        # --- Axis scaling controls ---
        grp = QGroupBox("Axis Scale (mm)")
        g = QVBoxLayout(grp)

        self.x_scale = QDoubleSpinBox(); self.x_scale.setRange(0.1, 50.0); self.x_scale.setValue(1.0)
        self.y_scale = QDoubleSpinBox(); self.y_scale.setRange(0.1, 50.0); self.y_scale.setValue(1.0)
        self.z_scale = QDoubleSpinBox(); self.z_scale.setRange(0.1, 20.0); self.z_scale.setValue(2.0)

        g.addWidget(QLabel("X Scale (mm)")); g.addWidget(self.x_scale)
        g.addWidget(QLabel("Y Scale (mm)")); g.addWidget(self.y_scale)
        g.addWidget(QLabel("Z Scale (mm)")); g.addWidget(self.z_scale)

        v.addWidget(grp)

        self.gen_btn = QPushButton("Generate 3D Mesh")
        self.gen_btn.clicked.connect(self.generate_mesh)
        v.addWidget(self.gen_btn)

        self.save_btn = QPushButton("Export STL")
        self.save_btn.clicked.connect(self.export_stl)
        v.addWidget(self.save_btn)

        self.progress = QProgressBar()
        v.addWidget(self.progress)
        v.addStretch()

        splitter.addWidget(left)

        self.canvas = MeshCanvas()
        splitter.addWidget(self.canvas)
        splitter.setSizes([300, 1100])

        self.statusBar().showMessage("Ready")

    def load_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif);;All Files (*)"
        )
        if not path:
            return
        try:
            self.image_path = path
            img = Image.open(path).convert("L")
            self.Z = np.array(img, dtype=float)
            self.statusBar().showMessage(
                f"Loaded: {os.path.basename(path)} ({self.Z.shape[1]}x{self.Z.shape[0]})"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Image load failed: {e}")

    def generate_mesh(self):
        if self.Z is None:
            QMessageBox.warning(self, "Warning", "Load an image first.")
            return
        try:
            self.progress.setValue(10)
            Z = (255 - self.Z) / 255.0 * self.z_scale.value()

            ny, nx = Z.shape
            X = np.arange(nx) * self.x_scale.value()
            Y = np.arange(ny) * self.y_scale.value()
            X, Y = np.meshgrid(X, Y)

            self.progress.setValue(50)
            self.canvas.plot_heightmap(X, Y, Z)
            self.progress.setValue(100)
            self.statusBar().showMessage("3D heightmap generated with XY scaling.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Mesh generation failed: {e}")
            self.progress.setValue(0)

    def export_stl(self):
        if mesh is None:
            QMessageBox.warning(self, "Unavailable", "numpy-stl not installed or failed to load.")
            return
        if self.Z is None:
            QMessageBox.warning(self, "Warning", "Generate a mesh first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save STL", "", "STL Files (*.stl);;All Files (*)"
        )
        if not path:
            return
        try:
            Z = (255 - self.Z) / 255.0 * self.z_scale.value()

            ny, nx = Z.shape
            X = np.arange(nx) * self.x_scale.value()
            Y = np.arange(ny) * self.y_scale.value()

            verts, faces = [], []
            for i in range(ny - 1):
                for j in range(nx - 1):
                    v1 = [X[j], Y[i], Z[i, j]]
                    v2 = [X[j + 1], Y[i], Z[i, j + 1]]
                    v3 = [X[j], Y[i + 1], Z[i + 1, j]]
                    v4 = [X[j + 1], Y[i + 1], Z[i + 1, j + 1]]
                    idx = len(verts)
                    verts += [v1, v2, v3, v4]
                    faces += [[idx, idx + 1, idx + 2], [idx + 1, idx + 3, idx + 2]]

            verts = np.array(verts)
            faces = np.array(faces)
            mesh_obj = mesh.Mesh(np.zeros(faces.shape[0], dtype=mesh.Mesh.dtype))
            for i, f in enumerate(faces):
                for j in range(3):
                    mesh_obj.vectors[i][j] = verts[f[j], :]
            mesh_obj.save(path)
            self.statusBar().showMessage(f"STL saved: {path}")
            QMessageBox.information(self, "Export Complete", f"Saved: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"STL export failed: {e}")


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
    win = Pic23DApp()
    win.show()
    sys.exit(app.exec())