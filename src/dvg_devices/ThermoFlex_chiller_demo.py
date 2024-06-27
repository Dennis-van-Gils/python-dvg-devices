#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt/PySide GUI to interface with a Thermo Scientific
ThermoFlex recirculating chiller.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "23-05-2024"
__version__ = "1.5.0"
print(__url__)
# pylint: disable=wrong-import-position, missing-function-docstring

import sys

import qtpy
from qtpy import QtCore, QtGui, QtWidgets as QtWid

import dvg_pyqt_controls as controls
from dvg_devices.ThermoFlex_chiller_protocol_RS232 import ThermoFlex_chiller
from dvg_devices.ThermoFlex_chiller_qdev import ThermoFlex_chiller_qdev

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(self, qdev: ThermoFlex_chiller_qdev, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setWindowTitle("ThermoFlex chiller control")
        self.setGeometry(40, 60, 0, 0)
        self.setFont(QtGui.QFont("Arial", 9))
        self.setStyleSheet(
            controls.SS_TEXTBOX_READ_ONLY
            + controls.SS_GROUP
            + controls.SS_HOVER
        )

        # Top grid
        self.lbl_title = QtWid.QLabel("ThermoFlex chiller control")
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

        # Round up full window
        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(grid_top)
        vbox.addLayout(qdev.hbly_GUI)
        vbox.addStretch(1)


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

    main_thread = QtCore.QThread.currentThread()
    if isinstance(main_thread, QtCore.QThread):
        main_thread.setObjectName("MAIN")  # For DEBUG info

    if qtpy.PYQT6 or qtpy.PYSIDE6:
        sys.argv += ["-platform", "windows:darkmode=0"]
    app = QtWid.QApplication(sys.argv)
    app.setStyle("Fusion")

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

    def about_to_quit():
        print("About to quit")
        app.processEvents()
        chiller_qdev.quit()
        chiller.close()

    app.aboutToQuit.connect(about_to_quit)
    window = MainWindow(qdev=chiller_qdev)
    window.show()

    sys.exit(app.exec())
