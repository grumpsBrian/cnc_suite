#!/usr/bin/env python3
"""
STL 3D Viewer – CNC Suite Edition
Brian Wilson (Grump) and AI. Inspired by scorchworks
"""
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import sys, os, struct, numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QSlider, QGroupBox, QFileDialog, QMessageBox,
    QSplitter, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

# 🔸 unified theme import
from themes.theme_utils import apply_theme


# ---------- STL Loader Thread ----------
class STLFileLoader(QThread):
    progress_updated = pyqtSignal(int)
    file_loaded = pyqtSignal(object, object, object)
    error_occurred = pyqtSignal(str)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            self.progress_updated.emit(10)
            with open(self.file_path, "rb") as f:
                header = f.read(80)
                tri_count = struct.unpack("<I", f.read(4))[0]
                if tri_count == 0:
                    raise ValueError("No triangles found.")
                vertices = np.zeros((tri_count * 3, 3), dtype=np.float32)
                faces = np.zeros((tri_count, 3), dtype=np.int32)
                normals = np.zeros((tri_count, 3), dtype=np.float32)
                for i in range(tri_count):
                    data = f.read(50)
                    if len(data) < 50:
                        break
                    values = struct.unpack("<12fH", data)
                    n = values[0:3]
                    v1 = values[3:6]; v2 = values[6:9]; v3 = values[9:12]
                    normals[i] = n
                    f_idx = i * 3
                    vertices[f_idx:f_idx+3] = np.array([v1, v2, v3])
                    faces[i] = [f_idx, f_idx+1, f_idx+2]
                    if i % 10000 == 0:
                        self.progress_updated.emit(10 + int((i / tri_count) * 80))
            self.progress_updated.emit(100)
            self.file_loaded.emit(vertices, faces, normals)
        except Exception as e:
            self.error_occurred.emit(str(e))


# ---------- Viewer ----------
class STL3DViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.vertices = self.faces = self.normals = None
        self.current_file = None
        self.setWindowTitle("STL 3D Viewer – CNC Suite")
        self.resize(1400, 900)
        self._init_ui()

    def _init_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # Left panel
        left = QWidget()
        lv = QVBoxLayout(left)
        self.load_btn = QPushButton("Load STL File")
        self.load_btn.clicked.connect(self.load_stl_file)
        lv.addWidget(self.load_btn)

        self.color_combo = QComboBox()
        self.color_combo.addItems(["Light Blue", "Light Gray", "Green", "Red", "Orange", "White"])
        lv.addWidget(QLabel("Model Color"))
        lv.addWidget(self.color_combo)

        self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setRange(10, 100)
        self.alpha_slider.setValue(90)
        lv.addWidget(QLabel("Transparency"))
        lv.addWidget(self.alpha_slider)

        self.wire_check = QCheckBox("Show Wireframe")
        self.face_check = QCheckBox("Show Faces"); self.face_check.setChecked(True)
        self.norm_check = QCheckBox("Color by Normal")
        for w in (self.wire_check, self.face_check, self.norm_check):
            lv.addWidget(w)

        self.progress = QProgressBar()
        lv.addWidget(self.progress)
        lv.addStretch()
        splitter.addWidget(left)

        # Right panel
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.addWidget(QLabel("3D Preview"))
        self.fig = Figure()
        self.ax = self.fig.add_subplot(111, projection="3d")
        self.canvas = FigureCanvasQTAgg(self.fig)
        rv.addWidget(self.canvas)
        splitter.addWidget(right)
        splitter.setSizes([300, 1100])

        self.statusBar().showMessage("Ready")

        # Bind controls
        self.alpha_slider.valueChanged.connect(self.update_3d_view)
        self.color_combo.currentTextChanged.connect(self.update_3d_view)
        self.wire_check.stateChanged.connect(self.update_3d_view)
        self.face_check.stateChanged.connect(self.update_3d_view)
        self.norm_check.stateChanged.connect(self.update_3d_view)

    # ---------- Logic ----------
    def load_stl_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select STL File", "", "STL Files (*.stl)")
        if not path:
            return
        self.current_file = path
        self.statusBar().showMessage(f"Loading {os.path.basename(path)} …")
        self.progress.setValue(0)
        self.loader = STLFileLoader(path)
        self.loader.progress_updated.connect(self.progress.setValue)
        self.loader.file_loaded.connect(self.on_file_loaded)
        self.loader.error_occurred.connect(lambda e: QMessageBox.critical(self, "Error", e))
        self.loader.start()

    def on_file_loaded(self, vertices, faces, normals):
        self.vertices, self.faces, self.normals = vertices, faces, normals
        self.statusBar().showMessage(f"Loaded: {os.path.basename(self.current_file)}")
        self.progress.setValue(100)
        self.update_3d_view()

    def update_3d_view(self):
        self.ax.clear()
        if self.vertices is None or self.faces is None:
            self.ax.set_title("No model loaded")
            self.canvas.draw()
            return

        color_map = {
            "Light Blue": (0.68, 0.85, 0.9),
            "Light Gray": (0.83, 0.83, 0.83),
            "Green": (0.0, 0.5, 0.0),
            "Red": (1.0, 0.0, 0.0),
            "Orange": (1.0, 0.65, 0.0),
            "White": (1.0, 1.0, 1.0),
        }
        base_color = color_map.get(self.color_combo.currentText(), (0.5, 0.5, 0.5))
        alpha = self.alpha_slider.value() / 100.0

        if self.face_check.isChecked():
            face_colors = [base_color + (alpha,)] * len(self.faces)
            if self.norm_check.isChecked() and self.normals is not None:
                face_colors = np.clip((self.normals + 1.0) / 2.0, 0, 1)
            poly = Poly3DCollection(
                [self.vertices[f] for f in self.faces],
                facecolors=face_colors,
                edgecolor="black" if self.wire_check.isChecked() else "none",
                linewidth=0.3, alpha=alpha
            )
            self.ax.add_collection3d(poly)

        mins = np.min(self.vertices, axis=0)
        maxs = np.max(self.vertices, axis=0)
        ctr = (mins + maxs) / 2
        rng = np.max(maxs - mins) / 2 or 1
        self.ax.set_xlim(ctr[0]-rng, ctr[0]+rng)
        self.ax.set_ylim(ctr[1]-rng, ctr[1]+rng)
        self.ax.set_zlim(ctr[2]-rng, ctr[2]+rng)
        self.ax.set_box_aspect([1,1,1])
        self.ax.set_title(os.path.basename(self.current_file))
        self.canvas.draw()


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
    win = STL3DViewer()
    win.show()
    sys.exit(app.exec())
