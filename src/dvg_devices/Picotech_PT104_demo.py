#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt/PySide GUI to interface with a Picotech PT-104 pt100/1000
temperature logger.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "04-04-2024"
__version__ = "1.4.0"
# pylint: disable=wrong-import-position, missing-function-docstring

import os
import sys

# Mechanism to support both PyQt and PySide
# -----------------------------------------

PYQT5 = "PyQt5"
PYQT6 = "PyQt6"
PYSIDE2 = "PySide2"
PYSIDE6 = "PySide6"
QT_LIB_ORDER = [PYQT5, PYSIDE2, PYSIDE6, PYQT6]
QT_LIB = None

# Parse optional cli argument to enfore a QT_LIB
# cli example: python benchmark.py pyside6
if len(sys.argv) > 1:
    arg1 = str(sys.argv[1]).upper()
    for i, lib in enumerate(QT_LIB_ORDER):
        if arg1 == lib.upper():
            QT_LIB = lib
            break

if QT_LIB is None:
    for lib in QT_LIB_ORDER:
        if lib in sys.modules:
            QT_LIB = lib
            break

if QT_LIB is None:
    for lib in QT_LIB_ORDER:
        try:
            __import__(lib)
            QT_LIB = lib
            break
        except ImportError:
            pass

if QT_LIB is None:
    this_file = __file__.rsplit(os.sep, maxsplit=1)[-1]
    raise ImportError(
        f"{this_file} requires PyQt5, PyQt6, PySide2 or PySide6; "
        "none of these packages could be imported."
    )

# fmt: off
# pylint: disable=import-error, no-name-in-module
if QT_LIB == PYQT5:
    from PyQt5 import QtCore, QtGui, QtWidgets as QtWid    # type: ignore
elif QT_LIB == PYQT6:
    from PyQt6 import QtCore, QtGui, QtWidgets as QtWid    # type: ignore
elif QT_LIB == PYSIDE2:
    from PySide2 import QtCore, QtGui, QtWidgets as QtWid  # type: ignore
elif QT_LIB == PYSIDE6:
    from PySide6 import QtCore, QtGui, QtWidgets as QtWid  # type: ignore
# pylint: enable=import-error, no-name-in-module
# fmt: on

# \end[Mechanism to support both PyQt and PySide]
# -----------------------------------------------

import dvg_pyqt_controls as controls
from dvg_devices.Picotech_PT104_protocol_UDP import Picotech_PT104
from dvg_devices.Picotech_PT104_qdev import Picotech_PT104_qdev

# Show debug info in terminal? Warning: Slow! Do not leave on unintentionally.
DEBUG = False

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(self, qdev: Picotech_PT104_qdev, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setWindowTitle("Picotech PT-104")
        self.setGeometry(40, 60, 0, 0)
        self.setFont(QtGui.QFont("Arial", 9))
        self.setStyleSheet(
            controls.SS_TEXTBOX_READ_ONLY
            + controls.SS_GROUP
            + controls.SS_HOVER
        )

        # Top grid
        self.qlbl_title = QtWid.QLabel(f"PT-104\n{chr(177)}15 mK")
        self.qlbl_title.setFont(
            QtGui.QFont("Palatino", 10, weight=QtGui.QFont.Weight.Bold)
        )
        self.qlbl_title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.qpbt_exit = QtWid.QPushButton("Exit")
        self.qpbt_exit.clicked.connect(self.close)
        self.qpbt_exit.setMinimumHeight(30)

        grid_top = QtWid.QGridLayout()
        grid_top.addWidget(self.qlbl_title, 0, 0)
        grid_top.addWidget(
            self.qpbt_exit, 0, 1, QtCore.Qt.AlignmentFlag.AlignRight
        )

        # Round up full window
        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(grid_top)
        vbox.addWidget(qdev.qgrp)
        vbox.addStretch(1)
        vbox.setAlignment(qdev.qgrp, QtCore.Qt.AlignmentFlag.AlignLeft)
        qdev.qgrp.setTitle("")


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # fmt: off
    IP_ADDRESS    = "10.10.100.2"
    PORT          = 1234
    ENA_channels  = [1, 1, 1, 1]
    gain_channels = [1, 1, 1, 1]
    # fmt: on

    # --------------------------------------------------------------------------
    #   Connect to and set up Picotech PT-104
    # --------------------------------------------------------------------------

    pt104 = Picotech_PT104(name="PT104")
    if pt104.connect(IP_ADDRESS, PORT):
        pt104.begin()
        pt104.start_conversion(ENA_channels, gain_channels)

    # --------------------------------------------------------------------------
    #   Create application
    # --------------------------------------------------------------------------

    QtCore.QThread.currentThread().setObjectName("MAIN")  # For DEBUG info
    app = QtWid.QApplication(sys.argv)

    # --------------------------------------------------------------------------
    #   Set up communication threads for the PT104
    # --------------------------------------------------------------------------

    pt104_qdev = Picotech_PT104_qdev(
        dev=pt104,
        DAQ_interval_ms=1000,
        debug=DEBUG,
    )
    pt104_qdev.start()

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    def about_to_quit():
        print("About to quit")
        app.processEvents()
        pt104_qdev.quit()
        pt104.close()

    app.aboutToQuit.connect(about_to_quit)
    window = MainWindow(qdev=pt104_qdev)
    window.show()

    if QT_LIB in (PYQT5, PYSIDE2):
        sys.exit(app.exec_())
    else:
        sys.exit(app.exec())
