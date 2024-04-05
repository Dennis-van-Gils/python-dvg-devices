#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt/PySide GUI to interface with a Keysight N8700 power supply
(PSU).
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "04-04-2024"
__version__ = "1.4.0"
# pylint: disable=wrong-import-position, missing-function-docstring, bare-except

import os
import sys
from pathlib import Path

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
from dvg_debug_functions import ANSI, dprint

from dvg_qdeviceio import DAQ_TRIGGER
from dvg_devices.Keysight_N8700_protocol_SCPI import Keysight_N8700
from dvg_devices.Keysight_N8700_qdev import Keysight_N8700_qdev

# Show debug info in terminal? Warning: Slow! Do not leave on unintentionally.
DEBUG = False

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(
        self,
        qdevs: list[Keysight_N8700_qdev],
        parent=None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)

        self.setWindowTitle("Keysight N8700 power supply control")
        self.setGeometry(40, 60, 0, 0)
        self.setStyleSheet(
            controls.SS_TEXTBOX_READ_ONLY
            + controls.SS_GROUP
            + controls.SS_HOVER
        )

        # Top grid
        self.lbl_title = QtWid.QLabel("Keysight N8700 power supply control")
        self.lbl_title.setFont(
            QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Weight.Bold)
        )
        self.pbtn_exit = QtWid.QPushButton("Exit")
        self.pbtn_exit.clicked.connect(self.close)
        self.pbtn_exit.setMinimumHeight(30)

        grid_top = QtWid.QGridLayout()
        grid_top.addWidget(self.lbl_title, 0, 0)
        grid_top.addWidget(
            self.pbtn_exit, 0, 1, QtCore.Qt.AlignmentFlag.AlignRight
        )

        # PSU groups
        hbox1 = QtWid.QHBoxLayout()
        for qdev in qdevs:
            hbox1.addWidget(qdev.grpb)
        hbox1.addStretch(1)

        # Round up full window
        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(grid_top)
        vbox.addLayout(hbox1)
        vbox.addStretch(1)


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # VISA addresses of the Keysight PSUs
    VISA_ADDRESS_PSU_1 = "USB0::0x0957::0x8707::US15M3727P::INSTR"
    VISA_ADDRESS_PSU_2 = "USB0::0x0957::0x8707::US15M3728P::INSTR"
    VISA_ADDRESS_PSU_3 = "USB0::0x0957::0x8707::US15M3726P::INSTR"

    # Config files
    PATH_CONFIG_PSU_1 = Path(
        os.getcwd() + "/config/settings_Keysight_PSU_1.txt"
    )
    PATH_CONFIG_PSU_2 = Path(
        os.getcwd() + "/config/settings_Keysight_PSU_2.txt"
    )
    PATH_CONFIG_PSU_3 = Path(
        os.getcwd() + "/config/settings_Keysight_PSU_3.txt"
    )

    # The state of the PSUs is polled with this time interval
    UPDATE_INTERVAL_MS = 1000  # [ms]

    # --------------------------------------------------------------------------
    #   Connect to and set up Keysight power supplies (PSU)
    # --------------------------------------------------------------------------

    rm = pyvisa.ResourceManager()

    psu1 = Keysight_N8700(VISA_ADDRESS_PSU_1, PATH_CONFIG_PSU_1, "PSU 1")
    psu2 = Keysight_N8700(VISA_ADDRESS_PSU_2, PATH_CONFIG_PSU_2, "PSU 2")
    psu3 = Keysight_N8700(VISA_ADDRESS_PSU_3, PATH_CONFIG_PSU_3, "PSU 3")
    psus = [psu1, psu2, psu3]

    for psu in psus:
        if psu.connect(rm):
            psu.read_config_file()
            psu.begin()

    # --------------------------------------------------------------------------
    #   Create application
    # --------------------------------------------------------------------------

    QtCore.QThread.currentThread().setObjectName("MAIN")  # For DEBUG info
    app = QtWid.QApplication(sys.argv)

    # --------------------------------------------------------------------------
    #   Set up communication threads for the PSUs
    # --------------------------------------------------------------------------

    psu_qdevs: list[Keysight_N8700_qdev] = []
    for psu in psus:
        psu_qdevs.append(
            Keysight_N8700_qdev(
                dev=psu,
                DAQ_trigger=DAQ_TRIGGER.SINGLE_SHOT_WAKE_UP,
                debug=DEBUG,
            )
        )

    # DEBUG information
    psu_qdevs[0].worker_DAQ.debug_color = ANSI.YELLOW  # type: ignore
    psu_qdevs[0].worker_jobs.debug_color = ANSI.CYAN  # type: ignore
    psu_qdevs[1].worker_DAQ.debug_color = ANSI.GREEN  # type: ignore
    psu_qdevs[1].worker_jobs.debug_color = ANSI.RED  # type: ignore

    for psu_qdev in psu_qdevs:
        psu_qdev.start()

    # --------------------------------------------------------------------------
    #   Set up PSU update timer
    # --------------------------------------------------------------------------

    def trigger_update_psus():
        if DEBUG:
            dprint("timer_psus: wake up all DAQ")

        for psu_qdev_ in psu_qdevs:
            if psu_qdev_.worker_DAQ is not None:
                psu_qdev_.worker_DAQ.wake_up()

    timer_psus = QtCore.QTimer()
    timer_psus.timeout.connect(trigger_update_psus)
    timer_psus.start(UPDATE_INTERVAL_MS)

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    def about_to_quit():
        print("About to quit")
        app.processEvents()
        for psu_qdev_ in psu_qdevs:
            psu_qdev_.quit()
        for psu_ in psus:
            try:
                psu_.close()
            except:
                pass
        try:
            rm.close()
        except:
            pass

    app.aboutToQuit.connect(about_to_quit)
    window = MainWindow(qdevs=psu_qdevs)
    window.show()

    if QT_LIB in (PYQT5, PYSIDE2):
        sys.exit(app.exec_())
    else:
        sys.exit(app.exec())
