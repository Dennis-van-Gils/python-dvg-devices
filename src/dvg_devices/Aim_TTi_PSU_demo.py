#!/usr/bin/env python3
# -*- coding: utf-8 -*-
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "18-08-2020"
__version__ = "0.2.2"

import sys

from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets as QtWid

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
        hbox.addWidget(self.pbtn_exit, alignment=QtCore.Qt.AlignTop)
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
    sys.exit(app.exec_())
