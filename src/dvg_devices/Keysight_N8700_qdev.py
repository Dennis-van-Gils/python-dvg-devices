#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt5 module to provide multithreaded communication and periodical data
acquisition for a Keysight N8700 power supply (PSU).
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "23-07-2020"
__version__ = "0.2.2"

import numpy as np

from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets as QtWid

from dvg_pyqt_controls import (
    create_Toggle_button,
    create_tiny_error_LED,
    SS_TEXTBOX_ERRORS,
    SS_GROUP,
)
from dvg_debug_functions import dprint, print_fancy_traceback as pft
from dvg_pid_controller import PID_Controller

from dvg_qdeviceio import QDeviceIO, DAQ_TRIGGER
from dvg_devices.Keysight_N8700_protocol_SCPI import Keysight_N8700

# Monospace font
FONT_MONOSPACE = QtGui.QFont("Monospace", 12, weight=QtGui.QFont.Bold)
FONT_MONOSPACE.setStyleHint(QtGui.QFont.TypeWriter)

# Enumeration
class GUI_input_fields:
    [ALL, OVP_level, V_source, I_source, P_source] = range(5)


# Short-hand alias for DEBUG information
def get_tick():
    return QtCore.QDateTime.currentMSecsSinceEpoch()


class Keysight_N8700_qdev(QDeviceIO):
    """Manages multithreaded communication and periodical data acquisition for
    a Keysight N8700 power supply (PSU), referred to as the 'device'.

    In addition, it also provides PyQt5 GUI objects for control of the device.
    These can be incorporated into your application.

    All device I/O operations will be offloaded to 'workers', each running in
    a newly created thread.

    (*): See 'dvg_qdeviceio.QDeviceIO()' for details.

    Args:
        dev:
            Reference to a
            'dvg_devices.Keysight_N8700_protocol_SCPI.Keysight_N8700'
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
        dev: Keysight_N8700,
        DAQ_trigger=DAQ_TRIGGER.INTERNAL_TIMER,
        DAQ_interval_ms=200,
        DAQ_timer_type=QtCore.Qt.CoarseTimer,
        critical_not_alive_count=1,
        debug=False,
        **kwargs,
    ):
        super().__init__(dev, **kwargs)  # Pass kwargs onto QtCore.QObject()

        # Add PID controller on the power output
        # DvG, 25-06-2018: Kp=0.5, Ki=2, Kd=0
        self.dev.PID_power = PID_Controller(Kp=0.5, Ki=2, Kd=0)

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
        self.signal_GUI_input_field_update.connect(self.update_GUI_input_field)
        self.connect_signals_to_slots()

        self.update_GUI()
        self.update_GUI_input_field()

    # --------------------------------------------------------------------------
    #   DAQ_function
    # --------------------------------------------------------------------------

    def DAQ_function(self):
        DEBUG_local = False
        if DEBUG_local:
            tick = get_tick()

        # Clear input and output buffers of the device. Seems to resolve
        # intermittent communication time-outs.
        self.dev.device.clear()

        # Finish all operations at the device first
        if not self.dev.wait_for_OPC():
            return False

        if not self.dev.query_V_meas():
            return False
        if not self.dev.query_I_meas():
            return False

        # --------------------
        #   Heater power PID
        # --------------------
        # PID controllers work best when the process and control variables have
        # a linear relationship.
        # Here:
        #   Process var: V (voltage)
        #   Control var: P (power)
        #   Relation   : P = R / V^2
        #
        # Hence, we transform P into P_star
        #   Control var: P_star = sqrt(P)
        #   Relation   : P_star = sqrt(R) / V
        # When we assume R remains constant (which is not the case as the
        # resistance is a function of the heater temperature, but the dependence
        # is expected to be insignificant in our small temperature range of 20
        # to 100 deg C), we now have linearized the PID feedback relation.
        self.dev.PID_power.set_mode(
            (self.dev.state.ENA_output and self.dev.state.ENA_PID),
            self.dev.state.P_meas,
            self.dev.state.V_source,
        )

        self.dev.PID_power.setpoint = np.sqrt(self.dev.state.P_source)
        if self.dev.PID_power.compute(np.sqrt(self.dev.state.P_meas)):
            # New PID output got computed -> send new voltage to PSU
            if self.dev.PID_power.output < 1:
                # PSU does not regulate well below 1 V, hence clamp to 0
                self.dev.PID_power.output = 0
            if not self.dev.set_V_source(self.dev.PID_power.output):
                return False
            # Wait for the set_V_source operation to finish.
            # Takes ~ 300 ms to complete with wait_for_OPC.
            if not self.dev.wait_for_OPC():
                return False

        if not self.dev.query_ENA_OCP():
            return False
        if not self.dev.query_status_OC():
            return False
        if not self.dev.query_status_QC():
            return False
        if not self.dev.query_ENA_output():
            return False

        # Explicitly force the output state to off when the output got disabled
        # on a hardware level by a triggered protection or fault.
        if self.dev.state.ENA_output & (
            self.dev.state.status_QC_OV
            | self.dev.state.status_QC_OC
            | self.dev.state.status_QC_PF
            | self.dev.state.status_QC_OT
            | self.dev.state.status_QC_INH
        ):
            self.dev.state.ENA_output = False
            self.dev.set_ENA_output(False)

        if DEBUG_local:
            tock = get_tick()
            dprint("%s: done in %i" % (self.dev.name, tock - tick))

        # Check if there are errors in the device queue and retrieve all
        # if any and append these to 'dev.state.all_errors'.
        if DEBUG_local:
            dprint("%s: query errors" % self.dev.name)
            tick = get_tick()
        self.dev.query_all_errors_in_queue()
        if DEBUG_local:
            tock = get_tick()
            dprint("%s: stb done in %i" % (self.dev.name, tock - tick))

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
        p = {"alignment": QtCore.Qt.AlignRight, "font": FONT_MONOSPACE}
        self.V_meas = QtWid.QLabel("0.00  V   ", **p)
        self.I_meas = QtWid.QLabel("0.000 A   ", **p)
        self.P_meas = QtWid.QLabel("0.00  W   ", **p)

        # Source
        p = {"maximumWidth": 60, "alignment": QtCore.Qt.AlignRight}
        self.pbtn_ENA_output = create_Toggle_button("Output OFF")
        self.V_source = QtWid.QLineEdit("0.00", **p)
        self.I_source = QtWid.QLineEdit("0.000", **p)
        self.P_source = QtWid.QLineEdit("0.00", **p)
        self.pbtn_ENA_PID = create_Toggle_button(
            "OFF", minimumHeight=28, minimumWidth=60
        )

        # Protection
        self.OVP_level = QtWid.QLineEdit("0.000", **p)
        self.pbtn_ENA_OCP = create_Toggle_button(
            "OFF", minimumHeight=28, minimumWidth=60
        )

        # Questionable condition status registers
        self.status_QC_OV = create_tiny_error_LED()
        self.status_QC_OC = create_tiny_error_LED()
        self.status_QC_PF = create_tiny_error_LED()
        self.status_QC_OT = create_tiny_error_LED()
        self.status_QC_INH = create_tiny_error_LED()
        self.status_QC_UNR = create_tiny_error_LED()

        # Operation condition status registers
        self.status_OC_WTG = create_tiny_error_LED()
        self.status_OC_CV = create_tiny_error_LED()
        self.status_OC_CC = create_tiny_error_LED()

        # Final elements
        self.errors = QtWid.QLineEdit("")
        self.errors.setStyleSheet(SS_TEXTBOX_ERRORS)
        self.pbtn_ackn_errors = QtWid.QPushButton("Acknowledge errors")
        self.pbtn_reinit = QtWid.QPushButton("Reinitialize")
        self.pbtn_save_defaults = QtWid.QPushButton("Save")
        self.pbtn_debug_test = QtWid.QPushButton("Debug test")
        self.lbl_update_counter = QtWid.QLabel("0")

        i = 0
        p = {"alignment": QtCore.Qt.AlignLeft + QtCore.Qt.AlignVCenter}

        grid = QtWid.QGridLayout()
        grid.setVerticalSpacing(0)
        # fmt: off
        grid.addWidget(self.V_meas                       , i, 0, 1, 4); i+=1
        grid.addWidget(self.I_meas                       , i, 0, 1, 4); i+=1
        grid.addWidget(self.P_meas                       , i, 0, 1, 4); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 8)             , i, 0)      ; i+=1
        grid.addWidget(self.pbtn_ENA_output              , i, 0, 1, 4); i+=1

        grid.addItem(QtWid.QSpacerItem(1, 10)            , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Source:")           , i, 0, 1, 4); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 4)             , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Voltage")           , i, 0, 1, 2)
        grid.addWidget(self.V_source                     , i, 2)
        grid.addWidget(QtWid.QLabel("V", **p)            , i, 3)      ; i+=1
        grid.addItem(QtWid.QSpacerItem(1, 2)             , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Current")           , i, 0, 1, 2)
        grid.addWidget(self.I_source                     , i, 2)
        grid.addWidget(QtWid.QLabel("A", **p)            , i, 3)      ; i+=1
        grid.addItem(QtWid.QSpacerItem(1, 2)             , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Power PID")         , i, 0, 1, 2)
        grid.addWidget(self.pbtn_ENA_PID                 , i, 2,
                                                  QtCore.Qt.AlignLeft); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 2)             , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Power")             , i, 0, 1, 2)
        grid.addWidget(self.P_source                     , i, 2)
        grid.addWidget(QtWid.QLabel("W", **p)            , i, 3)      ; i+=1

        grid.addItem(QtWid.QSpacerItem(1, 10)            , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Protection:")       , i, 0, 1, 4); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 4)             , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("OVP")               , i, 0, 1, 2)
        grid.addWidget(self.OVP_level                    , i, 2)
        grid.addWidget(QtWid.QLabel("V", **p)            , i, 3)      ; i+=1
        grid.addItem(QtWid.QSpacerItem(1, 2)             , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("OCP")               , i, 0, 1, 2)
        grid.addWidget(self.pbtn_ENA_OCP                 , i, 2,
                                                  QtCore.Qt.AlignLeft); i+=1

        grid.addItem(QtWid.QSpacerItem(1, 10)            , i, 0)      ; i+=1
        grid.addWidget(self.status_QC_OV                 , i, 0)
        grid.addWidget(QtWid.QLabel("OV")                , i, 1)
        grid.addWidget(QtWid.QLabel("| over-voltage")    , i, 2, 1, 2); i+=1
        grid.addWidget(self.status_QC_OC                 , i, 0)
        grid.addWidget(QtWid.QLabel("OC")                , i, 1)
        grid.addWidget(QtWid.QLabel("| over-current")    , i, 2, 1, 2); i+=1
        grid.addWidget(self.status_QC_PF                 , i, 0)
        grid.addWidget(QtWid.QLabel("PF")                , i, 1)
        grid.addWidget(QtWid.QLabel("| AC power failure"), i, 2, 1, 2); i+=1
        grid.addWidget(self.status_QC_OT                 , i, 0)
        grid.addWidget(QtWid.QLabel("OT")                , i, 1)
        grid.addWidget(QtWid.QLabel("| over-temperature"), i, 2, 1, 2); i+=1
        grid.addWidget(self.status_QC_INH                , i, 0)
        grid.addWidget(QtWid.QLabel("INH")               , i, 1)
        grid.addWidget(QtWid.QLabel("| output inhibited"), i, 2, 1, 2); i+=1
        grid.addWidget(self.status_QC_UNR                , i, 0)
        grid.addWidget(QtWid.QLabel("UNR")               , i, 1)
        grid.addWidget(QtWid.QLabel("| unregulated")     , i, 2, 1, 2); i+=1

        grid.addItem(QtWid.QSpacerItem(1, 10)            , i, 0)      ; i+=1
        grid.addWidget(self.status_OC_WTG                , i, 0)
        grid.addWidget(QtWid.QLabel("WTG")               , i, 1)
        grid.addWidget(QtWid.QLabel("| waiting for trigger"), i, 2, 1, 2); i+=1
        grid.addWidget(self.status_OC_CV                 , i, 0)
        grid.addWidget(QtWid.QLabel("CV")                , i, 1)
        grid.addWidget(QtWid.QLabel("| constant voltage"), i, 2, 1, 2); i+=1
        grid.addWidget(self.status_OC_CC                 , i, 0)
        grid.addWidget(QtWid.QLabel("CC")                , i, 1)
        grid.addWidget(QtWid.QLabel("| constant current"), i, 2, 1, 2); i+=1

        grid.addItem(QtWid.QSpacerItem(1, 10)            , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Errors")            , i, 0, 1, 2)
        grid.addWidget(self.errors                       , i, 2, 1, 2); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 4)             , i, 0)      ; i+=1
        grid.addWidget(self.pbtn_ackn_errors             , i, 0, 1, 4); i+=1

        hbox = QtWid.QHBoxLayout()
        hbox.addWidget(self.pbtn_save_defaults)
        hbox.addWidget(self.pbtn_reinit)
        grid.addLayout(hbox                              , i, 0, 1, 4); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 4)             , i, 0)      ; i+=1
        grid.addWidget(self.lbl_update_counter           , i, 0, 1, 4); i+=1
        # grid.addWidget(self.pbtn_debug_test              , i, 0, 1, 4); i+=1
        # fmt: on

        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 1)
        grid.setAlignment(QtCore.Qt.AlignTop)
        # grid.setAlignment(QtCore.Qt.AlignLeft)
        self.grid = grid

        self.grpb = QtWid.QGroupBox("%s" % self.dev.name)
        self.grpb.setStyleSheet(SS_GROUP)
        self.grpb.setLayout(self.grid)

    # --------------------------------------------------------------------------
    #   update_GUI
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def update_GUI(self):
        """NOTE: 'self.dev.mutex' is not being locked, because we are only
        reading 'state' for displaying purposes. We can do this because 'state'
        members are written and read atomicly, with the only exception being
        'all_errors', and it bears no consequences to read wrongly.
        Not locking the mutex might speed up the program.
        """
        if self.dev.is_alive:
            if self.dev.state.ENA_PID:
                self.pbtn_ENA_PID.setChecked(True)
                self.pbtn_ENA_PID.setText("ON")
                self.V_source.setReadOnly(True)
                self.V_source.setText("%.2f" % self.dev.state.V_source)
            else:
                self.pbtn_ENA_PID.setChecked(False)
                self.pbtn_ENA_PID.setText("OFF")
                self.V_source.setReadOnly(False)

            if self.dev.state.status_QC_INH:
                self.V_meas.setText("")
                self.I_meas.setText("Inhibited")
                self.I_meas.setAlignment(QtCore.Qt.AlignCenter)
                self.P_meas.setText("")
            else:
                # fmt: off
                self.V_meas.setText("%.2f  V   " % self.dev.state.V_meas)
                self.I_meas.setText("%.3f A   "  % self.dev.state.I_meas)
                self.I_meas.setAlignment(QtCore.Qt.AlignRight)
                self.P_meas.setText("%.2f  W   " % self.dev.state.P_meas)
                # fmt: on

            self.pbtn_ENA_output.setChecked(self.dev.state.ENA_output)
            if self.pbtn_ENA_output.isChecked():
                self.pbtn_ENA_output.setText("Output ON")
            else:
                self.pbtn_ENA_output.setText("Output OFF")

            self.pbtn_ENA_OCP.setChecked(self.dev.state.ENA_OCP)
            if self.pbtn_ENA_OCP.isChecked():
                self.pbtn_ENA_OCP.setText("ON")
            else:
                self.pbtn_ENA_OCP.setText("OFF")

            self.status_QC_OV.setChecked(self.dev.state.status_QC_OV)
            self.status_QC_OC.setChecked(self.dev.state.status_QC_OC)
            self.status_QC_PF.setChecked(self.dev.state.status_QC_PF)
            self.status_QC_OT.setChecked(self.dev.state.status_QC_OT)
            self.status_QC_INH.setChecked(self.dev.state.status_QC_INH)
            self.status_QC_UNR.setChecked(self.dev.state.status_QC_UNR)

            self.status_OC_WTG.setChecked(self.dev.state.status_OC_WTG)
            self.status_OC_CV.setChecked(self.dev.state.status_OC_CV)
            self.status_OC_CC.setChecked(self.dev.state.status_OC_CC)

            self.errors.setReadOnly(self.dev.state.all_errors != [])
            self.errors.setText("%s" % ";".join(self.dev.state.all_errors))

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
        if GUI_input_field == GUI_input_fields.OVP_level:
            self.OVP_level.setText("%.2f" % self.dev.state.OVP_level)
            self.dev.PID_power.set_output_limits(
                0, self.dev.state.OVP_level * 0.95
            )

        elif GUI_input_field == GUI_input_fields.V_source:
            self.V_source.setText("%.2f" % self.dev.state.V_source)

        elif GUI_input_field == GUI_input_fields.I_source:
            self.I_source.setText("%.3f" % self.dev.state.I_source)

        elif GUI_input_field == GUI_input_fields.P_source:
            self.P_source.setText("%.2f" % self.dev.state.P_source)

        else:
            self.OVP_level.setText("%.2f" % self.dev.state.OVP_level)
            self.dev.PID_power.set_output_limits(
                0, self.dev.state.OVP_level * 0.95
            )

            self.V_source.setText("%.2f" % self.dev.state.V_source)
            self.I_source.setText("%.3f" % self.dev.state.I_source)
            self.P_source.setText("%.2f" % self.dev.state.P_source)

    # --------------------------------------------------------------------------
    #   GUI functions
    # --------------------------------------------------------------------------

    def process_pbtn_ENA_output(self):
        if self.pbtn_ENA_output.isChecked():
            # Clear output protection, if triggered and turn on output
            self.send(self.dev.clear_output_protection_and_turn_on)
        else:
            # Turn off output
            self.send(self.dev.turn_off)

    def process_pbtn_ENA_PID(self):
        self.dev.state.ENA_PID = self.pbtn_ENA_PID.isChecked()

    def process_pbtn_ENA_OCP(self):
        self.send(self.dev.set_ENA_OCP, self.pbtn_ENA_OCP.isChecked())

    def process_pbtn_ackn_errors(self):
        # Lock the dev mutex because string operations are not atomic
        locker = QtCore.QMutexLocker(self.dev.mutex)
        self.dev.state.all_errors = []
        self.errors.setText("")
        self.errors.setReadOnly(False)  # To change back to regular colors
        locker.unlock()

    def process_pbtn_reinit(self):
        str_msg = "Are you sure you want reinitialize the power supply?"
        reply = QtWid.QMessageBox.question(
            None,
            ("Reinitialize %s" % self.dev.name),
            str_msg,
            QtWid.QMessageBox.Yes | QtWid.QMessageBox.No,
            QtWid.QMessageBox.No,
        )

        if reply == QtWid.QMessageBox.Yes:
            self.dev.read_config_file()
            self.add_to_jobs_queue(self.dev.reinitialize)
            self.add_to_jobs_queue(
                "signal_GUI_input_field_update", GUI_input_fields.ALL
            )
            self.process_jobs_queue()

            self.dev.state.ENA_PID = False

    def process_pbtn_save_defaults(self):
        str_title = "Save defaults %s" % self.dev.name
        str_msg = (
            "Are you sure you want to save the current values:\n\n"
            "  - Source voltage\n"
            "  - Source current\n"
            "  - Source power\n"
            "  - OVP\n"
            "  - OCP\n\n"
            "as default?\n"
            "These will then automatically be loaded next time."
        )
        reply = QtWid.QMessageBox.question(
            None,
            str_title,
            str_msg,
            QtWid.QMessageBox.Yes | QtWid.QMessageBox.No,
            QtWid.QMessageBox.No,
        )

        if reply == QtWid.QMessageBox.Yes:
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

    def process_pbtn_debug_test(self):
        pass

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

    def set_P_source_from_textbox(self):
        try:
            power = float(self.P_source.text())
        except (TypeError, ValueError):
            power = 0.0
        except:
            raise

        if power < 0:
            power = 0
        self.dev.state.P_source = power
        self.update_GUI_input_field(GUI_input_fields.P_source)

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

    # --------------------------------------------------------------------------
    #   connect_signals_to_slots
    # --------------------------------------------------------------------------

    def connect_signals_to_slots(self):
        self.pbtn_ENA_output.clicked.connect(self.process_pbtn_ENA_output)
        self.pbtn_ENA_PID.clicked.connect(self.process_pbtn_ENA_PID)
        self.pbtn_ENA_OCP.clicked.connect(self.process_pbtn_ENA_OCP)
        self.pbtn_ackn_errors.clicked.connect(self.process_pbtn_ackn_errors)
        self.pbtn_reinit.clicked.connect(self.process_pbtn_reinit)
        self.pbtn_save_defaults.clicked.connect(self.process_pbtn_save_defaults)
        self.pbtn_debug_test.clicked.connect(self.process_pbtn_debug_test)

        self.V_source.editingFinished.connect(self.send_V_source_from_textbox)
        self.I_source.editingFinished.connect(self.send_I_source_from_textbox)
        self.P_source.editingFinished.connect(self.set_P_source_from_textbox)
        self.OVP_level.editingFinished.connect(self.send_OVP_level_from_textbox)
