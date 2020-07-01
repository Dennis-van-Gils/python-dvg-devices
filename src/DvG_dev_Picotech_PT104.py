#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt5 GUI to interface with a Picotech PT-104 pt100/1000
temperature logger.
"""
__author__      = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__         = ""
__date__        = "17-09-2018"
__version__     = "1.0.0"

import sys

from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets as QtWid

from DvG_pyqt_controls import SS_TEXTBOX_READ_ONLY

import DvG_dev_Picotech_PT104__fun_UDP  as pt104_functions
import DvG_dev_Picotech_PT104__pyqt_lib as pt104_pyqt_lib

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------

class MainWindow(QtWid.QWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setGeometry(40, 60, 0, 0)
        self.setWindowTitle("Picotech PT-104")

        # Top grid
        self.qlbl_title = QtWid.QLabel("PT-104\n%s15 mK" % chr(177),
            font=QtGui.QFont("Palatino", 10, weight=QtGui.QFont.Bold),
            alignment=QtCore.Qt.AlignCenter)
        self.qpbt_exit = QtWid.QPushButton("Exit")
        self.qpbt_exit.clicked.connect(self.close)
        self.qpbt_exit.setMinimumHeight(30)

        grid_top = QtWid.QGridLayout()
        grid_top.addWidget(self.qlbl_title, 0, 0)
        grid_top.addWidget(self.qpbt_exit , 0, 1, QtCore.Qt.AlignRight)

        # Round up full window
        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(grid_top)
        vbox.addWidget(pt104_pyqt.qgrp)
        vbox.addStretch(1)
        vbox.setAlignment(pt104_pyqt.qgrp, QtCore.Qt.AlignLeft)
        pt104_pyqt.qgrp.setTitle('')

# ------------------------------------------------------------------------------
#   about_to_quit
# ------------------------------------------------------------------------------

def about_to_quit():
    print("About to quit")
    app.processEvents()
    pt104_pyqt.close_all_threads()
    try: pt104.close()
    except: pass

# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == '__main__':
    IP_ADDRESS    = "10.10.100.2"
    PORT          = 1234
    ENA_channels  = [1, 1, 1, 1]
    gain_channels = [1, 1, 1, 1]

    # --------------------------------------------------------------------------
    #   Connect to and set up Picotech PT-104
    # --------------------------------------------------------------------------

    pt104 = pt104_functions.PT104(name="PT104")
    if pt104.connect(IP_ADDRESS, PORT):
        pt104.begin()
        pt104.start_conversion(ENA_channels, gain_channels)

    # --------------------------------------------------------------------------
    #   Create application
    # --------------------------------------------------------------------------
    QtCore.QThread.currentThread().setObjectName('MAIN')    # For DEBUG info

    app = 0    # Work-around for kernel crash when using Spyder IDE
    app = QtWid.QApplication(sys.argv)
    app.setFont(QtGui.QFont("Arial", 9))
    app.setStyleSheet(SS_TEXTBOX_READ_ONLY)
    app.aboutToQuit.connect(about_to_quit)

    # --------------------------------------------------------------------------
    #   Set up communication threads for the PT104
    # --------------------------------------------------------------------------

    pt104_pyqt = pt104_pyqt_lib.PT104_pyqt(dev=pt104,
                                           DAQ_update_interval_ms=1000)
    pt104_pyqt.start_thread_worker_DAQ()

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
