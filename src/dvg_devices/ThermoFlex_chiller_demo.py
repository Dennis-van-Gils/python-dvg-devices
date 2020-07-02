#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt5 GUI to interface with a Thermo Scientific ThermoFlex
recirculating chiller.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "02-07-2020"  # 0.0.1 was stamped 14-09-2018
__version__ = "0.0.2"  # 0.0.1 corresponds to prototype 1.0.0

import sys
from pathlib import Path

from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets as QtWid

from dvg_debug_functions import ANSI
from DvG_pyqt_controls import SS_TEXTBOX_READ_ONLY

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
        self.lbl_title = QtWid.QLabel("ThermoFlex chiller control",
            font=QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Bold))
        self.pbtn_exit = QtWid.QPushButton("Exit")
        self.pbtn_exit.clicked.connect(self.close)
        self.pbtn_exit.setMinimumHeight(30)

        grid_top = QtWid.QGridLayout()
        grid_top.addWidget(self.lbl_title, 0, 0)
        grid_top.addWidget(self.pbtn_exit, 0, 1, QtCore.Qt.AlignRight)

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
    try: chiller.close()
    except: pass

# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == '__main__':
    # Temperature setpoint limits in software, not on a hardware level
    MIN_SETPOINT_DEG_C = 10     # [deg C]
    MAX_SETPOINT_DEG_C = 40     # [deg C]

    # Config file containing COM port address
    PATH_CONFIG = Path("config/port_chiller.txt")

    # The state of the chiller is polled with this time interval
    UPDATE_INTERVAL_MS = 1000   # [ms]

    # --------------------------------------------------------------------------
    #   Connect to ThermoFlex chiller
    # --------------------------------------------------------------------------

    chiller = ThermoFlex_chiller(
                        min_setpoint_degC=MIN_SETPOINT_DEG_C,
                        max_setpoint_degC=MAX_SETPOINT_DEG_C,
                        name='chiller')
    if chiller.auto_connect(PATH_CONFIG):
        chiller.begin()

    # --------------------------------------------------------------------------
    #   Create application
    # --------------------------------------------------------------------------
    QtCore.QThread.currentThread().setObjectName('MAIN')    # For DEBUG info

    app = 0    # Work-around for kernel crash when using Spyder IDE
    app = QtWid.QApplication(sys.argv)
    app.setFont(QtGui.QFont("Arial", 9))
    app.setStyleSheet(SS_TEXTBOX_READ_ONLY)
    app.aboutToQuit.connect(about_to_quit)

    # --------------------------------------------------------------------------
    #   Set up communication threads for the chiller
    # --------------------------------------------------------------------------

    chiller_qdev = ThermoFlex_chiller_qdev(chiller, UPDATE_INTERVAL_MS)

    # For DEBUG info
    chiller_qdev.worker_DAQ.debug_color = ANSI.YELLOW
    chiller_qdev.worker_jobs.debug_color = ANSI.CYAN

    chiller_qdev.start()

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
