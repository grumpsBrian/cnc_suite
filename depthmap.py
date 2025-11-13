#!/usr/bin/env python3
"""
DepthMap Generator – CNC Suite Edition
Brian Wilson (Grump) and AI. Inspired by scorchworks
"""

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from PIL import Image, ImageFilter, ImageOps
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QFileDialog,
    QVBoxLayout, QSlider, QSplitter, QMessageBox, QProgressBar, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap, QColor

from themes.theme_utils import apply_theme


class CNCDepthMapGeneratorQt(QMainWindow):
    def __init__(self, colors):
        super().__init__()
        self.colors = colors
        self.setWindowTitle("DepthMap Generator – CNC Suite")
        self.resize(1200, 800)
        self.loaded_image = None
        self.processed_image = None
        self.depth_array = None
        self.zoom_factor = 1.0
        self.init_ui()

    def init_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # Left control panel
        left = QWidget()
        lv = QVBoxLayout(left)

        load_btn = QPushButton("Load Image")
        load_btn.clicked.connect(self.load_image)
        lv.addWidget(load_btn)

        gen_btn = QPushButton("Generate Depth Map")
        gen_btn.clicked.connect(self.generate_depthmap)
        lv.addWidget(gen_btn)

        save_btn = QPushButton("Export G-code")
        save_btn.clicked.connect(self.export_gcode)
        lv.addWidget(save_btn)

        lv.addWidget(QLabel("Blur"))
        self.blur_slider = QSlider(Qt.Orientation.Horizontal)
        self.blur_slider.setRange(0, 10)
        self.blur_slider.setValue(1)
        lv.addWidget(self.blur_slider)

        self.invert_btn = QPushButton("Invert")
        self.invert_btn.setCheckable(True)
        lv.addWidget(self.invert_btn)

        lv.addWidget(QLabel("Max depth (mm)"))
        self.max_depth = QDoubleSpinBox()
        self.max_depth.setRange(-50.0, 50.0)
        self.max_depth.setDecimals(3)
        self.max_depth.setValue(0.0)
        lv.addWidget(self.max_depth)

        lv.addWidget(QLabel("Min depth (mm)"))
        self.min_depth = QDoubleSpinBox()
        self.min_depth.setRange(-50.0, 50.0)
        self.min_depth.setDecimals(3)
        self.min_depth.setValue(-2.0)
        lv.addWidget(self.min_depth)

        lv.addWidget(QLabel("Work width (mm)"))
        self.work_width = QDoubleSpinBox()
        self.work_width.setRange(1.0, 1000.0)
        self.work_width.setDecimals(2)
        self.work_width.setValue(50.0)
        lv.addWidget(self.work_width)

        lv.addWidget(QLabel("Resolution (mm/step)"))
        self.resolution = QDoubleSpinBox()
        self.resolution.setRange(0.05, 5.0)
        self.resolution.setDecimals(3)
        self.resolution.setValue(0.2)
        lv.addWidget(self.resolution)

        self.progress = QProgressBar()
        lv.addWidget(self.progress)
        lv.addStretch()
        splitter.addWidget(left)

        # Right preview area
        right = QWidget()
        rv = QVBoxLayout(right)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(800, 600)

        # 🔸 Use theme color for preview background + border
        self.image_label.setStyleSheet(
            f"background-color: {self.colors['base']}; "
            f"border: 2px solid {self.colors['accent']};"
        )

        self.image_label.wheelEvent = self.handle_zoom
        rv.addWidget(self.image_label)
        splitter.addWidget(right)
        splitter.setSizes([260, 940])

    # ---------- Zoom ----------
    def handle_zoom(self, event):
        delta = event.angleDelta().y()
        self.zoom_factor *= 1.1 if delta > 0 else 1 / 1.1
        self.zoom_factor = max(0.1, min(self.zoom_factor, 10.0))
        self.update_zoomed_image()

    def update_zoomed_image(self):
        if self.processed_image is not None:
            base = QPixmap.fromImage(self.processed_image)
        elif self.loaded_image is not None:
            base = QPixmap.fromImage(self.loaded_image)
        else:
            return
        w = int(800 * self.zoom_factor)
        h = int(600 * self.zoom_factor)
        scaled = base.scaled(
            w, h, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)

    # ---------- Core ----------
    def load_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "", "Images (*.png *.jpg *.bmp)"
        )
        if not path:
            return
        img = Image.open(path).convert("L")
        self.loaded_image = self.pil_to_qimage(img)
        self.processed_image = None
        self.depth_array = None
        self.update_zoomed_image()
        self.statusBar().showMessage(f"Loaded: {os.path.basename(path)}")

    def generate_depthmap(self):
        if not self.loaded_image:
            QMessageBox.warning(self, "No Image", "Load an image first.")
            return
        self.progress.setValue(10)
        self.statusBar().showMessage("Processing...")
        QTimer.singleShot(100, self._do_generate)

    def _do_generate(self):
        self.progress.setValue(40)
        img = self.qimage_to_pil(self.loaded_image)
        if self.blur_slider.value() > 0:
            img = img.filter(ImageFilter.GaussianBlur(self.blur_slider.value()))
        if self.invert_btn.isChecked():
            img = ImageOps.invert(img)
        arr = np.array(img).astype(np.float32) / 255.0
        self.depth_array = arr
        depth_img = Image.fromarray((arr * 255).astype(np.uint8))
        self.processed_image = self.pil_to_qimage(depth_img)
        self.update_zoomed_image()
        self.progress.setValue(100)
        self.statusBar().showMessage("Depth map generated.")

    def export_gcode(self):
        if self.processed_image is None or self.depth_array is None:
            QMessageBox.warning(self, "No Depth Map", "Generate depth map first.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export G-code", "", "G-code (*.gcode *.nc *.txt)"
        )
        if not path:
            return

        z_min = self.min_depth.value()
        z_max = self.max_depth.value()
        width_mm = self.work_width.value()
        step_mm = self.resolution.value()

        h, w = self.depth_array.shape
        aspect = h / w
        height_mm = width_mm * aspect

        pixel_step_x = max(1, int((width_mm / step_mm) / w))
        pixel_step_y = max(1, int((height_mm / step_mm) / h))
        scale_x = width_mm / w
        scale_y = height_mm / h

        lines = [
            "(DepthMap generated G-code)",
            "G90 ; absolute positioning",
            "G21 ; millimeters",
            "G0 Z5.000",
        ]

        feedrate = 300.0
        for y in range(0, h, pixel_step_y):
            y_mm = y * scale_y
            lines.append(f"G0 Y{y_mm:.3f}")
            for x in range(0, w, pixel_step_x):
                val = self.depth_array[y, x]
                z = z_min + (1 - val) * (z_max - z_min)
                x_mm = x * scale_x
                lines.append(f"G1 X{x_mm:.3f} Z{z:.3f} F{feedrate:.1f}")
            lines.append("G0 Z5.000")
        lines.append("G0 X0 Y0 Z5.000")
        lines.append("M2")

        with open(path, "w") as f:
            f.write("\n".join(lines))

        QMessageBox.information(self, "Export", f"G-code saved to:\n{path}")

    # ---------- Helpers ----------
    def pil_to_qimage(self, im):
        im = im.convert("L")
        data = im.tobytes("raw", "L")
        return QImage(data, im.width, im.height, QImage.Format.Format_Grayscale8)

    def qimage_to_pil(self, qimg):
        ptr = qimg.bits()
        ptr.setsize(qimg.width() * qimg.height())
        return Image.frombuffer("L", (qimg.width(), qimg.height()), bytes(ptr), "raw", "L", 0, 1)


# ---------- Entry ----------
if __name__ == "__main__":
    theme, color = "dark", "grey"
    if "--theme" in sys.argv:
        i = sys.argv.index("--theme")
        if i + 1 < len(sys.argv):
            theme = sys.argv[i + 1].lower()
    if "--color" in sys.argv:
        i = sys.argv.index("--color")
        if i + 1 < len(sys.argv):
            color = sys.argv[i + 1].lower()

    app = QApplication(sys.argv)
    colors = apply_theme(app, theme, color)

    win = CNCDepthMapGeneratorQt(colors)
    win.show()
    sys.exit(app.exec())
