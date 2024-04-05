#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt/PySide GUI to interface with a a Keysight (former HP or
Agilent) 34970A/34972A data acquisition/switch unit.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "04-04-2024"
__version__ = "1.4.0"
# pylint: disable=wrong-import-position, missing-function-docstring, bare-except

import os
import sys

# VISA address of the Keysight 3497xA data acquisition/switch unit containing a
# multiplexer plug-in module. Hence, we simply call this device a 'mux'.
# MUX_VISA_ADDRESS = "USB0::0x0957::0x2007::MY49018071::INSTR"
MUX_VISA_ADDRESS = "GPIB0::9::INSTR"

# SCPI commands to be send to the mux to set up the scan cycle.
"""
scan_list = "(@101:112)"
MUX_SCPI_COMMANDS = [
            f"rout:open {scan_list}",
            f"conf:temp TC,J,{scan_list}",
            f"unit:temp C,{scan_list}",
            f"sens:temp:tran:tc:rjun:type INT,{scan_list}",
            f"sens:temp:tran:tc:check ON,{scan_list}",
            f"sens:temp:nplc 1,{scan_list}",
            f"rout:scan {scan_list}",
]
"""

scan_list = "(@101:110)"
MUX_SCPI_COMMANDS = [
    f"rout:open {scan_list}",
    f"conf:res 1e6,{scan_list}",
    f"sens:res:nplc 1,{scan_list}",
    f"rout:scan {scan_list}",
]

# A scan will be performed by the mux every N milliseconds
DAQ_INTERVAL_MS = 1000  # [ms]

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

import pyvisa

import dvg_pyqt_controls as controls
from dvg_devices.Keysight_3497xA_protocol_SCPI import Keysight_3497xA
from dvg_devices.Keysight_3497xA_qdev import Keysight_3497xA_qdev

# Show debug info in terminal? Warning: Slow! Do not leave on unintentionally.
DEBUG = False

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(self, qdev: Keysight_3497xA_qdev, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setWindowTitle("Keysight 3497xA control")
        self.setGeometry(40, 60, 0, 0)
        self.setFont(QtGui.QFont("Arial", 9))
        self.setStyleSheet(
            controls.SS_TEXTBOX_READ_ONLY
            + controls.SS_GROUP
            + controls.SS_HOVER
        )

        # Top grid
        self.qlbl_title = QtWid.QLabel("Keysight 3497xA control")
        self.qlbl_title.setFont(
            QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Weight.Bold)
        )
        self.qpbt_exit = QtWid.QPushButton("Exit")
        self.qpbt_exit.clicked.connect(self.close)
        self.qpbt_exit.setMinimumHeight(30)

        grid_top = QtWid.QGridLayout()
        grid_top.addWidget(self.qlbl_title, 0, 0)
        grid_top.addWidget(
            self.qpbt_exit, 0, 1, QtCore.Qt.AlignmentFlag.AlignRight
        )

        # Bottom grid
        hbox1 = QtWid.QHBoxLayout()
        hbox1.addWidget(qdev.qgrp)
        hbox1.addStretch(1)
        hbox1.setAlignment(qdev.qgrp, QtCore.Qt.AlignmentFlag.AlignTop)

        # Round up full window
        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(grid_top)
        vbox.addLayout(hbox1)
        vbox.addStretch(1)


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":

    # --------------------------------------------------------------------------
    #   Connect to Keysight 3497xA (mux)
    # --------------------------------------------------------------------------

    rm = pyvisa.ResourceManager()
    mux = Keysight_3497xA(MUX_VISA_ADDRESS, "MUX")

    try:
        if mux.connect(rm):
            mux.begin(MUX_SCPI_COMMANDS)
    except ValueError as e:
        # No connection could be made to the VISA device because module
        # dependencies are missing. Print error, not raise and continue to
        # show the GUI.
        print(e)

    # --------------------------------------------------------------------------
    #   Create application
    # --------------------------------------------------------------------------

    QtCore.QThread.currentThread().setObjectName("MAIN")  # For DEBUG info
    app = QtWid.QApplication(sys.argv)

    # --------------------------------------------------------------------------
    #   Set up communication threads for the mux
    # --------------------------------------------------------------------------

    mux_qdev = Keysight_3497xA_qdev(
        dev=mux,
        DAQ_interval_ms=DAQ_INTERVAL_MS,
        debug=DEBUG,
    )
    mux_qdev.start()

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    def about_to_quit():
        print("About to quit")
        app.processEvents()
        mux_qdev.quit()
        try:
            mux.close()
        except:
            pass
        try:
            rm.close()
        except:
            pass

    app.aboutToQuit.connect(about_to_quit)
    window = MainWindow(qdev=mux_qdev)
    window.show()

    if QT_LIB in (PYQT5, PYSIDE2):
        sys.exit(app.exec_())
    else:
        sys.exit(app.exec())
