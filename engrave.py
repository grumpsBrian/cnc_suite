#!/usr/bin/env python3
"""
CNC Engrave Suite – CNC Suite Edition
Brian Wilson (Grump) and AI. Inspired by scorchworks
"""

import sys, os, math
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import (
    QColor, QPen, QPainter, QFontDatabase, QFont, QTransform, QPainterPath,
    QImage, QPixmap
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QGridLayout,
    QGraphicsView, QGraphicsScene, QLabel, QLineEdit, QDoubleSpinBox,
    QComboBox, QPushButton, QSplitter, QCheckBox, QStatusBar, QToolBar,
    QFileDialog, QMessageBox, QSlider
)

# Optional DXF export
try:
    import ezdxf
    DXF_AVAILABLE = True
except Exception:
    DXF_AVAILABLE = False

# Optional image processing
try:
    import cv2
    import numpy as np
    IMAGE_PROCESSING_AVAILABLE = True
except Exception:
    IMAGE_PROCESSING_AVAILABLE = False

from themes.theme_utils import apply_theme


# ---------- Zoomable View ----------
class ZoomableGraphicsView(QGraphicsView):
    def __init__(self, colors, *a, **kw):
        super().__init__(*a, **kw)
        self._zoom = 1.0
        self._last = None
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Theme background for preview
        self.setBackgroundBrush(QColor(colors["base"]))

    def wheelEvent(self, e):
        f = 1.1 if e.angleDelta().y() > 0 else 1 / 1.1
        self.scale(f, f)
        self._zoom *= f
        try:
            self.parent().window().update_status(self._zoom)
        except Exception:
            pass

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._last = e.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._last and e.buttons() & Qt.MouseButton.LeftButton:
            d = e.pos() - self._last
            self._last = e.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._last = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseReleaseEvent(e)


# ---------- Main ----------
class CNCEngraveApp(QMainWindow):
    FONT_DIR = "fonts"

    def __init__(self, colors):
        super().__init__()
        self.colors = colors
        self.setWindowTitle("CNC Engrave Suite")
        self.resize(1500, 900)

        self.scene = QGraphicsScene()
        self.view = ZoomableGraphicsView(colors, self.scene)
        self.path = None
        self.vector_paths = []
        self.current_image = None
        self.image_path = None

        self.init_ui()

    # ---- UI ----
    def init_ui(self):
        # Simple toolbar with theme note (kept minimal)
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # ---- Left controls ----
        left = QWidget()
        grid = QGridLayout(left)
        r = 0

        def spin(lbl, val, rng, step=0.1):
            nonlocal r
            grid.addWidget(QLabel(lbl), r, 0)
            box = QDoubleSpinBox()
            box.setRange(*rng)
            box.setValue(val)
            box.setSingleStep(step)
            grid.addWidget(box, r, 1)
            r += 1
            return box

        # --- Image Vectorization ---
        grid.addWidget(QLabel("<b>Image Vectorization</b>"), r, 0, 1, 2); r += 1

        self.import_img_btn = QPushButton("Import Image")
        self.import_img_btn.clicked.connect(self.import_image)
        grid.addWidget(self.import_img_btn, r, 0, 1, 2); r += 1

        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(10, 200)
        self.threshold_slider.setValue(100)
        grid.addWidget(QLabel("Threshold:"), r, 0)
        grid.addWidget(self.threshold_slider, r, 1); r += 1

        self.simplify_slider = QSlider(Qt.Orientation.Horizontal)
        self.simplify_slider.setRange(1, 100)
        self.simplify_slider.setValue(10)
        grid.addWidget(QLabel("Simplify:"), r, 0)
        grid.addWidget(self.simplify_slider, r, 1); r += 1

        self.vectorize_btn = QPushButton("Vectorize Image")
        self.vectorize_btn.clicked.connect(self.vectorize_image)
        grid.addWidget(self.vectorize_btn, r, 0, 1, 2); r += 1

        # Live preview updates
        self.threshold_slider.valueChanged.connect(self.vectorize_image)
        self.simplify_slider.valueChanged.connect(self.vectorize_image)

        # --- Text Geometry ---
        grid.addWidget(QLabel("<b>Text Geometry</b>"), r, 0, 1, 2); r += 1
        self.text_height = spin("Height (mm)", 20, (0.1, 500))
        self.text_angle = spin("Angle (°)", 0, (-360, 360))
        self.radius = spin("Circle Radius (mm)", 0, (-10000, 10000))
        self.diameter_mode = QCheckBox("Diameter Mode")
        grid.addWidget(self.diameter_mode, r, 0, 1, 2); r += 1

        self.line_spacing = spin("Line Spacing (mm)", 25, (0, 200))
        self.word_space = spin("Word Spacing (%)", 100, (10, 400))
        self.char_space = spin("Char Spacing (%)", 100, (10, 400))
        self.line_thick = spin("Line Thickness (mm)", 0.2, (0.01, 10))
        self.justify = QComboBox()
        self.justify.addItems(["Left", "Center", "Right", "Circle", "Diameter"])
        grid.addWidget(QLabel("Justify"), r, 0)
        grid.addWidget(self.justify, r, 1); r += 1
        grid.setRowStretch(r, 1)

        # ---- Center ----
        center = QWidget()
        cv = QVBoxLayout(center)
        # themed border around preview
        self.view.setStyleSheet(
            f"background-color: {self.colors['base']}; "
            f"border: 2px solid {self.colors['accent']};"
        )
        cv.addWidget(self.view, 8)
        self.text_input = QLineEdit("Hello World")
        cv.addWidget(self.text_input, 1)

        # ---- Right panel ----
        right = QWidget()
        rg = QGridLayout(right)
        rr = 0
        rg.addWidget(QLabel("<b>G-Code Parameters</b>"), rr, 0, 1, 2); rr += 1

        def spinr(lbl, val, rng, step=0.1):
            nonlocal rr
            rg.addWidget(QLabel(lbl), rr, 0)
            b = QDoubleSpinBox()
            b.setRange(*rng)
            b.setValue(val)
            b.setSingleStep(step)
            rg.addWidget(b, rr, 1)
            rr += 1
            return b

        self.feed = spinr("Feed (mm/min)", 300, (1, 50000), 10)
        self.depth = spinr("Total Depth (mm)", -1, (-50, 0), 0.1)
        self.step = spinr("Step Depth (mm)", -0.3, (-10, 0), 0.1)
        self.safez = spinr("Safe Z (mm)", 5, (0, 100), 1)
        self.laser = QCheckBox("Laser Mode (M3/M5)")
        rg.addWidget(self.laser, rr, 0, 1, 2); rr += 1

        # Export / preview buttons
        self.preview_btn = QPushButton("Preview Text")
        self.preview_btn.clicked.connect(self.preview_text)
        rg.addWidget(self.preview_btn, rr, 0, 1, 2); rr += 1

        self.gcode_btn = QPushButton("Generate G-Code")
        self.gcode_btn.clicked.connect(self.export_gcode)
        rg.addWidget(self.gcode_btn, rr, 0, 1, 2); rr += 1

        self.dxf_btn = QPushButton("Export DXF")
        self.dxf_btn.clicked.connect(self.export_dxf)
        rg.addWidget(self.dxf_btn, rr, 0, 1, 2); rr += 1

        self.svg_btn = QPushButton("Export SVG")
        self.svg_btn.clicked.connect(self.export_svg)
        rg.addWidget(self.svg_btn, rr, 0, 1, 2); rr += 1

        # ---- Fonts (right-bottom) ----
        font_widget = QWidget()
        fv = QVBoxLayout(font_widget)
        font_label = QLabel("<b>Available Fonts</b>")
        font_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fv.addWidget(font_label)
        self.fonts = QComboBox()
        self.fonts.setMinimumWidth(300)
        self.fonts.setMaxVisibleItems(25)
        self.fonts.setStyleSheet(
            "QComboBox { min-height: 200px; font-size: 11pt; }"
            "QAbstractItemView { min-height: 400px; font-size: 11pt; }"
        )
        self.populate_fonts()
        fv.addWidget(self.fonts)
        fv.addStretch(1)

        right_wrap = QWidget()
        rv = QVBoxLayout(right_wrap)
        rv.addWidget(right)
        rv.addWidget(font_widget)

        # Assemble splitter
        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(right_wrap)
        splitter.setSizes([340, 780, 340])

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.update_status(1.0)

    # ---- Status ----
    def update_status(self, zoom):
        self.status.showMessage(f"Zoom: {zoom:.2f}×")

    # ---- Image Vectorizer ----
    def import_image(self):
        if not IMAGE_PROCESSING_AVAILABLE:
            QMessageBox.warning(self, "Image Processing Unavailable", "Install opencv-python and numpy.")
            return
        fn, _ = QFileDialog.getOpenFileName(
            self, "Import Image", "", "Image Files (*.png *.jpg *.jpeg *.bmp *.tiff);;All Files (*)"
        )
        if not fn:
            return
        img = cv2.imread(fn)
        if img is None:
            QMessageBox.warning(self, "Error", "Could not load image.")
            return
        self.current_image = img
        self.image_path = fn
        self.scene.clear()
        self.scene.addPixmap(QPixmap.fromImage(QImage(fn)))
        self.view.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.status.showMessage(f"Image loaded: {os.path.basename(fn)}")

    def vectorize_image(self):
        if not IMAGE_PROCESSING_AVAILABLE or self.current_image is None:
            return
        gray = cv2.cvtColor(self.current_image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        thr = self.threshold_slider.value()
        edges = cv2.Canny(blurred, thr / 2, thr)
        contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        self.scene.clear()
        self.vector_paths = []
        if not contours:
            self.status.showMessage("No contours found.")
            return
        max_dim = max(self.current_image.shape[:2])
        scale = 200.0 / max_dim if max_dim else 1.0
        for contour in contours:
            if cv2.contourArea(contour) < 10:
                continue
            eps = (self.simplify_slider.value() / 1000.0) * cv2.arcLength(contour, True)
            contour = cv2.approxPolyDP(contour, eps, True)
            path = QPainterPath()
            p0 = contour[0][0]
            path.moveTo((p0[0] - self.current_image.shape[1]/2)*scale,
                        (p0[1] - self.current_image.shape[0]/2)*scale)
            for pt in contour[1:]:
                x = (pt[0][0] - self.current_image.shape[1]/2)*scale
                y = (pt[0][1] - self.current_image.shape[0]/2)*scale
                path.lineTo(x, y)
            path.closeSubpath()
            self.vector_paths.append(path)
            pen = QPen(QColor(self.colors["accent"]))
            pen.setWidthF(0.4)
            self.scene.addPath(path, pen)
        if self.vector_paths:
            combined = QPainterPath()
            for p in self.vector_paths:
                combined.addPath(p)
            self.view.fitInView(combined.boundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self.status.showMessage(f"Vectorized {len(self.vector_paths)} paths.")

    # ---- Font & Text ----
    def populate_fonts(self):
        self.fonts.clear()
        font_dir = self.FONT_DIR
        if not os.path.isdir(font_dir):
            self.fonts.addItem("(no fonts folder)")
            return
        fonts = [f for f in os.listdir(font_dir) if f.lower().endswith((".ttf", ".otf"))]
        fonts.sort()
        self.fonts.addItems(fonts or ["(no fonts found)"])

    def preview_text(self):
        text = self.text_input.text().strip()
        if not text:
            return
        fontfile = os.path.join(self.FONT_DIR, self.fonts.currentText())
        if not os.path.isfile(fontfile):
            self.status.showMessage("Font file not found.")
            return
        fid = QFontDatabase.addApplicationFont(fontfile)
        fams = QFontDatabase.applicationFontFamilies(fid)
        if not fams:
            self.status.showMessage("Could not load font.")
            return
        fam = fams[0]
        font = QFont(fam, int(self.text_height.value()))
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, self.char_space.value())
        path = self.layout_text(text, font)
        self.path = path
        self.scene.clear()
        pen = QPen(QColor(self.colors["text"]))
        pen.setWidthF(self.line_thick.value())
        self.scene.addPath(path, pen)
        br = path.boundingRect()
        self.view.fitInView(br, Qt.AspectRatioMode.KeepAspectRatio)
        self.status.showMessage("Preview updated.")

    def layout_text(self, text, font):
        path = QPainterPath()
        justify = self.justify.currentText()
        radius = self.radius.value()
        if self.diameter_mode.isChecked() and radius != 0:
            radius = radius / 2.0
        lines = text.split("\n")
        y = 0
        for line in lines:
            if justify == "Circle" and abs(radius) > 1e-3 and len(line) > 0:
                ang_step = 360 / len(line)
                for i, ch in enumerate(line):
                    chpath = QPainterPath()
                    chpath.addText(0, 0, font, ch)
                    angle = -ang_step * i
                    tr = QTransform()
                    tr.rotate(angle)
                    tr.translate(0, -radius)
                    tr.rotate(-angle)
                    path.addPath(tr.map(chpath))
            elif justify == "Diameter" and abs(radius) > 1e-3:
                line_path = QPainterPath()
                total_width = 0
                char_paths = []
                for ch in line:
                    ch_path = QPainterPath()
                    ch_path.addText(0, 0, font, ch)
                    char_paths.append(ch_path)
                    total_width += ch_path.boundingRect().width() * (self.char_space.value() / 100.0)
                current_x = -total_width / 2
                for ch_path in char_paths:
                    char_width = ch_path.boundingRect().width() * (self.char_space.value() / 100.0)
                    tr = QTransform()
                    tr.translate(current_x + char_width / 2, 0)
                    line_path.addPath(tr.map(ch_path))
                    current_x += char_width
                path.addPath(line_path)
            else:
                lp = QPainterPath()
                lp.addText(0, 0, font, line)
                br = lp.boundingRect()
                xoff = 0
                if justify == "Center":
                    xoff = -br.width() / 2
                elif justify == "Right":
                    xoff = -br.width()
                lp.translate(xoff, y)
                path.addPath(lp)
                y += self.line_spacing.value()
        tr = QTransform()
        tr.rotate(self.text_angle.value())
        return tr.map(path)

    # ---- G-code ----
    def path_to_gcode(self, path: QPainterPath):
        if not path or path.isEmpty():
            return ""
        feed = self.feed.value()
        depth = self.depth.value()
        step = self.step.value()
        safe = self.safez.value()
        passes = max(1, int(abs(depth / step))) if step != 0 else 1
        g = ["(CNC Engrave)", "G21 G90"]
        if self.laser.isChecked():
            g.append("M3 (Laser On)")
        g.append(f"G0 Z{safe:.3f}")
        for p in range(passes):
            z = max(step * (p + 1), depth)
            g.append(f"(Pass {p + 1}/{passes} Z={z:.3f})")
            started = False
            for i in range(path.elementCount()):
                el = path.elementAt(i)
                if i == 0 or el.isMoveTo():
                    if started:
                        g.append(f"G0 Z{safe:.3f}")
                    g.append(f"G0 X{el.x:.3f} Y{el.y:.3f}")
                    g.append(f"G1 Z{z:.3f} F{feed:.1f}")
                    started = True
                elif el.isLineTo():
                    g.append(f"G1 X{el.x:.3f} Y{el.y:.3f} F{feed:.1f}")
            g.append(f"G0 Z{safe:.3f}")
        if self.laser.isChecked():
            g.append("M5 (Laser Off)")
        g.append(f"G0 Z{safe:.3f}")
        g.append("M30")
        return "\n".join(g)

    def export_gcode(self):
        try:
            if self.vector_paths:
                combined_path = QPainterPath()
                for p in self.vector_paths:
                    combined_path.addPath(p)
                gcode = self.path_to_gcode(combined_path)
            else:
                if not self.path:
                    QMessageBox.warning(self, "No Preview", "Preview text or vectorize image first.")
                    return
                gcode = self.path_to_gcode(self.path)

            fn, _ = QFileDialog.getSaveFileName(self, "Save G-Code", "engrave_output.nc",
                                                "G-Code Files (*.nc *.gcode);;All Files (*)")
            if not fn:
                return
            with open(fn, "w") as f:
                f.write(gcode)
            self.status.showMessage(f"G-code saved: {fn}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ---- DXF / SVG ----
    def export_dxf(self):
        if not DXF_AVAILABLE:
            QMessageBox.warning(self, "DXF Export Unavailable", "Install ezdxf.")
            return
        if not self.path and not self.vector_paths:
            QMessageBox.warning(self, "No Preview", "Preview text or vectorize image first.")
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Save DXF", "engrave_output.dxf", "DXF Files (*.dxf);;All Files (*)")
        if not fn:
            return
        try:
            doc = ezdxf.new('R2010')
            msp = doc.modelspace()
            paths = self.vector_paths if self.vector_paths else [self.path]
            for qpath in paths:
                pts = []
                for i in range(qpath.elementCount()):
                    el = qpath.elementAt(i)
                    if el.isMoveTo() or el.isLineTo():
                        pts.append((el.x, el.y))
                if len(pts) >= 2:
                    msp.add_lwpolyline(pts)
            doc.saveas(fn)
            self.status.showMessage(f"DXF saved: {fn}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def export_svg(self):
        if not self.path and not self.vector_paths:
            QMessageBox.warning(self, "No Preview", "Preview text or vectorize image first.")
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Save SVG", "engrave_output.svg", "SVG Files (*.svg);;All Files (*)")
        if not fn:
            return
        try:
            paths = self.vector_paths if self.vector_paths else [self.path]
            # simple SVG writer for polylines
            def svg_escape(s): return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            minx=miny= float("inf"); maxx=maxy= float("-inf")
            polylines=[]
            for qpath in paths:
                pts=[]
                for i in range(qpath.elementCount()):
                    el=qpath.elementAt(i)
                    if el.isMoveTo() or el.isLineTo():
                        pts.append((el.x, el.y))
                        minx=min(minx, el.x); maxx=max(maxx, el.x)
                        miny=min(miny, el.y); maxy=max(maxy, el.y)
                if len(pts)>=2:
                    polylines.append(pts)
            if minx==float("inf"):
                QMessageBox.warning(self,"Empty","Nothing to export.")
                return
            width=maxx-minx or 1; height=maxy-miny or 1
            with open(fn,"w") as f:
                f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{minx} {miny} {width} {height}">')
                stroke=self.colors["accent"]
                for pts in polylines:
                    d=" ".join(f"{x},{y}" for x,y in pts)
                    f.write(f'<polyline fill="none" stroke="{svg_escape(stroke)}" stroke-width="0.3" points="{svg_escape(d)}" />')
                f.write("</svg>")
            self.status.showMessage(f"SVG saved: {fn}")
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

    win = CNCEngraveApp(colors)
    win.show()
    sys.exit(app.exec())
