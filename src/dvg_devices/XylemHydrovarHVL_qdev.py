#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt/Pyside module to provide multithreaded communication and periodical data
acquisition for a Xylem Hydrovar HVL variable speed pump controller.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "23-05-2024"
__version__ = "1.5.0"
# pylint: disable=broad-except, missing-function-docstring, multiple-statements

import time
from enum import IntEnum

from qtpy import QtCore, QtWidgets as QtWid
from qtpy.QtCore import Signal, Slot  # type: ignore

from dvg_debug_functions import dprint, print_fancy_traceback as pft
import dvg_pyqt_controls as controls
from dvg_qdeviceio import QDeviceIO, DAQ_TRIGGER
from dvg_devices.XylemHydrovarHVL_protocol_RTU import XylemHydrovarHVL, HVL_Mode


# Enumeration
class GUI_input_fields(IntEnum):
    ALL = 0
    P_WANTED = 1
    F_WANTED = 2
    HVL_MODE = 3


class XylemHydrovarHVL_qdev(QDeviceIO):
    """Manages multithreaded communication and periodical data acquisition for
    a Xylem Hydrovar HVL variable speed drive (VSD) controller.

    In addition, it also provides PyQt/PySide GUI objects for control of the
    device. These can be incorporated into your application.

    All device I/O operations will be offloaded to 'workers', each running in
    a newly created thread.

    (*): See 'dvg_qdeviceio.QDeviceIO()' for details.

    Args:
        dev:
            Reference to a 'XylemHydrovarHVL_protocol_RTU.XylemHydrovarHVL'
            instance.

        debug:
            Show debug info in terminal? Warning: Slow! Do not leave on
            unintentionally.

    Main GUI objects:
        qgrp_control (PyQt5.QtWidgets.QGroupBox)
        qgrp_inverter (PyQt5.QtWidgets.QGroupBox)
        qgrp_error_status (PyQt5.QtWidgets.QGroupBox)
    """

    signal_GUI_input_field_update = Signal(int)
    signal_pump_just_stopped_and_reached_standstill = Signal()

    def __init__(
        self,
        dev: XylemHydrovarHVL,
        DAQ_trigger=DAQ_TRIGGER.INTERNAL_TIMER,
        DAQ_interval_ms=200,
        DAQ_timer_type=QtCore.Qt.TimerType.PreciseTimer,
        critical_not_alive_count=3,
        debug=False,
        **kwargs,
    ):
        super().__init__(dev, **kwargs)  # Pass kwargs onto QtCore.QObject()
        self.dev: XylemHydrovarHVL  # Enforce type: removes `_NoDevice()`

        self.create_worker_DAQ(
            DAQ_trigger=DAQ_trigger,
            DAQ_function=self._DAQ_function,
            DAQ_interval_ms=DAQ_interval_ms,
            DAQ_timer_type=DAQ_timer_type,
            critical_not_alive_count=critical_not_alive_count,
            debug=debug,
        )
        self.create_worker_jobs(jobs_function=self._jobs_function, debug=debug)

        self._create_GUI()
        self.signal_DAQ_updated.connect(self._update_GUI)
        self.signal_connection_lost.connect(self._update_GUI)
        self.signal_GUI_input_field_update.connect(self._update_GUI_input_field)

        self._update_GUI()
        self._update_GUI_input_field()

        # Mechanism to detect that the pump has received a stop command and has
        # reached full standstill.
        # ----------------------------------------------------------------------
        # Below flag is True as soon as the `pump stop` command is send. It will
        # reset to False as soon as full standstill is achieved, after which
        # signal `signal_pump_just_stopped_and_reached_standstill` will be
        # emitted.
        self.pump_is_stopping = False

    # --------------------------------------------------------------------------
    #   _DAQ_function
    # --------------------------------------------------------------------------

    def _DAQ_function(self) -> bool:
        """Every DAQ time step, read the following:
        - error status
        - device status
        - actual pressure
        - actual inverter frequency

        Every N'th DAQ time step, read the following:
        - inverter diagnostics
        """
        DEBUG_local = False
        if DEBUG_local:
            tick = time.perf_counter()

        success = self.dev.read_error_status()
        success &= self.dev.read_device_status()
        success &= self.dev.read_actual_pressure()
        success &= self.dev.read_actual_frequency()

        if (self.update_counter_DAQ % 5) == 0:
            success &= self.dev.read_inverter_diagnostics()

        if self.pump_is_stopping:
            if self.dev.state.pump_is_running:
                # Pump is still coasting down
                pass
            else:
                # Reached standstill
                self.pump_is_stopping = False
                self.signal_pump_just_stopped_and_reached_standstill.emit()
                print("Pump reached standstill")

        if not success:
            return False

        if DEBUG_local:
            tock = time.perf_counter()
            dprint(f"{self.dev.name}: done in {tock - tick:.3f}")

        return True

    # --------------------------------------------------------------------------
    #   _jobs_function
    # --------------------------------------------------------------------------

    def _jobs_function(self, func, args):
        if func == "signal_GUI_input_field_update":
            # Special instruction
            self.signal_GUI_input_field_update.emit(*args)
        else:
            # Default job processing:
            # Send I/O operation to the device
            try:
                func(*args)
            except Exception as err:
                pft(err)

    # --------------------------------------------------------------------------
    #   _create_GUI
    # --------------------------------------------------------------------------

    def _create_GUI(self):
        p = {
            "alignment": QtCore.Qt.AlignmentFlag.AlignRight,
            "minimumWidth": controls.e8(8),
            "maximumWidth": controls.e8(8),
        }
        p2 = {**p, "readOnly": True}

        # Pump control
        self.pbtn_pump_onoff = controls.create_Toggle_button("OFFLINE")
        self.indicator_pump_running = controls.create_tiny_LED()
        self.rbtn_mode_pressure = QtWid.QRadioButton("Regulate pressure")
        self.rbtn_mode_frequency = QtWid.QRadioButton("Fixed frequency")
        self.qled_P_wanted = QtWid.QLineEdit("nan", **p)
        self.qled_P_actual = QtWid.QLineEdit("nan", **p2)
        self.qled_P_limits = QtWid.QLineEdit(
            f"0 \u2013 {self.dev.max_pressure_setpoint_bar:.2f}", **p2
        )
        self.qled_f_wanted = QtWid.QLineEdit("nan", **p)
        self.qled_f_actual = QtWid.QLineEdit("nan", **p2)
        self.qled_f_limits = QtWid.QLineEdit(
            f"{self.dev.state.min_frequency:.0f} \u2013 "
            f"{self.dev.state.max_frequency:.0f}",
            **p2,
        )
        self.qlbl_update_counter = QtWid.QLabel("0")

        self.pbtn_pump_onoff.clicked.connect(self._process_pbtn_pump_onoff)
        self.rbtn_mode_pressure.clicked.connect(self._process_rbtn_mode)
        self.rbtn_mode_frequency.clicked.connect(self._process_rbtn_mode)
        self.qled_P_wanted.editingFinished.connect(
            self._send_P_wanted_from_textbox
        )
        self.qled_f_wanted.editingFinished.connect(
            self._send_f_wanted_from_textbox
        )

        # fmt: off
        i = 0
        grid = QtWid.QGridLayout()
        grid.setVerticalSpacing(4)

        grid.addWidget(self.pbtn_pump_onoff            , i, 0, 1, 3); i+=1
        grid.addWidget(QtWid.QLabel("Pump running?")   , i, 0, 1, 2)
        grid.addWidget(self.indicator_pump_running     , i, 2)      ; i+=1
        grid.addItem(QtWid.QSpacerItem(1, 10)          , i, 0)      ; i+=1

        grid.addWidget(QtWid.QLabel("<b>Mode</b>")     , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)           , i, 0)      ; i+=1
        grid.addWidget(self.rbtn_mode_pressure         , i, 0, 1, 3); i+=1
        grid.addWidget(self.rbtn_mode_frequency        , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 10)          , i, 0)      ; i+=1

        grid.addWidget(QtWid.QLabel("<b>Pressure</b>") , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)           , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Wanted")          , i, 0)
        grid.addWidget(self.qled_P_wanted              , i, 1)
        grid.addWidget(QtWid.QLabel("bar")             , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("Actual")          , i, 0)
        grid.addWidget(self.qled_P_actual              , i, 1)
        grid.addWidget(QtWid.QLabel("bar")             , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("Limits")          , i, 0)
        grid.addWidget(self.qled_P_limits              , i, 1)
        grid.addWidget(QtWid.QLabel("bar")             , i, 2)      ; i+=1
        grid.addItem(QtWid.QSpacerItem(1, 10)          , i, 0)      ; i+=1

        grid.addWidget(QtWid.QLabel("<b>Frequency</b>"), i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)           , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Wanted")          , i, 0)
        grid.addWidget(self.qled_f_wanted              , i, 1)
        grid.addWidget(QtWid.QLabel("Hz")              , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("Actual")          , i, 0)
        grid.addWidget(self.qled_f_actual              , i, 1)
        grid.addWidget(QtWid.QLabel("Hz")              , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("Limits")          , i, 0)
        grid.addWidget(self.qled_f_limits              , i, 1)
        grid.addWidget(QtWid.QLabel("Hz")              , i, 2)      ; i+=1
        grid.addItem(QtWid.QSpacerItem(1, 10)          , i, 0)      ; i+=1
        grid.addWidget(self.qlbl_update_counter        , i, 0)
        # fmt: on

        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 1)
        grid.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        self.qgrp_control = QtWid.QGroupBox("Pump control")
        self.qgrp_control.setLayout(grid)

        # Inverter diagnostics
        self.qled_inverter_temp = QtWid.QLineEdit("nan", **p2)
        self.qled_inverter_curr_A = QtWid.QLineEdit("nan", **p2)
        self.qled_inverter_curr_pct = QtWid.QLineEdit("nan", **p2)
        self.qled_inverter_volt = QtWid.QLineEdit("nan", **p2)

        # fmt: off
        i = 0
        grid = QtWid.QGridLayout()
        grid.setVerticalSpacing(4)

        grid.addWidget(QtWid.QLabel("Temp.")           , i, 0)
        grid.addWidget(self.qled_inverter_temp         , i, 1)
        grid.addWidget(QtWid.QLabel("\u00b0C")         , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("Voltage")         , i, 0)
        grid.addWidget(self.qled_inverter_volt         , i, 1)
        grid.addWidget(QtWid.QLabel("V")               , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("Current")         , i, 0)
        grid.addWidget(self.qled_inverter_curr_A       , i, 1)
        grid.addWidget(QtWid.QLabel("A")               , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("Current")         , i, 0)
        grid.addWidget(self.qled_inverter_curr_pct     , i, 1)
        grid.addWidget(QtWid.QLabel("%")               , i, 2)      ; i+=1
        # fmt: on

        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 1)
        grid.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        self.qgrp_inverter = QtWid.QGroupBox("Inverter")
        self.qgrp_inverter.setLayout(grid)

        # Error status
        self.qpte_error_status = QtWid.QPlainTextEdit()
        self.qpte_error_status.setStyleSheet(controls.SS_TEXTBOX_ERRORS)

        grid = QtWid.QGridLayout()
        grid.setVerticalSpacing(4)
        grid.addWidget(self.qpte_error_status, 0, 0)
        grid.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        self.qgrp_error_status = QtWid.QGroupBox("Error status")
        self.qgrp_error_status.setLayout(grid)

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

        if not self.dev.is_alive:
            self.qgrp_control.setEnabled(False)
            self.qgrp_inverter.setEnabled(False)
            self.qgrp_error_status.setEnabled(False)
            self.pbtn_pump_onoff.setText("OFFLINE")
            return

        # Shorthand
        state = self.dev.state
        error_status = self.dev.error_status

        # Pump control
        if state.pump_is_enabled:
            self.pbtn_pump_onoff.setEnabled(True)
            if state.pump_is_on:
                self.pbtn_pump_onoff.setChecked(True)
                self.pbtn_pump_onoff.setText("Pump is ON")
            else:
                self.pbtn_pump_onoff.setChecked(False)
                self.pbtn_pump_onoff.setText("Pump is OFF")
        else:
            self.pbtn_pump_onoff.setEnabled(False)
            self.pbtn_pump_onoff.setChecked(False)
            self.pbtn_pump_onoff.setText("Pump is DISABLED")

        self.indicator_pump_running.setChecked(state.pump_is_running)
        self.qled_P_actual.setText(f"{state.actual_pressure:.2f}")
        self.qled_f_actual.setText(f"{state.actual_frequency:.1f}")

        # Inverter diagnostics
        self.qled_inverter_temp.setText(f"{state.inverter_temp:.0f}")
        self.qled_inverter_volt.setText(f"{state.inverter_volt:.0f}")
        self.qled_inverter_curr_A.setText(f"{state.inverter_curr_A:.2f}")
        self.qled_inverter_curr_pct.setText(f"{state.inverter_curr_pct:.0f}")

        # Error status
        if error_status.has_error():
            error_text = ""
            if error_status.overcurrent:
                error_text += "#11: OVERCURRENT\n"
            if error_status.overload:
                error_text += "#12: OVERLOAD"
            if error_status.overvoltage:
                error_text += "#13: OVERVOLTAGE"
            if error_status.phase_loss:
                error_text += "#16: PHASE LOSS"
            if error_status.inverter_overheat:
                error_text += "#14: INVERTER OVERHEAT"
            if error_status.motor_overheat:
                error_text += "#15: MOTOR OVERHEAT"
            if error_status.lack_of_water:
                error_text += "#21: LACK OF WATER"
            if error_status.minimum_threshold:
                error_text += "#22: MINIMUM THRESHOLD"
            if error_status.act_val_sensor_1:
                error_text += "#23: ACT VAL SENSOR 1"
            if error_status.act_val_sensor_2:
                error_text += "#24: ACT VAL SENSOR 2"
            if error_status.setpoint_1_low_mA:
                error_text += "#25: SETPOINT 1 I<4 mA"
            if error_status.setpoint_2_low_mA:
                error_text += "#26: SETPOINT 2 I<4 mA"
            self.qpte_error_status.setReadOnly(True)
            self.qpte_error_status.setPlainText(error_text)
        else:
            if self.dev.device_status.device_has_a_warning:
                self.qpte_error_status.setReadOnly(True)
                self.qpte_error_status.setPlainText("WARNING!!!")
            else:
                self.qpte_error_status.setReadOnly(False)
                self.qpte_error_status.setPlainText("No errors")

        # Update counter
        self.qlbl_update_counter.setText(f"{self.update_counter_DAQ}")

    # --------------------------------------------------------------------------
    #   _update_GUI_input_field
    # --------------------------------------------------------------------------

    @Slot()
    @Slot(int)
    def _update_GUI_input_field(self, GUI_input_field=GUI_input_fields.ALL):
        if GUI_input_field == GUI_input_fields.P_WANTED:
            self.qled_P_wanted.setText(f"{self.dev.state.wanted_pressure:.2f}")

        elif GUI_input_field == GUI_input_fields.F_WANTED:
            self.qled_f_wanted.setText(f"{self.dev.state.wanted_frequency:.1f}")

        elif GUI_input_field == GUI_input_fields.HVL_MODE:
            if self.dev.state.hvl_mode == HVL_Mode.CONTROLLER:
                self.rbtn_mode_pressure.setChecked(True)
            if self.dev.state.hvl_mode == HVL_Mode.ACTUATOR:
                self.rbtn_mode_frequency.setChecked(True)

        else:
            self.qled_P_wanted.setText(f"{self.dev.state.wanted_pressure:.2f}")
            self.qled_f_wanted.setText(f"{self.dev.state.wanted_frequency:.1f}")
            if self.dev.state.hvl_mode == HVL_Mode.CONTROLLER:
                self.rbtn_mode_pressure.setChecked(True)
            if self.dev.state.hvl_mode == HVL_Mode.ACTUATOR:
                self.rbtn_mode_frequency.setChecked(True)

    # --------------------------------------------------------------------------
    #   GUI functions
    # --------------------------------------------------------------------------

    @Slot()
    def _process_pbtn_pump_onoff(self):
        if self.dev.state.pump_is_on:
            self.send_pump_stop()
        else:
            self.send_pump_start()

    @Slot()
    def _send_P_wanted_from_textbox(self):
        try:
            P_bar = float(self.qled_P_wanted.text())
        except (TypeError, ValueError):
            P_bar = 0.0
        except Exception as err:
            raise err

        self.add_to_jobs_queue(self.dev.set_wanted_pressure, P_bar)
        self.add_to_jobs_queue(
            "signal_GUI_input_field_update", GUI_input_fields.P_WANTED
        )
        self.process_jobs_queue()

    @Slot()
    def _send_f_wanted_from_textbox(self):
        try:
            f_Hz = float(self.qled_f_wanted.text())
        except (TypeError, ValueError):
            f_Hz = self.dev.state.min_frequency
        except Exception as err:
            raise err

        self.add_to_jobs_queue(self.dev.set_wanted_frequency, f_Hz)
        self.add_to_jobs_queue(
            "signal_GUI_input_field_update", GUI_input_fields.F_WANTED
        )
        self.process_jobs_queue()

    @Slot()
    def _process_rbtn_mode(self):
        # Very elaborate logic scheme here, but necessary to have the
        # confirmation dialog work all right.

        # Figure out the request
        if self.rbtn_mode_pressure.isChecked():
            reqs_mode = HVL_Mode.CONTROLLER
            reqs_mode_str = "regulate pressure"
        else:
            reqs_mode = HVL_Mode.ACTUATOR
            reqs_mode_str = "fixed frequency"

        if self.dev.state.hvl_mode == reqs_mode:
            # Actually no change requested
            return

        # Ask user to confirm request
        reply = QtWid.QMessageBox.question(
            self.qgrp_control,
            "Confirm mode change",
            f"Change the mode to `{reqs_mode_str}`?",
            QtWid.QMessageBox.StandardButton.Yes
            | QtWid.QMessageBox.StandardButton.No,
        )

        # Canceled by user
        if reply == QtWid.QMessageBox.StandardButton.No:
            self.rbtn_mode_pressure.setChecked(
                self.dev.state.hvl_mode == HVL_Mode.CONTROLLER
            )
            self.rbtn_mode_frequency.setChecked(
                self.dev.state.hvl_mode == HVL_Mode.ACTUATOR
            )
            return

        # Eager mode change
        self.dev.state.hvl_mode = reqs_mode

        # Send and confirm mode change coming back from the pump
        self.add_to_jobs_queue(self.dev.set_hvl_mode, reqs_mode)
        self.add_to_jobs_queue(
            "signal_GUI_input_field_update", GUI_input_fields.HVL_MODE
        )
        self.process_jobs_queue()

    # --------------------------------------------------------------------------
    #   Worker communication functions
    # --------------------------------------------------------------------------

    @Slot()
    def send_pump_start(self):
        """Schedule a 'pump start' as soon as possible."""
        self.send(self.dev.pump_start)

        # React as fast as possible
        QtWid.QApplication.processEvents()

    @Slot()
    def send_pump_stop(self):
        """Schedule a 'pump stop' as soon as possible."""
        self.send(self.dev.pump_stop)
        self.pump_is_stopping = True

        # React as fast as possible
        QtWid.QApplication.processEvents()
