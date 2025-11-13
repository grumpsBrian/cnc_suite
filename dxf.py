#!/usr/bin/env python3
"""
DXF Editor Brian Wilson (Grump) and AI. Inspired by scorchworks
"""
import sys
import os
import math

# --- ADDED 3 LINES BELOW ---
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from themes.theme_utils import apply_theme
# ---------------------------

# ---- Third-party DXF ----
try:
    import ezdxf
except ImportError:
    print("Error: ezdxf not installed. Run: pip install ezdxf")
    sys.exit(1)

# ---- PyQt6 imports ----
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QCheckBox, QDoubleSpinBox,
    QSpinBox, QGroupBox, QFileDialog, QMessageBox, QStatusBar,
    QSplitter, QTextEdit, QListWidget, QListWidgetItem,
    QToolBar, QToolButton, QScrollArea, QFrame, QSizePolicy
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QPointF, QRectF, QSize
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPixmap, QIcon,
    QPainterPath, QKeySequence, QTransform, QAction, QPalette
)
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter



# -------------------------------------------------------
# THEME: Updated to use theme_utils.py
# -------------------------------------------------------
def apply_dxf_theme(app, theme: str = "dark", color: str = "grey"):
    """
    Apply theme using the unified theme system
    """
    return apply_theme(app, theme, color)


# =======================================================
# Canvas widget (zoom/pan/draw/select/grid/snap)
# =======================================================
class DXFCanvas(QWidget):
    mouseMoved = pyqtSignal(float, float)
    itemSelected = pyqtSignal(object)
    viewChanged  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(600, 400)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # View
        self.scale = 50.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.grid_step = 1.0

        # Items
        self.drawn_items = []     # {'type': 'line'|'circle'|'rectangle'|'polyline', 'points': [...], 'selected': bool}
        self.temp_items = []
        self.selected_item = None
        self.hover_item = None

        # Interaction
        self.panning = False
        self.last_pan_point = QPointF()
        self.drawing = False
        self.current_tool = "select"
        self.current_points = []

        # Options
        self.show_grid = True
        self.snap_to_grid = True
        self.show_axes = True

        # Colors - will be updated by theme
        self.grid_color = QColor(80, 80, 80)
        self.axes_color = QColor(150, 150, 150)
        self.selection_color = QColor(255, 80, 80)
        self.hover_color = QColor(255, 200, 0)

        self.setMouseTracking(True)

    def update_theme_colors(self, theme_colors):
        """
        Update canvas colors based on theme
        """
        self.grid_color = QColor(theme_colors.get("accent"))
        self.grid_color.setAlpha(80)  # Make grid more subtle
        
        self.axes_color = QColor(theme_colors.get("accent"))
        self.axes_color.setAlpha(150)
        
        self.selection_color = QColor(255, 80, 80)  # Keep selection red for visibility
        self.hover_color = QColor(255, 200, 0)  # Keep hover yellow for visibility
        
        self.update()

    # ------------- coordinate helpers -------------
    def world_to_screen(self, wx, wy):
        sx = wx * self.scale + self.offset_x + self.width()/2
        sy = -wy * self.scale + self.offset_y + self.height()/2
        return QPointF(sx, sy)

    def screen_to_world(self, sx, sy):
        wx = (sx - self.width()/2 - self.offset_x) / self.scale
        wy = -(sy - self.height()/2 - self.offset_y) / self.scale
        return (wx, wy)

    def snap_point(self, wx, wy):
        if not self.snap_to_grid:
            return (wx, wy)
        step = max(self.grid_step, 1e-9)
        return (round(wx/step)*step, round(wy/step)*step)

    # ------------- add/select -------------
    def add_item(self, item_type, points, properties=None):
        it = {'type': item_type, 'points': points[:], 'selected': False}
        self.drawn_items.append(it)
        self.update()
        return it

    def clear_selection(self):
        for it in self.drawn_items:
            it['selected'] = False
        self.selected_item = None
        self.update()

    def select_item_at(self, wx, wy, tol_px=5.0):
        tol = tol_px / self.scale
        for it in reversed(self.drawn_items):
            if self._near_item(wx, wy, it, tol):
                self.clear_selection()
                it['selected'] = True
                self.selected_item = it
                self.itemSelected.emit(it)
                self.update()
                return it
        self.clear_selection()
        self.itemSelected.emit(None)
        return None

    def _near_item(self, x, y, it, tol):
        t = it['type']
        pts = it['points']
        if t == 'line':
            (x1, y1), (x2, y2) = pts
            return self._point_line_dist(x, y, x1, y1, x2, y2) <= tol
        if t == 'circle':
            (cx, cy), radius = pts
            return abs(math.hypot(x - cx, y - cy) - radius) <= tol
        if t == 'rectangle':
            (x1, y1), (x2, y2) = pts
            xs = sorted([x1, x2]); ys = sorted([y1, y2])
            # near any edge
            edges = [((xs[0], ys[0]), (xs[1], ys[0])),
                     ((xs[1], ys[0]), (xs[1], ys[1])),
                     ((xs[1], ys[1]), (xs[0], ys[1])),
                     ((xs[0], ys[1]), (xs[0], ys[0]))]
            return any(self._point_line_dist(x, y, a[0], a[1], b[0], b[1]) <= tol for a, b in edges)
        if t == 'polyline':
            if len(pts) < 2: return False
            for i in range(len(pts)-1):
                (x1, y1), (x2, y2) = pts[i], pts[i+1]
                if self._point_line_dist(x, y, x1, y1, x2, y2) <= tol:
                    return True
        return False

    @staticmethod
    def _point_line_dist(px, py, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(px - x1, py - y1)
        u = max(0.0, min(1.0, ((px - x1)*dx + (py - y1)*dy) / (dx*dx + dy*dy)))
        cx, cy = x1 + u*dx, y1 + u*dy
        return math.hypot(px - cx, py - cy)

    # ------------- painting -------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        p.fillRect(self.rect(), self.palette().color(QPalette.ColorRole.Window))
        if self.show_grid:
            self._draw_grid(p)
        if self.show_axes:
            self._draw_axes(p)

        # items
        for it in self.drawn_items:
            self._draw_item(p, it, is_temp=False)
        for it in self.temp_items:
            self._draw_item(p, it, is_temp=True)

        if self.selected_item:
            self._draw_selection(p, self.selected_item)

    def _draw_grid(self, p: QPainter):
        p.save()
        p.setPen(QPen(self.grid_color, 1))
        vis = self._visible_world_rect()

        target_px = 40.0
        step_w = target_px / self.scale
        exp = math.floor(math.log10(max(step_w, 1e-9)))
        base = step_w / (10 ** exp)
        if base <= 1.5:
            nice = 1
        elif base <= 3.5:
            nice = 2
        else:
            nice = 5
        self.grid_step = nice * (10 ** exp)

        # verticals
        x = math.floor(vis.left() / self.grid_step) * self.grid_step
        while x <= vis.right():
            a = self.world_to_screen(x, vis.top())
            b = self.world_to_screen(x, vis.bottom())
            p.drawLine(a, b)
            x += self.grid_step

        # horizontals
        y = math.floor(vis.bottom() / self.grid_step) * self.grid_step
        while y <= vis.top():
            a = self.world_to_screen(vis.left(), y)
            b = self.world_to_screen(vis.right(), y)
            p.drawLine(a, b)
            y += self.grid_step

        p.restore()

    def _draw_axes(self, p: QPainter):
        p.save()
        p.setPen(QPen(self.axes_color, 2))
        origin = self.world_to_screen(0, 0)
        left   = self.world_to_screen(-10000, 0)
        right  = self.world_to_screen(10000, 0)
        top    = self.world_to_screen(0, 10000)
        bot    = self.world_to_screen(0, -10000)
        p.drawLine(left, right)
        p.drawLine(bot, top)
        p.restore()

    def _draw_item(self, p: QPainter, it, is_temp=False):
        p.save()
        
        # Use theme colors for drawing
        text_color = self.palette().color(QPalette.ColorRole.Text)
        accent_color = self.palette().color(QPalette.ColorRole.Highlight)
        
        pen = QPen(text_color, 2)
        if is_temp:
            pen.setStyle(Qt.PenStyle.DashLine)
        if it.get('selected'):
            pen.setColor(self.selection_color)
            pen.setWidth(3)
        else:
            # Use accent color for normal items
            pen.setColor(accent_color)
            
        p.setPen(pen)

        t = it['type']
        pts = it['points']
        if t == 'line':
            p1, p2 = self.world_to_screen(*pts[0]), self.world_to_screen(*pts[1])
            p.drawLine(p1, p2)
        elif t == 'rectangle':
            r = QRectF(self.world_to_screen(*pts[0]), self.world_to_screen(*pts[1])).normalized()
            p.drawRect(r)
        elif t == 'circle':
            (cx, cy), radius = pts
            c = self.world_to_screen(cx, cy)
            r = radius * self.scale
            p.drawEllipse(QRectF(c.x()-r, c.y()-r, 2*r, 2*r))
        elif t == 'polyline' and len(pts) >= 2:
            path = QPainterPath(self.world_to_screen(*pts[0]))
            for pt in pts[1:]:
                path.lineTo(self.world_to_screen(*pt))
            p.drawPath(path)

        p.restore()

    def _draw_selection(self, p: QPainter, it):
        p.save()
        pen = QPen(self.selection_color, 1, Qt.PenStyle.DashLine)
        p.setPen(pen)
        if it['type'] == 'line':
            for pt in it['points']:
                s = self.world_to_screen(*pt)
                p.drawRect(QRectF(s.x()-3, s.y()-3, 6, 6))
        elif it['type'] == 'circle':
            c = self.world_to_screen(*it['points'][0])
            p.drawRect(QRectF(c.x()-3, c.y()-3, 6, 6))
        elif it['type'] == 'rectangle':
            # corners
            (x1,y1),(x2,y2) = it['points']
            for pt in [(x1,y1),(x1,y2),(x2,y1),(x2,y2)]:
                s = self.world_to_screen(*pt)
                p.drawRect(QRectF(s.x()-3, s.y()-3, 6, 6))
        p.restore()

    def _visible_world_rect(self):
        r = self.rect()
        tl = self.screen_to_world(r.left(), r.top())
        br = self.screen_to_world(r.right(), r.bottom())
        return QRectF(QPointF(tl[0], tl[1]), QPointF(br[0], br[1]))

    # ------------- interaction -------------
    def wheelEvent(self, e):
        mouse_before = self.screen_to_world(e.position().x(), e.position().y())
        factor = 1.1 if e.angleDelta().y() > 0 else 1/1.1
        new_scale = max(0.1, min(1000.0, self.scale * factor))
        if new_scale != self.scale:
            self.scale = new_scale
            mouse_after = self.screen_to_world(e.position().x(), e.position().y())
            # keep mouse anchor
            self.offset_x += (mouse_after[0]-mouse_before[0]) * self.scale
            self.offset_y -= (mouse_after[1]-mouse_before[1]) * self.scale
            self.update()
            self.viewChanged.emit()

    def mousePressEvent(self, e):
        wx, wy = self.screen_to_world(e.position().x(), e.position().y())
        sx, sy = self.snap_point(wx, wy)
        if e.button() == Qt.MouseButton.MiddleButton or (e.button() == Qt.MouseButton.LeftButton and e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.panning = True
            self.last_pan_point = e.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if e.button() == Qt.MouseButton.LeftButton:
            if self.current_tool == "select":
                self.select_item_at(wx, wy)
            else:
                self._start_drawing(sx, sy)
        if e.button() == Qt.MouseButton.RightButton:
            self.select_item_at(wx, wy)
        self.update()

    def mouseMoveEvent(self, e):
        wx, wy = self.screen_to_world(e.position().x(), e.position().y())
        sx, sy = self.snap_point(wx, wy)
        self.mouseMoved.emit(sx, sy)
        if self.panning:
            d = e.position() - self.last_pan_point
            self.offset_x += d.x()
            self.offset_y += d.y()
            self.last_pan_point = e.position()
            self.update()
        elif self.drawing and self.current_tool != "select":
            self._continue_drawing(sx, sy)
        else:
            # hover
            old = self.hover_item
            self.hover_item = None
            for it in reversed(self.drawn_items):
                if self._near_item(wx, wy, it, 5.0/self.scale):
                    self.hover_item = it
                    break
            if self.hover_item != old:
                self.update()

    def mouseReleaseEvent(self, e):
        wx, wy = self.screen_to_world(e.position().x(), e.position().y())
        sx, sy = self.snap_point(wx, wy)
        if e.button() == Qt.MouseButton.LeftButton and self.drawing:
            if self.current_tool == "polyline":
                # left-click adds points; right-click will finalize
                self.current_points.append((sx, sy))
                self._update_temp_item()
            else:
                self._finish_drawing(sx, sy)
        if e.button() == Qt.MouseButton.MiddleButton or (e.button() == Qt.MouseButton.LeftButton and e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Delete and self.selected_item:
            self.drawn_items.remove(self.selected_item)
            self.selected_item = None
            self.update()
            e.accept()
            return
        if e.key() == Qt.Key.Key_Escape:
            if self.drawing:
                self._cancel_drawing()
            else:
                self.clear_selection()
            e.accept()
            return
        super().keyPressEvent(e)

    # ------------- drawing ops -------------
    def _start_drawing(self, x, y):
        self.drawing = True
        self.current_points = [(x, y)]
        if self.current_tool in ("line", "rectangle", "circle", "polyline"):
            self.current_points.append((x, y))
        self._update_temp_item()

    def _continue_drawing(self, x, y):
        if not self.drawing or not self.current_points: return
        self.current_points[-1] = (x, y)
        self._update_temp_item()

    def _finish_drawing(self, x, y):
        if not self.drawing: return
        self.current_points[-1] = (x, y)
        if len(self.current_points) >= 2:
            if self.current_tool == "line":
                it = self.add_item('line', [self.current_points[0], self.current_points[-1]])
            elif self.current_tool == "rectangle":
                it = self.add_item('rectangle', [self.current_points[0], self.current_points[-1]])
            elif self.current_tool == "circle":
                c = self.current_points[0]
                r = math.hypot(self.current_points[-1][0]-c[0], self.current_points[-1][1]-c[1])
                it = self.add_item('circle', [c, r])
            elif self.current_tool == "polyline":
                it = self.add_item('polyline', self.current_points[:-1])  # drop temp last
            else:
                it = None
            if it:
                self.clear_selection()
                it['selected'] = True
                self.selected_item = it
                self.itemSelected.emit(it)
        self._cancel_drawing()

    def _cancel_drawing(self):
        self.drawing = False
        self.current_points = []
        self.temp_items = []
        self.update()

    def _update_temp_item(self):
        self.temp_items = []
        if len(self.current_points) < 2:
            self.update(); return
        t = self.current_tool
        if t == "line":
            self.temp_items.append({'type':'line', 'points': self.current_points[:]})
        elif t == "rectangle":
            self.temp_items.append({'type':'rectangle', 'points': self.current_points[:]})
        elif t == "circle":
            c, rp = self.current_points[0], self.current_points[-1]
            r = math.hypot(rp[0]-c[0], rp[1]-c[1])
            self.temp_items.append({'type':'circle', 'points':[c, r]})
        elif t == "polyline":
            self.temp_items.append({'type':'polyline', 'points': self.current_points[:]})
        self.update()

    # ------------- view -------------
    def fit_to_content(self):
        if not self.drawn_items: return
        minx=miny= float("inf"); maxx=maxy= float("-inf")
        for it in self.drawn_items:
            if it['type']=='circle':
                (cx,cy), r = it['points']
                minx=min(minx, cx-r); maxx=max(maxx, cx+r)
                miny=min(miny, cy-r); maxy=max(maxy, cy+r)
            else:
                for (x,y) in it['points']:
                    minx=min(minx,x); maxx=max(maxx,x)
                    miny=min(miny,y); maxy=max(maxy,y)
        if minx==float("inf"): return
        pad = 0.1*max(maxx-minx, maxy-miny)
        minx-=pad; miny-=pad; maxx+=pad; maxy+=pad
        w=maxx-minx; h=maxy-miny
        if w==0 or h==0: return
        sx=(self.width()-40)/w; sy=(self.height()-40)/h
        self.scale = max(0.1, min(1000.0, min(sx, sy)))
        cx=(minx+maxx)/2; cy=(miny+maxy)/2
        self.offset_x = - (cx*self.scale)
        self.offset_y =   (cy*self.scale)
        self.update()
        self.viewChanged.emit()

    # ------------- DXF I/O -------------
    def export_to_doc(self, doc):
        msp = doc.modelspace()
        # remove existing
        for e in list(msp):
            msp.delete_entity(e)
        for it in self.drawn_items:
            t=it['type']; pts=it['points']
            if t=='line':
                msp.add_line(pts[0], pts[1])
            elif t=='rectangle':
                (x1,y1),(x2,y2)=pts
                poly=[(x1,y1),(x2,y1),(x2,y2),(x1,y2),(x1,y1)]
                msp.add_lwpolyline(poly)
            elif t=='circle':
                c, r = pts
                msp.add_circle(c, r)
            elif t=='polyline':
                msp.add_lwpolyline(pts)


# =======================================================
# Main window (menus, toolbar, left panel, right canvas)
# =======================================================
class DXFEditorQt(QMainWindow):
    def __init__(self, theme_colors=None):
        super().__init__()
        self.doc = None
        self.filename = None
        self.theme_colors = theme_colors or {}
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("DXF Editor - Qt6")
        self.setGeometry(100, 50, 1600, 1000)

        # Menu
        self._setup_menubar()

        # Toolbar
        self._setup_toolbar()

        # Central
        central = QWidget(); self.setCentralWidget(central)
        main_layout = QHBoxLayout(central); main_layout.setContentsMargins(5,5,5,5); main_layout.setSpacing(5)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        left = self._create_control_panel()
        right = self._create_canvas_panel()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([350, 1250])

        self.status_bar = QStatusBar(); self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready - Create or Open a DXF to start")

        self.new_dxf()

    # ----- menus -----
    def _setup_menubar(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        act_new = QAction("&New", self); act_new.setShortcut(QKeySequence.StandardKey.New); act_new.triggered.connect(self.new_dxf); file_menu.addAction(act_new)
        act_open= QAction("&Open", self); act_open.setShortcut(QKeySequence.StandardKey.Open); act_open.triggered.connect(self.open_dxf); file_menu.addAction(act_open)
        act_save= QAction("&Save", self); act_save.setShortcut(QKeySequence.StandardKey.Save); act_save.triggered.connect(self.save_dxf); file_menu.addAction(act_save)
        act_saveas= QAction("Save &As", self); act_saveas.setShortcut(QKeySequence.StandardKey.SaveAs); act_saveas.triggered.connect(self.save_as_dxf); file_menu.addAction(act_saveas)
        file_menu.addSeparator()
        act_print = QAction("&Print…", self); act_print.setShortcut(QKeySequence.StandardKey.Print); act_print.triggered.connect(self.print_dxf); file_menu.addAction(act_print)
        file_menu.addSeparator()
        act_exit= QAction("E&xit", self); act_exit.setShortcut("Ctrl+Q"); act_exit.triggered.connect(self.close); file_menu.addAction(act_exit)

        view_menu = mb.addMenu("&View")
        act_zi = QAction("Zoom &In", self); act_zi.setShortcut(QKeySequence.StandardKey.ZoomIn); act_zi.triggered.connect(self.zoom_in); view_menu.addAction(act_zi)
        act_zo = QAction("Zoom &Out", self); act_zo.setShortcut(QKeySequence.StandardKey.ZoomOut); act_zo.triggered.connect(self.zoom_out); view_menu.addAction(act_zo)
        act_fit = QAction("&Fit to View", self); act_fit.setShortcut("Ctrl+F"); act_fit.triggered.connect(self.fit_to_view); view_menu.addAction(act_fit)
        view_menu.addSeparator()
        self.act_grid = QAction("Show &Grid", self, checkable=True); self.act_grid.setChecked(True); self.act_grid.triggered.connect(self.toggle_grid); view_menu.addAction(self.act_grid)
        self.act_snap = QAction("&Snap to Grid", self, checkable=True); self.act_snap.setChecked(True); self.act_snap.triggered.connect(self.toggle_snap); view_menu.addAction(self.act_snap)

    # ----- toolbar -----
    def _setup_toolbar(self):
        tb = QToolBar("Main Toolbar"); tb.setIconSize(QSize(24,24)); self.addToolBar(tb)

        # tool buttons
        self.tool_buttons = {}
        for tid, label in [("select","Select"), ("line","Line"), ("circle","Circle"), ("rectangle","Rectangle"), ("polyline","Polyline")]:
            btn = QToolButton(); btn.setText(label); btn.setCheckable(True)
            btn.clicked.connect(lambda checked, t=tid: self.set_tool(t))
            tb.addWidget(btn); self.tool_buttons[tid]=btn
        self.tool_buttons["select"].setChecked(True)

        tb.addSeparator()
        zi=QToolButton(); zi.setText("Zoom In"); zi.clicked.connect(self.zoom_in); tb.addWidget(zi)
        zo=QToolButton(); zo.setText("Zoom Out"); zo.clicked.connect(self.zoom_out); tb.addWidget(zo)
        fit=QToolButton(); fit.setText("Fit View"); fit.clicked.connect(self.fit_to_view); tb.addWidget(fit)

    # ----- panels -----
    def _create_control_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel); layout.setSpacing(10)

        # File operations
        grp_file = QGroupBox("File Operations"); gl = QVBoxLayout(grp_file)
        b_new=QPushButton("New DXF"); b_new.clicked.connect(self.new_dxf); gl.addWidget(b_new)
        b_open=QPushButton("Open DXF"); b_open.clicked.connect(self.open_dxf); gl.addWidget(b_open)
        b_save=QPushButton("Save"); b_save.clicked.connect(self.save_dxf); gl.addWidget(b_save)
        b_saveas=QPushButton("Save As"); b_saveas.clicked.connect(self.save_as_dxf); gl.addWidget(b_saveas)
        layout.addWidget(grp_file)

        # Display options
        grp_disp=QGroupBox("Display Options"); dl=QVBoxLayout(grp_disp)
        self.grid_check=QCheckBox("Show Grid"); self.grid_check.setChecked(True); self.grid_check.toggled.connect(self.toggle_grid); dl.addWidget(self.grid_check)
        self.snap_check=QCheckBox("Snap to Grid"); self.snap_check.setChecked(True); self.snap_check.toggled.connect(self.toggle_snap); dl.addWidget(self.snap_check)
        layout.addWidget(grp_disp)

        # Entity management
        grp_ent=QGroupBox("Entity Management"); el=QVBoxLayout(grp_ent)
        self.entity_list=QListWidget(); self.entity_list.itemSelectionChanged.connect(self.on_entity_selected_list); el.addWidget(self.entity_list)
        b_del=QPushButton("Delete Selected"); b_del.clicked.connect(self.delete_selected); el.addWidget(b_del)
        layout.addWidget(grp_ent)

        # Info
        grp_info=QGroupBox("Information"); il=QVBoxLayout(grp_info)
        self.coord_label=QLabel("X: 0.000, Y: 0.000"); il.addWidget(self.coord_label)
        self.selection_label=QLabel("No selection"); il.addWidget(self.selection_label)
        self.dxf_info_label=QLabel("No DXF loaded"); self.dxf_info_label.setWordWrap(True); il.addWidget(self.dxf_info_label)
        layout.addWidget(grp_info)

        layout.addStretch()
        return panel

    def _create_canvas_panel(self):
        panel = QWidget(); v = QVBoxLayout(panel)
        self.canvas = DXFCanvas()
        self.canvas.mouseMoved.connect(self.on_mouse_moved)
        self.canvas.itemSelected.connect(self.on_item_selected)
        self.canvas.viewChanged.connect(self.on_view_changed)
        
        # Apply theme colors to canvas
        if self.theme_colors:
            self.canvas.update_theme_colors(self.theme_colors)
            
        v.addWidget(self.canvas)
        return panel

    # ----- tool selection -----
    def set_tool(self, tool_id):
        for t, b in self.tool_buttons.items():
            if t != tool_id:
                b.setChecked(False)
        self.canvas.current_tool = tool_id
        self.canvas._cancel_drawing()
        if tool_id == "select":
            self.canvas.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.canvas.setCursor(Qt.CursorShape.CrossCursor)
        self.status_bar.showMessage(f"Tool: {tool_id.capitalize()}")

    # ----- canvas signal handlers -----
    def on_mouse_moved(self, x, y):
        self.coord_label.setText(f"X: {x:.3f}, Y: {y:.3f}")

    def on_item_selected(self, item):
        if item:
            t=item['type']; pts=item['points']
            if t=='line':
                self.selection_label.setText(f"Line: ({pts[0][0]:.2f},{pts[0][1]:.2f}) → ({pts[1][0]:.2f},{pts[1][1]:.2f})")
            elif t=='circle':
                self.selection_label.setText(f"Circle: Center ({pts[0][0]:.2f},{pts[0][1]:.2f}), R={pts[1]:.2f}")
            elif t=='rectangle':
                self.selection_label.setText(f"Rectangle: ({pts[0][0]:.2f},{pts[0][1]:.2f}) ↔ ({pts[1][0]:.2f},{pts[1][1]:.2f})")
            elif t=='polyline':
                self.selection_label.setText(f"Polyline: {len(pts)} points")
            self._refresh_entity_list()
        else:
            self.selection_label.setText("No selection")

    def on_view_changed(self):
        s = self.canvas.scale
        msg = f"Scale: {s:.2f}" if s >= 1 else f"Scale: 1:{1/s:.0f}"
        self.status_bar.showMessage(msg)

    def on_entity_selected_list(self):
        sel = self.entity_list.selectedItems()
        if not sel: return
        idx = self.entity_list.row(sel[0])
        if 0 <= idx < len(self.canvas.drawn_items):
            self.canvas.clear_selection()
            it = self.canvas.drawn_items[idx]
            it['selected'] = True
            self.canvas.selected_item = it
            self.canvas.update()
            self.on_item_selected(it)

    # ----- view toggles -----
    def toggle_grid(self):
        state = self.grid_check.isChecked()
        self.canvas.show_grid = state
        if hasattr(self, 'act_grid'):
            self.act_grid.setChecked(state)
        self.canvas.update()

    def toggle_snap(self):
        state = self.snap_check.isChecked()
        self.canvas.snap_to_grid = state
        if hasattr(self, 'act_snap'):
            self.act_snap.setChecked(state)

    # ----- zoom / fit -----
    def zoom_in(self):
        self.canvas.scale = min(1000.0, self.canvas.scale * 1.2)
        self.canvas.update(); self.on_view_changed()

    def zoom_out(self):
        self.canvas.scale = max(0.1, self.canvas.scale / 1.2)
        self.canvas.update(); self.on_view_changed()

    def fit_to_view(self):
        self.canvas.fit_to_content()

    # ----- entity ops -----
    def delete_selected(self):
        if self.canvas.selected_item:
            self.canvas.drawn_items.remove(self.canvas.selected_item)
            self.canvas.selected_item = None
            self.canvas.update()
            self._refresh_entity_list()
            self.selection_label.setText("No selection")

    # ----- DXF ops -----
    def new_dxf(self):
        try:
            self.doc = ezdxf.new('R2010')
            self.filename = None
            self.canvas.drawn_items = []
            self.canvas.selected_item = None
            self.canvas.update()
            self._refresh_entity_list()
            self._update_dxf_info()
            self.status_bar.showMessage("Created new DXF document")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create new DXF:\n{e}")

    def open_dxf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open DXF File", "", "DXF Files (*.dxf);;All Files (*.*)")
        if not path: return
        try:
            self.doc = ezdxf.readfile(path)
            self.filename = path
            self._import_doc_entities()
            self._refresh_entity_list()
            self._update_dxf_info()
            self.canvas.fit_to_content()
            self.status_bar.showMessage(f"Loaded: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load DXF:\n{e}")

    def save_dxf(self):
        if not self.doc:
            QMessageBox.warning(self, "Warning", "No DXF document to save")
            return
        if not self.filename:
            self.save_as_dxf(); return
        try:
            self.canvas.export_to_doc(self.doc)
            self.doc.saveas(self.filename)
            self.status_bar.showMessage(f"Saved: {self.filename}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save DXF:\n{e}")

    def save_as_dxf(self):
        if not self.doc:
            QMessageBox.warning(self, "Warning", "No DXF document to save")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save DXF File", "", "DXF Files (*.dxf);;All Files (*.*)")
        if not path: return
        try:
            self.canvas.export_to_doc(self.doc)
            self.doc.saveas(path)
            self.filename = path
            self.status_bar.showMessage(f"Saved: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save DXF:\n{e}")

    def print_dxf(self):
        if not self.doc:
            QMessageBox.information(self, "Print", "Nothing to print.")
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() == QPrintDialog.DialogCode.Accepted:
            # Simple print: render canvas
            # (For CAD-accurate printing, export to vector/pdf; this keeps parity with your UI.)
            from PyQt6.QtGui import QPixmap
            pm = QPixmap(self.canvas.size())
            self.canvas.render(pm)
            painter = QPainter(printer)
            rect = painter.viewport()
            size = pm.size()
            size.scale(rect.size(), Qt.AspectRatioMode.KeepAspectRatio)
            painter.setViewport(rect.x(), rect.y(), size.width(), size.height())
            painter.setWindow(pm.rect())
            painter.drawPixmap(0, 0, pm)
            painter.end()

    def _import_doc_entities(self):
        self.canvas.drawn_items = []
        if not self.doc: return
        msp = self.doc.modelspace()
        for e in msp:
            try:
                t = e.dxftype()
                if t == 'LINE':
                    s, t_ = e.dxf.start, e.dxf.end
                    self.canvas.add_item('line', [(s.x, s.y), (t_.x, t_.y)])
                elif t == 'CIRCLE':
                    c = e.dxf.center; r = e.dxf.radius
                    self.canvas.add_item('circle', [(c.x, c.y), r])
                elif t in ('LWPOLYLINE', 'POLYLINE'):
                    pts=[]
                    try:
                        for pt in e.get_points():
                            pts.append((pt[0], pt[1]))
                    except Exception:
                        try:
                            for v in e.vertices():
                                loc=v.dxf.location; pts.append((loc.x, loc.y))
                        except Exception:
                            pass
                    if pts:
                        if t=='LWPOLYLINE' and getattr(e, 'closed', False):
                            pts.append(pts[0])
                        self.canvas.add_item('polyline', pts)
            except Exception:
                continue
        self.canvas.update()

    def _refresh_entity_list(self):
        self.entity_list.clear()
        for i, it in enumerate(self.canvas.drawn_items):
            self.entity_list.addItem(QListWidgetItem(f"{i}: {it['type'].capitalize()}"))

    def _update_dxf_info(self):
        if not self.doc:
            self.dxf_info_label.setText("No DXF loaded"); return
        ents = list(self.doc.modelspace())
        info = (f"DXF Information:\n"
                f"File: {self.filename or 'Unsaved'}\n"
                f"Version: {self.doc.dxfversion}\n"
                f"Entities: {len(ents)}\n"
                f"Layers: {len(self.doc.layers)}")
        self.dxf_info_label.setText(info)


# -------------------------------------------------------
# Entry point
# -------------------------------------------------------
if __name__ == "__main__":
    theme = "dark"
    color = "grey"
    
    # Parse command line arguments
    if "--theme" in sys.argv:
        i = sys.argv.index("--theme")
        if i + 1 < len(sys.argv):
            theme = sys.argv[i + 1].lower()
    
    if "--color" in sys.argv:
        i = sys.argv.index("--color")
        if i + 1 < len(sys.argv):
            color = sys.argv[i + 1].lower()

    app = QApplication(sys.argv)
    theme_colors = apply_dxf_theme(app, theme, color)

    win = DXFEditorQt(theme_colors)
    win.show()
    sys.exit(app.exec())