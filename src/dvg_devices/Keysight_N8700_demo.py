#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt/PySide GUI to interface with a Keysight N8700 power supply
(PSU).
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "12-06-2024"
__version__ = "1.5.0"
print(__url__)
# pylint: disable=wrong-import-position, missing-function-docstring, bare-except

import os
import sys
from pathlib import Path
from typing import List

import qtpy
from qtpy import QtCore, QtGui, QtWidgets as QtWid
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
        qdevs: List[Keysight_N8700_qdev],
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

    main_thread = QtCore.QThread.currentThread()
    if isinstance(main_thread, QtCore.QThread):
        main_thread.setObjectName("MAIN")  # For DEBUG info

    if qtpy.PYQT6 or qtpy.PYSIDE6:
        sys.argv += ["-platform", "windows:darkmode=0"]
    app = QtWid.QApplication(sys.argv)
    app.setStyle("Fusion")

    # --------------------------------------------------------------------------
    #   Set up communication threads for the PSUs
    # --------------------------------------------------------------------------

    psu_qdevs: List[Keysight_N8700_qdev] = []
    for psu in psus:
        psu_qdevs.append(
            Keysight_N8700_qdev(
                dev=psu,
                DAQ_trigger=DAQ_TRIGGER.SINGLE_SHOT_WAKE_UP,
                debug=DEBUG,
            )
        )

    # DEBUG information
    psu_qdevs[0].worker_DAQ.debug_color = ANSI.YELLOW
    psu_qdevs[0].worker_jobs.debug_color = ANSI.CYAN
    psu_qdevs[1].worker_DAQ.debug_color = ANSI.GREEN
    psu_qdevs[1].worker_jobs.debug_color = ANSI.RED

    for psu_qdev in psu_qdevs:
        psu_qdev.start()

    # --------------------------------------------------------------------------
    #   Set up PSU update timer
    # --------------------------------------------------------------------------

    def trigger_update_psus():
        if DEBUG:
            dprint("timer_psus: wake up all DAQ")

        for psu_qdev_ in psu_qdevs:
            psu_qdev_.wake_up_DAQ()

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

    sys.exit(app.exec())
