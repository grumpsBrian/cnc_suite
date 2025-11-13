#!/usr/bin/env python3
"""
CNC Suite Unified Launcher
--------------------------
A suite of tools for CNC editing, ok so nothing grand, very basic but they suit me and that's who I wrote them for. In fact been referred to as like using a etch-a-sketch, I prefer to think of it as my swiss army knife. Have a lot of fun with it. Brian Wilson (Grump)
"""

import sys
import os
import json
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton,
    QGridLayout, QMessageBox, QComboBox, QCheckBox, QHBoxLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor

# Local import
from themes.theme_utils import apply_theme


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
TOOLS_PATH = os.path.join(os.path.dirname(__file__), "tools")

TOOLS = [
    ("Depth Map", "depthmap.py"),
    ("DXF Editor", "dxf.py"),
    ("GCode Viewer", "Gcode_viewer.py"),
    ("Pic2Laser", "pic2laser.py"),
    ("Pic23D", "pic23d.py"),
    ("GCode Sender", "sender.py"),
    ("STL Slicer", "slicer.py"),
    ("STL Viewer", "stl_viewer.py"),
    ("Text Engrave", "engrave.py"),
]


def load_config():
    """Load last-used theme settings."""
    default = {"theme": "dark", "color": "grey"}
    if not os.path.exists(CONFIG_PATH):
        return default
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return default
            return {**default, **data}
    except Exception:
        return default


def save_config(cfg):
    """Save theme settings persistently."""
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CNC / Laser Tools Suite – PyQt6")
        self.resize(750, 520)

        # Load config
        cfg = load_config()
        self.theme_mode = cfg.get("theme", "dark")
        self.color_mode = cfg.get("color", "grey")

        # Apply palette
        apply_theme(QApplication.instance(), self.theme_mode, self.color_mode)

        # --- UI ---
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        title = QLabel("CNC / Laser Tools Suite")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: bold; margin: 12px;")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(10)
        layout.addLayout(grid)

        row = col = 0
        for name, filename in TOOLS:
            btn = QPushButton(name)
            btn.setMinimumHeight(42)
            btn.clicked.connect(lambda checked, f=filename: self.launch_tool(f))
            grid.addWidget(btn, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1

        # --- Theme controls ---
        control_bar = QHBoxLayout()
        control_bar.addStretch(1)

        control_bar.addWidget(QLabel("Color:"))
        self.color_combo = QComboBox()
        self.color_combo.addItems(["grey", "red", "blue", "green"])
        self.color_combo.setCurrentText(self.color_mode)
        self.color_combo.currentTextChanged.connect(self.change_color)
        control_bar.addWidget(self.color_combo)

        self.dark_toggle = QCheckBox("Dark Mode")
        self.dark_toggle.setChecked(self.theme_mode == "dark")
        self.dark_toggle.stateChanged.connect(self.toggle_dark_mode)
        control_bar.addWidget(self.dark_toggle)

        layout.addLayout(control_bar)
        layout.addStretch(1)

        self.statusBar().showMessage("Select a tool to launch.")

    # -------------------------------
    # Theme control handlers
    # -------------------------------
    def change_color(self, color):
        self.color_mode = color
        apply_theme(QApplication.instance(), self.theme_mode, self.color_mode)
        save_config({"theme": self.theme_mode, "color": self.color_mode})

    def toggle_dark_mode(self, state):
        self.theme_mode = "dark" if state else "light"
        apply_theme(QApplication.instance(), self.theme_mode, self.color_mode)
        save_config({"theme": self.theme_mode, "color": self.color_mode})

    # -------------------------------
    # Launch external tool
    # -------------------------------
    def launch_tool(self, filename):
        path = os.path.join(TOOLS_PATH, filename)
        if not os.path.exists(path):
            QMessageBox.warning(self, "Missing File", f"{filename} not found in /tools/")
            return

        try:
            subprocess.Popen([
                sys.executable,
                path,
                "--theme", self.theme_mode,
                "--color", self.color_mode
            ])
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


def main():
    app = QApplication(sys.argv)
    cfg = load_config()
    apply_theme(app, cfg.get("theme", "dark"), cfg.get("color", "grey"))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
