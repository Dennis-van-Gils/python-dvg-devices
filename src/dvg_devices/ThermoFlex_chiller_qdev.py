#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt/PySide module to provide multithreaded communication and periodical data
acquisition for a Thermo Scientific ThermoFlex recirculating chiller.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "23-05-2024"
__version__ = "1.5.0"
# pylint: disable=missing-function-docstring, broad-except

from qtpy import QtCore, QtGui, QtWidgets as QtWid
from qtpy.QtCore import Signal, Slot  # type: ignore

import dvg_pyqt_controls as controls
from dvg_debug_functions import print_fancy_traceback as pft
from dvg_qdeviceio import QDeviceIO, DAQ_TRIGGER
from dvg_devices.ThermoFlex_chiller_protocol_RS232 import ThermoFlex_chiller

# Special characters
CHAR_DEG_C = chr(176) + "C"


class ThermoFlex_chiller_qdev(QDeviceIO):
    """Manages multithreaded communication and periodical data acquisition for
    a Thermo Scientific ThermoFlex recirculating chiller, referred to as the
    'device'.

    In addition, it also provides PyQt/PySide GUI objects for control of the
    device. These can be incorporated into your application.

    (*): See 'dvg_qdeviceio.QDeviceIO()' for details.

    Args:
        dev:
            Reference to a
            'dvg_devices.ThermoFlex_chiller_protocol_RS232.ThermoFlex_chiller'
            instance.

        debug:
            Show debug info in terminal? Warning: Slow! Do not leave on
            unintentionally.

    Main GUI objects:
        hbly_GUI (PyQt5.QtWidgets.QHBoxLayout)
    """

    signal_GUI_alarm_values_update = Signal()
    signal_GUI_PID_values_update = Signal()

    def __init__(
        self,
        dev: ThermoFlex_chiller,
        DAQ_interval_ms=1000,
        DAQ_timer_type=QtCore.Qt.TimerType.CoarseTimer,
        critical_not_alive_count=1,
        debug=False,
        **kwargs,
    ):
        super().__init__(dev, **kwargs)  # Pass kwargs onto QtCore.QObject()
        self.dev: ThermoFlex_chiller  # Enforce type: removes `_NoDevice()`

        self.create_worker_DAQ(
            DAQ_trigger=DAQ_TRIGGER.INTERNAL_TIMER,
            DAQ_function=self.DAQ_function,
            DAQ_interval_ms=DAQ_interval_ms,
            DAQ_timer_type=DAQ_timer_type,
            critical_not_alive_count=critical_not_alive_count,
            debug=debug,
        )

        self.create_worker_jobs(jobs_function=self.jobs_function, debug=debug)

        self.create_GUI()
        self.signal_DAQ_updated.connect(self.update_GUI)
        self.signal_GUI_PID_values_update.connect(self.update_GUI_PID_values)
        self.signal_GUI_alarm_values_update.connect(
            self.update_GUI_alarm_values
        )

        if not self.dev.is_alive:
            self.update_GUI()  # Correctly reflect an offline device

    # --------------------------------------------------------------------------
    #   DAQ_function
    # --------------------------------------------------------------------------

    def DAQ_function(self) -> bool:
        success = self.dev.query_status_bits()
        success &= self.dev.query_state()

        return success

    # --------------------------------------------------------------------------
    #   jobs_function
    # --------------------------------------------------------------------------

    def jobs_function(self, func, args):
        if func == "signal_GUI_alarm_values_update":
            # Special instruction
            self.signal_GUI_alarm_values_update.emit()
        elif func == "signal_GUI_PID_values_update":
            # Special instruction
            self.signal_GUI_PID_values_update.emit()
        else:
            # Default job processing:
            # Send I/O operation to the device
            try:
                func(*args)
            except Exception as err:
                pft(err)

    # --------------------------------------------------------------------------
    #   create_GUI
    # --------------------------------------------------------------------------

    def create_GUI(self):
        # Groupbox "Alarm values"
        # -----------------------
        p = {
            "alignment": QtCore.Qt.AlignmentFlag.AlignRight,
            "minimumWidth": 50,
            "maximumWidth": 30,
            "readOnly": True,
        }
        self.LO_flow = QtWid.QLineEdit(**p)
        self.HI_flow = QtWid.QLineEdit(**p)
        self.LO_pres = QtWid.QLineEdit(**p)
        self.HI_pres = QtWid.QLineEdit(**p)
        self.LO_temp = QtWid.QLineEdit(**p)
        self.HI_temp = QtWid.QLineEdit(**p)
        self.pbtn_read_alarm_values = QtWid.QPushButton("Read")
        self.pbtn_read_alarm_values.setMinimumSize(50, 30)
        self.pbtn_read_alarm_values.clicked.connect(
            self.process_pbtn_read_alarm_values
        )

        p = {"parent": None, "alignment": QtCore.Qt.AlignmentFlag.AlignCenter}
        grid = QtWid.QGridLayout()
        # fmt: off
        grid.addWidget(QtWid.QLabel("Values can be set in the chiller's menu",
                                    **p)          , 0, 0, 1, 4)
        grid.addWidget(QtWid.QLabel("LO")         , 1, 1)
        grid.addWidget(QtWid.QLabel("HI")         , 1, 2)
        grid.addWidget(QtWid.QLabel("Flow rate")  , 2, 0)
        grid.addWidget(self.LO_flow               , 2, 1)
        grid.addWidget(self.HI_flow               , 2, 2)
        grid.addWidget(QtWid.QLabel("LPM")        , 2, 3)
        grid.addWidget(QtWid.QLabel("Pressure")   , 3, 0)
        grid.addWidget(self.LO_pres               , 3, 1)
        grid.addWidget(self.HI_pres               , 3, 2)
        grid.addWidget(QtWid.QLabel("bar")        , 3, 3)
        grid.addWidget(QtWid.QLabel("Temperature"), 4, 0)
        grid.addWidget(self.LO_temp               , 4, 1)
        grid.addWidget(self.HI_temp               , 4, 2)
        grid.addWidget(QtWid.QLabel(CHAR_DEG_C)   , 4, 3)
        grid.addWidget(self.pbtn_read_alarm_values, 5, 0)
        # fmt: on

        self.grpb_alarms = QtWid.QGroupBox("Alarm values")
        self.grpb_alarms.setLayout(grid)

        # Groupbox "PID feedback"
        # -----------------------
        p = {
            "alignment": QtCore.Qt.AlignmentFlag.AlignRight,
            "minimumWidth": 50,
            "maximumWidth": 30,
            "readOnly": True,
        }
        self.PID_P = QtWid.QLineEdit(**p)
        self.PID_I = QtWid.QLineEdit(**p)
        self.PID_D = QtWid.QLineEdit(**p)
        self.pbtn_read_PID_values = QtWid.QPushButton("Read")
        self.pbtn_read_PID_values.setMinimumSize(50, 30)
        self.pbtn_read_PID_values.clicked.connect(
            self.process_pbtn_read_PID_values
        )

        p = {"parent": None, "alignment": QtCore.Qt.AlignmentFlag.AlignCenter}
        grid = QtWid.QGridLayout()
        # fmt: off
        grid.addWidget(QtWid.QLabel("Values can be set in the chiller's menu",
                                    **p)                          , 0, 0, 1, 3)
        grid.addWidget(QtWid.QLabel("P", **p)                     , 1, 0)
        grid.addWidget(self.PID_P                                 , 1, 1)
        grid.addWidget(QtWid.QLabel("% span of 100" + CHAR_DEG_C) , 1, 2)
        grid.addWidget(QtWid.QLabel("I", **p)                     , 2, 0)
        grid.addWidget(self.PID_I                                 , 2, 1)
        grid.addWidget(QtWid.QLabel("repeats/minute")             , 2, 2)
        grid.addWidget(QtWid.QLabel("D", **p)                     , 3, 0)
        grid.addWidget(self.PID_D                                 , 3, 1)
        grid.addWidget(QtWid.QLabel("minutes")                    , 3, 2)
        grid.addWidget(self.pbtn_read_PID_values                  , 4, 0)
        # fmt: on

        self.grpb_PID = QtWid.QGroupBox("PID feedback")
        self.grpb_PID.setLayout(grid)

        # Groupbox "Status bits"
        # ----------------------
        # fmt: off
        self.SB_tripped                = controls.create_error_LED()
        self.SB_tripped.setText("No faults")
        self.SB_high_temp_fixed        = controls.create_tiny_error_LED()
        self.SB_low_temp_fixed         = controls.create_tiny_error_LED()
        self.SB_high_temp              = controls.create_tiny_error_LED()
        self.SB_low_temp               = controls.create_tiny_error_LED()
        self.SB_high_pressure          = controls.create_tiny_error_LED()
        self.SB_low_pressure           = controls.create_tiny_error_LED()
        self.SB_drip_pan               = controls.create_tiny_error_LED()
        self.SB_high_level             = controls.create_tiny_error_LED()
        self.SB_phase_monitor          = controls.create_tiny_error_LED()
        self.SB_motor_overload         = controls.create_tiny_error_LED()
        self.SB_LPC                    = controls.create_tiny_error_LED()
        self.SB_HPC                    = controls.create_tiny_error_LED()
        self.SB_external_EMO           = controls.create_tiny_error_LED()
        self.SB_local_EMO              = controls.create_tiny_error_LED()
        self.SB_low_flow               = controls.create_tiny_error_LED()
        self.SB_low_level              = controls.create_tiny_error_LED()
        self.SB_sense_5V               = controls.create_tiny_error_LED()
        self.SB_invalid_level          = controls.create_tiny_error_LED()
        self.SB_low_fixed_flow_warning = controls.create_tiny_error_LED()
        self.SB_high_pressure_factory  = controls.create_tiny_error_LED()
        self.SB_low_pressure_factory   = controls.create_tiny_error_LED()

        p = {"parent":None, "alignment": QtCore.Qt.AlignmentFlag.AlignRight}
        grid = QtWid.QGridLayout()
        grid.addWidget(self.SB_tripped                           , 0, 0, 1, 2)
        grid.addItem(QtWid.QSpacerItem(1, 12)                          , 1, 0)
        grid.addWidget(QtWid.QLabel("high temp fixed fault", **p)      , 2, 0)
        grid.addWidget(self.SB_high_temp_fixed                         , 2, 1)
        grid.addWidget(QtWid.QLabel("low temp fixed fault", **p)       , 3, 0)
        grid.addWidget(self.SB_low_temp_fixed                          , 3, 1)
        grid.addWidget(QtWid.QLabel("high temp fault/warning", **p)    , 4, 0)
        grid.addWidget(self.SB_high_temp                               , 4, 1)
        grid.addWidget(QtWid.QLabel("low temp fault/warning", **p)     , 5, 0)
        grid.addWidget(self.SB_low_temp                                , 5, 1)
        grid.addWidget(QtWid.QLabel("high pressure fault/warning", **p), 6, 0)
        grid.addWidget(self.SB_high_pressure                           , 6, 1)
        grid.addWidget(QtWid.QLabel("low pressure fault/warning", **p) , 7, 0)
        grid.addWidget(self.SB_low_pressure                            , 7, 1)
        grid.addWidget(QtWid.QLabel("drip pan fault", **p)             , 8, 0)
        grid.addWidget(self.SB_drip_pan                                , 8, 1)
        grid.addWidget(QtWid.QLabel("high level fault", **p)           , 9, 0)
        grid.addWidget(self.SB_high_level                              , 9, 1)
        grid.addWidget(QtWid.QLabel("phase monitor fault", **p)        , 10, 0)
        grid.addWidget(self.SB_phase_monitor                           , 10, 1)
        grid.addWidget(QtWid.QLabel("motor overload fault", **p)       , 11, 0)
        grid.addWidget(self.SB_motor_overload                          , 11, 1)
        grid.addWidget(QtWid.QLabel("LPC fault", **p)                  , 12, 0)
        grid.addWidget(self.SB_LPC                                     , 12, 1)
        grid.addWidget(QtWid.QLabel("HPC fault", **p)                  , 13, 0)
        grid.addWidget(self.SB_HPC                                     , 13, 1)
        grid.addWidget(QtWid.QLabel("external EMO fault", **p)         , 14, 0)
        grid.addWidget(self.SB_external_EMO                            , 14, 1)
        grid.addWidget(QtWid.QLabel("local EMO fault", **p)            , 15, 0)
        grid.addWidget(self.SB_local_EMO                               , 15, 1)
        grid.addWidget(QtWid.QLabel("low flow fault", **p)             , 16, 0)
        grid.addWidget(self.SB_low_flow                                , 16, 1)
        grid.addWidget(QtWid.QLabel("low level fault", **p)            , 17, 0)
        grid.addWidget(self.SB_low_level                               , 17, 1)
        grid.addWidget(QtWid.QLabel("sense 5V fault", **p)             , 18, 0)
        grid.addWidget(self.SB_sense_5V                                , 18, 1)
        grid.addWidget(QtWid.QLabel("invalid level fault", **p)        , 19, 0)
        grid.addWidget(self.SB_invalid_level                           , 19, 1)
        grid.addWidget(QtWid.QLabel("low fixed flow warning", **p)     , 20, 0)
        grid.addWidget(self.SB_low_fixed_flow_warning                  , 20, 1)
        grid.addWidget(QtWid.QLabel("high pressure factory fault", **p), 21, 0)
        grid.addWidget(self.SB_high_pressure_factory                   , 21, 1)
        grid.addWidget(QtWid.QLabel("low pressure factory fault", **p) , 22, 0)
        grid.addWidget(self.SB_low_pressure_factory                    , 22, 1)
        # fmt: on

        self.grpb_SBs = QtWid.QGroupBox("Status bits")
        self.grpb_SBs.setLayout(grid)

        # Groupbox "Control"
        # ------------------
        p = {
            "alignment": QtCore.Qt.AlignmentFlag.AlignRight,
            "minimumWidth": 50,
            "maximumWidth": 30,
        }
        p2 = {**p, "readOnly": True}

        self.lbl_offline = QtWid.QLabel("OFFLINE")
        self.lbl_offline.setVisible(False)
        self.lbl_offline.setFont(
            QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Weight.Bold)
        )
        self.lbl_offline.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        # fmt: off
        self.pbtn_on       = controls.create_Toggle_button("Off")
        self.pbtn_on.clicked.connect(self.process_pbtn_on)
        self.powering_down = controls.create_tiny_error_LED()
        self.send_setpoint = QtWid.QLineEdit(**p)
        self.send_setpoint.editingFinished.connect(
            self.send_setpoint_from_textbox
        )
        self.read_setpoint = QtWid.QLineEdit(**p2)
        self.read_temp     = QtWid.QLineEdit(**p2)
        self.read_flow     = QtWid.QLineEdit(**p2)
        self.read_supply   = QtWid.QLineEdit(**p2)
        self.read_suction  = QtWid.QLineEdit(**p2)
        self.lbl_update_counter = QtWid.QLabel("0")

        p = {"parent": None, "alignment": QtCore.Qt.AlignmentFlag.AlignRight}

        grid = QtWid.QGridLayout()
        grid.addWidget(self.lbl_offline                         , 0, 0, 1, 3)
        grid.addWidget(self.pbtn_on                             , 1, 0, 1, 3)
        grid.addWidget(QtWid.QLabel("Is powering up/down?", **p), 2, 0, 1, 2)
        grid.addWidget(self.powering_down                       , 2, 2)
        grid.addItem(QtWid.QSpacerItem(1, 12)                   , 3, 0)
        grid.addWidget(QtWid.QLabel("Send setpoint")            , 4, 0)
        grid.addWidget(QtWid.QLabel("Read setpoint")            , 5, 0)
        grid.addWidget(self.send_setpoint                       , 4, 1)
        grid.addWidget(self.read_setpoint                       , 5, 1)
        grid.addWidget(QtWid.QLabel(CHAR_DEG_C)                 , 4, 2)
        grid.addWidget(QtWid.QLabel(CHAR_DEG_C)                 , 5, 2)
        grid.addItem(QtWid.QSpacerItem(1, 12)                   , 6, 0)
        grid.addWidget(QtWid.QLabel("Read temp")                , 7, 0)
        grid.addWidget(self.read_temp                           , 7, 1)
        grid.addWidget(QtWid.QLabel(CHAR_DEG_C)                 , 7, 2)
        grid.addWidget(QtWid.QLabel("Read flow")                , 8, 0)
        grid.addWidget(self.read_flow                           , 8, 1)
        grid.addWidget(QtWid.QLabel("LPM")                      , 8, 2)
        grid.addWidget(QtWid.QLabel("Read supply")              , 9, 0)
        grid.addWidget(self.read_supply                         , 9, 1)
        grid.addWidget(QtWid.QLabel("bar")                      , 9, 2)
        grid.addWidget(QtWid.QLabel("Read suction")             , 10, 0)
        grid.addWidget(self.read_suction                        , 10, 1)
        grid.addWidget(QtWid.QLabel("bar")                      , 10, 2)

        grid.addItem(QtWid.QSpacerItem(1, 12)                      , 11, 0)
        grid.addWidget(QtWid.QLabel("Nominal values @ 15-02-2018:"), 12, 0, 1, 3)
        grid.addWidget(QtWid.QLabel("Read flow")                   , 13, 0)
        grid.addWidget(QtWid.QLabel("80  ", **p)                   , 13, 1)
        grid.addWidget(QtWid.QLabel("LPM")                         , 13, 2)
        grid.addWidget(QtWid.QLabel("Read supply")                 , 14, 0)
        grid.addWidget(QtWid.QLabel("2.9  ", **p)                  , 14, 1)
        grid.addWidget(QtWid.QLabel("bar")                         , 14, 2)
        grid.addWidget(QtWid.QLabel("Read suction")                , 15, 0)
        grid.addWidget(QtWid.QLabel("40  ", **p)                   , 15, 1)
        grid.addWidget(QtWid.QLabel("bar")                         , 15, 2)
        grid.addWidget(self.lbl_update_counter                     , 16, 0, 1, 2)
        # fmt: on

        self.grpb_control = QtWid.QGroupBox("Control")
        self.grpb_control.setLayout(grid)

        # --------------------------------------
        #   Round up final QtWid.QHBoxLayout()
        # --------------------------------------

        vbox = QtWid.QVBoxLayout()
        vbox.addWidget(self.grpb_alarms)
        vbox.addWidget(self.grpb_PID)
        vbox.setAlignment(self.grpb_alarms, QtCore.Qt.AlignmentFlag.AlignTop)
        vbox.setAlignment(self.grpb_PID, QtCore.Qt.AlignmentFlag.AlignTop)
        vbox.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        self.hbly_GUI = QtWid.QHBoxLayout()
        self.hbly_GUI.addLayout(vbox)
        self.hbly_GUI.addWidget(self.grpb_SBs)
        self.hbly_GUI.addWidget(self.grpb_control)
        self.hbly_GUI.addStretch(1)
        self.hbly_GUI.setAlignment(
            self.grpb_SBs, QtCore.Qt.AlignmentFlag.AlignTop
        )
        self.hbly_GUI.setAlignment(
            self.grpb_control, QtCore.Qt.AlignmentFlag.AlignTop
        )
        self.hbly_GUI.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # tab_chiller.setLayout(self.hbly_GUI)

    # --------------------------------------------------------------------------
    #   update_GUI
    # --------------------------------------------------------------------------

    @Slot()
    def update_GUI(self):
        """NOTE: 'self.dev.mutex' is not being locked, because we are only
        reading 'state' for displaying purposes. We can do this because 'state'
        members are written and read atomicly.
        Not locking the mutex might speed up the program.
        """
        if self.dev.is_alive:
            # At startup
            if self.update_counter_DAQ == 1:
                self.update_GUI_alarm_values()
                self.update_GUI_PID_values()
                self.send_setpoint.setText(f"{self.dev.state.setpoint:.1f}")

            # State
            # fmt: off
            self.read_setpoint.setText(f"{self.dev.state.setpoint:.1f}")
            self.read_temp.setText    (f"{self.dev.state.temp:.1f}")
            self.read_flow.setText    (f"{self.dev.state.flow:.1f}")
            self.read_supply.setText  (f"{self.dev.state.supply_pres:.2f}")
            self.read_suction.setText (f"{self.dev.state.suction_pres:.2f}")
            # fmt: on

            # Power
            SBs = self.dev.status_bits  # Short-hand
            self.pbtn_on.setChecked(bool(SBs.running))
            if SBs.running:
                self.pbtn_on.setText("ON")
            else:
                self.pbtn_on.setText("OFF")
            self.powering_down.setChecked(bool(SBs.powering_down))

            # Status bits
            self.SB_tripped.setChecked(bool(SBs.fault_tripped))
            if self.dev.status_bits.fault_tripped:
                self.SB_tripped.setText("FAULT TRIPPED")
            else:
                self.SB_tripped.setText("No faults")
            self.SB_drip_pan.setChecked(bool(SBs.drip_pan_fault))
            self.SB_external_EMO.setChecked(bool(SBs.external_EMO_fault))
            self.SB_high_level.setChecked(bool(SBs.high_level_fault))
            self.SB_high_pressure.setChecked(bool(SBs.high_pressure_fault))
            self.SB_high_pressure_factory.setChecked(
                bool(SBs.high_pressure_fault_factory)
            )
            self.SB_high_temp.setChecked(bool(SBs.high_temp_fault))
            self.SB_high_temp_fixed.setChecked(bool(SBs.high_temp_fixed_fault))
            self.SB_HPC.setChecked(bool(SBs.HPC_fault))
            self.SB_invalid_level.setChecked(bool(SBs.invalid_level_fault))
            self.SB_local_EMO.setChecked(bool(SBs.local_EMO_fault))
            self.SB_low_fixed_flow_warning.setChecked(
                bool(SBs.low_fixed_flow_warning)
            )
            self.SB_low_flow.setChecked(bool(SBs.low_flow_fault))
            self.SB_low_level.setChecked(bool(SBs.low_level_fault))
            self.SB_low_pressure.setChecked(bool(SBs.low_pressure_fault))
            self.SB_low_pressure_factory.setChecked(
                bool(SBs.low_pressure_fault_factory)
            )
            self.SB_low_temp.setChecked(bool(SBs.low_temp_fault))
            self.SB_low_temp_fixed.setChecked(bool(SBs.low_temp_fixed_fault))
            self.SB_LPC.setChecked(bool(SBs.LPC_fault))
            self.SB_motor_overload.setChecked(bool(SBs.motor_overload_fault))
            self.SB_phase_monitor.setChecked(bool(SBs.phase_monitor_fault))
            self.SB_sense_5V.setChecked(bool(SBs.sense_5V_fault))

            self.lbl_update_counter.setText(f"{self.update_counter_DAQ}")
        else:
            self.grpb_alarms.setEnabled(False)
            self.grpb_PID.setEnabled(False)
            self.grpb_SBs.setEnabled(False)
            self.grpb_control.setEnabled(False)

            self.pbtn_on.setVisible(False)
            self.lbl_offline.setVisible(True)

    @Slot()
    def update_GUI_alarm_values(self):
        self.LO_flow.setText(f"{self.dev.values_alarm.LO_flow:.1f}")
        if self.dev.values_alarm.HI_flow == 0:
            self.HI_flow.setText("No limit")
        else:
            self.HI_flow.setText(f"{self.dev.values_alarm.HI_flow:.1f}")
        self.LO_pres.setText(f"{self.dev.values_alarm.LO_pres:.2f}")
        self.HI_pres.setText(f"{self.dev.values_alarm.HI_pres:.2f}")
        self.LO_temp.setText(f"{self.dev.values_alarm.LO_temp:.1f}")
        self.HI_temp.setText(f"{self.dev.values_alarm.HI_temp:.1f}")

    @Slot()
    def update_GUI_PID_values(self):
        self.PID_P.setText(f"{self.dev.values_PID.P:.1f}")
        self.PID_I.setText(f"{self.dev.values_PID.I:.2f}")
        self.PID_D.setText(f"{self.dev.values_PID.D:.1f}")

    # --------------------------------------------------------------------------
    #   GUI functions
    # --------------------------------------------------------------------------

    @Slot()
    def process_pbtn_on(self):
        if self.dev.status_bits.running:
            self.send(self.dev.turn_off)
        else:
            self.send(self.dev.turn_on)

    @Slot()
    def process_pbtn_read_alarm_values(self):
        self.add_to_jobs_queue(self.dev.query_alarm_values_and_units)
        self.add_to_jobs_queue("signal_GUI_alarm_values_update")
        self.process_jobs_queue()

    @Slot()
    def process_pbtn_read_PID_values(self):
        self.add_to_jobs_queue(self.dev.query_PID_values)
        self.add_to_jobs_queue("signal_GUI_PID_values_update")
        self.process_jobs_queue()

    @Slot()
    def send_setpoint_from_textbox(self):
        try:
            setpoint = float(self.send_setpoint.text())
        except (TypeError, ValueError):
            setpoint = 22.0
        except Exception as err:
            raise err

        setpoint = max(setpoint, self.dev.min_setpoint_degC)
        setpoint = min(setpoint, self.dev.max_setpoint_degC)
        self.send_setpoint.setText(f"{setpoint:.1f}")

        self.send(self.dev.send_setpoint, setpoint)
