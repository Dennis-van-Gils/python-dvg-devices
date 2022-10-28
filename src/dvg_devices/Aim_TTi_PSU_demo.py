#!/usr/bin/env python3
# -*- coding: utf-8 -*-
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "28-10-2022"
__version__ = "1.0.0"

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
    this_file = __file__.split(os.sep)[-1]
    raise Exception(
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

from dvg_pyqt_controls import SS_TEXTBOX_READ_ONLY, SS_GROUP
from dvg_devices.Aim_TTi_PSU_protocol_RS232 import Aim_TTi_PSU
from dvg_devices.Aim_TTi_PSU_qdev import Aim_TTi_PSU_qdev

# Show debug info in terminal? Warning: Slow! Do not leave on unintentionally.
DEBUG = False

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setGeometry(600, 120, 0, 0)
        self.setWindowTitle("Aim TTi power supply control")

        self.pbtn_exit = QtWid.QPushButton("Exit")
        self.pbtn_exit.clicked.connect(self.close)
        self.pbtn_exit.setMinimumHeight(30)

        hbox = QtWid.QHBoxLayout()
        hbox.addWidget(psu_qdev.grpb)
        hbox.addWidget(
            self.pbtn_exit, alignment=QtCore.Qt.AlignmentFlag.AlignTop
        )
        hbox.addStretch(1)

        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(hbox)
        vbox.addStretch(1)


# ------------------------------------------------------------------------------
#   about_to_quit
# ------------------------------------------------------------------------------


def about_to_quit():
    print("About to quit")
    app.processEvents()
    psu_qdev.quit()
    psu.close()


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Config file containing COM port address
    PATH_PORT = "config/port_Aim_TTi_PSU.txt"

    # The state of the PSU is polled with this time interval
    DAQ_INTERVAL_MS = 200  # [ms]

    # --------------------------------------------------------------------------
    #   Connect to power supply
    # --------------------------------------------------------------------------

    psu = Aim_TTi_PSU(name="Aim TTi PSU")
    if psu.auto_connect(filepath_last_known_port=PATH_PORT):
        psu.begin()

    # --------------------------------------------------------------------------
    #   Create application
    # --------------------------------------------------------------------------
    QtCore.QThread.currentThread().setObjectName("MAIN")  # For DEBUG info

    app = QtWid.QApplication(sys.argv)
    app.setFont(QtGui.QFont("Arial", 9))
    app.setStyleSheet(SS_TEXTBOX_READ_ONLY + SS_GROUP)
    app.aboutToQuit.connect(about_to_quit)

    # --------------------------------------------------------------------------
    #   Set up communication threads for the PSU
    # --------------------------------------------------------------------------

    psu_qdev = Aim_TTi_PSU_qdev(
        dev=psu, DAQ_interval_ms=DAQ_INTERVAL_MS, debug=DEBUG
    )
    psu_qdev.start()

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    window = MainWindow()
    window.show()
    if QT_LIB in (PYQT5, PYSIDE2):
        sys.exit(app.exec_())
    else:
        sys.exit(app.exec())
