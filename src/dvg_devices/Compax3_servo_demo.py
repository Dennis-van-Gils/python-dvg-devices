#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt5 GUI to interface with a Compax3 traverse controller.
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
from dvg_utils.dvg_pyqt_controls import SS_TEXTBOX_READ_ONLY, SS_GROUP

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
        self.lbl_title = QtWid.QLabel("Compax3 traverse controller",
            font=QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Bold))
        self.pbtn_exit = QtWid.QPushButton("Exit")
        self.pbtn_exit.clicked.connect(self.close)
        self.pbtn_exit.setMinimumHeight(30)

        grid_top = QtWid.QGridLayout()
        grid_top.addWidget(self.lbl_title, 0, 0)
        grid_top.addWidget(self.pbtn_exit, 0, 1, QtCore.Qt.AlignRight)

        # Traverse schematic image
        lbl_trav_img = QtWid.QLabel()
        lbl_trav_img.setPixmap(QtGui.QPixmap(str(Path(sys.modules[__name__].__file__).parent) + "/Traverse_layout.png"))
        lbl_trav_img.setFixedSize(244, 240)

        grid = QtWid.QGridLayout()
        grid.addWidget(lbl_trav_img, 0, 0, QtCore.Qt.AlignTop)

        grpb_trav_img = QtWid.QGroupBox("Traverse schematic")
        grpb_trav_img.setStyleSheet(SS_GROUP)
        grpb_trav_img.setLayout(grid)

        # Round up full window
        vbox = QtWid.QVBoxLayout()
        vbox.addWidget(grpb_trav_img)
        vbox.addWidget(trav_step_nav.grpb)
        vbox.addStretch(1)
        vbox.setAlignment(trav_step_nav.grpb, QtCore.Qt.AlignLeft)

        hbox = QtWid.QHBoxLayout()
        hbox.addWidget(trav_vert_qdev.qgrp)
        hbox.addWidget(trav_horz_qdev.qgrp)
        hbox.addLayout(vbox)
        hbox.addStretch(1)
        hbox.setAlignment(trav_horz_qdev.qgrp, QtCore.Qt.AlignTop)
        hbox.setAlignment(trav_vert_qdev.qgrp, QtCore.Qt.AlignTop)

        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(grid_top)
        vbox.addLayout(hbox)

# ------------------------------------------------------------------------------
#   Act on step signals
# ------------------------------------------------------------------------------

@QtCore.pyqtSlot()
def act_upon_signal_step_up(new_pos: float):
    trav_vert_qdev.qled_new_pos.setText("%.2f" % new_pos)
    trav_vert_qdev.process_pbtn_move_to_new_pos()

@QtCore.pyqtSlot()
def act_upon_signal_step_down(new_pos: float):
    trav_vert_qdev.qled_new_pos.setText("%.2f" % new_pos)
    trav_vert_qdev.process_pbtn_move_to_new_pos()

@QtCore.pyqtSlot()
def act_upon_signal_step_left(new_pos: float):
    trav_horz_qdev.qled_new_pos.setText("%.2f" % new_pos)
    trav_horz_qdev.process_pbtn_move_to_new_pos()

@QtCore.pyqtSlot()
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
        try: trav.close()
        except: pass

# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == '__main__':

    # Specific connection settings of each traverse axis of our setup
    class Trav_connection_params():
        # Serial number of the Compax3 traverse controller to connect to.
        # Set to '' or None to connect to any Compax3.
        serial = None
        # Display name
        name = "TRAV"
        # Path to the config textfile containing the (last used) RS232 port
        path_config = Path("config/port_Compax3_trav.txt")

    # Horizontal axis
    trav_conn_horz = Trav_connection_params()
    trav_conn_horz.serial = "4409980001"
    trav_conn_horz.name   = "TRAV HORZ"
    trav_conn_horz.path_config = Path("config/port_Compax3_trav_horz.txt")

    # Vertical axis
    trav_conn_vert = Trav_connection_params()
    trav_conn_vert.serial = "4319370001"
    trav_conn_vert.name   = "TRAV VERT"
    trav_conn_vert.path_config = Path("config/port_Compax3_trav_vert.txt")

    # The state of the traverse controllers is polled with this time interval
    UPDATE_INTERVAL_MS = 250   # [ms]

    # --------------------------------------------------------------------------
    #   Connect to and set up Compax3 traverse controllers
    # --------------------------------------------------------------------------

    trav_horz = Compax3_servo(name=trav_conn_horz.name)
    trav_vert = Compax3_servo(name=trav_conn_vert.name)

    if trav_horz.auto_connect(trav_conn_horz.path_config,
                              trav_conn_horz.serial):
        trav_horz.begin()

        # Set the default motion profile (= #2) parameters
        trav_horz.store_motion_profile(target_position=0,
                                       velocity=10,
                                       mode=1,
                                       accel=100,
                                       decel=100,
                                       jerk=1e6,
                                       profile_number=2)

    if trav_vert.auto_connect(trav_conn_vert.path_config,
                              trav_conn_vert.serial):
        trav_vert.begin()

        # Set the default motion profile (= #2) parameters
        trav_vert.store_motion_profile(target_position=0,
                                       velocity=10,
                                       mode=1,
                                       accel=100,
                                       decel=100,
                                       jerk=1e6,
                                       profile_number=2)

    travs = [trav_horz, trav_vert]

    # --------------------------------------------------------------------------
    #   Create application
    # --------------------------------------------------------------------------
    QtCore.QThread.currentThread().setObjectName('MAIN')    # For DEBUG info

    app = 0    # Work-around for kernel crash when using Spyder IDE
    app = QtWid.QApplication(sys.argv)
    app.setFont(QtGui.QFont("Arial", 9))
    app.setStyleSheet(SS_TEXTBOX_READ_ONLY)
    app.aboutToQuit.connect(about_to_quit)

    # Create PyQt GUI interfaces and communication threads for the device
    trav_horz_qdev = Compax3_servo_qdev(trav_horz, UPDATE_INTERVAL_MS)

    trav_vert_qdev = Compax3_servo_qdev(trav_vert, UPDATE_INTERVAL_MS)

    travs_qdev = [trav_horz_qdev, trav_vert_qdev]

    # Create Compax3 single step navigator
    trav_step_nav = Compax3_step_navigator(
                        trav_horz=trav_horz, trav_vert=trav_vert)
    trav_step_nav.step_up.connect(act_upon_signal_step_up)
    trav_step_nav.step_down.connect(act_upon_signal_step_down)
    trav_step_nav.step_left.connect(act_upon_signal_step_left)
    trav_step_nav.step_right.connect(act_upon_signal_step_right)

    # For DEBUG info
    trav_horz_qdev.worker_DAQ.debug_color  = ANSI.YELLOW
    trav_horz_qdev.worker_jobs.debug_color = ANSI.CYAN
    trav_vert_qdev.worker_DAQ.debug_color  = ANSI.YELLOW
    trav_vert_qdev.worker_jobs.debug_color = ANSI.CYAN

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
    sys.exit(app.exec_())
