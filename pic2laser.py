#!/usr/bin/env python3
"""
Pic2Laser – CNC Suite Edition
Brian Wilson (Grump) and AI. Inspired by scorchworks
"""

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QSlider, QProgressBar, QSplitter,
    QDoubleSpinBox, QMessageBox, QCheckBox
)
from PIL import Image, ImageOps
import numpy as np

from themes.theme_utils import apply_theme


# ---------- Main Window ----------
class Pic2LaserApp(QMainWindow):
    def __init__(self, colors):
        super().__init__()
        self.colors = colors
        self.setWindowTitle("Pic2Laser – CNC Suite")
        self.resize(1200, 800)
        self.image = None
        self.processed = None
        self.init_ui()

    def init_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # --- Left panel ---
        left = QWidget()
        lv = QVBoxLayout(left)

        load_btn = QPushButton("Load Image")
        load_btn.clicked.connect(self.load_image)
        lv.addWidget(load_btn)

        lv.addWidget(QLabel("Brightness"))
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(-100, 100)
        self.brightness_slider.setValue(0)
        lv.addWidget(self.brightness_slider)

        lv.addWidget(QLabel("Contrast"))
        self.contrast_slider = QSlider(Qt.Orientation.Horizontal)
        self.contrast_slider.setRange(-100, 100)
        self.contrast_slider.setValue(0)
        lv.addWidget(self.contrast_slider)

        lv.addWidget(QLabel("Gamma"))
        self.gamma_slider = QSlider(Qt.Orientation.Horizontal)
        self.gamma_slider.setRange(1, 400)
        self.gamma_slider.setValue(100)
        lv.addWidget(self.gamma_slider)

        self.invert_btn = QCheckBox("Invert Image")
        lv.addWidget(self.invert_btn)

        process_btn = QPushButton("Preview Laser Output")
        process_btn.clicked.connect(self.process_image)
        lv.addWidget(process_btn)

        export_btn = QPushButton("Export G-code")
        export_btn.clicked.connect(self.export_gcode)
        lv.addWidget(export_btn)

        self.progress = QProgressBar()
        lv.addWidget(self.progress)
        lv.addStretch()
        splitter.addWidget(left)

        # --- Right preview area ---
        right = QWidget()
        rv = QVBoxLayout(right)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(800, 600)
        # 🔸 Theme-based preview background
        self.image_label.setStyleSheet(
            f"background-color: {self.colors['base']}; "
            f"border: 2px solid {self.colors['accent']};"
        )
        rv.addWidget(self.image_label)
        splitter.addWidget(right)
        splitter.setSizes([280, 920])

        # Connections for real-time update
        self.brightness_slider.valueChanged.connect(self.preview_update)
        self.contrast_slider.valueChanged.connect(self.preview_update)
        self.gamma_slider.valueChanged.connect(self.preview_update)
        self.invert_btn.stateChanged.connect(self.preview_update)

        self.statusBar().showMessage("Ready")

    # ---------- Image Processing ----------
    def load_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "", "Images (*.png *.jpg *.bmp)"
        )
        if not path:
            return
        self.image = Image.open(path).convert("L")
        self.processed = None
        self.update_preview(self.image)
        self.statusBar().showMessage(f"Loaded: {os.path.basename(path)}")

    def preview_update(self):
        if self.image is None:
            return
        self.process_image(update_only=True)

    def process_image(self, update_only=False):
        if self.image is None:
            QMessageBox.warning(self, "No Image", "Load an image first.")
            return

        self.progress.setValue(10)
        QTimer.singleShot(50, lambda: self._do_process(update_only))

    def _do_process(self, update_only):
        img = self.image.copy()

        # Brightness & Contrast
        brightness = self.brightness_slider.value()
        contrast = self.contrast_slider.value()
        gamma = self.gamma_slider.value() / 100.0

        np_img = np.array(img).astype(np.float32)
        np_img = np_img * (1 + contrast / 100.0) + brightness
        np_img = np.clip(np_img, 0, 255)
        np_img = (np_img / 255.0) ** (1.0 / gamma) * 255.0
        np_img = np.clip(np_img, 0, 255).astype(np.uint8)

        img = Image.fromarray(np_img)

        if self.invert_btn.isChecked():
            img = ImageOps.invert(img)

        self.processed = img
        self.update_preview(img)
        self.progress.setValue(100)

        if not update_only:
            self.statusBar().showMessage("Laser preview updated.")

    def update_preview(self, pil_image):
        if pil_image is None:
            return
        qimg = QImage(
            pil_image.tobytes("raw", "L"),
            pil_image.width,
            pil_image.height,
            QImage.Format.Format_Grayscale8
        )
        pixmap = QPixmap.fromImage(qimg)
        scaled = pixmap.scaled(
            self.image_label.width(), self.image_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)

    # ---------- G-code Export ----------
    def export_gcode(self):
        if self.processed is None:
            QMessageBox.warning(self, "No Processed Image", "Generate laser preview first.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save G-code", "", "G-code (*.gcode *.nc *.txt)"
        )
        if not path:
            return

        width_mm = 50.0
        height_mm = 50.0
        feedrate = 1000.0
        laser_min = 0
        laser_max = 255

        arr = np.array(self.processed)
        h, w = arr.shape
        gcode = [
            "(Pic2Laser G-code)",
            "G21 ; metric units",
            "G90 ; absolute positioning",
            "M4 S0",
        ]

        for y in range(h):
            if y % 2 == 0:
                x_range = range(w)
            else:
                x_range = range(w - 1, -1, -1)
            gcode.append(f"G0 Y{y / h * height_mm:.3f}")
            for x in x_range:
                intensity = arr[y, x] / 255.0
                power = int(laser_min + (1 - intensity) * (laser_max - laser_min))
                gcode.append(f"G1 X{x / w * width_mm:.3f} S{power} F{feedrate:.1f}")
            gcode.append("M5")
        gcode.append("G0 X0 Y0")
        gcode.append("M2")

        try:
            with open(path, "w") as f:
                f.write("\n".join(gcode))
            QMessageBox.information(self, "Export Complete", f"G-code saved to:\n{path}")
            self.statusBar().showMessage("G-code export complete.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


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

    win = Pic2LaserApp(colors)
    win.show()
    sys.exit(app.exec())
