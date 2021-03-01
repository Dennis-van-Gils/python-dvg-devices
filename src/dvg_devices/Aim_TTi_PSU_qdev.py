#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt5 module to provide multithreaded communication and periodical data
acquisition for an Aim TTi power supply unit (PSU), QL series II.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "01-03-2021"
__version__ = "0.2.3"

import time

import numpy as np
from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets as QtWid

from dvg_pyqt_controls import create_Toggle_button, create_tiny_error_LED
from dvg_debug_functions import dprint, print_fancy_traceback as pft
from dvg_pid_controller import PID_Controller

from dvg_qdeviceio import QDeviceIO, DAQ_TRIGGER
from dvg_devices.Aim_TTi_PSU_protocol_RS232 import Aim_TTi_PSU

# Monospace font
FONT_MONOSPACE = QtGui.QFont("Monospace", 12, weight=QtGui.QFont.Bold)
FONT_MONOSPACE.setStyleHint(QtGui.QFont.TypeWriter)

# Enumeration
class GUI_input_fields:
    [ALL, V_source, I_source, OVP_level, OCP_level] = range(5)


class Aim_TTi_PSU_qdev(QDeviceIO):
    """Manages multithreaded communication and periodical data acquisition for
    an Aim TTi power supply unit (PSU), referred to as the 'device'.

    In addition, it also provides PyQt5 GUI objects for control of the device.
    These can be incorporated into your application.

    All device I/O operations will be offloaded to 'workers', each running in
    a newly created thread.

    (*): See 'dvg_qdeviceio.QDeviceIO()' for details.

    Args:
        dev:
            Reference to a 'dvg_devices.Aim_TTi_PSU_protocol_RS232.Aim_TTi_PSU'
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
        dev: Aim_TTi_PSU,
        DAQ_trigger=DAQ_TRIGGER.INTERNAL_TIMER,
        DAQ_interval_ms=200,
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

        self.update_GUI()
        self.update_GUI_input_field()

    # --------------------------------------------------------------------------
    #   DAQ_function
    # --------------------------------------------------------------------------

    def DAQ_function(self):
        DEBUG_local = False
        if DEBUG_local:
            tick = time.perf_counter()

        if not self.dev.query_V_meas():
            return False
        if not self.dev.query_I_meas():
            return False
        if not self.dev.query_LSR():
            return False
        if not self.dev.query_ENA_output():
            return False

        # Explicitly force the output state to off when the output got disabled
        # on a hardware level by a triggered protection or fault.
        if self.dev.state.ENA_output and self.dev.state.LSR_is_tripped:
            self.dev.state.ENA_output = False
            self.dev.set_ENA_output(False)

        if DEBUG_local:
            tock = time.perf_counter()
            dprint("%s: done in %i" % (self.dev.name, tock - tick))

        return True

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
        # Measure
        p = {"alignment": QtCore.Qt.AlignCenter, "font": FONT_MONOSPACE}
        self.V_meas = QtWid.QLabel(" 0.000 V", **p)
        self.I_meas = QtWid.QLabel(" 0.000 A", **p)
        self.P_meas = QtWid.QLabel(" 0.000 W", **p)

        # Source
        p = {"maximumWidth": 60, "alignment": QtCore.Qt.AlignRight}
        self.pbtn_ENA_output = create_Toggle_button("Output OFF")
        self.pbtn_ENA_output.clicked.connect(self.process_pbtn_ENA_output)
        self.V_source = QtWid.QLineEdit("0.000", **p)
        self.V_source.editingFinished.connect(self.send_V_source_from_textbox)
        self.I_source = QtWid.QLineEdit("0.000", **p)
        self.I_source.editingFinished.connect(self.send_I_source_from_textbox)

        # Protection
        self.OVP_level = QtWid.QLineEdit("0.0", **p)
        self.OVP_level.editingFinished.connect(self.send_OVP_level_from_textbox)
        self.OCP_level = QtWid.QLineEdit("0.00", **p)
        self.OCP_level.editingFinished.connect(self.send_OCP_level_from_textbox)

        # Trips
        # self.status_LSR_TRIP_AUX = create_tiny_error_LED()
        self.status_LSR_TRIP_SENSE = create_tiny_error_LED()
        self.status_LSR_TRIP_OTP = create_tiny_error_LED()
        self.status_LSR_TRIP_OCP = create_tiny_error_LED()
        self.status_LSR_TRIP_OVP = create_tiny_error_LED()

        # Modes
        # self.status_LSR_MODE_AUX_CC = create_tiny_error_LED()
        self.status_LSR_MODE_CC = create_tiny_error_LED()
        self.status_LSR_MODE_CV = create_tiny_error_LED()

        # Final elements
        self.pbtn_reset_trips = QtWid.QPushButton("Reset trips")
        self.pbtn_reset_trips.clicked.connect(self.process_pbtn_reset_trips)
        self.pbtn_save_settings = QtWid.QPushButton("Save settings")
        self.pbtn_save_settings.clicked.connect(self.process_pbtn_save_settings)
        self.pbtn_load_settings = QtWid.QPushButton("Load settings")
        self.pbtn_load_settings.clicked.connect(self.process_pbtn_load_settings)
        self.lbl_update_counter = QtWid.QLabel("0")

        i = 0
        p = {"alignment": QtCore.Qt.AlignLeft + QtCore.Qt.AlignVCenter}

        grid = QtWid.QGridLayout()
        grid.setVerticalSpacing(0)
        # fmt: off
        grid.addWidget(self.V_meas                          , i, 0, 1, 4); i+=1
        grid.addWidget(self.I_meas                          , i, 0, 1, 4); i+=1
        grid.addWidget(self.P_meas                          , i, 0, 1, 4); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 8)                , i, 0)      ; i+=1
        grid.addWidget(self.pbtn_ENA_output                 , i, 0, 1, 4); i+=1

        grid.addItem(QtWid.QSpacerItem(1, 10)               , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Source:")              , i, 0, 1, 4); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 4)                , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Voltage")              , i, 0, 1, 2)
        grid.addWidget(self.V_source                        , i, 2)
        grid.addWidget(QtWid.QLabel("V", **p)               , i, 3)      ; i+=1
        grid.addItem(QtWid.QSpacerItem(1, 2)                , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Current")              , i, 0, 1, 2)
        grid.addWidget(self.I_source                        , i, 2)
        grid.addWidget(QtWid.QLabel("A", **p)               , i, 3)      ; i+=1

        grid.addItem(QtWid.QSpacerItem(1, 10)               , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Protection:")          , i, 0, 1, 4); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 4)                , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("OVP")                  , i, 0, 1, 2)
        grid.addWidget(self.OVP_level                       , i, 2)
        grid.addWidget(QtWid.QLabel("V", **p)               , i, 3)      ; i+=1
        grid.addItem(QtWid.QSpacerItem(1, 2)                , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("OCP")                  , i, 0, 1, 2)
        grid.addWidget(self.OCP_level                       , i, 2)
        grid.addWidget(QtWid.QLabel("A", **p)               , i, 3)      ; i+=1

        grid.addItem(QtWid.QSpacerItem(1, 10)               , i, 0)      ; i+=1
        grid.addWidget(self.status_LSR_TRIP_OVP             , i, 0)
        grid.addWidget(QtWid.QLabel("over-voltage trip")    , i, 1, 1, 3); i+=1
        grid.addWidget(self.status_LSR_TRIP_OCP             , i, 0)
        grid.addWidget(QtWid.QLabel("over-current trip")    , i, 1, 1, 3); i+=1
        grid.addWidget(self.status_LSR_TRIP_OTP             , i, 0)
        grid.addWidget(QtWid.QLabel("over-temperature trip"), i, 1, 1, 3); i+=1
        grid.addWidget(self.status_LSR_TRIP_SENSE           , i, 0)
        grid.addWidget(QtWid.QLabel("sense trip")           , i, 1, 1, 3); i+=1

        grid.addItem(QtWid.QSpacerItem(1, 10)               , i, 0)      ; i+=1
        grid.addWidget(self.status_LSR_MODE_CV              , i, 0)
        grid.addWidget(QtWid.QLabel("constant-voltage mode"), i, 1, 1, 3); i+=1
        grid.addWidget(self.status_LSR_MODE_CC              , i, 0)
        grid.addWidget(QtWid.QLabel("constant-current mode"), i, 1, 1, 3); i+=1

        grid.addItem(QtWid.QSpacerItem(1, 10)               , i, 0)      ; i+=1
        grid.addWidget(self.pbtn_reset_trips                , i, 0, 1, 4); i+=1

        grid.addItem(QtWid.QSpacerItem(1, 10)               , i, 0)      ; i+=1
        grid.addWidget(self.pbtn_save_settings              , i, 0, 1, 4); i+=1
        grid.addWidget(self.pbtn_load_settings              , i, 0, 1, 4); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 4)                , i, 0)      ; i+=1
        grid.addWidget(self.lbl_update_counter              , i, 0, 1, 4); i+=1
        # fmt: on

        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 1)
        grid.setAlignment(QtCore.Qt.AlignTop)
        # grid.setAlignment(QtCore.Qt.AlignLeft)
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
            if self.dev.state.LSR_is_tripped:
                self.V_meas.setText("Safety")
                self.I_meas.setText("tripped")
                self.P_meas.setText("")
            else:
                self.V_meas.setText("%6.3f V" % self.dev.state.V_meas)
                self.I_meas.setText("%6.3f A" % self.dev.state.I_meas)
                self.P_meas.setText("%6.3f W" % self.dev.state.P_meas)

            self.pbtn_ENA_output.setChecked(self.dev.state.ENA_output)
            if self.pbtn_ENA_output.isChecked():
                self.pbtn_ENA_output.setText("Output ON")
            else:
                self.pbtn_ENA_output.setText("Output OFF")

            self.status_LSR_TRIP_SENSE.setChecked(self.dev.state.LSR_TRIP_SENSE)
            self.status_LSR_TRIP_OTP.setChecked(self.dev.state.LSR_TRIP_OTP)
            self.status_LSR_TRIP_OCP.setChecked(self.dev.state.LSR_TRIP_OCP)
            self.status_LSR_TRIP_OVP.setChecked(self.dev.state.LSR_TRIP_OVP)
            self.status_LSR_MODE_CC.setChecked(self.dev.state.LSR_MODE_CC)
            self.status_LSR_MODE_CV.setChecked(self.dev.state.LSR_MODE_CV)

            self.lbl_update_counter.setText("%s" % self.update_counter_DAQ)
        else:
            self.V_meas.setText("")
            self.I_meas.setText("Offline")
            self.I_meas.setAlignment(QtCore.Qt.AlignCenter)
            self.P_meas.setText("")
            self.grpb.setEnabled(False)

    # --------------------------------------------------------------------------
    #   update_GUI_input_field
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    @QtCore.pyqtSlot(int)
    def update_GUI_input_field(self, GUI_input_field=GUI_input_fields.ALL):
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

    # --------------------------------------------------------------------------
    #   GUI functions
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def process_pbtn_ENA_output(self):
        if self.pbtn_ENA_output.isChecked():
            # Clear output protection, if triggered and turn on output
            self.send(self.dev.reset_trips_and_turn_on)
        else:
            # Turn off output
            self.send(self.dev.turn_off)

    @QtCore.pyqtSlot()
    def process_pbtn_reset_trips(self):
        self.send(self.dev.reset_trips)

    @QtCore.pyqtSlot()
    def process_pbtn_save_settings(self):
        str_title = "Save settings %s" % self.dev.name
        str_msg = (
            "This will save the following settings to file:\n"
            "  - source voltage\n"
            "  - source current\n"
            "  - OVP (over-voltage protection)\n"
            "  - OCP (over-current protection)"
        )
        reply = QtWid.QMessageBox.information(
            None,
            str_title,
            str_msg,
            QtWid.QMessageBox.Cancel | QtWid.QMessageBox.Ok,
            QtWid.QMessageBox.Cancel,
        )

        if reply == QtWid.QMessageBox.Ok:
            if self.dev.write_config_file():
                QtWid.QMessageBox.information(
                    None,
                    str_title,
                    "Successfully saved to disk:\n%s" % self.dev.path_config,
                )
            else:
                QtWid.QMessageBox.critical(
                    None,
                    str_title,
                    "Failed to save to disk:\n%s" % self.dev.path_config,
                )

    @QtCore.pyqtSlot()
    def process_pbtn_load_settings(self):
        str_title = "Load settings %s" % self.dev.name
        str_msg = (
            "This will reset the power supply and\n"
            "load the following settings from file:\n"
            "  - source voltage\n"
            "  - source current\n"
            "  - OVP (over-voltage protection)\n"
            "  - OCP (over-current protection)"
        )
        reply = QtWid.QMessageBox.question(
            None,
            str_title,
            str_msg,
            QtWid.QMessageBox.Cancel | QtWid.QMessageBox.Ok,
            QtWid.QMessageBox.Cancel,
        )

        if reply == QtWid.QMessageBox.Ok:
            self.dev.read_config_file()
            self.add_to_jobs_queue(self.dev.reinitialize)
            self.add_to_jobs_queue(
                "signal_GUI_input_field_update", GUI_input_fields.ALL
            )
            self.process_jobs_queue()

    @QtCore.pyqtSlot()
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

    @QtCore.pyqtSlot()
    def send_I_source_from_textbox(self):
        try:
            current = float(self.I_source.text())
        except (TypeError, ValueError):
            current = 0.0
        except:
            raise

        if current < 0:
            current = 0

        self.add_to_jobs_queue(self.dev.set_I_source, current)
        self.add_to_jobs_queue(self.dev.query_I_source)
        self.add_to_jobs_queue(
            "signal_GUI_input_field_update", GUI_input_fields.I_source
        )
        self.process_jobs_queue()

    @QtCore.pyqtSlot()
    def send_OVP_level_from_textbox(self):
        try:
            OVP_level = float(self.OVP_level.text())
        except (TypeError, ValueError):
            OVP_level = 0.0
        except:
            raise

        self.add_to_jobs_queue(self.dev.set_OVP_level, OVP_level)
        self.add_to_jobs_queue(self.dev.query_OVP_level)
        self.add_to_jobs_queue(
            "signal_GUI_input_field_update", GUI_input_fields.OVP_level
        )
        self.process_jobs_queue()

    @QtCore.pyqtSlot()
    def send_OCP_level_from_textbox(self):
        try:
            OCP_level = float(self.OCP_level.text())
        except (TypeError, ValueError):
            OCP_level = 0.0
        except:
            raise

        self.add_to_jobs_queue(self.dev.set_OCP_level, OCP_level)
        self.add_to_jobs_queue(self.dev.query_OCP_level)
        self.add_to_jobs_queue(
            "signal_GUI_input_field_update", GUI_input_fields.OCP_level
        )
        self.process_jobs_queue()
