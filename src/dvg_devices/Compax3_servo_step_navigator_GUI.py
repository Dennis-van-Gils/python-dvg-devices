#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt/PySide module to provide two-axis single-step navigation for two Compax3
traverse controllers. The user can hit the arrow keys on the keyboard for
moving in steps.

Will emit pyqtSignals 'step_up', 'step_down', 'step_left' and 'step_right'
whenever an arrow button is clicked in the GUI or an arrow key is pressed on the
keyboard. Connect to these signals in your own application to act upon it.

No communication with a Compax3 servo controller will take place inside this
module. It will only read out the software state. Pure GUI.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "28-10-2022"
__version__ = "1.0.0"
# pylint: disable=try-except-raise

import os
import sys

# Mechanism to support both PyQt and PySide
# -----------------------------------------

PYQT5 = "PyQt5"
PYQT6 = "PyQt6"
PYSIDE2 = "PySide2"
PYSIDE6 = "PySide6"
QT_LIB_ORDER = [PYQT5, PYSIDE2, PYSIDE6, PYQT6]
QT_LIB = None

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
    from PyQt5.QtCore import pyqtSignal as Signal          # type: ignore
elif QT_LIB == PYQT6:
    from PyQt6 import QtCore, QtGui, QtWidgets as QtWid    # type: ignore
    from PyQt6.QtCore import pyqtSlot as Slot              # type: ignore
    from PyQt6.QtCore import pyqtSignal as Signal          # type: ignore
elif QT_LIB == PYSIDE2:
    from PySide2 import QtCore, QtGui, QtWidgets as QtWid  # type: ignore
    from PySide2.QtCore import Slot                        # type: ignore
    from PySide2.QtCore import Signal                      # type: ignore
elif QT_LIB == PYSIDE6:
    from PySide6 import QtCore, QtGui, QtWidgets as QtWid  # type: ignore
    from PySide6.QtCore import Slot                        # type: ignore
    from PySide6.QtCore import Signal                      # type: ignore
# pylint: enable=import-error, no-name-in-module
# fmt: on

# \end[Mechanism to support both PyQt and PySide]
# -----------------------------------------------

import numpy as np

from dvg_debug_functions import print_fancy_traceback as pft
from dvg_pyqt_controls import create_Toggle_button, SS_GROUP

from dvg_devices.Compax3_servo_protocol_RS232 import Compax3_servo


class Compax3_step_navigator(QtWid.QWidget):
    # fmt: off
    step_up    = Signal(float)
    step_down  = Signal(float)
    step_left  = Signal(float)
    step_right = Signal(float)
    # fmt: on

    def __init__(
        self,
        trav_horz: Compax3_servo = None,
        trav_vert: Compax3_servo = None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        if not (isinstance(trav_horz, Compax3_servo) or trav_horz is None):
            pft("Argument 'trav_horz' is of a wrong type.", 3)
            sys.exit(1)
        if not (isinstance(trav_vert, Compax3_servo) or trav_vert is None):
            pft("Argument 'trav_vert' is of a wrong type.", 3)
            sys.exit(1)

        self.listening_to_arrow_keys = False
        self.trav_horz = trav_horz
        self.trav_vert = trav_vert
        self.horz_pos = np.nan  # [mm]
        self.vert_pos = np.nan  # [mm]
        self.step_size = np.nan  # [mm]

        self.create_GUI()
        self.connect_signals_to_slots()
        self.process_editingFinished_qled_step_size()

    def create_GUI(self):
        self.pbtn_step_activate = create_Toggle_button("Disabled")
        self.qled_step_size = QtWid.QLineEdit(
            "1.0", alignment=QtCore.Qt.AlignmentFlag.AlignRight
        )
        self.qled_step_size.setFixedWidth(70)

        grid_sub = QtWid.QGridLayout()
        grid_sub.addWidget(self.pbtn_step_activate, 0, 0, 1, 3)
        grid_sub.addWidget(QtWid.QLabel("Step size"), 1, 0)
        grid_sub.addWidget(self.qled_step_size, 1, 1)
        grid_sub.addWidget(QtWid.QLabel("mm"), 1, 2)

        font_1 = QtGui.QFont("Arial", 20)
        font_2 = QtGui.QFont("Arial", 30)
        p1 = {"font": font_1, "enabled": False}
        p2 = {"font": font_2, "enabled": False}
        self.pbtn_step_up = QtWid.QPushButton(chr(0x25B2), **p1)
        self.pbtn_step_up.setFixedSize(50, 50)
        self.pbtn_step_down = QtWid.QPushButton(chr(0x25BC), **p1)
        self.pbtn_step_down.setFixedSize(50, 50)
        self.pbtn_step_left = QtWid.QPushButton(chr(0x25C0), **p2)
        self.pbtn_step_left.setFixedSize(50, 50)
        self.pbtn_step_right = QtWid.QPushButton(chr(0x25B6), **p2)
        self.pbtn_step_right.setFixedSize(50, 50)

        self.pted_focus_trap = QtWid.QPlainTextEdit("", enabled=False)
        self.pted_focus_trap.setFixedSize(0, 0)

        # fmt: off
        grid = QtWid.QGridLayout()
        grid.addLayout(grid_sub               , 0, 0, 1, 4)
        grid.addItem(QtWid.QSpacerItem(1, 12) , 1, 0)
        grid.addWidget(self.pbtn_step_up      , 2, 1, QtCore.Qt.AlignmentFlag.AlignHCenter)
        grid.addWidget(self.pbtn_step_left    , 3, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)
        grid.addWidget(self.pbtn_step_right   , 3, 2, QtCore.Qt.AlignmentFlag.AlignHCenter)
        grid.addWidget(self.pbtn_step_down    , 4, 1, QtCore.Qt.AlignmentFlag.AlignHCenter)
        grid.addWidget(self.pted_focus_trap   , 5, 1, QtCore.Qt.AlignmentFlag.AlignHCenter)
        # fmt: on

        self.grpb = QtWid.QGroupBox("Move single step")
        self.grpb.eventFilter = self.eventFilter
        self.grpb.installEventFilter(self.grpb)
        self.grpb.setStyleSheet(SS_GROUP)
        self.grpb.setLayout(grid)

    def eventFilter(self, obj, event):
        if self.listening_to_arrow_keys:
            if (
                event.type() == QtCore.QEvent.Type.KeyRelease
            ) and not event.isAutoRepeat():
                if event.key() == QtCore.Qt.Key.Key_Up:
                    print("up")
                    self.process_step_up()
                    self.pted_focus_trap.setFocus()
                    event.ignore()
                    return True

                if event.key() == QtCore.Qt.Key.Key_Down:
                    print("down")
                    self.process_step_down()
                    self.pted_focus_trap.setFocus()
                    event.ignore()
                    return True

                if event.key() == QtCore.Qt.Key.Key_Left:
                    print("left")
                    self.process_step_left()
                    self.pted_focus_trap.setFocus()
                    event.ignore()
                    return True

                if event.key() == QtCore.Qt.Key.Key_Right:
                    print("right")
                    self.process_step_right()
                    self.pted_focus_trap.setFocus()
                    event.ignore()
                    return True

        return super().eventFilter(obj, event)

    @Slot()
    def process_pbtn_step_activate(self):
        if self.pbtn_step_activate.isChecked():
            self.listening_to_arrow_keys = True
            self.pbtn_step_activate.setText("Enabled")
            self.pbtn_step_up.setEnabled(True)
            self.pbtn_step_down.setEnabled(True)
            self.pbtn_step_left.setEnabled(True)
            self.pbtn_step_right.setEnabled(True)
            self.pted_focus_trap.setEnabled(True)
            self.qled_step_size.setReadOnly(True)

            self.pted_focus_trap.setFocus()

            if self.trav_horz is not None:
                self.horz_pos = float("%.2f" % self.trav_horz.state.cur_pos)
            if self.trav_vert is not None:
                self.vert_pos = float("%.2f" % self.trav_vert.state.cur_pos)
        else:
            self.pbtn_step_activate.setText("Disabled")
            self.listening_to_arrow_keys = False
            self.pbtn_step_up.setEnabled(False)
            self.pbtn_step_down.setEnabled(False)
            self.pbtn_step_left.setEnabled(False)
            self.pbtn_step_right.setEnabled(False)
            self.pted_focus_trap.setEnabled(False)
            self.qled_step_size.setReadOnly(False)

    @Slot()
    def process_editingFinished_qled_step_size(self):
        try:
            val = float(self.qled_step_size.text())
        except (TypeError, ValueError):
            val = 0.0
        except:
            raise
        val = max(0.0, val)
        self.qled_step_size.setText("%.2f" % val)
        self.step_size = val

    def connect_signals_to_slots(self):
        self.pbtn_step_activate.clicked.connect(self.process_pbtn_step_activate)
        self.qled_step_size.editingFinished.connect(
            self.process_editingFinished_qled_step_size
        )
        self.pbtn_step_up.clicked.connect(self.process_step_up)
        self.pbtn_step_down.clicked.connect(self.process_step_down)
        self.pbtn_step_left.clicked.connect(self.process_step_left)
        self.pbtn_step_right.clicked.connect(self.process_step_right)

    def process_step_up(self):
        self.vert_pos += self.step_size
        self.step_up.emit(self.vert_pos)

    def process_step_down(self):
        self.vert_pos -= self.step_size
        self.step_down.emit(self.vert_pos)

    def process_step_left(self):
        self.horz_pos -= self.step_size
        self.step_left.emit(self.horz_pos)

    def process_step_right(self):
        self.horz_pos += self.step_size
        self.step_right.emit(self.horz_pos)
