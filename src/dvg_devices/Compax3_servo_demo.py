#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt/PySide GUI to interface with a Compax3 servo controller.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "28-10-2022"
__version__ = "1.0.0"
# pylint: disable=bare-except

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
    this_file = __file__.split(os.sep)[-1]
    raise ImportError(
        f"{this_file} requires PyQt5, PyQt6, PySide2 or PySide6; "
        "none of these packages could be imported."
    )

# fmt: off
# pylint: disable=import-error, no-name-in-module
if QT_LIB == PYQT5:
    from PyQt5 import QtCore, QtGui, QtWidgets as QtWid    # type: ignore
    from PyQt5.QtCore import pyqtSlot as Slot              # type: ignore
elif QT_LIB == PYQT6:
    from PyQt6 import QtCore, QtGui, QtWidgets as QtWid    # type: ignore
    from PyQt6.QtCore import pyqtSlot as Slot              # type: ignore
elif QT_LIB == PYSIDE2:
    from PySide2 import QtCore, QtGui, QtWidgets as QtWid  # type: ignore
    from PySide2.QtCore import Slot                        # type: ignore
elif QT_LIB == PYSIDE6:
    from PySide6 import QtCore, QtGui, QtWidgets as QtWid  # type: ignore
    from PySide6.QtCore import Slot                        # type: ignore
# pylint: enable=import-error, no-name-in-module
# fmt: on

# \end[Mechanism to support both PyQt and PySide]
# -----------------------------------------------

from dvg_pyqt_controls import SS_TEXTBOX_READ_ONLY, SS_GROUP

from dvg_devices.Compax3_servo_protocol_RS232 import Compax3_servo
from dvg_devices.Compax3_servo_qdev import Compax3_servo_qdev
from dvg_devices.Compax3_servo_step_navigator_GUI import Compax3_step_navigator

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setGeometry(40, 60, 0, 0)
        self.setWindowTitle("Compax3 traverse controller")

        # Top grid
        self.lbl_title = QtWid.QLabel(
            "Compax3 traverse controller",
            font=QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Weight.Bold),
        )
        self.pbtn_exit = QtWid.QPushButton("Exit")
        self.pbtn_exit.clicked.connect(self.close)
        self.pbtn_exit.setMinimumHeight(30)

        grid_top = QtWid.QGridLayout()
        grid_top.addWidget(self.lbl_title, 0, 0)
        grid_top.addWidget(
            self.pbtn_exit, 0, 1, QtCore.Qt.AlignmentFlag.AlignRight
        )

        # Traverse schematic image
        lbl_trav_img = QtWid.QLabel()
        lbl_trav_img.setPixmap(
            QtGui.QPixmap(
                str(Path(sys.modules[__name__].__file__).parent)
                + "/Traverse_layout.png"
            )
        )
        lbl_trav_img.setFixedSize(244, 240)

        grid = QtWid.QGridLayout()
        grid.addWidget(lbl_trav_img, 0, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        grpb_trav_img = QtWid.QGroupBox("Traverse schematic")
        grpb_trav_img.setStyleSheet(SS_GROUP)
        grpb_trav_img.setLayout(grid)

        # Round up full window
        vbox = QtWid.QVBoxLayout()
        vbox.addWidget(grpb_trav_img)
        vbox.addWidget(trav_step_nav.grpb)
        vbox.addStretch(1)
        vbox.setAlignment(trav_step_nav.grpb, QtCore.Qt.AlignmentFlag.AlignLeft)

        hbox = QtWid.QHBoxLayout()
        hbox.addWidget(trav_vert_qdev.qgrp)
        hbox.addWidget(trav_horz_qdev.qgrp)
        hbox.addLayout(vbox)
        hbox.addStretch(1)
        hbox.setAlignment(trav_horz_qdev.qgrp, QtCore.Qt.AlignmentFlag.AlignTop)
        hbox.setAlignment(trav_vert_qdev.qgrp, QtCore.Qt.AlignmentFlag.AlignTop)

        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(grid_top)
        vbox.addLayout(hbox)


# ------------------------------------------------------------------------------
#   Act on step signals
# ------------------------------------------------------------------------------


@Slot()
def act_upon_signal_step_up(new_pos: float):
    trav_vert_qdev.qled_new_pos.setText("%.2f" % new_pos)
    trav_vert_qdev.process_pbtn_move_to_new_pos()


@Slot()
def act_upon_signal_step_down(new_pos: float):
    trav_vert_qdev.qled_new_pos.setText("%.2f" % new_pos)
    trav_vert_qdev.process_pbtn_move_to_new_pos()


@Slot()
def act_upon_signal_step_left(new_pos: float):
    trav_horz_qdev.qled_new_pos.setText("%.2f" % new_pos)
    trav_horz_qdev.process_pbtn_move_to_new_pos()


@Slot()
def act_upon_signal_step_right(new_pos: float):
    trav_horz_qdev.qled_new_pos.setText("%.2f" % new_pos)
    trav_horz_qdev.process_pbtn_move_to_new_pos()


# ------------------------------------------------------------------------------
#   about_to_quit
# ------------------------------------------------------------------------------


def about_to_quit():
    print("About to quit")
    app.processEvents()

    for trav_qdev in travs_qdev:
        trav_qdev.quit()

    for trav in travs:
        trav.close()


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Specific connection settings of each traverse axis of our setup
    class Trav_connection_params:
        # Serial number of the Compax3 traverse controller to connect to.
        # Set to '' or None to connect to any Compax3.
        serial = None
        # Display name
        name = "TRAV"
        # Path to the config textfile containing the (last used) RS232 port
        path_config = "config/port_Compax3_trav.txt"

    # Horizontal axis
    trav_conn_horz = Trav_connection_params()
    trav_conn_horz.serial = "4409980001"
    trav_conn_horz.name = "TRAV HORZ"
    trav_conn_horz.path_config = "config/port_Compax3_trav_horz.txt"

    # Vertical axis
    trav_conn_vert = Trav_connection_params()
    trav_conn_vert.serial = "4319370001"
    trav_conn_vert.name = "TRAV VERT"
    trav_conn_vert.path_config = "config/port_Compax3_trav_vert.txt"

    # The state of the traverse controllers is polled with this time interval
    UPDATE_INTERVAL_MS = 250  # [ms]

    # --------------------------------------------------------------------------
    #   Connect to and set up Compax3 traverse controllers
    # --------------------------------------------------------------------------

    trav_horz = Compax3_servo(
        name=trav_conn_horz.name,
        connect_to_serial_number=trav_conn_horz.serial,
    )
    trav_vert = Compax3_servo(
        name=trav_conn_vert.name,
        connect_to_serial_number=trav_conn_vert.serial,
    )

    if trav_horz.auto_connect(
        filepath_last_known_port=trav_conn_horz.path_config
    ):
        trav_horz.begin()

        # Set the default motion profile (= #2) parameters
        trav_horz.store_motion_profile(
            target_position=0,
            velocity=10,
            mode=1,
            accel=100,
            decel=100,
            jerk=1e6,
            profile_number=2,
        )

    if trav_vert.auto_connect(
        filepath_last_known_port=trav_conn_vert.path_config
    ):
        trav_vert.begin()

        # Set the default motion profile (= #2) parameters
        trav_vert.store_motion_profile(
            target_position=0,
            velocity=10,
            mode=1,
            accel=100,
            decel=100,
            jerk=1e6,
            profile_number=2,
        )

    travs = [trav_horz, trav_vert]

    # --------------------------------------------------------------------------
    #   Create application
    # --------------------------------------------------------------------------
    QtCore.QThread.currentThread().setObjectName("MAIN")  # For DEBUG info

    app = 0  # Work-around for kernel crash when using Spyder IDE
    app = QtWid.QApplication(sys.argv)
    app.setFont(QtGui.QFont("Arial", 9))
    app.setStyleSheet(SS_TEXTBOX_READ_ONLY)
    app.aboutToQuit.connect(about_to_quit)

    # Create PyQt GUI interfaces and communication threads for the device
    trav_horz_qdev = Compax3_servo_qdev(
        dev=trav_horz, DAQ_interval_ms=UPDATE_INTERVAL_MS
    )
    trav_vert_qdev = Compax3_servo_qdev(
        dev=trav_vert, DAQ_interval_ms=UPDATE_INTERVAL_MS
    )
    travs_qdev = [trav_horz_qdev, trav_vert_qdev]

    # Create Compax3 single step navigator
    trav_step_nav = Compax3_step_navigator(
        trav_horz=trav_horz, trav_vert=trav_vert
    )
    trav_step_nav.step_up.connect(act_upon_signal_step_up)
    trav_step_nav.step_down.connect(act_upon_signal_step_down)
    trav_step_nav.step_left.connect(act_upon_signal_step_left)
    trav_step_nav.step_right.connect(act_upon_signal_step_right)

    # Create window
    window = MainWindow()

    # --------------------------------------------------------------------------
    #   Start threads
    # --------------------------------------------------------------------------

    trav_horz_qdev.start()
    trav_vert_qdev.start()

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    window.show()
    if QT_LIB in (PYQT5, PYSIDE2):
        sys.exit(app.exec_())
    else:
        sys.exit(app.exec())
