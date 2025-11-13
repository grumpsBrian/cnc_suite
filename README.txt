# CNC Tool Suite (PyQt 6)

A complete open-source CNC and laser-engraving environment written in Python 3 / PyQt 6.  
Includes modular tools for generating, viewing, editing, slicing, and sending G-code, with a unified launcher and consistent theming.

---

## 🚀 Features

| Tool | Function |
|------|-----------|
| **DepthMap** | Convert images to 3D heightmaps and generate engraving G-code |
| **DXF Editor** | Draw, zoom, pan, and export 2D DXF designs |
| **Engrave** | Create text engravings with live G-code preview |
| **G-code Viewer** | Inspect and rotate toolpaths before sending |
| **Pic2Laser** | Convert raster images into laser engraving paths |
| **Pic23D** | Turn grayscale images into 3D STL height models |
| **STL Viewer** | View, color, and inspect 3D STL files |
| **Slicer** | Slice STL models into layers and export G-code |
| **Sender** | Stream G-code to CNC controllers with serial connection |

All applications share the same modern PyQt 6 interface and can be launched independently or from `main.py`.

---

## 💻 Requirements

Python ≥ 3.11  
Install dependencies with:

```bash
pip install -r requirements.txt --upgrade


PyQt6>=6.4.0
matplotlib>=3.6.0
numpy>=1.24.0
Pillow>=9.0.0
numpy-stl>=3.0.0
scipy>=1.9.0
shapely>=2.0.0
trimesh>=3.9.0
ezdxf>=1.0.0
pyclipper>=1.3.0
pyserial>=3.5


Launch the Suite  python3 main.py

Run the unified launcher:  python3 depthmap.py --theme dark

Each tool can run standalone — all share the same look and feel.


---

## 📘 `UserManual.md`

```markdown
# CNC Tool Suite – User Manual

---

## 1️⃣  Introduction

This suite provides a full toolchain for CNC milling, engraving, laser cutting, and 3D model processing.  
Each module runs independently or from the main launcher (`main.py`).  
All share a consistent PyQt 6 interface with selectable light/dark themes.

---

## 2️⃣  Installation

1. **Install Python 3.11** or later.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt

3️⃣ Interface Overview
3.1 Main Menu (main.py)

Central hub for all tools.

Buttons to open each module.

Light/Dark theme toggle (persistent during session).

Runs each tool in its own subprocess for stability.

3.2 Common UI Features

Unified Fusion-style theme via apply_theme().

Resizable split layouts (QSplitter).

Clean icon-less toolbar with plain-text titles.

Keyboard shortcuts for basic actions (zoom, open, reset).

4️⃣ Tool Descriptions
🟢 DepthMap Generator

Load a grayscale or color image.

Adjust blur, invert, and contrast.

Converts brightness to depth using NumPy.

Preview 3D heightmap in real time.

Export G-code for engraving or milling.

Menu actions:

Load Image – open PNG/JPG.

Generate DepthMap – compute surface.

Export G-code – save engraving file.

🔵 DXF Editor

Grid-based 2D editor for lines, circles, rectangles.

Pan, zoom, and snap-to-grid enabled.

Select/delete objects.

Save and export DXF files via ezdxf.

🟣 Engrave

Text-to-G-code generator with live preview.

Supports TTF font import (requires ttf2cxf_stream).

Adjustable feed rate, depth, and text size.

Live preview plot updates on change.

Save G-code directly for CNC/laser engraving.

🔶 G-code Viewer

Load .gcode, .nc, .ngc, or .txt files.

Interactive 3D rotation and zoom.

Color-coded toolpaths.

Simple control panel (Zoom ±, Rotate ◄/►, Reset, Clear).

🔴 Pic2Laser

Converts raster images to laser engraving paths.

Adjustable brightness threshold and scaling.

Outputs optimized G-code for laser engraving.

🟤 Pic23D

Converts grayscale images to 3D STL meshes.

Adjustable scaling and smoothing.

Uses numpy-stl for fast binary STL generation.

🟡 STL Viewer

Load and visualize 3D STL files.

Control color, transparency, and wireframe display.

Color by normals or base color.

Fully 3D interactive rotation/zoom.

🟠 Slicer

Slice STL files into layers and generate G-code.

Uses Shapely and SciPy for geometry operations.

Layer navigation slider and progress bar.

Save final G-code for printing or milling.

⚙️ Sender

Serial G-code streamer for GRBL or similar controllers.

Port/baud selection.

Start, pause, and stop control.

Real-time log window with G-code echo.

3D toolpath preview synced with sent data.

5️⃣ Troubleshooting
Issue	Cause	Fix
ValueError: 'Qt6Agg' not valid backend	Matplotlib backend mismatch	Replace with qtagg
ValueError: numpy.dtype size changed	NumPy / numpy-stl binary mismatch	pip install --force-reinstall numpy numpy-stl
ModuleNotFoundError: shapely	Missing geometry lib	pip install shapely
Black window / no 3D preview	Matplotlib 3D not installed	pip install matplotlib
No serial ports in Sender	PySerial missing	pip install pyserial

