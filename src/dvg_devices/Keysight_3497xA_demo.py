#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt5 GUI to interface with a a Keysight (former HP or Agilent)
34970A/34972A data acquisition/switch unit.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "02-07-2020"  # 0.0.1 was stamped 14-09-2018
__version__ = "0.0.2"  # 0.0.1 corresponds to prototype 1.0.0



import sys

import visa

from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets as QtWid

from dvg_utils.dvg_pyqt_controls import SS_TEXTBOX_READ_ONLY

from dvg_devices.Keysight_3497xA_protocol_SCPI import Keysight_3497xA
from dvg_devices.Keysight_3497xA_qdev import Keysight_3497xA_qdev

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------

class MainWindow(QtWid.QWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setGeometry(600, 120, 0, 0)
        self.setWindowTitle("Keysight 3497xA control")

        # Top grid
        self.qlbl_title = QtWid.QLabel("Keysight 3497xA control",
            font=QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Bold))
        self.qpbt_exit = QtWid.QPushButton("Exit")
        self.qpbt_exit.clicked.connect(self.close)
        self.qpbt_exit.setMinimumHeight(30)

        grid_top = QtWid.QGridLayout()
        grid_top.addWidget(self.qlbl_title, 0, 0)
        grid_top.addWidget(self.qpbt_exit, 0, 1, QtCore.Qt.AlignRight)

        # Bottom grid
        hbox1 = QtWid.QHBoxLayout()
        hbox1.addWidget(mux_qdev.qgrp)
        hbox1.addStretch(1)
        hbox1.setAlignment(mux_qdev.qgrp, QtCore.Qt.AlignTop)

        # Round up full window
        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(grid_top)
        vbox.addLayout(hbox1)
        vbox.addStretch(1)

# ------------------------------------------------------------------------------
#   about_to_quit
# ------------------------------------------------------------------------------

def about_to_quit():
    print("About to quit")
    app.processEvents()
    mux_qdev.quit()
    try: mux.close()
    except: pass
    try: rm.close()
    except: pass

# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == '__main__':
    # VISA address of the Keysight 3497xA data acquisition/switch unit
    # containing a multiplexer plug-in module. Hence, we simply call this device
    # a 'mux'.
    #MUX_VISA_ADDRESS = "USB0::0x0957::0x2007::MY49018071::INSTR"
    MUX_VISA_ADDRESS = "GPIB0::9::INSTR"

    # A scan will be performed by the mux every N milliseconds
    MUX_SCANNING_INTERVAL_MS = 1000       # [ms]

    # SCPI commands to be send to the 3497xA to set up the scan cycle.
    """
    scan_list = "(@301:312)"
    MUX_SCPI_COMMANDS = [
                "rout:open %s" % scan_list,
                "conf:temp TC,J,%s" % scan_list,
                "unit:temp C,%s" % scan_list,
                "sens:temp:tran:tc:rjun:type INT,%s" % scan_list,
                "sens:temp:tran:tc:check ON,%s" % scan_list,
                "sens:temp:nplc 1,%s" % scan_list,
                "rout:scan %s" % scan_list]
    """

    scan_list = "(@101)"
    MUX_SCPI_COMMANDS = [
                "rout:open %s" % scan_list,
                "conf:res 1e5,%s" % scan_list,
                "sens:res:nplc 1,%s" % scan_list,
                "rout:scan %s" % scan_list]

    # --------------------------------------------------------------------------
    #   Connect to Keysight 3497xA (mux)
    # --------------------------------------------------------------------------

    rm = visa.ResourceManager()

    mux = Keysight_3497xA(MUX_VISA_ADDRESS, "MUX_1")
    if mux.connect(rm):
        mux.begin(MUX_SCPI_COMMANDS)

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
    #   Set up communication threads for the mux
    # --------------------------------------------------------------------------

    mux_qdev = Keysight_3497xA_qdev(mux, MUX_SCANNING_INTERVAL_MS)
    mux_qdev.start()

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
