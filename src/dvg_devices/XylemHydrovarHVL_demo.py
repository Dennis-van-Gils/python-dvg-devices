#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt/PySide GUI to interface with an Xylem Hydrovar HVL
variable speed pump controller."""
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
from dvg_devices.XylemHydrovarHVL_protocol_RTU import XylemHydrovarHVL
from dvg_devices.XylemHydrovarHVL_qdev import XylemHydrovarHVL_qdev

# Show debug info in terminal? Warning: Slow! Do not leave on unintentionally.
DEBUG = False

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(self, qdev: XylemHydrovarHVL_qdev, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setWindowTitle("Xylem Hydrovar HVL")
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

        p = {"alignment": QtCore.Qt.AlignmentFlag.AlignTop}
        hbox = QtWid.QHBoxLayout()
        hbox.addWidget(qdev.qgrp_control)

        vbox = QtWid.QVBoxLayout()
        vbox.addWidget(qdev.qgrp_inverter)
        vbox.addWidget(qdev.qgrp_error_status)

        hbox.addLayout(vbox)
        hbox.addWidget(self.pbtn_exit, **p)
        hbox.addStretch(1)

        vbox_final = QtWid.QVBoxLayout(self)
        vbox_final.addLayout(hbox)
        vbox_final.addStretch(1)


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Config file containing COM port address
    PATH_PORT = "config/port_Hydrovar.txt"

    # The state of the pump is polled with this time interval
    DAQ_INTERVAL_MS = 200  # [ms]

    # --------------------------------------------------------------------------
    #   Connect to Xylem Hydrovar HVL pump
    # --------------------------------------------------------------------------

    pump = XylemHydrovarHVL(
        connect_to_modbus_slave_address=0x01,
        max_pressure_setpoint_bar=3,
    )
    pump.serial_settings = {
        "baudrate": 115200,
        "bytesize": 8,
        "parity": "N",
        "stopbits": 1,
        "timeout": 0.2,
        "write_timeout": 0.2,
    }

    if pump.auto_connect(PATH_PORT):
        pump.begin()

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
    #   Set up communication threads for the Xylem Hydrovar HVL pump
    # --------------------------------------------------------------------------

    pump_qdev = XylemHydrovarHVL_qdev(
        dev=pump,
        DAQ_interval_ms=DAQ_INTERVAL_MS,
        debug=DEBUG,
    )

    pump_qdev.start()

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    def about_to_quit():
        print("About to quit")
        app.processEvents()
        pump_qdev.quit()
        pump.close()

    app.aboutToQuit.connect(about_to_quit)
    window = MainWindow(qdev=pump_qdev)
    window.show()

    sys.exit(app.exec())
