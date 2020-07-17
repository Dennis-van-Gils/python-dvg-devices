#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt5 GUI to interface with a Bronkhorst mass flow controller
(MFC).
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "15-07-2020"
__version__ = "0.0.7"
# pylint: disable=bare-except

import sys

from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets as QtWid

from dvg_devices.Bronkhorst_MFC_protocol_RS232 import Bronkhorst_MFC
from dvg_devices.Bronkhorst_MFC_qdev import Bronkhorst_MFC_qdev


# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setGeometry(40, 60, 0, 0)
        self.setWindowTitle("Bronkhorst mass flow controller")

        # Top grid
        self.qlbl_title = QtWid.QLabel(
            "Bronkhorst MFC",
            font=QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Bold),
        )
        self.qpbt_exit = QtWid.QPushButton("Exit")
        self.qpbt_exit.clicked.connect(self.close)
        self.qpbt_exit.setMinimumHeight(30)

        grid_top = QtWid.QGridLayout()
        grid_top.addWidget(self.qlbl_title, 0, 0)
        grid_top.addWidget(self.qpbt_exit, 0, 1, QtCore.Qt.AlignRight)

        # Round up full window
        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(grid_top)
        vbox.addWidget(mfc_qdev.qgrp)
        vbox.addStretch(1)
        vbox.setAlignment(mfc_qdev.qgrp, QtCore.Qt.AlignLeft)
        mfc_qdev.qgrp.setTitle("")


# ------------------------------------------------------------------------------
#   about_to_quit
# ------------------------------------------------------------------------------


def about_to_quit():
    print("About to quit")
    app.processEvents()
    mfc_qdev.quit()
    mfc.close()


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Config file containing COM port address
    PATH_CONFIG = "config/port_Bronkhorst_MFC_1.txt"

    # Serial number of Bronkhorst mass flow controller to connect to.
    # SERIAL_MFC = "M16216843A"
    SERIAL_MFC = None

    # The state of the MFC is polled with this time interval
    DAQ_INTERVAL_MS = 200  # [ms]

    # --------------------------------------------------------------------------
    #   Connect to Bronkhorst mass flow controller (MFC)
    # --------------------------------------------------------------------------

    mfc = Bronkhorst_MFC(connect_to_serial_number=SERIAL_MFC)
    if mfc.auto_connect(filepath_last_known_port=PATH_CONFIG):
        mfc.begin()

    # --------------------------------------------------------------------------
    #   Create application
    # --------------------------------------------------------------------------
    QtCore.QThread.currentThread().setObjectName("MAIN")  # For DEBUG info

    app = 0  # Work-around for kernel crash when using Spyder IDE
    app = QtWid.QApplication(sys.argv)
    app.setFont(QtGui.QFont("Arial", 9))
    app.aboutToQuit.connect(about_to_quit)

    # --------------------------------------------------------------------------
    #   Set up communication threads for the MFC
    # --------------------------------------------------------------------------

    mfc_qdev = Bronkhorst_MFC_qdev(dev=mfc, DAQ_interval_ms=DAQ_INTERVAL_MS)
    mfc_qdev.start()

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
