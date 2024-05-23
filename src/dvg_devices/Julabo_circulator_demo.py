#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt/PySide GUI to interface with a Julabo circulating bath."""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "23-05-2024"
__version__ = "1.4.0"
print(__url__)
# pylint: disable=wrong-import-position, missing-function-docstring

import sys

import qtpy
from qtpy import QtCore, QtGui, QtWidgets as QtWid

import dvg_pyqt_controls as controls
from dvg_devices.Julabo_circulator_protocol_RS232 import Julabo_circulator
from dvg_devices.Julabo_circulator_qdev import Julabo_circulator_qdev

# Show debug info in terminal? Warning: Slow! Do not leave on unintentionally.
DEBUG = False

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(self, qdev: Julabo_circulator_qdev, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setWindowTitle("Julabo control")
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

        hbox = QtWid.QHBoxLayout()
        hbox.addWidget(qdev.grpb)
        hbox.addWidget(
            self.pbtn_exit, alignment=QtCore.Qt.AlignmentFlag.AlignTop
        )
        hbox.addStretch(1)

        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(hbox)
        vbox.addStretch(1)


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Config file containing COM port address
    PATH_PORT = "config/port_Julabo.txt"

    # The state of the Julabo is polled with this time interval
    DAQ_INTERVAL_MS = 500  # [ms]

    # --------------------------------------------------------------------------
    #   Connect to Julabo
    # --------------------------------------------------------------------------

    julabo = Julabo_circulator(name="Julabo")
    if julabo.auto_connect(filepath_last_known_port=PATH_PORT):
        julabo.begin()

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
    #   Set up communication threads for the Julabo
    # --------------------------------------------------------------------------

    julabo_qdev = Julabo_circulator_qdev(
        dev=julabo,
        DAQ_interval_ms=DAQ_INTERVAL_MS,
        debug=DEBUG,
    )
    julabo_qdev.start()

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    def about_to_quit():
        print("About to quit")
        app.processEvents()
        julabo_qdev.quit()
        julabo.close()

    app.aboutToQuit.connect(about_to_quit)
    window = MainWindow(qdev=julabo_qdev)
    window.show()

    sys.exit(app.exec())
