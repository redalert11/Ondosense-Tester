
# app.py
from PyQt6 import QtWidgets
import pyqtgraph as pg
from main_window import MainWindow

def main():
    app = QtWidgets.QApplication([])
    pg.setConfigOptions(antialias=True)
    win = MainWindow()
    win.show()
    app.exec()

if __name__ == "__main__":
    main()
