#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt/PySide GUI to interface with MDrive stepper motors by
Novanta IMS (former Schneider Electric) set up in party mode.
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
from dvg_devices.MDrive_stepper_protocol_RS422 import (
    MDrive_Motor,
    MDrive_Controller,
)
from dvg_devices.MDrive_stepper_qdev import MDrive_Controller_qdev

# Show debug info in terminal? Warning: Slow! Do not leave on unintentionally.
DEBUG = False

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------

SS_TABS = (
    "QTabWidget::pane {"
    "   border: 0px solid gray;}"
    "QTabBar::tab:selected {"
    "   background: " + controls.COLOR_GROUP_BG + "; "
    "   border-bottom-color: " + controls.COLOR_GROUP_BG + ";}"
    "QTabWidget>QWidget>QWidget {"
    "   border: 2px solid gray;"
    "   background: " + controls.COLOR_GROUP_BG + ";} "
    "QTabBar::tab {"
    "   background: " + controls.COLOR_TAB + ";"
    "   border: 2px solid gray;"
    "   border-bottom-color: " + controls.COLOR_TAB + ";"
    "   border-top-left-radius: 4px;"
    "   border-top-right-radius: 4px;"
    # "   min-width: 119px;"
    "   padding: 6px;} "
    "QTabBar::tab:hover {"
    "   background: " + controls.COLOR_HOVER + ";"
    "   border: 2px solid " + controls.COLOR_HOVER_BORDER + ";"
    "   border-bottom-color: " + controls.COLOR_HOVER + ";"
    "   border-top-left-radius: 4px;"
    "   border-top-right-radius: 4px;"
    "   padding: 6px;} "
    "QTabWidget::tab-bar {"
    "   left: 0px;}"
)


class MainWindow(QtWid.QWidget):
    def __init__(self, qdev: MDrive_Controller_qdev, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setWindowTitle("MDrive control")
        self.setGeometry(40, 60, 0, 0)
        self.setFont(QtGui.QFont("Arial", 9))
        self.setStyleSheet(
            controls.SS_TEXTBOX_READ_ONLY
            + controls.SS_GROUP
            + controls.SS_HOVER
            + SS_TABS
        )

        self.pbtn_exit = QtWid.QPushButton("Exit")
        self.pbtn_exit.clicked.connect(self.close)
        self.pbtn_exit.setMinimumHeight(30)

        hbox = QtWid.QHBoxLayout()
        hbox.addLayout(qdev.hbox, stretch=1)
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
    PATH_PORT = "config/port_MDrive.txt"

    # The state of the MDrive motor(s) is polled with this time interval
    DAQ_INTERVAL_MS = 200  # [ms]

    # --------------------------------------------------------------------------
    #   Connect to MDrive Controller
    # --------------------------------------------------------------------------

    mdrive = MDrive_Controller()
    if mdrive.auto_connect(filepath_last_known_port=PATH_PORT):
        # mdrive.begin()
        mdrive.begin(device_names_to_scan="xyz")
    else:
        # Ensure showing the GUI even when no connection could be made -> We add
        # in a dummy motor.
        mdrive.motors.append(
            MDrive_Motor(controller=mdrive, device_name="not found")
        )

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
    #   Set up communication threads for the MDrive Controller
    # --------------------------------------------------------------------------

    mdrive_qdev = MDrive_Controller_qdev(
        dev=mdrive,
        DAQ_interval_ms=DAQ_INTERVAL_MS,
        debug=DEBUG,
    )
    mdrive_qdev.start()

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    def about_to_quit():
        print("About to quit")
        app.processEvents()
        mdrive_qdev.quit()
        mdrive.close()

    app.aboutToQuit.connect(about_to_quit)
    window = MainWindow(qdev=mdrive_qdev)
    window.show()

    sys.exit(app.exec())
