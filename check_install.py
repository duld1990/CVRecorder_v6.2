import sys
import struct
assert sys.version_info[:2] == (3, 11), 'Python 3.11 required'
assert struct.calcsize('P') == 8, '64-bit Python required'
import tkinter
import numpy
import cv2
from PIL import Image, ImageTk
print('Python:', sys.version)
print('OpenCV:', cv2.__version__, '| NumPy:', numpy.__version__)
root = tkinter.Tk()
root.withdraw()
root.update()
root.destroy()
print('PASS: imports and Tk GUI initialized. Camera recording not tested.')

from cv2_enumerate_cameras import enumerate_cameras
print('Named camera enumeration dependency: OK')
