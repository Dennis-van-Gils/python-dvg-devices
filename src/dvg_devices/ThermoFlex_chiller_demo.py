#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt/PySide GUI to interface with a Thermo Scientific
ThermoFlex recirculating chiller.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "14-09-2022"
__version__ = "1.0.0"

# Mechanism to support both PyQt and PySide
# -----------------------------------------
import os
import sys

QT_LIB = os.getenv("PYQTGRAPH_QT_LIB")
PYSIDE = "PySide"
PYSIDE2 = "PySide2"
PYSIDE6 = "PySide6"
PYQT4 = "PyQt4"
PYQT5 = "PyQt5"
PYQT6 = "PyQt6"

# pylint: disable=import-error, no-name-in-module
# fmt: off
if QT_LIB is None:
    libOrder = [PYQT5, PYSIDE2, PYSIDE6, PYQT6]
    for lib in libOrder:
        if lib in sys.modules:
            QT_LIB = lib
            break

if QT_LIB is None:
    for lib in libOrder:
        try:
            __import__(lib)
            QT_LIB = lib
            break
        except ImportError:
            pass

if QT_LIB is None:
    raise Exception(
        "ThermoFlex_chiller_demo requires PyQt5, PyQt6, PySide2 or PySide6; "
        "none of these packages could be imported."
    )

if QT_LIB == PYQT5:
    from PyQt5 import QtCore, QtGui, QtWidgets as QtWid    # type: ignore
elif QT_LIB == PYQT6:
    from PyQt6 import QtCore, QtGui, QtWidgets as QtWid    # type: ignore
elif QT_LIB == PYSIDE2:
    from PySide2 import QtCore, QtGui, QtWidgets as QtWid  # type: ignore
elif QT_LIB == PYSIDE6:
    from PySide6 import QtCore, QtGui, QtWidgets as QtWid  # type: ignore

# fmt: on
# pylint: enable=import-error, no-name-in-module
# \end[Mechanism to support both PyQt and PySide]
# -----------------------------------------------

from dvg_pyqt_controls import SS_TEXTBOX_READ_ONLY

from dvg_devices.ThermoFlex_chiller_protocol_RS232 import ThermoFlex_chiller
from dvg_devices.ThermoFlex_chiller_qdev import ThermoFlex_chiller_qdev

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setGeometry(40, 60, 0, 0)
        self.setWindowTitle("ThermoFlex chiller control")

        # Top grid
        self.lbl_title = QtWid.QLabel(
            "ThermoFlex chiller control",
            font=QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Weight.Bold),
        )
        self.pbtn_exit = QtWid.QPushButton("Exit")
        self.pbtn_exit.clicked.connect(self.close)
        self.pbtn_exit.setMinimumHeight(30)

        grid_top = QtWid.QGridLayout()
        grid_top.addWidget(self.lbl_title, 0, 0)
        grid_top.addWidget(
            self.pbtn_exit, 0, 1, QtCore.Qt.AlignmentFlag.AlignRight
        )

        # Round up full window
        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(grid_top)
        vbox.addLayout(chiller_qdev.hbly_GUI)
        vbox.addStretch(1)


# ------------------------------------------------------------------------------
#   about_to_quit
# ------------------------------------------------------------------------------


def about_to_quit():
    print("About to quit")
    app.processEvents()
    chiller_qdev.quit()
    chiller.close()


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Temperature setpoint limits in software, not on a hardware level
    MIN_SETPOINT_DEG_C = 10  # [deg C]
    MAX_SETPOINT_DEG_C = 40  # [deg C]

    # Config file containing COM port address
    PATH_CONFIG = "config/port_chiller.txt"

    # The state of the chiller is polled with this time interval
    UPDATE_INTERVAL_MS = 1000  # [ms]

    # --------------------------------------------------------------------------
    #   Connect to ThermoFlex chiller
    # --------------------------------------------------------------------------

    chiller = ThermoFlex_chiller(
        name="chiller",
        min_setpoint_degC=MIN_SETPOINT_DEG_C,
        max_setpoint_degC=MAX_SETPOINT_DEG_C,
    )
    if chiller.auto_connect(filepath_last_known_port=PATH_CONFIG):
        chiller.begin()

    # --------------------------------------------------------------------------
    #   Create application
    # --------------------------------------------------------------------------
    QtCore.QThread.currentThread().setObjectName("MAIN")  # For DEBUG info

    app = 0  # Work-around for kernel crash when using Spyder IDE
    app = QtWid.QApplication(sys.argv)
    app.setFont(QtGui.QFont("Arial", 9))
    app.setStyleSheet(SS_TEXTBOX_READ_ONLY)
    app.aboutToQuit.connect(about_to_quit)

    # --------------------------------------------------------------------------
    #   Set up communication threads for the chiller
    # --------------------------------------------------------------------------

    chiller_qdev = ThermoFlex_chiller_qdev(
        dev=chiller, DAQ_interval_ms=UPDATE_INTERVAL_MS
    )
    chiller_qdev.start()

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    window = MainWindow()
    window.show()
    if QT_LIB in (PYQT5, PYSIDE2):
        sys.exit(app.exec_())
    else:
        sys.exit(app.exec())
