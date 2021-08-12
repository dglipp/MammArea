import pydicom
from pathlib import Path
import matplotlib.pyplot as plt
from skimage.filters import threshold_otsu
from skimage.transform import resize
import sys
from PyQt5.QtWidgets import QApplication, QPushButton, QGroupBox, QGridLayout, QVBoxLayout
from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtCore import Qt
import numpy as np


def main(root):
    DATAROOT = Path(root)
    for t in DATAROOT.glob('**/*.dcm'):
        test = pydicom.dcmread(t)

        img = test.pixel_array

        plt.imshow(img, cmap='gray')


        thresh = threshold_otsu(img)

        bin = img > thresh
        plt.show()


        plt.imshow(bin, cmap='gray')

        plt.show()

class Drawable():
    def __init__(self, array):
        self.raw_img = array
        self.dims = list(array.shape)

    def set_dims(self, shape):
        self.dims = list(shape)

    def set_x_dim(self, x, fix_ratio=True):
        if fix_ratio:
            scale = x / self.dims[0]
            self.dims[1] = int(self.dims[1] * scale)
        self.dims[0] = x
        
    def set_y_dim(self, y, fix_ratio=True):
        if fix_ratio:
            scale = y / self.dims[1]
            self.dims[0] = int(self.dims[0] * scale)
        self.dims[1] = y

    def get_drawable(self):
        image = resize(self.raw_img, self.dims, anti_aliasing=True)
        image = ((image - image.min())/(image.max() - image.min())*255).astype(np.uint8)
        drawable = QtGui.QImage(image.tobytes('C'), self.dims[1], self.dims[0], self.dims[1], QtGui.QImage.Format_Grayscale8)
        return drawable


class MainWindow(QtWidgets.QWidget):
    def __init__(self, screen):
        super().__init__()

        self.title = 'MammArea'
        self.left = 10
        self.top = 10
        self.width = 320
        self.height = 100

        self.available_size = (screen[2] - screen[0], screen[3] - screen[1])

        self.setWindowTitle("")
        self.setGeometry(self.left, self.top, self.width, self.height)
        
        self.createGridLayout()
        
        self.setLayout(self.layout)
        #self.draw_something()

    def draw_something(self):
        painter = QtGui.QPainter(self.label.pixmap())
        painter.drawLine(10, 10, 300, 200)
        painter.end()

    def create_image(self):
        label = QtWidgets.QLabel()
        test = pydicom.dcmread('/home/digileap/Projects/MammArea/data/mammo/4656975/2D_PROC/1.2.840.113619.2.401.101117117513079.17839180329091021.3.dcm')
        dcm = Drawable(test.pixel_array)

        xratio, yratio = (self.available_size[0] / dcm.dims[0], self.available_size[1] / dcm.dims[1])

        if xratio <= yratio:
            dcm.set_x_dim(int(xratio * dcm.dims[0] * 0.5))
        else:
            dcm.set_y_dim(int(yratio * dcm.dims[1] * 0.5))

        canvas = QtGui.QPixmap(dcm.get_drawable())
        label.setPixmap(canvas)
        label.setScaledContents(True)
        return label

    def createGridLayout(self):
        self.layout = QGridLayout()
        self.layout.setRowStretch(1, 1)
        self.layout.setRowStretch(2, 4)
        
        self.layout.addWidget(QPushButton('1'),0,0)
        self.layout.addWidget(QPushButton('2'),0,1)
        self.layout.addWidget(self.create_image(),1,0)
        self.layout.addWidget(self.create_image(),1,1)
        
def application():

    app = QtWidgets.QApplication(sys.argv)

    window = MainWindow(app.primaryScreen().availableGeometry().getRect())
    window.show()
    app.exec_()






if __name__ == "__main__":
    #main(sys.argv[1])
    application()


'''


        test = pydicom.dcmread('/home/digileap/Projects/MammArea/data/mammo/4656975/2D_PROC/1.2.840.113619.2.401.101117117513079.17839180329091021.3.dcm')

        image = resize(test.pixel_array, (300, 300), anti_aliasing=True)

        image = ((image - image.min())/(image.max() - image.min())*255).astype(np.uint8)
        image = np.ones(image.shape).astype(np.uint8)
        im = QtGui.QImage(image, 300, 300, QtGui.QImage.Format_Mono)
'''