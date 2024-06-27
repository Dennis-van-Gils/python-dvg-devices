#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt/PySide module to provide multithreaded communication and periodical data
acquisition for a Bronkhorst mass flow controller (MFC).
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "23-05-2024"
__version__ = "1.5.0"
# pylint: disable=missing-function-docstring

import time

from qtpy import QtCore, QtGui, QtWidgets as QtWid
from qtpy.QtCore import Signal, Slot  # type: ignore

from dvg_debug_functions import print_fancy_traceback as pft
from dvg_qdeviceio import QDeviceIO, DAQ_TRIGGER
from dvg_devices.Bronkhorst_MFC_protocol_RS232 import Bronkhorst_MFC


class Bronkhorst_MFC_qdev(QDeviceIO):
    """Manages multithreaded communication and data acquisition for a
    Bronkhorst mass flow controller (MFC), referred to as the 'device'.

    In addition, it also provides PyQt/PySide GUI objects for control of the
    device. These can be incorporated into your application.

    Extra functionality is provided to allow for automatic closing and opening
    of a peripheral valve that could be in line with the mass flow controller.
    This can be used to e.g. prevent liquid from entering the mass flow
    controller from the upstream side when the flow rate has dropped to 0 for
    some reason. Signals 'signal_valve_auto_close' and 'signal_valve_auto_open'
    are emitted from within this class and the user can connect to these to
    automate opening and closing of such a valve. There is a deadtime where the
    auto close signal will not be emitted after a setpoint > 0 has been send,
    because time might have to be given to the mass flow controller to get the
    flow going.

    All device I/O operations will be offloaded to 'workers', each running in
    a newly created thread.

    (*): See 'dvg_qdeviceio.QDeviceIO()' for details.

    Args:
        dev:
            Reference to a
            'dvg_devices.Bronkhorst_MFC_protocol_RS232.Bronkhorst_MFC'
            instance.

        valve_auto_close_deadtime_period_ms (optional, default=3000):
            Deadtime period in milliseconds of the auto close signal after a
            setpoint > 0 has been send.

        debug:
            Show debug info in terminal? Warning: Slow! Do not leave on
            unintentionally.

    Main GUI objects:
        qgrp (PyQt5.QtWidgets.QGroupBox)

    Signals:
        signal_valve_auto_close()
        signal_valve_auto_open()
    """

    signal_valve_auto_close = Signal()
    signal_valve_auto_open = Signal()

    def __init__(
        self,
        dev: Bronkhorst_MFC,
        DAQ_interval_ms=200,
        DAQ_timer_type=QtCore.Qt.TimerType.CoarseTimer,
        critical_not_alive_count=1,
        valve_auto_close_deadtime_period_ms: int = 3000,
        debug=False,
        **kwargs,
    ):
        super().__init__(dev, **kwargs)  # Pass kwargs onto QtCore.QObject()
        self.dev: Bronkhorst_MFC  # Enforce type: removes `_NoDevice()`

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
        self.signal_DAQ_updated.connect(self._update_GUI)
        if not self.dev.is_alive:
            self._update_GUI()  # Correctly reflect an offline device

        # Auto open or close of an optional peripheral valve
        self._prev_flow_rate: float = self.dev.state.flow_rate
        self._valve_auto_close_briefly_prevent: bool = False
        self._valve_auto_close_deadtime_period_ms: int = (
            valve_auto_close_deadtime_period_ms
        )
        self._valve_auto_close_start_deadtime: float = 0  # Start time in [sec]

    # --------------------------------------------------------------------------
    #   _DAQ_function
    # --------------------------------------------------------------------------

    def _DAQ_function(self) -> bool:
        success = self.dev.query_setpoint()
        success &= self.dev.query_flow_rate()

        if success:
            # Check to signal auto open or close of an optional peripheral valve
            if (
                self.dev.state.flow_rate == 0
                and not self._prev_flow_rate == self.dev.state.flow_rate
            ):
                # The flow rate has just dropped to 0
                if (
                    self._valve_auto_close_briefly_prevent
                    and (
                        time.perf_counter()
                        - self._valve_auto_close_start_deadtime
                    )
                    < self._valve_auto_close_deadtime_period_ms * 1000
                ):
                    # We are still in deadtime
                    pass
                else:
                    # Signal auto close and force setpoint = 0
                    self.signal_valve_auto_close.emit()
                    self.dev.send_setpoint(0)
                    self._valve_auto_close_briefly_prevent = False
                    self._prev_flow_rate = self.dev.state.flow_rate
            else:
                self._prev_flow_rate = self.dev.state.flow_rate

        return success

    # --------------------------------------------------------------------------
    #   _jobs_function
    # --------------------------------------------------------------------------

    def _jobs_function(self, func, args):
        # Send I/O operation to the device
        try:
            func(*args)
        except Exception as err:  # pylint: disable=broad-except
            pft(err)

        # Check to signal auto open or close of an optional peripheral valve
        if func == self.dev.send_setpoint:
            if args[0] == 0:
                # Setpoint was set to 0 --> signal auto close
                self._valve_auto_close_briefly_prevent = False
                self.signal_valve_auto_close.emit()
            else:
                # Flow enabled --> start deadtime on auto close
                #              --> signal auto open
                self._valve_auto_close_briefly_prevent = True
                self._valve_auto_close_start_deadtime = time.perf_counter()
                self._prev_flow_rate = -1  # Necessary reset
                self.signal_valve_auto_open.emit()

    # --------------------------------------------------------------------------
    #   _create_GUI
    # --------------------------------------------------------------------------

    def _create_GUI(self):
        self.qlbl_offline = QtWid.QLabel("MFC OFFLINE")
        self.qlbl_offline.setVisible(False)
        self.qlbl_offline.setFont(
            QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Weight.Bold)
        )
        self.qlbl_offline.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        p = {
            "alignment": QtCore.Qt.AlignmentFlag.AlignRight,
            "minimumWidth": 50,
            "maximumWidth": 30,
        }
        p2 = {**p, "readOnly": True}
        # fmt: off
        self.qled_send_setpoint  = QtWid.QLineEdit(**p)
        self.qled_read_setpoint  = QtWid.QLineEdit(**p2)
        self.qled_flow_rate      = QtWid.QLineEdit(**p2)
        self.qlbl_update_counter = QtWid.QLabel("0")
        # fmt: on

        self.qled_send_setpoint.editingFinished.connect(
            self._send_setpoint_from_textbox
        )

        # fmt: off
        self.grid = QtWid.QGridLayout()
        self.grid.setVerticalSpacing(4)
        self.grid.addWidget(self.qlbl_offline             , 0, 0, 1, 3)
        self.grid.addWidget(QtWid.QLabel("Send setpoint") , 1, 0)
        self.grid.addWidget(self.qled_send_setpoint       , 1, 1)
        self.grid.addWidget(QtWid.QLabel("ln/min")        , 1, 2)
        self.grid.addWidget(QtWid.QLabel("Read setpoint") , 2, 0)
        self.grid.addWidget(self.qled_read_setpoint       , 2, 1)
        self.grid.addWidget(QtWid.QLabel("ln/min")        , 2, 2)
        self.grid.addItem(QtWid.QSpacerItem(1, 12)        , 3, 0)
        self.grid.addWidget(QtWid.QLabel("Read flow rate"), 4, 0)
        self.grid.addWidget(self.qled_flow_rate           , 4, 1)
        self.grid.addWidget(QtWid.QLabel("ln/min")        , 4, 2)
        self.grid.addWidget(self.qlbl_update_counter      , 5, 0, 1, 3)
        # fmt: on

        self.qgrp = QtWid.QGroupBox(f"{self.dev.name}")
        self.qgrp.setLayout(self.grid)

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
        if self.dev.is_alive:
            # At startup
            if self.update_counter_DAQ == 1:
                self.qled_send_setpoint.setText(
                    f"{self.dev.state.setpoint:.2f}"
                )
            self.qled_flow_rate.setText(f"{self.dev.state.flow_rate:.2f}")
            self.qled_read_setpoint.setText(f"{self.dev.state.setpoint:.2f}")
            self.qlbl_update_counter.setText(f"{self.update_counter_DAQ}")
        else:
            self.qgrp.setEnabled(False)
            self.qlbl_offline.setVisible(True)

    # --------------------------------------------------------------------------
    #   GUI functions
    # --------------------------------------------------------------------------

    @Slot()
    def _send_setpoint_from_textbox(self):
        try:
            setpoint = float(self.qled_send_setpoint.text())
        except (TypeError, ValueError):
            setpoint = 0.0
        except Exception as err:
            raise err

        setpoint = max(setpoint, 0)
        setpoint = min(setpoint, self.dev.max_flow_rate)
        self.qled_send_setpoint.setText(f"{setpoint:.2f}")

        self.send(self.dev.send_setpoint, setpoint)
