#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt/PySide module to provide multithreaded communication and periodical data
acquisition with an OptLasers thermoelectric cooler (TEC) controller.
Specifically written for the OptLasers TEC-8A-24V-PID-HC-RS232 controller, see
https://optlasers.com/tec-controllers/tec-8a-24v-pid-hc-rs232-programmable-temperature-controller.
"""

__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "17-08-2026"
__version__ = "1.7.1"
# pylint: disable=missing-function-docstring, multiple-statements

import os
from enum import IntEnum
from pathlib import Path

from qtpy import QtCore, QtWidgets as QtWid
from qtpy.QtCore import Slot, Signal  # type: ignore

import dvg_pyqt_controls as controls
from dvg_debug_functions import print_fancy_traceback as pft
from dvg_qdeviceio import QDeviceIO, DAQ_TRIGGER
from dvg_devices.OptLasers_TEC_controller_protocol_RS232 import OptLasersTEC

# Special characters
CHAR_DEG_C = chr(176) + "C"


# Enumeration
class GUI_input_fields(IntEnum):
    ALL = 0
    supply = 1
    P = 2
    I = 3
    D = 4
    T_min = 5
    T_max = 6
    T_set = 7


class OptLasersTEC_qdev(QDeviceIO):
    """Manages multithreaded communication and periodical data acquisition with
    an OptLasers thermoelectric cooler (TEC) controller. referred to as the
    'device'.

    In addition, it also provides PyQt/PySide GUI objects for control of the
    device. These can be incorporated into your application.

    All device I/O operations will be offloaded to 'workers', each running in
    a newly created thread.

    (*): See 'dvg_qdeviceio.QDeviceIO()' for details.

    Args:
        dev:
            Reference to a
            'dvg_devices.OptLasers_TEC_controller_protocol_RS232.OptLasersTEC'
            instance.

        (*) DAQ_interval_ms:
            The minimal readout period for continuous polling of the TEC
            controller variables is around 1.09 sec. Do not try to read faster
            than this.

        debug:
            Show debug info in terminal? Warning: Slow! Do not leave on
            unintentionally.

    Main GUI objects:
        qgrp (PyQt5.QtWidgets.QGroupBox)
    """

    signal_GUI_input_field_update = Signal(int)

    def __init__(
        self,
        dev: OptLasersTEC,
        DAQ_interval_ms=1250,
        DAQ_timer_type=QtCore.Qt.TimerType.CoarseTimer,
        critical_not_alive_count=0,
        debug=False,
        **kwargs,
    ):
        super().__init__(dev, **kwargs)  # Pass kwargs onto QtCore.QObject()
        self.dev: OptLasersTEC  # Enforce type: removes `_NoDevice()`

        self.create_worker_DAQ(
            DAQ_trigger=DAQ_TRIGGER.INTERNAL_TIMER,
            DAQ_function=self._DAQ_function,
            DAQ_interval_ms=DAQ_interval_ms,
            DAQ_timer_type=DAQ_timer_type,
            critical_not_alive_count=critical_not_alive_count,
            debug=debug,
        )

        self.create_worker_jobs(jobs_function=self._jobs_function, debug=debug)

        self._create_GUI()
        self.signal_DAQ_updated.connect(self._update_GUI_readings)
        self.signal_GUI_input_field_update.connect(self._update_GUI_input_field)

        self._update_GUI_readings()
        self._update_GUI_input_field()

    # --------------------------------------------------------------------------
    #   _DAQ_function
    # --------------------------------------------------------------------------

    def _DAQ_function(self) -> bool:
        # print("Obtained interval: %.0f" % self.obtained_DAQ_interval_ms)
        return self.dev.query_state()

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
            except Exception as err:  # pylint: disable=broad-exception-caught
                pft(err)

    # --------------------------------------------------------------------------
    #   _create_GUI
    # --------------------------------------------------------------------------

    def _create_GUI(self):
        # Hyperlink to device manual
        # --------------------------
        path_manual = Path(os.path.dirname(os.path.realpath(__file__)))
        path_manual = os.path.join(
            path_manual.as_uri(),
            "manuals",
            "Manual_OptLasers_TEC_controller.pdf",
        )
        self.qlbl_manual = QtWid.QLabel(
            f"<a href='{path_manual}'>Open manual</a>"
        )
        self.qlbl_manual.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.qlbl_manual.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self.qlbl_manual.setOpenExternalLinks(True)

        # TEC settings
        # ------------
        fm = self.qlbl_manual.fontMetrics()
        em_width = fm.horizontalAdvance("M")

        p = {
            "alignment": QtCore.Qt.AlignmentFlag.AlignCenter,
            "fixedWidth": em_width * 6,
        }

        self.pbtn_supply = controls.create_Toggle_button()
        self.qlin_P = QtWid.QLineEdit(**p)
        self.qlin_I = QtWid.QLineEdit(**p)
        self.qlin_D = QtWid.QLineEdit(**p)
        self.qlin_T_min = QtWid.QLineEdit(**p)
        self.qlin_T_max = QtWid.QLineEdit(**p)
        self.qlin_T_set = QtWid.QLineEdit(**p)

        # TEC readings
        # ------------
        p["readOnly"] = True
        self.indicator_OC = controls.create_error_LED()
        self.qlin_status = QtWid.QLineEdit(**p)
        self.qlin_PWM = QtWid.QLineEdit(**p)
        self.qlin_T_meas = QtWid.QLineEdit(**p)
        self.qlbl_update_counter = QtWid.QLabel("0")

        self.grid = QtWid.QGridLayout()
        self.grid.setVerticalSpacing(0)
        i = 0
        # fmt: off
        self.grid.addWidget(QtWid.QLabel("<b>Settings</b>"), i, 0)      ; i += 1
        self.grid.addItem(QtWid.QSpacerItem(0, 2)          , i, 0)      ; i += 1
        self.grid.addWidget(QtWid.QLabel("Supply")         , i, 0)
        self.grid.addWidget(self.pbtn_supply               , i, 1, 1, 2); i += 1

        self.grid.addItem(QtWid.QSpacerItem(0, 10)         , i, 0)      ; i += 1
        self.grid.addWidget(QtWid.QLabel("P")              , i, 0)
        self.grid.addWidget(self.qlin_P                    , i, 1)
        self.grid.addWidget(QtWid.QLabel("[0 - 20.0]")     , i, 2)      ; i += 1
        self.grid.addWidget(QtWid.QLabel("I")              , i, 0)
        self.grid.addWidget(self.qlin_I                    , i, 1)
        self.grid.addWidget(QtWid.QLabel("[0 - 20.0]")     , i, 2)      ; i += 1
        self.grid.addWidget(QtWid.QLabel("D")              , i, 0)
        self.grid.addWidget(self.qlin_D                    , i, 1)
        self.grid.addWidget(QtWid.QLabel("[0 - 20.0]")     , i, 2)      ; i += 1

        self.grid.addItem(QtWid.QSpacerItem(0, 10)         , i, 0)      ; i += 1
        self.grid.addWidget(QtWid.QLabel("T_min")          , i, 0)
        self.grid.addWidget(self.qlin_T_min                , i, 1)
        self.grid.addWidget(QtWid.QLabel(CHAR_DEG_C)       , i, 2)      ; i += 1
        self.grid.addWidget(QtWid.QLabel("T_max")          , i, 0)
        self.grid.addWidget(self.qlin_T_max                , i, 1)
        self.grid.addWidget(QtWid.QLabel(CHAR_DEG_C)       , i, 2)      ; i += 1
        self.grid.addWidget(QtWid.QLabel("T_set")          , i, 0)
        self.grid.addWidget(self.qlin_T_set                , i, 1)
        self.grid.addWidget(QtWid.QLabel(CHAR_DEG_C)       , i, 2)      ; i += 1

        self.grid.addItem(QtWid.QSpacerItem(0, 10)         , i, 0)      ; i += 1
        self.grid.addWidget(QtWid.QLabel("<b>Readings</b>"), i, 0)      ; i += 1
        self.grid.addItem(QtWid.QSpacerItem(0, 2)          , i, 0)      ; i += 1
        self.grid.addWidget(QtWid.QLabel("Open\nCollector"), i, 0)
        self.grid.addWidget(self.indicator_OC              , i, 1)      ; i += 1
        self.grid.addWidget(QtWid.QLabel("Status")         , i, 0)
        self.grid.addWidget(self.qlin_status               , i, 1)      ; i += 1
        self.grid.addWidget(QtWid.QLabel("PWM")            , i, 0)
        self.grid.addWidget(self.qlin_PWM                  , i, 1)
        self.grid.addWidget(QtWid.QLabel("%")              , i, 2)      ; i += 1
        self.grid.addWidget(QtWid.QLabel("T_meas")         , i, 0)
        self.grid.addWidget(self.qlin_T_meas               , i, 1)
        self.grid.addWidget(QtWid.QLabel(f"{chr(177)}2 {chr(176)}C"), i, 2); i += 1
        self.grid.addItem(QtWid.QSpacerItem(0, 10)         , i, 0)      ; i += 1
        self.grid.addWidget(self.qlbl_update_counter       , i, 0)
        self.grid.addWidget(self.qlbl_manual               , i, 1, 1, 2)
        # fmt: on

        self.qgrp = QtWid.QGroupBox(f"{self.dev.name}")
        self.qgrp.setLayout(self.grid)

        # Connect signals
        self.pbtn_supply.clicked.connect(self._process_pbtn_supply)
        self.qlin_P.editingFinished.connect(self._process_qlin_P)
        self.qlin_I.editingFinished.connect(self._process_qlin_I)
        self.qlin_D.editingFinished.connect(self._process_qlin_D)
        self.qlin_T_min.editingFinished.connect(self._process_qlin_T_min)
        self.qlin_T_max.editingFinished.connect(self._process_qlin_T_max)
        self.qlin_T_set.editingFinished.connect(self._process_qlin_T_set)

    # --------------------------------------------------------------------------
    #   GUI updates
    # --------------------------------------------------------------------------

    @Slot()
    def _update_GUI_readings(self):
        # NOTE: It is not necessary to lock and unlock 'self.dev.mutex' here,
        # because the `state` members are written and read atomicly.
        if not self.dev.is_alive:
            self.qgrp.setEnabled(False)
            return

        if self.dev.state.PWM < 0:
            self.qlin_status.setText("cooling")
        elif self.dev.state.PWM > 0:
            self.qlin_status.setText("heating")
        else:
            self.qlin_status.setText("idle")

        self.indicator_OC.setChecked(bool(self.dev.state.OC))
        self.indicator_OC.setText(f"{self.dev.state.OC}")
        self.qlin_PWM.setText(f"{self.dev.state.PWM:d}")
        self.qlin_T_meas.setText(f"{self.dev.state.T_meas:.2f}")
        self.qlbl_update_counter.setText(f"{self.update_counter_DAQ}")

    @Slot()
    @Slot(int)
    def _update_GUI_input_field(self, GUI_input_field=GUI_input_fields.ALL):
        # NOTE: It is not necessary to lock and unlock 'self.dev.mutex' here,
        # because the `state` members are written and read atomicly.
        if GUI_input_field in (GUI_input_fields.ALL, GUI_input_fields.supply):
            self.pbtn_supply.setChecked(self.dev.state.is_supply_ON)
            self.pbtn_supply.setText(
                "ON" if self.dev.state.is_supply_ON else "OFF"
            )

        if GUI_input_field in (GUI_input_fields.ALL, GUI_input_fields.P):
            self.qlin_P.setText(f"{self.dev.state.P:.2f}")

        if GUI_input_field in (GUI_input_fields.ALL, GUI_input_fields.I):
            self.qlin_I.setText(f"{self.dev.state.I:.2f}")

        if GUI_input_field in (GUI_input_fields.ALL, GUI_input_fields.D):
            self.qlin_D.setText(f"{self.dev.state.D:.2f}")

        if GUI_input_field in (GUI_input_fields.ALL, GUI_input_fields.T_min):
            self.qlin_T_min.setText(f"{self.dev.state.T_min:d}")

        if GUI_input_field in (GUI_input_fields.ALL, GUI_input_fields.T_max):
            self.qlin_T_max.setText(f"{self.dev.state.T_max:d}")

        if GUI_input_field in (GUI_input_fields.ALL, GUI_input_fields.T_set):
            self.qlin_T_set.setText(f"{self.dev.state.T_set:.2f}")

    # --------------------------------------------------------------------------
    #   Handle controls
    # --------------------------------------------------------------------------

    def _process_qlin_helper(self, func, value, field: GUI_input_fields):
        self.add_to_jobs_queue(func, value)
        self.add_to_jobs_queue("signal_GUI_input_field_update", field)
        self.process_jobs_queue()

    @Slot()
    def _process_pbtn_supply(self):
        self.add_to_jobs_queue(
            self.dev.turn_supply_OFF
            if self.dev.state.is_supply_ON
            else self.dev.turn_supply_ON
        )
        self.add_to_jobs_queue(
            "signal_GUI_input_field_update", GUI_input_fields.supply
        )
        self.process_jobs_queue()

    @Slot()
    def _process_qlin_P(self):
        self._process_qlin_helper(
            self.dev.send_P,
            _str2float(self.qlin_P.text()),
            GUI_input_fields.P,
        )

    @Slot()
    def _process_qlin_I(self):
        self._process_qlin_helper(
            self.dev.send_I,
            _str2float(self.qlin_I.text()),
            GUI_input_fields.I,
        )

    @Slot()
    def _process_qlin_D(self):
        self._process_qlin_helper(
            self.dev.send_D,
            _str2float(self.qlin_D.text()),
            GUI_input_fields.D,
        )

    @Slot()
    def _process_qlin_T_min(self):
        self._process_qlin_helper(
            self.dev.send_T_min,
            _str2int(self.qlin_T_min.text()),
            GUI_input_fields.T_min,
        )

    @Slot()
    def _process_qlin_T_max(self):
        self._process_qlin_helper(
            self.dev.send_T_max,
            _str2int(self.qlin_T_max.text()),
            GUI_input_fields.T_max,
        )

    @Slot()
    def _process_qlin_T_set(self):
        self._process_qlin_helper(
            self.dev.send_T_set,
            _str2float(self.qlin_T_set.text(), 21),
            GUI_input_fields.T_set,
        )


def _str2float(input_str: str, fallback_value: float = 0.0) -> float:
    try:
        val = float(input_str)
    except ValueError:
        val = fallback_value
    except Exception as err:
        raise err

    return val


def _str2int(input_str: str, fallback_value: int = 0) -> int:
    try:
        val = int(float(input_str))
    except ValueError:
        val = fallback_value
    except Exception as err:
        raise err

    return val
