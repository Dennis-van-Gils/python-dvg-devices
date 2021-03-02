#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt5 module to provide multithreaded communication and periodical data
acquisition for a Julabo circulating bath.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "01-03-2021"
__version__ = "0.2.4"
# pylint: disable=broad-except

import time

import numpy as np
from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets as QtWid

from dvg_pyqt_controls import create_Toggle_button, create_tiny_error_LED
from dvg_debug_functions import dprint, print_fancy_traceback as pft

from dvg_qdeviceio import QDeviceIO, DAQ_TRIGGER
from dvg_devices.Julabo_circulator_protocol_RS232 import Julabo_circulator


class Julabo_circulator_qdev(QDeviceIO):
    """Manages multithreaded communication and periodical data acquisition for
    a Julabo circulator, referred to as the 'device'.

    In addition, it also provides PyQt5 GUI objects for control of the device.
    These can be incorporated into your application.

    All device I/O operations will be offloaded to 'workers', each running in
    a newly created thread.

    (*): See 'dvg_qdeviceio.QDeviceIO()' for details.

    Args:
        dev:
            Reference to a
            'dvg_devices.Julabo_circulator_protocol_RS232.Julabo_circulator'
            instance.

        debug:
            Show debug info in terminal? Warning: Slow! Do not leave on
            unintentionally.

    Main GUI objects:
        qgrp (PyQt5.QtWidgets.QGroupBox)
    """

    signal_GUI_input_field_update = QtCore.pyqtSignal(int)

    def __init__(
        self,
        dev: Julabo_circulator,
        DAQ_trigger=DAQ_TRIGGER.INTERNAL_TIMER,
        DAQ_interval_ms=500,
        DAQ_timer_type=QtCore.Qt.CoarseTimer,
        critical_not_alive_count=3,
        debug=False,
        **kwargs,
    ):
        super().__init__(dev, **kwargs)  # Pass kwargs onto QtCore.QObject()

        self.create_worker_DAQ(
            DAQ_trigger=DAQ_trigger,
            DAQ_function=self.DAQ_function,
            DAQ_interval_ms=DAQ_interval_ms,
            DAQ_timer_type=DAQ_timer_type,
            critical_not_alive_count=critical_not_alive_count,
            debug=debug,
        )
        self.create_worker_jobs(jobs_function=self.jobs_function, debug=debug)

        self.create_GUI()
        self.signal_DAQ_updated.connect(self.update_GUI)
        self.signal_connection_lost.connect(self.update_GUI)
        self.signal_GUI_input_field_update.connect(self.update_GUI_input_field)

        self.safe_temp.setText("%.2f" % self.dev.state.safe_temp)
        self.sub_temp.setText("%.2f" % self.dev.state.sub_temp)
        self.over_temp.setText("%.2f" % self.dev.state.over_temp)
        self.send_setpoint("%.2f" % self.dev.state.setpoint)

        self.update_GUI()
        self.update_GUI_input_field()

    # --------------------------------------------------------------------------
    #   DAQ_function
    # --------------------------------------------------------------------------

    def DAQ_function(self):
        return self.dev.query_common_readings()

    # --------------------------------------------------------------------------
    #   jobs_function
    # --------------------------------------------------------------------------

    def jobs_function(self, func, args):
        if func == "signal_GUI_input_field_update":
            # Special instruction
            self.signal_GUI_input_field_update.emit(*args)
        else:
            # Default job processing:
            # Send I/O operation to the device
            try:
                func(*args)
                self.dev.wait_for_OPC()
            except Exception as err:
                pft(err)

    # --------------------------------------------------------------------------
    #   create GUI
    # --------------------------------------------------------------------------

    def create_GUI(self):
        # Safety
        p = {
            "alignment": QtCore.Qt.AlignRight,
            "minimumWidth": 60,
            "maximumWidth": 30,
        }
        self.safe_sens = QtWid.QLineEdit("nan", **p, readOnly=True)
        self.safe_temp = QtWid.QLineEdit("nan", **p, readOnly=True)
        self.sub_temp = QtWid.QLineEdit("nan", **p)
        self.over_temp = QtWid.QLineEdit("nan", **p)

        # Control
        self.pbtn_running = create_Toggle_button("OFFLINE")
        self.pbtn_running.clicked.connect(self.process_pbtn_running)
        self.send_setpoint = QtWid.QLineEdit("nan", **p)
        self.send_setpoint.textChanged.connect(self.send_setpoint_from_textbox)
        self.read_setpoint = QtWid.QLineEdit("nan", **p, readOnly=True)
        self.bath_temp = QtWid.QLineEdit("nan", **p, readOnly=True)
        self.pt100_temp = QtWid.QLineEdit("nan", **p, readOnly=True)
        self.status = QtWid.QTextEdit(minimumWidth=200, readOnly=True)
        self.update_counter = QtWid.QLabel("0")

        i = 0
        p = {"alignment": QtCore.Qt.AlignLeft}
        lbl_temp_unit = "\u00b0%s" % self.dev.state.temp_unit

        # fmt: off
        grid = QtWid.QGridLayout()
        grid.setVerticalSpacing(4)

        grid.addWidget(QtWid.QLabel("<b>Safety</b>")        , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)                , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Safe sensor")          , i, 0)
        grid.addWidget(self.safe_sens                       , i, 1)
        grid.addWidget(QtWid.QLabel(lbl_temp_unit)          , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("Safe temp.")           , i, 0)
        grid.addWidget(self.safe_temp                       , i, 1)
        grid.addWidget(QtWid.QLabel(lbl_temp_unit)          , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("Sub temp.")            , i, 0)
        grid.addWidget(self.sub_temp                        , i, 1)
        grid.addWidget(QtWid.QLabel(lbl_temp_unit)          , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("Over temp.")           , i, 0)
        grid.addWidget(self.over_temp                       , i, 1)
        grid.addWidget(QtWid.QLabel(lbl_temp_unit)          , i, 2)      ; i+=1

        grid.addItem(QtWid.QSpacerItem(1, 10)               , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("<b>Control</b>")       , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)                , i, 0)      ; i+=1
        grid.addWidget(self.pbtn_running                    , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 8)                , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Send setpoint")        , i, 0)
        grid.addWidget(self.send_setpoint                   , i, 1)
        grid.addWidget(QtWid.QLabel(lbl_temp_unit)          , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("Read setpoint")        , i, 0)
        grid.addWidget(self.read_setpoint                   , i, 1)
        grid.addWidget(QtWid.QLabel(lbl_temp_unit)          , i, 2)      ; i+=1
        grid.addItem(QtWid.QSpacerItem(1, 8)                , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Bath temp.")           , i, 0)
        grid.addWidget(self.bath_temp                       , i, 1)
        grid.addWidget(QtWid.QLabel(lbl_temp_unit)          , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("Pt100 temp.")          , i, 0)
        grid.addWidget(self.pt100_temp                      , i, 1)
        grid.addWidget(QtWid.QLabel(lbl_temp_unit)          , i, 2)      ; i+=1
        grid.addItem(QtWid.QSpacerItem(1, 8)                , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Status")               , i, 0, 1, 3); i+=1
        grid.addWidget(self.status                          , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 4)                , i, 0)      ; i+=1
        grid.addWidget(self.update_counter                  , i, 0, 1, 3); i+=1
        # fmt: on

        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 1)
        grid.setAlignment(QtCore.Qt.AlignTop)
        self.grid = grid

        self.grpb = QtWid.QGroupBox("%s" % self.dev.name)
        self.grpb.setLayout(self.grid)

    # --------------------------------------------------------------------------
    #   update_GUI
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def update_GUI(self):
        """NOTE: 'self.dev.mutex' is not being locked, because we are only
        reading 'state' for displaying purposes. We can do this because 'state'
        members are written and read atomicly.
        """
        if self.dev.is_alive:
            self.safe_sens.setText("%.2f" % self.dev.state.safe_sens)

            self.pbtn_running.setChecked(self.dev.state.running)
            if self.pbtn_running.isChecked():
                self.pbtn_running.setText("RUNNING")
            else:
                self.pbtn_running.setText("Idle")

            self.read_setpoint.setText("%.2f" % self.dev.state.setpoint_1)
            self.bath_temp.setText("%.2f" % self.dev.state.bath_temp)
            self.pt100_temp.setText("%.2f" % self.dev.state.pt100_temp)
            self.status.setText(self.dev.state.status)

            self.update_counter.setText("%s" % self.update_counter_DAQ)
        else:
            self.pbtn_running.setText("OFFLINE")
            self.grpb.setEnabled(False)

    # --------------------------------------------------------------------------
    #   update_GUI_input_field
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def update_GUI_input_field(self):
        pass
        """
        if GUI_input_field == GUI_input_fields.V_source:
            self.V_source.setText("%.3f" % self.dev.state.V_source)

        elif GUI_input_field == GUI_input_fields.I_source:
            self.I_source.setText("%.3f" % self.dev.state.I_source)

        elif GUI_input_field == GUI_input_fields.OVP_level:
            self.OVP_level.setText("%.1f" % self.dev.state.OVP_level)

        elif GUI_input_field == GUI_input_fields.OCP_level:
            self.OCP_level.setText("%.2f" % self.dev.state.OCP_level)

        else:
            self.V_source.setText("%.3f" % self.dev.state.V_source)
            self.I_source.setText("%.3f" % self.dev.state.I_source)
            self.OVP_level.setText("%.1f" % self.dev.state.OVP_level)
            self.OCP_level.setText("%.2f" % self.dev.state.OCP_level)
        """

    # --------------------------------------------------------------------------
    #   GUI functions
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def process_pbtn_running(self):
        if self.dev.state.running:
            self.send(self.dev.turn_off)
        else:
            self.send(self.dev.turn_on)

    @QtCore.pyqtSlot()
    def send_setpoint_from_textbox(self):
        try:
            setpoint = float(self.send_setpoint.text())
        except (TypeError, ValueError):
            # Revert to previously set setpoint
            setpoint = self.dev.state.setpoint
        except:
            raise

        self.send_setpoint.setText("%.2f" % setpoint)
        self.send(self.dev.set_setpoint, setpoint)

    """
    def send_V_source_from_textbox(self):
        try:
            voltage = float(self.V_source.text())
        except (TypeError, ValueError):
            voltage = 0.0
        except:
            raise

        if voltage < 0:
            voltage = 0

        self.add_to_jobs_queue(self.dev.set_V_source, voltage)
        self.add_to_jobs_queue(self.dev.query_V_source)
        self.add_to_jobs_queue(
            "signal_GUI_input_field_update", GUI_input_fields.V_source
        )
        self.process_jobs_queue()
    """
