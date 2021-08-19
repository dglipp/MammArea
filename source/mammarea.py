import pydicom
import nibabel
from skimage.filters import threshold_otsu
from skimage.transform import resize
from skimage import io
from PIL import Image
import pandas as pd
import sys
import os
from pathlib import Path
import shutil
from PyQt5.QtWidgets import QCheckBox, QLabel, QGridLayout, QPushButton, QWidget
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QSize, Qt
import numpy as np

def is_inside(point, rect):
    if point[0] < rect[0] or point[1] < rect[1] or point[0] > rect[2] or point[1] > rect[3]:
        return False
    return True

class Drawable():
    def __init__(self, array):
        self.dicom = array
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
    def __init__(self, width, height):
        super().__init__()
        self.preferred_savedir = Path(os.path.expanduser('~'))
        self.setMouseTracking(True)
        self.is_drawing = False
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.setFrameShape(QtWidgets.QFrame.Box)
        self.dcm = None
        self.draw_point = None
        
        self.installEventFilter(self)
        self.brush_radius = 30
        self.brush_color = Qt.black
        self.img_rect = None
        self.scale = 1
        self.area_label_hook = None
        
        self.m_circle = MouseCircle(self)

    def setImage(self, img):
        self.dcm = Mask(img)
        self.pix = QtGui.QPixmap(self.dcm.get_drawable())
        self.setPixmap(self.pix)

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
        if self.img_rect:
            if is_inside((mouse_point.x(), mouse_point.y()), self.img_rect):
                self.m_circle.show()
            else:
                self.mouseReleaseEvent(event)
                self.m_circle.hide()
        else:
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

    def save_image(self):
        image = self.pix.toImage().convertToFormat(QtGui.QImage.Format_Grayscale8)
        fn = f'.tmp/tmp_msk_{np.random.rand(1)}.png'
        image.save(fn)
        np_img = io.imread(fn)
        np_img[np_img != 0] = 255
        area = np.sum(np_img == 255) * self.dcm.vox_dims[0] * self.dcm.vox_dims[1]
        os.remove(fn)
        x, y = self.dcm.vox_dims
        affine = np.array([[x, 0, 0, 0],
                           [0, y, 0, 0],
                           [0, 0, 1, 0],
                           [0, 0, 0, 1]])

        mask = nibabel.Nifti1Image(np_img.T, affine=affine)
        mask.set_sform(None, code=0)
        mask.set_qform(None, code=0)
        filepath = QtWidgets.QFileDialog.getSaveFileName(None, 'Save mask', 
                                                         str(self.preferred_savedir / f'mask_{int(area)}mm2.nii'),
                                                         "Masks (*.nii);;Images (*.png *.jpg)")
        
        if filepath[0] != '':
            savepath = Path(filepath[0])
            if savepath.suffix == '.nii':
                savepath = str(savepath) + '.gz'
                nibabel.save(mask, savepath)
            else:
                try:
                    image.save(str(savepath))
                except:
                    err = QtWidgets.QMessageBox()
                    err.about(self, 'Error', 'Extension not supported!')

class ImageFrame(QtWidgets.QLabel):
    def __init__(self, width, height):
        super().__init__()
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self.setFrameShape(QtWidgets.QFrame.Box)
        self.setMouseTracking(True)
        self.dcm = None

        self.installEventFilter(self)

    def setImage(self, img):
        self.dcm = Drawable(img)
        self.pix = QtGui.QPixmap(self.dcm.get_drawable())
        self.setPixmap(self.pix)

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
        self.idpacs_label = QLabel()
        self.area_label = QLabel()
        self.mimage = ImageFrame(300, 400)
        self.mmask = MaskFrame(300, 400)

        self.layout = QGridLayout()
        self.layout.addWidget(self.idpacs_label, 0,0)
        self.layout.addWidget(self.area_label, 0,1)
        self.layout.addWidget(self.mimage,1,0)
        self.layout.addWidget(self.mmask,1,1)
        self.setLayout(self.layout)

    def createGridLayout(self, path):
        img = pydicom.dcmread(path)
        try:
            if img.Modality != 'MG':
                raise TypeError('')
        except:
            raise TypeError('')

        self.mmask.setImage(img)
        self.mimage.setImage(img)
        proj = None
        try:
            proj = str(img[(0x0045, 0x101b)].value)[2:-1]
        except:
            err = QtWidgets.QMessageBox()
            err.about(self, 'Warning', 'It seems not a 2D projection!')
            proj = None
        screen = self.parent_window.available_size
        self.parent_window.setGeometry(screen.adjusted(int(screen.size().height()*0.1), int(screen.size().height()*0.1), int(-screen.size().width()*0.1), int(-screen.size().width()*0.1)))
        self.idpacs_label.setText(f"ID PACS: {img.PatientID}\nAccession Number: {img.AccessionNumber}\nProjection: {proj}")
        self.area_label.setText(f'Segmented area: {self.mmask.get_image_area()} \u339F')
        self.mmask.area_label_hook = self.area_label
        self.idpacs_label.setFixedHeight(60)
        self.area_label.setFixedHeight(60)
        
class InitWindow(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent_win = parent
        self.createGridLayout()
        self.setLayout(self.layout)

    def createGridLayout(self):
        self.layout = QGridLayout()
        self.layout.setContentsMargins(0,0,0,50)
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
        df = {'IDPACS':[], 'Accession Number':[], 'Projection':[], 'Area':[]}
        self.start_button.setDisabled(True)
        self.info.setText('Calculation ongoing...')
        self.progress.setValue(0)
        save = self.mask_box.isChecked()
        fn = Path(f'.tmp/save_{np.random.rand(1)}')
        os.makedirs(fn, exist_ok=True)
        l = len(self.mg_paths)
        for i, p in enumerate(self.mg_paths):
            dcm = pydicom.dcmread(p)
            idpacs = dcm.PatientID
            acc = dcm.AccessionNumber
            proj = str(dcm[(0x0045, 0x101b)].value)[2:-1]

            thresh = threshold_otsu(dcm.pixel_array)
            bin = (dcm.pixel_array > thresh) * 255
            vox_dims = dcm[(0x0018, 0x1164)].value
            area = np.sum(bin == 255) * vox_dims[0] * vox_dims[1]
            if save:
                os.makedirs(fn / idpacs / acc, exist_ok=True)
                Image.fromarray(bin.astype(np.uint8)).save(fn / idpacs / acc / f'{proj}_{int(area)}mm2.png')
                x, y = vox_dims
                affine = np.array([[x, 0, 0, 0],
                                [0, y, 0, 0],
                                [0, 0, 1, 0],
                                [0, 0, 0, 1]])

                mask = nibabel.Nifti1Image(bin.T, affine=affine)
                mask.set_sform(None, code=0)
                mask.set_qform(None, code=0)
                nibabel.save(mask, fn / idpacs / acc / f'{proj}_{int(area)}mm2.nii.gz')
            df['IDPACS'].append(idpacs)
            df['Accession Number'].append(acc)
            df['Projection'].append(proj)
            df['Area'].append(np.round(area,2))
            self.progress.setValue(int(i/l*100))
        
        self.progress.setValue(100)
        pd.DataFrame(df).to_excel(fn / 'areas.xlsx')

        filepath = QtWidgets.QFileDialog.getExistingDirectory(None,
                                                    'Select results data folder',
                                                    self.parent_win.preferred_folder,
                                                    QtWidgets.QFileDialog.ShowDirsOnly)
        if filepath:
            self.parent_win.preferred_folder = filepath
            dest = Path(filepath) / f'results_{int(np.random.rand(1)*10000)}'
            try:
                shutil.move(fn, dest)
                self.info.setText('Data saved correctly!')
            except Exception as e:
                print(e)
                err = QtWidgets.QMessageBox()
                err.about(self, 'Error', "Couldn't write here!")
                self.info.setText('Retry...')
        
        self.start_button.setDisabled(False)
        

    def createGridLayout(self, path):
        self.parent_win.setGeometry(QtCore.QRect(QtCore.QPoint(int(self.parent_win.available_size.width()/2), int(self.parent_win.available_size.height()/2)), QSize(300, 300)))
        self.proot = path
        
        self.mg_paths = []
        id = []
        acc = []
        path_list = list(Path(path).rglob('*.dcm'))
        l = len(path_list)
        for i, p in enumerate(path_list):
            self.progress.setValue(int((i+1)/l*100))
            dcm = pydicom.dcmread(p, stop_before_pixels=True)
            try:
                if dcm.Modality == 'MG':
                    id.append(dcm.PatientID)
                    acc.append(dcm.AccessionNumber)
                    self.mg_paths.append(p)
            except:
                pass

        self.progress.setValue(100)
        self.info.setText(f'Read \t{len(self.mg_paths)} images\n\t{len(np.unique(id))} IDs\n\t{len(np.unique(acc))} Accession Numbers')
        if len(self.mg_paths) == 0:
            err = QtWidgets.QMessageBox()
            err.about(self, 'Error', "No MG Dicom files found!")
            self.parent_win.set_automatic()
        
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, screen):
        super().__init__()
        self.title = 'MammArea'
        self.available_size = screen
        self.setWindowTitle(self.title)
        self.setMouseTracking(True)

        self.preferred_folder = os.path.expanduser('~')
        self.stack = QtWidgets.QStackedLayout()
        self.manual_window = ManualWindow(self)
        self.auto_window = AutoWindow(self)
        self.stack.addWidget(InitWindow(self))
        self.stack.addWidget(self.manual_window)
        self.stack.addWidget(self.auto_window)
        self.dummy_window = QWidget()
        self.dummy_window.setMouseTracking(True)
        self.dummy_window.setLayout(self.stack)
        self.central = 'init'
        self.setGeometry(QtCore.QRect(QtCore.QPoint(int(self.available_size.width()/2), int(self.available_size.height()/2)), QSize(300, 300)))
        self.setCentralWidget(self.dummy_window)

    def set_manual(self):
        filepath = QtWidgets.QFileDialog.getOpenFileName(None,
                                                'Select file',
                                                self.preferred_folder)
        if filepath:
            if filepath != ('', ''):
                try:
                    self.manual_window.createGridLayout(filepath[0])
                    self.create_manual_toolbar()
                    self.stack.setCurrentIndex(1)
                    self.central = 'manual'
                    self.preferred_folder = str(Path(filepath[0]).parent)
                except TypeError as e:
                    print(e)
                    err = QtWidgets.QMessageBox()
                    err.about(self, 'Error', 'Not a MG modality image!')
                except Exception as e:
                    print(e)
                    err = QtWidgets.QMessageBox()
                    err.about(self, 'Error', "Not a Dicom file!")
        else:
            err = QtWidgets.QMessageBox()
            err.about(self, 'Error', "File path doesn't exist!")

    def set_automatic(self):
        self.create_auto_toolbar()
        filepath = QtWidgets.QFileDialog.getExistingDirectory(None,
                                                                   'Select root folder',
                                                                   self.preferred_folder,
                                                                   QtWidgets.QFileDialog.ShowDirsOnly)
        if filepath:
            self.preferred_folder = str(Path(filepath).parent)
            self.stack.setCurrentIndex(2)
            self.auto_window.createGridLayout(filepath)
            self.central = 'auto'
        else:
            self.set_init()

    def set_init(self):
        self.setGeometry(QtCore.QRect(QtCore.QPoint(int(self.available_size.width()/2), int(self.available_size.height()/2)), QSize(300, 300)))
        self.stack.setCurrentIndex(0)
        self.removeToolBar(self.editToolbar)
        self.central = 'init'

    def create_manual_toolbar(self):
        self.editToolbar = self.addToolBar('Brush menu')
        self.editToolbar.setIconSize(QtCore.QSize(50, 50))

        brushAction = QtWidgets.QAction(QtGui.QIcon('assets/brush.png'), 'Brush', self)
        self.editToolbar.addAction(brushAction)
        brushAction.triggered.connect(lambda x: self.manual_window.mmask.set_brush_color(Qt.white))
        brushAction.triggered.connect(lambda x: self.manual_window.mmask.m_circle.set_pen_color(Qt.green))

        rubberAction = QtWidgets.QAction(QtGui.QIcon('assets/rubber.png'), 'Rubber', self)
        self.editToolbar.addAction(rubberAction)
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
        self.editToolbar.addWidget(sizeContainer)

        saveAction = QtWidgets.QAction(QtGui.QIcon('assets/save.png'), 'Save', self)
        self.editToolbar.addAction(saveAction)
        saveAction.triggered.connect(self.manual_window.mmask.save_image)
        exitAction = QtWidgets.QAction(QtGui.QIcon('assets/exit.png'), 'Exit', self)
        self.editToolbar.addAction(exitAction)
        exitAction.triggered.connect(self.set_init)

    def create_auto_toolbar(self):
        self.editToolbar = self.addToolBar('Auto menu')
        exitAction = QtWidgets.QAction(QtGui.QIcon('assets/exit.png'), 'Exit', self)
        self.editToolbar.addAction(exitAction)
        exitAction.triggered.connect(self.set_init)

    def wheelEvent(self, event):
        if self.central == 'manual':
            delta = int(event.angleDelta().y() / 50)
            rad = self.brushSizeSlider.value() + delta
            self.brushSizeSlider.setValue(rad)
            self.brushSizeLcd.display(rad)
            self.manual_window.mmask.m_circle.set_size(rad)
            self.manual_window.mmask.m_circle.move(event.pos() - self.dummy_window.pos() - self.manual_window.pos() - self.manual_window.mmask.pos() - QtCore.QPoint(rad, rad))

    def mouseMoveEvent(self, event):
        if self.central == 'manual':
            moved_evt = QtGui.QMouseEvent(event.type(), 
                                        event.pos() - self.dummy_window.pos() - self.manual_window.pos() - self.manual_window.mmask.pos(),
                                        event.button(), event.buttons(), Qt.NoModifier)
            self.manual_window.mmask.mouseMoveEvent(moved_evt)

def application():
    os.chdir(Path(__file__).parent)
    shutil.rmtree('.tmp', ignore_errors=True)
    os.makedirs('.tmp', exist_ok=True)
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon('dgl.ico'))
    window = MainWindow(app.primaryScreen().availableGeometry())
    window.show()
    app.exec()
    shutil.rmtree('.tmp')

if __name__ == "__main__":
    application()
