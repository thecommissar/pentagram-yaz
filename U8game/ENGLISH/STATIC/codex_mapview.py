# requirements: pip install pygame PyQt5
import sys, os, struct, pygame
from PyQt5 import QtWidgets, QtGui, QtCore

# ---------------------------------------------------------------------------
# (palette, ShapeArchive, load_map_objects, map_to_screen functions unchanged)
# Copy the helper code from the previous snippet here
# ---------------------------------------------------------------------------

class PygameWidget(QtWidgets.QWidget):
    """Qt widget that hosts a Pygame surface."""
    def __init__(self, static_dir, map_index, parent=None):
        super().__init__(parent)
        self.static_dir = static_dir
        self.map_index = map_index
        self.setMinimumSize(800, 600)

        # Pygame initialization
        pygame.init()
        self.screen = pygame.Surface(self.size(), pygame.SRCALPHA)
        self.offset = pygame.Vector2(0, 0)

        self.palette = load_palette(os.path.join(static_dir, "U8PAL.PAL"))
        self.shapes = ShapeArchive(os.path.join(static_dir, "U8SHAPES.FLX"), self.palette)
        self.objs = load_map_objects(os.path.join(static_dir, "FIXED.DAT"), map_index)

        # Timer to drive the redraw loop
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(16)       # ~60 FPS

    # key handling -----------------------------------------------------------
    def keyPressEvent(self, event):
        step = 8
        if   event.key() == QtCore.Qt.Key_Left:  self.offset.x -= step
        elif event.key() == QtCore.Qt.Key_Right: self.offset.x += step
        elif event.key() == QtCore.Qt.Key_Up:    self.offset.y -= step
        elif event.key() == QtCore.Qt.Key_Down:  self.offset.y += step

    # render loop ------------------------------------------------------------
    def update_frame(self):
        self.screen.fill((0,0,0))
        for x,y,z,typ,frm in sorted(self.objs,key=lambda o:o[0]+o[1]+o[2]):
            img, xo, yo = self.shapes.load_frame(typ, frm)
            sx, sy = map_to_screen(x, y, z)
            self.screen.blit(img, (sx-xo+self.offset.x, sy-yo+self.offset.y))
        self.update()

    # Qt paint ---------------------------------------------------------------
    def paintEvent(self, event):
        img = pygame.image.tostring(self.screen, "RGBA")
        qimg = QtGui.QImage(img, self.screen.get_width(), self.screen.get_height(),
                            QtGui.QImage.Format_RGBA8888)
        painter = QtGui.QPainter(self)
        painter.drawImage(0, 0, qimg)

    # map switching ----------------------------------------------------------
    def load_map(self, index):
        self.map_index = index
        self.objs = load_map_objects(os.path.join(self.static_dir, "FIXED.DAT"), index)
        self.offset.update(0, 0)

# ---------------------------------------------------------------------------

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, static_dir):
        super().__init__()
        self.setWindowTitle("Ultima 8 Map Viewer")
        self.viewer = PygameWidget(static_dir, 0)
        self.setCentralWidget(self.viewer)

        # toolbar ------------------------------------------------------------
        toolbar = self.addToolBar("Maps")
        self.map_combo = QtWidgets.QComboBox()
        self.map_combo.addItems([f"Map {i}" for i in range(10)])  # adjust as needed
        self.map_combo.currentIndexChanged.connect(self.viewer.load_map)
        toolbar.addWidget(QtWidgets.QLabel("Select map:"))
        toolbar.addWidget(self.map_combo)

        # status bar ---------------------------------------------------------
        self.statusBar().showMessage("Arrow keys to pan")

def main():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow("/path/to/STATIC")   # <-- set your STATIC dir
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
