from numpy.core.numeric import array_equal
import pydicom
from skimage.filters import threshold_otsu
from skimage.transform import resize
from skimage import io
import sys
import os
import shutil
from PyQt5.QtWidgets import QLabel, QGridLayout
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QSize, Qt
import numpy as np

class Drawable():
    def __init__(self, array):
        self.raw_img = array.pixel_array
        self.vox_dims = array[(0x0018, 0x1164)].value
        self.dims = list(self.raw_img.shape)

    def get_drawable(self):
        image = resize(self.raw_img, self.dims, anti_aliasing=True)
        image = ((image - image.min())/(image.max() - image.min())*255).astype(np.uint8)
        drawable = QtGui.QImage(image.tobytes('C'), self.dims[1], self.dims[0], self.dims[1], QtGui.QImage.Format_Grayscale8)
        return drawable

class Mask(Drawable):
    def __init__(self, array):
        super().__init__(array)
        thresh = threshold_otsu(array.pixel_array)
        bin = (array.pixel_array > thresh) * 255
        self.raw_img = bin
        
def is_inside(point, rect):
    if point[0] < rect[0] or point[1] < rect[1] or point[0] > rect[2] or point[1] > rect[3]:
        return False
    return True

class MouseCircle(QLabel):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.rad = 30
        self.setFixedSize(QtCore.QSize(self.rad*2, self.rad*2))
        self.setMouseTracking(True)
        self.pen_color = Qt.red
    def set_size(self, rad):
        self.rad = rad
        self.setFixedSize(QtCore.QSize(rad*2, rad*2))

    def set_pen_color(self, color):
        self.pen_color = color
        
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        pen = QtGui.QPen()
        pen.setStyle(Qt.DashDotLine)
        pen.setWidth(3)
        pen.setBrush(self.pen_color)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QtCore.QPoint(self.rad, self.rad), self.rad, self.rad)

class MaskFrame(QtWidgets.QLabel):
    def __init__(self, width, height, img):
        super().__init__()
        self.setMouseTracking(True)
        self.is_drawing = False
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.setFrameShape(QtWidgets.QFrame.Box)
        self.dcm = img
        self.draw_point = None
        self.pix = QtGui.QPixmap(self.dcm.get_drawable())
        self.setPixmap(self.pix)
        self.installEventFilter(self)
        self.brush_radius = 30
        self.brush_color = Qt.black
        self.img_rect = None
        self.scale = 1
        self.area_label_hook = None
        
        self.m_circle = MouseCircle(self)

    def paintEvent(self, event):
        if not self.pix.isNull():
            size = self.size()
            scaledPix = self.pix.scaled(size, Qt.KeepAspectRatio, transformMode = Qt.FastTransformation)
            self.scale = self.pix.width() / scaledPix.width()
            point = QtCore.QPoint(0,0)
            point.setX(int((size.width() - scaledPix.width())/2))
            point.setY(int((size.height() - scaledPix.height())/2))
            
            self.img_rect = [point.x(), point.y(), point.x() + scaledPix.width(), point.y() + scaledPix.height()]
            if self.draw_point:
                if is_inside((self.draw_point.x(), self.draw_point.y()), self.img_rect):
                    painter = QtGui.QPainter(self.pix)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QtGui.QBrush(self.brush_color, Qt.SolidPattern))
                    painter.drawEllipse((self.draw_point - point)* self.scale, self.brush_radius * self.scale, self.brush_radius * self.scale)
                    self.draw_point = None
            scaledPix = self.pix.scaled(size, Qt.KeepAspectRatio, transformMode = Qt.FastTransformation)
            label_painter = QtGui.QPainter(self)
            label_painter.drawPixmap(point, scaledPix)

    def set_brush_radius(self, rad):
        self.brush_radius = rad
        self.m_circle.setFixedSize(QSize(rad*2, rad*2))

    def set_brush_color(self, color):
        self.brush_color = color

    def mouseMoveEvent(self, event):
        if self.is_drawing is True:
            self.draw_point = event.pos()
        self.repaint()
        self.m_circle.move(event.pos() - QtCore.QPoint(self.m_circle.rad, self.m_circle.rad))
        mouse_point = event.pos()

        if is_inside((mouse_point.x(), mouse_point.y()), self.img_rect):
            self.m_circle.show()
        else:
            self.mouseReleaseEvent(event)
            self.m_circle.hide()

    def mousePressEvent(self, event):
        self.draw_point = event.pos()
        self.repaint()
        self.is_drawing = True

    def mouseReleaseEvent(self, event):
        self.is_drawing = False
        self.area_label_hook.setText(f'Segmented area: {self.get_image_area()} \u339F')

    def get_image_area(self):
        image = self.pix.toImage().convertToFormat(QtGui.QImage.Format_Grayscale8)
        fn = f'.tmp/tmp_msk_{np.random.rand(1)}.png'
        image.save(fn)
        np_img = io.imread(fn)
        np_img[np_img != 0] = 255
        area = np.sum(np_img == 255) * self.dcm.vox_dims[0] * self.dcm.vox_dims[1]
        os.remove(fn)
        return np.round(area, 2)

class ImageFrame(QtWidgets.QLabel):
    def __init__(self, width, height, img):
        super().__init__()
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.setFrameShape(QtWidgets.QFrame.Box)
        self.setMouseTracking(True)
        self.dcm = img
        self.pix = QtGui.QPixmap(self.dcm.get_drawable())
        self.setPixmap(self.pix)
        self.installEventFilter(self)

    def paintEvent(self, event):
        if not self.pix.isNull():
            size = self.size()
            scaledPix = self.pix.scaled(size, Qt.KeepAspectRatio, transformMode = Qt.FastTransformation)
            point = QtCore.QPoint(0,0)
            point.setX(int((size.width() - scaledPix.width())/2))
            point.setY(int((size.height() - scaledPix.height())/2))
            label_painter = QtGui.QPainter(self)
            label_painter.drawPixmap(point, scaledPix)

class Window(QtWidgets.QWidget):
    def __init__(self, screen):
        super().__init__()
        self.createGridLayout()
        self.setLayout(self.layout)
        self.setMouseTracking(True)

    def createGridLayout(self):
        self.layout = QGridLayout()
        test = pydicom.dcmread('data/mammo/4656975/2D_PROC/1.2.840.113619.2.401.101117117513079.17839180329091021.3.dcm')
        self.mmask = MaskFrame(300, 400, Mask(test))
        self.idpacs_label = QLabel(f"ID PACS: {test.PatientID}")
        self.area_label = QLabel(f'Segmented area: {self.mmask.get_image_area()} \u339F')
        self.mmask.area_label_hook = self.area_label
        self.idpacs_label.setFixedHeight(30)
        self.area_label.setFixedHeight(30)

        self.layout.addWidget(self.idpacs_label, 0,0)
        self.layout.addWidget(self.area_label, 0,1)
        self.layout.addWidget(ImageFrame(300, 400, Drawable(test)),1,0)
        self.layout.addWidget(self.mmask,1,1)
        
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, screen):
        super().__init__()
        self.title = 'MammArea'
        self.available_size = screen
        self.setWindowTitle(self.title)
        self.setMouseTracking(True)
        self.setGeometry(screen.adjusted(int(screen.size().height()*0.1), int(screen.size().height()*0.1), int(-screen.size().width()*0.1), int(-screen.size().width()*0.1)))
        self.main_window = Window(screen)
        self.create_toolbar()
        self.setCentralWidget(self.main_window)

    def create_toolbar(self):
        editToolbar = self.addToolBar('Brush menu')
        editToolbar.setIconSize(QtCore.QSize(50, 50))

        brushAction = QtWidgets.QAction(QtGui.QIcon('assets/brush.png'), 'Brush', self)
        editToolbar.addAction(brushAction)
        brushAction.triggered.connect(lambda x: self.main_window.mmask.set_brush_color(Qt.white))
        brushAction.triggered.connect(lambda x: self.main_window.mmask.m_circle.set_pen_color(Qt.green))

        rubberAction = QtWidgets.QAction(QtGui.QIcon('assets/rubber.png'), 'Rubber', self)
        editToolbar.addAction(rubberAction)
        rubberAction.triggered.connect(lambda x: self.main_window.mmask.set_brush_color(Qt.black))
        rubberAction.triggered.connect(lambda x: self.main_window.mmask.m_circle.set_pen_color(Qt.red))

        sizeContainer = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout()

        self.brushSizeLcd = QtWidgets.QLCDNumber()
        self.brushSizeLcd.display(30)
        self.brushSizeSlider = QtWidgets.QSlider(Qt.Horizontal)
        self.brushSizeSlider.setRange(1, 300)
        self.brushSizeSlider.setValue(30)
        self.brushSizeSlider.setFocusPolicy(Qt.NoFocus)
        self.brushSizeSlider.valueChanged.connect(lambda x: self.main_window.mmask.set_brush_radius(self.brushSizeSlider.value()))
        self.brushSizeSlider.valueChanged.connect(lambda x: self.main_window.mmask.m_circle.set_size(self.brushSizeSlider.value()))
        self.brushSizeSlider.valueChanged.connect(lambda x: self.brushSizeLcd.display(self.brushSizeSlider.value()))
        self.brushSizeSlider.setMaximumWidth(100)
        self.brushSizeLcd.setMaximumWidth(100)
        vbox.addWidget(self.brushSizeLcd)
        vbox.addWidget(self.brushSizeSlider)
        sizeContainer.setLayout(vbox)
        editToolbar.addWidget(sizeContainer)

    def wheelEvent(self, event):
        delta = int(event.angleDelta().y() / 50)
        rad = self.brushSizeSlider.value() + delta
        self.brushSizeSlider.setValue(rad)
        self.brushSizeLcd.display(rad)
        self.main_window.mmask.m_circle.set_size(rad)
        self.main_window.mmask.m_circle.move(event.pos() - self.main_window.pos() - self.main_window.mmask.pos() - QtCore.QPoint(rad, rad))

    def mouseMoveEvent(self, event):
        moved_evt = QtGui.QMouseEvent(event.type(), 
                                      event.pos() - self.main_window.pos() - self.main_window.mmask.pos(),
                                      event.button(), event.buttons(), Qt.NoModifier)
        self.main_window.mmask.mouseMoveEvent(moved_evt)

def application():
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow(app.primaryScreen().availableGeometry())
    window.show()
    app.exec_()

if __name__ == "__main__":
    #main(sys.argv[1])
    os.makedirs('.tmp', exist_ok=True)
    application()
    shutil.rmtree('.tmp')