#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt/PySide GUI to interface with a Julabo circulating bath."""
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
from dvg_devices.Julabo_circulator_protocol_RS232 import Julabo_circulator
from dvg_devices.Julabo_circulator_qdev import Julabo_circulator_qdev

# Show debug info in terminal? Warning: Slow! Do not leave on unintentionally.
DEBUG = False

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(self, qdev: Julabo_circulator_qdev, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setWindowTitle("Julabo control")
        self.setGeometry(40, 60, 0, 0)
        self.setFont(QtGui.QFont("Arial", 9))
        self.setStyleSheet(
            controls.SS_TEXTBOX_READ_ONLY
            + controls.SS_GROUP
            + controls.SS_HOVER
        )

        self.pbtn_exit = QtWid.QPushButton("Exit")
        self.pbtn_exit.clicked.connect(self.close)
        self.pbtn_exit.setMinimumHeight(30)

        hbox = QtWid.QHBoxLayout()
        hbox.addWidget(qdev.grpb)
        hbox.addWidget(
            self.pbtn_exit, alignment=QtCore.Qt.AlignmentFlag.AlignTop
        )
        hbox.addStretch(1)

        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(hbox)
        vbox.addStretch(1)


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Config file containing COM port address
    PATH_PORT = "config/port_Julabo.txt"

    # The state of the Julabo is polled with this time interval
    DAQ_INTERVAL_MS = 500  # [ms]

    # --------------------------------------------------------------------------
    #   Connect to Julabo
    # --------------------------------------------------------------------------

    julabo = Julabo_circulator(name="Julabo")
    if julabo.auto_connect(filepath_last_known_port=PATH_PORT):
        julabo.begin()

    # --------------------------------------------------------------------------
    #   Create application
    # --------------------------------------------------------------------------

    QtCore.QThread.currentThread().setObjectName("MAIN")  # For DEBUG info
    app = QtWid.QApplication(sys.argv)

    # --------------------------------------------------------------------------
    #   Set up communication threads for the Julabo
    # --------------------------------------------------------------------------

    julabo_qdev = Julabo_circulator_qdev(
        dev=julabo,
        DAQ_interval_ms=DAQ_INTERVAL_MS,
        debug=DEBUG,
    )
    julabo_qdev.start()

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    def about_to_quit():
        print("About to quit")
        app.processEvents()
        julabo_qdev.quit()
        julabo.close()

    app.aboutToQuit.connect(about_to_quit)
    window = MainWindow(qdev=julabo_qdev)
    window.show()

    if QT_LIB in (PYQT5, PYSIDE2):
        sys.exit(app.exec_())
    else:
        sys.exit(app.exec())
