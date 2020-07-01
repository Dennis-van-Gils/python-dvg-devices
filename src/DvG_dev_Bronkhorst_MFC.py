#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt5 GUI to interface with a Bronkhorst mass flow controller
(MFC).
"""
__author__      = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__         = ""
__date__        = "14-09-2018"
__version__     = "1.0.0"

import sys
from pathlib import Path

from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets as QtWid

import DvG_dev_Bronkhorst_MFC__fun_RS232 as mfc_functions
import DvG_dev_Bronkhorst_MFC__pyqt_lib  as mfc_pyqt_lib

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------

class MainWindow(QtWid.QWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setGeometry(40, 60, 0, 0)
        self.setWindowTitle("Bronkhorst mass flow controller")

        # Top grid
        self.qlbl_title = QtWid.QLabel("Bronkhorst MFC",
            font=QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Bold))
        self.qpbt_exit = QtWid.QPushButton("Exit")
        self.qpbt_exit.clicked.connect(self.close)
        self.qpbt_exit.setMinimumHeight(30)

        grid_top = QtWid.QGridLayout()
        grid_top.addWidget(self.qlbl_title, 0, 0)
        grid_top.addWidget(self.qpbt_exit , 0, 1, QtCore.Qt.AlignRight)

        # Round up full window
        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(grid_top)
        vbox.addWidget(mfc_pyqt.qgrp)
        vbox.addStretch(1)
        vbox.setAlignment(mfc_pyqt.qgrp, QtCore.Qt.AlignLeft)
        mfc_pyqt.qgrp.setTitle('')

# ------------------------------------------------------------------------------
#   about_to_quit
# ------------------------------------------------------------------------------

def about_to_quit():
    print("About to quit")
    app.processEvents()
    mfc_pyqt.close_all_threads()
    try: mfc.close()
    except: pass

# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == '__main__':
    # Config file containing COM port address
    PATH_CONFIG = Path("config/port_Bronkhorst_MFC_1.txt")

    # Serial number of Bronkhorst mass flow controller to connect to.
    #SERIAL_MFC = "M16216843A"
    SERIAL_MFC = None

    # The state of the MFC is polled with this time interval
    UPDATE_INTERVAL_MS = 200   # [ms]

    # --------------------------------------------------------------------------
    #   Connect to Bronkhorst mass flow controller (MFC)
    # --------------------------------------------------------------------------

    mfc = mfc_functions.Bronkhorst_MFC(name="MFC")
    if mfc.auto_connect(PATH_CONFIG, SERIAL_MFC):
        mfc.begin()

    # --------------------------------------------------------------------------
    #   Create application
    # --------------------------------------------------------------------------
    QtCore.QThread.currentThread().setObjectName('MAIN')    # For DEBUG info

    app = 0    # Work-around for kernel crash when using Spyder IDE
    app = QtWid.QApplication(sys.argv)
    app.setFont(QtGui.QFont("Arial", 9))
    app.aboutToQuit.connect(about_to_quit)

    # --------------------------------------------------------------------------
    #   Set up communication threads for the MFC
    # --------------------------------------------------------------------------

    mfc_pyqt = mfc_pyqt_lib.Bronkhorst_MFC_pyqt(mfc, UPDATE_INTERVAL_MS)
    mfc_pyqt.start_thread_worker_DAQ()
    mfc_pyqt.start_thread_worker_send()

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
