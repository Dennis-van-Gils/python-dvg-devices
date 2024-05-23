#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt/PySide GUI to interface with a Compax3 servo controller.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "23-05-2024"
__version__ = "1.4.0"
print(__url__)
# pylint: disable=wrong-import-position, missing-function-docstring

import sys
from pathlib import Path

import qtpy
from qtpy import QtCore, QtGui, QtWidgets as QtWid
from qtpy.QtCore import Slot  # type: ignore

import dvg_pyqt_controls as controls
from dvg_devices.Compax3_servo_protocol_RS232 import Compax3_servo
from dvg_devices.Compax3_servo_qdev import Compax3_servo_qdev
from dvg_devices.Compax3_servo_step_navigator_GUI import Compax3_step_navigator

# Show debug info in terminal? Warning: Slow! Do not leave on unintentionally.
DEBUG = False

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(
        self,
        qdev_horz: Compax3_servo_qdev,
        qdev_vert: Compax3_servo_qdev,
        step_nav: Compax3_step_navigator,
        parent=None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)

        self.setWindowTitle("Compax3 traverse controller")
        self.setGeometry(40, 60, 0, 0)
        self.setFont(QtGui.QFont("Arial", 9))
        self.setStyleSheet(
            controls.SS_TEXTBOX_READ_ONLY
            + controls.SS_GROUP
            + controls.SS_HOVER
        )

        # Top grid
        self.lbl_title = QtWid.QLabel("Compax3 traverse controller")
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

        # Traverse schematic image
        lbl_trav_img = QtWid.QLabel()
        lbl_trav_img.setPixmap(
            QtGui.QPixmap(
                str(Path(sys.modules[__name__].__file__).parent)  # type: ignore
                + "/Traverse_layout.png"
            )
        )
        lbl_trav_img.setFixedSize(244, 240)

        grid = QtWid.QGridLayout()
        grid.addWidget(lbl_trav_img, 0, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        grpb_trav_img = QtWid.QGroupBox("Traverse schematic")
        grpb_trav_img.setLayout(grid)

        # Round up full window
        vbox = QtWid.QVBoxLayout()
        vbox.addWidget(grpb_trav_img)
        vbox.addWidget(step_nav.grpb)
        vbox.addStretch(1)
        vbox.setAlignment(step_nav.grpb, QtCore.Qt.AlignmentFlag.AlignLeft)

        hbox = QtWid.QHBoxLayout()
        hbox.addWidget(qdev_vert.qgrp)
        hbox.addWidget(qdev_horz.qgrp)
        hbox.addLayout(vbox)
        hbox.addStretch(1)
        hbox.setAlignment(qdev_horz.qgrp, QtCore.Qt.AlignmentFlag.AlignTop)
        hbox.setAlignment(qdev_vert.qgrp, QtCore.Qt.AlignmentFlag.AlignTop)

        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(grid_top)
        vbox.addLayout(hbox)


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Specific connection settings of each traverse axis of our setup
    class Trav_connection_params:
        # Serial number of the Compax3 traverse controller to connect to.
        # Set to "" to connect to any Compax3.
        serial = ""
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
    #   Connect to Compax3 traverse controllers
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

    main_thread = QtCore.QThread.currentThread()
    if isinstance(main_thread, QtCore.QThread):
        main_thread.setObjectName("MAIN")  # For DEBUG info

    if qtpy.PYQT6 or qtpy.PYSIDE6:
        sys.argv += ["-platform", "windows:darkmode=0"]
    app = QtWid.QApplication(sys.argv)
    app.setStyle("Fusion")

    # --------------------------------------------------------------------------
    #   Set up communication threads for the Compax3 traverse controllers
    # --------------------------------------------------------------------------

    trav_horz_qdev = Compax3_servo_qdev(
        dev=trav_horz,
        DAQ_interval_ms=UPDATE_INTERVAL_MS,
        debug=DEBUG,
    )
    trav_vert_qdev = Compax3_servo_qdev(
        dev=trav_vert,
        DAQ_interval_ms=UPDATE_INTERVAL_MS,
        debug=DEBUG,
    )
    travs_qdev = [trav_horz_qdev, trav_vert_qdev]

    # Create Compax3 single step navigator
    trav_step_nav = Compax3_step_navigator(
        trav_horz=trav_horz, trav_vert=trav_vert
    )

    # Act on step signals
    @Slot()
    def act_upon_signal_step_up(new_pos: float):
        trav_vert_qdev.qlin_new_pos.setText(f"{new_pos:.2f}")
        trav_vert_qdev.process_pbtn_move_to_new_pos()

    @Slot()
    def act_upon_signal_step_down(new_pos: float):
        trav_vert_qdev.qlin_new_pos.setText(f"{new_pos:.2f}")
        trav_vert_qdev.process_pbtn_move_to_new_pos()

    @Slot()
    def act_upon_signal_step_left(new_pos: float):
        trav_horz_qdev.qlin_new_pos.setText(f"{new_pos:.2f}")
        trav_horz_qdev.process_pbtn_move_to_new_pos()

    @Slot()
    def act_upon_signal_step_right(new_pos: float):
        trav_horz_qdev.qlin_new_pos.setText(f"{new_pos:.2f}")
        trav_horz_qdev.process_pbtn_move_to_new_pos()

    trav_step_nav.step_up.connect(act_upon_signal_step_up)
    trav_step_nav.step_down.connect(act_upon_signal_step_down)
    trav_step_nav.step_left.connect(act_upon_signal_step_left)
    trav_step_nav.step_right.connect(act_upon_signal_step_right)

    trav_horz_qdev.start()
    trav_vert_qdev.start()

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    def about_to_quit():
        print("About to quit")
        app.processEvents()
        for trav_qdev in travs_qdev:
            trav_qdev.quit()
        for trav in travs:
            trav.close()

    app.aboutToQuit.connect(about_to_quit)
    window = MainWindow(
        qdev_horz=trav_horz_qdev,
        qdev_vert=trav_vert_qdev,
        step_nav=trav_step_nav,
    )
    window.show()

    sys.exit(app.exec())
