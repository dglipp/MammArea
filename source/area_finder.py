from numpy.core.numeric import array_equal
import pydicom
from skimage.filters import threshold_otsu
from skimage.transform import resize
from skimage import io
import sys
import time
import os
from pathlib import Path
import shutil
from PyQt5.QtWidgets import QCheckBox, QLabel, QGridLayout, QPushButton, QVBoxLayout, QWidget
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

class ManualWindow(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__()
        self.setMouseTracking(True)
        self.parent_window = parent

    def createGridLayout(self, path):
        self.layout = QGridLayout()
        img = pydicom.dcmread(path)
        if img.Modality != 'MG':
            raise TypeError('')

        self.mmask = MaskFrame(300, 400, Mask(img))
        proj = None
        try:
            proj = str(img[(0x0045, 0x101b)].value)[2:-1]
        except:
            err = QtWidgets.QMessageBox()
            err.about(self, 'Warning', 'It seems not a 2D projection!')
            proj = None
        screen = self.parent_window.available_size
        self.parent_window.setGeometry(screen.adjusted(int(screen.size().height()*0.1), int(screen.size().height()*0.1), int(-screen.size().width()*0.1), int(-screen.size().width()*0.1)))
        self.idpacs_label = QLabel(f"ID PACS: {img.PatientID}\nAccession Number: {img.AccessionNumber}\nProjection: {proj}")
        self.area_label = QLabel(f'Segmented area: {self.mmask.get_image_area()} \u339F')
        self.mmask.area_label_hook = self.area_label
        self.idpacs_label.setFixedHeight(60)
        self.area_label.setFixedHeight(60)

        self.layout.addWidget(self.idpacs_label, 0,0)
        self.layout.addWidget(self.area_label, 0,1)
        self.layout.addWidget(ImageFrame(300, 400, Drawable(img)),1,0)
        self.layout.addWidget(self.mmask,1,1)
        self.setLayout(self.layout)

class InitWindow(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent_win = parent
        self.createGridLayout()
        self.setLayout(self.layout)

    def createGridLayout(self):
        self.layout = QGridLayout()
        self.manual = QPushButton("Manual")
        self.auto = QPushButton("Automatic")
        self.manual.clicked.connect(self.parent_win.set_manual)
        self.auto.clicked.connect(self.parent_win.set_automatic)
        self.manual.setFixedSize(QtCore.QSize(80, 40))
        self.auto.setFixedSize(QtCore.QSize(80, 40))
        self.layout.addWidget(self.manual, 0,0)
        self.layout.addWidget(self.auto, 0,1)

class AutoWindow(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent_win = parent
        self.layout = QGridLayout()
        self.info = QLabel('Reading folders...')
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setAlignment(Qt.AlignCenter)
        self.progress.setFixedSize(QtCore.QSize(250, 30))
        self.mask_box = QCheckBox('Save masks')
        self.start_button = QPushButton('Start calculation')
        self.start_button.clicked.connect(lambda x: self.calc())
        self.layout.addWidget(self.info, 0, 0, 1, 1)
        self.layout.addWidget(self.mask_box, 1, 0, Qt.AlignRight)
        self.layout.addWidget(self.start_button, 1, 1, Qt.AlignLeft)
        self.layout.addWidget(self.progress, 2, 0, 1, 2, Qt.AlignCenter)
        self.setLayout(self.layout)

    def calc(self):

        self.info.setText('Calculation ongoing...')
        self.progress.setValue(0)
        save = self.mask_box.isChecked()
        for p in self.mg_paths:
            pass
        filepath = QtWidgets.QFileDialog.getExistingDirectory(None,
                                                    'Select folder',
                                                    os.path.expanduser('~'),
                                                    QtWidgets.QFileDialog.ShowDirsOnly)

    def createGridLayout(self, path):
        self.parent_win.resize(300, 300)
        self.proot = path
        
        self.mg_paths = []
        id = []
        acc = []
        path_list = list(Path(path).rglob('*.dcm'))
        l = len(path_list)
        for i, p in enumerate(path_list):
            self.progress.setValue(int((i+1)/l*100))
            dcm = pydicom.dcmread(p, stop_before_pixels=True)
            if dcm.Modality == 'MG':
                id.append(dcm.PatientID)
                acc.append(dcm.AccessionNumber)
                self.mg_paths.append(p)

        self.progress.setValue(100)
        self.info.setText(f'Read \t{len(self.mg_paths)} images\n\t{len(np.unique(id))} IDs\n\t{len(np.unique(acc))} Accession Numbers')
        if len(self.mg_paths) == 0:
            err = QtWidgets.QMessageBox()
            err.about(self, 'Error', "No MG Dicom files found!")
            self.parent_win.set_automatic()
        
class MainWindow(QtWidgets.QWidget):
    def __init__(self, screen):
        super().__init__()
        self.title = 'MammArea'
        self.available_size = screen
        self.setWindowTitle(self.title)
        self.setMouseTracking(True)

        self.stack = QtWidgets.QStackedLayout()
        self.manual_window = ManualWindow(self)
        self.auto_window = AutoWindow(self)
        self.stack.addWidget(InitWindow(self))
        self.stack.addWidget(self.manual_window)
        self.stack.addWidget(self.auto_window)

        self.setLayout(self.stack)
        self.central = 'init'
        self.resize(300, 300)

    def set_manual(self):
        filepath = QtWidgets.QFileDialog.getOpenFileName(None,
                                                'Select file',
                                                os.path.expanduser('~'))
        if filepath:
            if filepath != ('', ''):
                try:
                    self.manual_window.createGridLayout(filepath[0])
                    self.create_manual_toolbar()
                    self.stack.setCurrentIndex(1)
                    self.central = 'manual'
                except TypeError:
                    err = QtWidgets.QMessageBox()
                    err.about(self, 'Error', 'Not a MG modality image!')
                except Exception as e:
                    err = QtWidgets.QMessageBox()
                    err.about(self, 'Error', "Not a Dicom file!")
        else:
            err = QtWidgets.QMessageBox()
            err.about(self, 'Error', "File path doesn't exist!")

    def set_automatic(self):
        filepath = QtWidgets.QFileDialog.getExistingDirectory(None,
                                                                   'Select root folder',
                                                                   os.path.expanduser('~'),
                                                                   QtWidgets.QFileDialog.ShowDirsOnly)
        if filepath:
            self.stack.setCurrentIndex(2)
            self.auto_window.createGridLayout(filepath)
            self.central = 'auto'

    def set_init(self):
        self.init_window = InitWindow(self)
        self.stack.setCurrentIndex(0)
        self.central = 'init'

    def create_manual_toolbar(self):
        editToolbar = self.addToolBar('Brush menu')
        editToolbar.setIconSize(QtCore.QSize(50, 50))

        brushAction = QtWidgets.QAction(QtGui.QIcon('assets/brush.png'), 'Brush', self)
        editToolbar.addAction(brushAction)
        brushAction.triggered.connect(lambda x: self.manual_window.mmask.set_brush_color(Qt.white))
        brushAction.triggered.connect(lambda x: self.manual_window.mmask.m_circle.set_pen_color(Qt.green))

        rubberAction = QtWidgets.QAction(QtGui.QIcon('assets/rubber.png'), 'Rubber', self)
        editToolbar.addAction(rubberAction)
        rubberAction.triggered.connect(lambda x: self.manual_window.mmask.set_brush_color(Qt.black))
        rubberAction.triggered.connect(lambda x: self.manual_window.mmask.m_circle.set_pen_color(Qt.red))

        sizeContainer = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout()

        self.brushSizeLcd = QtWidgets.QLCDNumber()
        self.brushSizeLcd.display(30)
        self.brushSizeSlider = QtWidgets.QSlider(Qt.Horizontal)
        self.brushSizeSlider.setRange(1, 300)
        self.brushSizeSlider.setValue(30)
        self.brushSizeSlider.setFocusPolicy(Qt.NoFocus)
        self.brushSizeSlider.valueChanged.connect(lambda x: self.manual_window.mmask.set_brush_radius(self.brushSizeSlider.value()))
        self.brushSizeSlider.valueChanged.connect(lambda x: self.manual_window.mmask.m_circle.set_size(self.brushSizeSlider.value()))
        self.brushSizeSlider.valueChanged.connect(lambda x: self.brushSizeLcd.display(self.brushSizeSlider.value()))
        self.brushSizeSlider.setMaximumWidth(100)
        self.brushSizeLcd.setMaximumWidth(100)
        vbox.addWidget(self.brushSizeLcd)
        vbox.addWidget(self.brushSizeSlider)
        sizeContainer.setLayout(vbox)
        editToolbar.addWidget(sizeContainer)

    def wheelEvent(self, event):
        if self.central == 'manual':
            delta = int(event.angleDelta().y() / 50)
            rad = self.brushSizeSlider.value() + delta
            self.brushSizeSlider.setValue(rad)
            self.brushSizeLcd.display(rad)
            self.manual_window.mmask.m_circle.set_size(rad)
            self.manual_window.mmask.m_circle.move(event.pos() - self.manual_window.pos() - self.manual_window.mmask.pos() - QtCore.QPoint(rad, rad))

    def mouseMoveEvent(self, event):
        if self.central == 'manual':
            moved_evt = QtGui.QMouseEvent(event.type(), 
                                        event.pos() - self.manual_window.pos() - self.manual_window.mmask.pos(),
                                        event.button(), event.buttons(), Qt.NoModifier)
            self.manual_window.mmask.mouseMoveEvent(moved_evt)

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