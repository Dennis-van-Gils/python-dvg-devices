#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt/PySide module to provide multithreaded communication and periodical data
acquisition for a Compax3 traverse controller.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "23-05-2024"
__version__ = "1.4.0"
# pylint: disable=missing-function-docstring, multiple-statements

from qtpy import QtCore, QtGui, QtWidgets as QtWid
from qtpy.QtCore import Slot  # type: ignore

import dvg_pyqt_controls as controls
from dvg_qdeviceio import QDeviceIO, DAQ_TRIGGER
from dvg_devices.Compax3_servo_protocol_RS232 import Compax3_servo


class Compax3_servo_qdev(QDeviceIO):
    """Manages multithreaded communication and periodical data acquisition for
    a Compax3 traverse controller, referred to as the 'device'.

    In addition, it also provides PyQt/PySide GUI objects for control of the
    device. These can be incorporated into your application.

    All device I/O operations will be offloaded to 'workers', each running in
    a newly created thread.

    (*): See 'dvg_qdeviceio.QDeviceIO()' for details.

    Args:
        dev:
            Reference to a
            'dvg_devices.Compax3_servo_protocol_RS232.Compax3_servo'
            instance.

        debug:
            Show debug info in terminal? Warning: Slow! Do not leave on
            unintentionally.

    Main GUI objects:
        qgrp (PyQt5.QtWidgets.QGroupBox)
    """

    def __init__(
        self,
        dev: Compax3_servo,
        DAQ_interval_ms=250,
        critical_not_alive_count=1,
        DAQ_timer_type=QtCore.Qt.TimerType.CoarseTimer,
        debug=False,
        **kwargs,
    ):
        super().__init__(dev, **kwargs)  # Pass kwargs onto QtCore.QObject()
        self.dev: Compax3_servo  # Enforce type: removes `_NoDevice()`

        self.create_worker_DAQ(
            DAQ_trigger=DAQ_TRIGGER.INTERNAL_TIMER,
            DAQ_function=self._DAQ_function,
            DAQ_interval_ms=DAQ_interval_ms,
            DAQ_timer_type=DAQ_timer_type,
            critical_not_alive_count=critical_not_alive_count,
            debug=debug,
        )

        self.create_worker_jobs(debug=debug)

        self._create_GUI()
        self._connect_signals_to_slots()
        self.signal_DAQ_updated.connect(self._update_GUI)

        if not self.dev.is_alive:
            self._update_GUI()  # Correctly reflect an offline device

        # Flags for Jog+/Jog- pushbutton control
        self._jog_plus_is_active = False
        self._jog_minus_is_active = False

    # --------------------------------------------------------------------------
    #   _DAQ_function
    # --------------------------------------------------------------------------

    def _DAQ_function(self) -> bool:
        success = self.dev.query_position()
        success &= self.dev.query_status_word_1()

        if not self.dev.status_word_1.no_error:
            self.dev.query_error()

        return success

    # --------------------------------------------------------------------------
    #   _create_GUI
    # --------------------------------------------------------------------------

    def _create_GUI(self):
        default_font_height = 17
        default_font_width = 8

        # Sub-groupbox: Status word 1 bits
        self.sw1_powerless = controls.create_tiny_LED()
        self.sw1_powered_stationary = controls.create_tiny_LED()
        self.sw1_zero_pos_known = controls.create_tiny_LED()
        self.sw1_pos_reached = controls.create_tiny_LED()

        i = 0
        p = {"parent": None, "alignment": QtCore.Qt.AlignmentFlag.AlignRight}
        grid = QtWid.QGridLayout()
        grid.setVerticalSpacing(4)
        # fmt: off
        grid.addWidget(QtWid.QLabel("powerless", **p)         , i, 0)
        grid.addWidget(self.sw1_powerless                     , i, 1); i+=1
        grid.addWidget(QtWid.QLabel("powered stationary", **p), i, 0)
        grid.addWidget(self.sw1_powered_stationary            , i, 1); i+=1
        grid.addWidget(QtWid.QLabel("zero pos. known", **p)   , i, 0)
        grid.addWidget(self.sw1_zero_pos_known                , i, 1); i+=1
        grid.addWidget(QtWid.QLabel("position reached", **p)  , i, 0)
        grid.addWidget(self.sw1_pos_reached                   , i, 1); i+=1
        # fmt: on
        # grid.setColumnStretch(0, 0)
        # grid.setColumnStretch(1, 0)

        self.qgrp_sw1 = QtWid.QGroupBox("Status word 1")
        self.qgrp_sw1.setLayout(grid)

        # Main groupbox
        font_lbl_status = QtGui.QFont(
            "Palatino", 14, weight=QtGui.QFont.Weight.Bold
        )
        self.lbl_status = QtWid.QLabel("OFFLINE")
        self.lbl_status.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setFont(font_lbl_status)
        self.lbl_status.setFixedHeight(
            3 * QtGui.QFontMetrics(font_lbl_status).height()
        )

        self.sw1_error_tripped = controls.create_error_LED(text="No error")
        self.error_msg = QtWid.QPlainTextEdit("")
        self.error_msg.setLineWrapMode(
            QtWid.QPlainTextEdit.LineWrapMode.WidgetWidth
        )
        self.error_msg.setStyleSheet(controls.SS_TEXTBOX_ERRORS)
        self.error_msg.setMinimumWidth(22 * default_font_width)
        self.error_msg.setFixedHeight(4 * default_font_height)
        self.pbtn_ackn_error = QtWid.QPushButton("Acknowledge error")
        p = {"parent": None, "alignment": QtCore.Qt.AlignmentFlag.AlignRight}
        p2 = {**p, "readOnly": True}
        self.qlin_cur_pos = QtWid.QLineEdit("nan", **p2)
        self.qlin_new_pos = QtWid.QLineEdit("nan", **p)
        self.pbtn_move_to_new_pos = QtWid.QPushButton("Move to new position")
        self.pbtn_move_to_new_pos.setFixedHeight(3 * default_font_height)
        self.pbtn_jog_plus = QtWid.QPushButton("Jog +")
        self.pbtn_jog_minus = QtWid.QPushButton("Jog -")
        self.pbtn_stop = QtWid.QPushButton("\nSTOP &&\nREMOVE POWER\n")
        self.lbl_update_counter = QtWid.QLabel("0")

        i = 0
        grid = QtWid.QGridLayout()
        grid.setVerticalSpacing(4)
        # fmt: off
        grid.addWidget(self.lbl_status             , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 12)      , i, 0)      ; i+=1
        grid.addWidget(self.sw1_error_tripped      , i, 0, 1, 3); i+=1
        grid.addWidget(self.error_msg              , i, 0, 1, 3); i+=1
        grid.addWidget(self.pbtn_ackn_error        , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 12)      , i, 0)      ; i+=1
        grid.addWidget(self.qgrp_sw1               , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 12)      , i, 0)      ; i+=1

        grid.addWidget(QtWid.QLabel("Position:")   , i, 0, 1, 3); i+=1
        grid.addWidget(QtWid.QLabel("Current")     , i, 0)
        grid.addWidget(self.qlin_cur_pos           , i, 1)
        grid.addWidget(QtWid.QLabel("mm")          , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("New")         , i, 0)
        grid.addWidget(self.qlin_new_pos           , i, 1)
        grid.addWidget(QtWid.QLabel("mm")          , i, 2)      ; i+=1

        grid.addItem(QtWid.QSpacerItem(1, 12)      , i, 0)      ; i+=1
        grid.addWidget(self.pbtn_move_to_new_pos   , i, 0, 1, 3); i+=1
        grid.addWidget(self.pbtn_jog_plus          , i, 0, 1, 3); i+=1
        grid.addWidget(self.pbtn_jog_minus         , i, 0, 1, 3); i+=1
        grid.addWidget(self.pbtn_stop              , i, 0, 1, 3); i+=1
        grid.addWidget(self.lbl_update_counter     , i, 0, 1, 3); i+=1
        # fmt: on
        # grid.setColumnStretch(0, 0)
        # grid.setColumnStretch(1, 0)
        # grid.setColumnStretch(2, 0)

        self.qgrp = QtWid.QGroupBox(f"{self.dev.name}")
        self.qgrp.setStyleSheet(controls.SS_GROUP)
        self.qgrp.setLayout(grid)
        self.qgrp.setMaximumWidth(200)  # Work-around, hard limit width

    # --------------------------------------------------------------------------
    #   _update_GUI
    # --------------------------------------------------------------------------

    @Slot()
    def _update_GUI(self):
        """NOTE: 'self.dev.mutex' is not being locked, because we are only
        reading 'state' for displaying purposes. We can do this because 'state'
        members are written and read atomicly.
        Not locking the mutex might speed up the program.
        """
        SW = self.dev.status_word_1  # Shorthand
        if self.dev.is_alive:
            # At startup
            if self.update_counter_DAQ == 1:
                self.qlin_new_pos.setText(f"{self.dev.state.cur_pos:.2f}")

            if SW.powerless:
                self.lbl_status.setText("powerless")
            else:
                if SW.powered_stationary:
                    self.lbl_status.setText("POWERED\nstationary")
                else:
                    self.lbl_status.setText("POWERED")

            self.sw1_error_tripped.setChecked(not SW.no_error)
            if SW.no_error:
                self.sw1_error_tripped.setText("No error")
                self.error_msg.setPlainText("")
                self.error_msg.setReadOnly(False)
                self.error_msg.setStyleSheet(controls.SS_TEXTBOX_ERRORS)
            else:
                self.sw1_error_tripped.setText("ERROR TRIPPED")
                self.error_msg.setPlainText(self.dev.state.error_msg)
                self.error_msg.setReadOnly(True)
                self.error_msg.setStyleSheet(controls.SS_TEXTBOX_ERRORS)
            self.sw1_powerless.setChecked(bool(SW.powerless))
            self.sw1_powered_stationary.setChecked(bool(SW.powered_stationary))
            self.sw1_zero_pos_known.setChecked(bool(SW.zero_pos_known))
            self.sw1_pos_reached.setChecked(bool(SW.pos_reached))
            self.qlin_cur_pos.setText(f"{self.dev.state.cur_pos:.2f}")

            self.lbl_update_counter.setText(f"{self.update_counter_DAQ}")
        else:
            self.qgrp.setEnabled(False)

    # --------------------------------------------------------------------------
    #   GUI functions
    # --------------------------------------------------------------------------

    @Slot()
    def process_pbtn_ackn_error(self):
        self.send(self.dev.acknowledge_error)

    @Slot()
    def process_editingFinished_qlin_new_pos(self):
        try:
            new_pos = float(self.qlin_new_pos.text())
        except (TypeError, ValueError):
            new_pos = 0.0
        except Exception as e:
            raise e
        self.qlin_new_pos.setText(f"{new_pos:.2f}")

    @Slot()
    def process_pbtn_move_to_new_pos(self):
        # Double check if the value in the QLineEdit is actually numeric
        try:
            new_pos = float(self.qlin_new_pos.text())
        except Exception as e:
            raise e
        self.send(self.dev.move_to_target_position, (new_pos, 2))

    @Slot()
    def process_pbtn_jog_plus_pressed(self):
        if not self._jog_plus_is_active:
            self._jog_plus_is_active = True
            self.send(self.dev.jog_plus)

    @Slot()
    def process_pbtn_jog_plus_released(self):
        self._jog_plus_is_active = False
        self.send(self.dev.stop_motion_but_keep_power)

    @Slot()
    def process_pbtn_jog_minus_pressed(self):
        if not self._jog_minus_is_active:
            self._jog_minus_is_active = True
            self.send(self.dev.jog_minus)

    @Slot()
    def process_pbtn_jog_minus_released(self):
        self._jog_minus_is_active = False
        self.send(self.dev.stop_motion_but_keep_power)

    @Slot()
    def process_pbtn_stop(self):
        self.send(self.dev.stop_motion_and_remove_power)

    # --------------------------------------------------------------------------
    #   _connect_signals_to_slots
    # --------------------------------------------------------------------------

    def _connect_signals_to_slots(self):
        # self.send_setpoint.editingFinished.connect(
        #        self.send_setpoint_from_textbox)

        self.pbtn_ackn_error.clicked.connect(self.process_pbtn_ackn_error)
        self.qlin_new_pos.editingFinished.connect(
            self.process_editingFinished_qlin_new_pos
        )
        self.pbtn_move_to_new_pos.clicked.connect(
            self.process_pbtn_move_to_new_pos
        )
        # self.pbtn_debug.clicked.connect(self.process_pbtn_debug)
        self.pbtn_jog_plus.pressed.connect(self.process_pbtn_jog_plus_pressed)
        self.pbtn_jog_plus.released.connect(self.process_pbtn_jog_plus_released)
        self.pbtn_jog_minus.pressed.connect(self.process_pbtn_jog_minus_pressed)
        self.pbtn_jog_minus.released.connect(
            self.process_pbtn_jog_minus_released
        )
        self.pbtn_stop.clicked.connect(self.process_pbtn_stop)
