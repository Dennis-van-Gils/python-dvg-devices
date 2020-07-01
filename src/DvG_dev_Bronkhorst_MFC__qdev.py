#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt5 module to provide multithreaded communication and periodical data
acquisition for a Bronkhorst mass flow controller (MFC).
"""
__author__      = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__         = ""
__date__        = "18-09-2018"
__version__     = "1.0.0"

from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets as QtWid
from PyQt5.QtCore import QDateTime

from DvG_pyqt_controls import SS_GROUP, SS_TEXTBOX_READ_ONLY
from DvG_debug_functions import print_fancy_traceback as pft

import DvG_dev_Bronkhorst_MFC__fun_RS232 as mfc_functions
import DvG_dev_Base__pyqt_lib            as Dev_Base_pyqt_lib

# Show debug info in terminal? Warning: Slow! Do not leave on unintentionally.
DEBUG_worker_DAQ  = False
DEBUG_worker_send = False

# ------------------------------------------------------------------------------
#   Bronkhorst_MFC_pyqt
# ------------------------------------------------------------------------------

class Bronkhorst_MFC_pyqt(Dev_Base_pyqt_lib.Dev_Base_pyqt, QtCore.QObject):
    """Manages multithreaded communication and periodical data acquisition for
    a Bronkhorst mass flow controller (MFC), referred to as the 'device'.

    In addition, it also provides PyQt5 GUI objects for control of the device.
    These can be incorporated into your application.

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
    a newly created thread instead of in the main/GUI thread.

        - Worker_DAQ:
            Periodically acquires data from the device.

        - Worker_send:
            Maintains a thread-safe queue where desired device I/O operations
            can be put onto, and sends the queued operations first in first out
            (FIFO) to the device.

    (*): See 'DvG_dev_Base__pyqt_lib.py' for details.

    Args:
        dev:
            Reference to a 'DvG_dev_Bronkhorst_MFC__fun_RS232.Bronkhorst_MFC'
            instance.

        (*) DAQ_update_interval_ms
        (*) DAQ_critical_not_alive_count
        (*) DAQ_timer_type

        valve_auto_close_deadtime_period_ms (optional, default=3000):
            Deadtime period in milliseconds of the auto close signal after a
            setpoint > 0 has been send.

    Main methods:
        (*) start_thread_worker_DAQ(...)
        (*) start_thread_worker_send(...)
        (*) close_all_threads()

    Inner-class instances:
        (*) worker_DAQ
        (*) worker_send

    Main data attributes:
        (*) DAQ_update_counter
        (*) obtained_DAQ_update_interval_ms
        (*) obtained_DAQ_rate_Hz

    Main GUI objects:
        qgrp (PyQt5.QtWidgets.QGroupBox)

    Signals:
        (*) signal_DAQ_updated()
        (*) signal_connection_lost()
        signal_valve_auto_close()
        signal_valve_auto_open()
    """
    signal_valve_auto_close = QtCore.pyqtSignal()
    signal_valve_auto_open  = QtCore.pyqtSignal()

    def __init__(self,
                 dev: mfc_functions.Bronkhorst_MFC,
                 DAQ_update_interval_ms=200,
                 DAQ_critical_not_alive_count=1,
                 DAQ_timer_type=QtCore.Qt.CoarseTimer,
                 valve_auto_close_deadtime_period_ms=3000,
                 parent=None):
        super(Bronkhorst_MFC_pyqt, self).__init__(parent=parent)

        self.attach_device(dev)

        self.create_worker_DAQ(DAQ_update_interval_ms,
                               self.DAQ_update,
                               DAQ_critical_not_alive_count,
                               DAQ_timer_type,
                               DEBUG=DEBUG_worker_DAQ)

        self.create_worker_send(self.alt_process_jobs_function,
                                DEBUG=DEBUG_worker_send)

        self.create_GUI()
        self.signal_DAQ_updated.connect(self.update_GUI)
        if not self.dev.is_alive:
            self.update_GUI()  # Correctly reflect an offline device

        # Auto open or close of an optional peripheral valve
        self.dev.state.prev_flow_rate = self.dev.state.flow_rate
        self.dev.valve_auto_close_briefly_prevent = False
        self.dev.valve_auto_close_deadtime_period_ms = \
            valve_auto_close_deadtime_period_ms
        self.dev.valve_auto_close_start_deadtime  = 0

    # --------------------------------------------------------------------------
    #   DAQ_update
    # --------------------------------------------------------------------------

    def DAQ_update(self):
        success = self.dev.query_setpoint()
        success &= self.dev.query_flow_rate()

        if success:
            # Check to signal auto open or close of an optional peripheral valve
            if (self.dev.state.flow_rate == 0 and not
                self.dev.state.prev_flow_rate == self.dev.state.flow_rate):
                # The flow rate has just dropped to 0
                if (self.dev.valve_auto_close_briefly_prevent and
                    self.dev.valve_auto_close_start_deadtime.msecsTo(
                            QDateTime.currentDateTime())
                    < self.dev.valve_auto_close_deadtime_period_ms):
                    # We are still in deadtime
                    pass
                else:
                    # Signal auto close and force setpoint = 0
                    self.signal_valve_auto_close.emit()
                    self.dev.send_setpoint(0)
                    self.dev.valve_auto_close_briefly_prevent = False
                    self.dev.state.prev_flow_rate = self.dev.state.flow_rate
            else:
                self.dev.state.prev_flow_rate = self.dev.state.flow_rate

        return success

    # --------------------------------------------------------------------------
    #   alt_process_jobs_function
    # --------------------------------------------------------------------------

    def alt_process_jobs_function(self, func, args):
        # Send I/O operation to the device
        try:
            func(*args)
        except Exception as err:
            pft(err)

        # Check to signal auto open or close of an optional peripheral valve
        if func == self.dev.send_setpoint:
            if args[0] == 0:
                # Setpoint was set to 0 --> signal auto close
                self.dev.valve_auto_close_briefly_prevent = False
                self.signal_valve_auto_close.emit()
            else:
                # Flow enabled --> start deadtime on auto close
                #              --> signal auto open
                self.dev.valve_auto_close_briefly_prevent = True
                self.dev.valve_auto_close_start_deadtime = \
                    QDateTime.currentDateTime()
                self.dev.state.prev_flow_rate = -1  # Necessary reset
                self.signal_valve_auto_open.emit()

    # --------------------------------------------------------------------------
    #   create_GUI
    # --------------------------------------------------------------------------

    def create_GUI(self):
        self.qlbl_offline = QtWid.QLabel("MFC OFFLINE", visible=False,
            font=QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Bold),
            alignment=QtCore.Qt.AlignCenter)

        p = {'alignment': QtCore.Qt.AlignRight,
             'minimumWidth': 50,
             'maximumWidth': 30,
             'styleSheet': SS_TEXTBOX_READ_ONLY}
        self.qled_send_setpoint  = QtWid.QLineEdit(**p)
        self.qled_read_setpoint  = QtWid.QLineEdit(**p, readOnly=True)
        self.qled_flow_rate      = QtWid.QLineEdit(**p, readOnly=True)
        self.qlbl_update_counter = QtWid.QLabel("0")

        self.qled_send_setpoint.editingFinished.connect(
                self.send_setpoint_from_textbox)

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

        self.qgrp = QtWid.QGroupBox("%s" % self.dev.name)
        self.qgrp.setStyleSheet(SS_GROUP)
        self.qgrp.setLayout(self.grid)

    # --------------------------------------------------------------------------
    #   update_GUI
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def update_GUI(self):
        """NOTE: 'self.dev.mutex' is not being locked, because we are only
        reading 'state' for displaying purposes. We can do this because 'state'
        members are written and read atomicly.
        Not locking the mutex might speed up the program.
        """
        if self.dev.is_alive:
            # At startup
            if self.DAQ_update_counter == 1:
                self.qled_send_setpoint.setText("%.2f" %
                                                self.dev.state.setpoint)
            self.qled_flow_rate.setText("%.2f" % self.dev.state.flow_rate)
            self.qled_read_setpoint.setText("%.2f" % self.dev.state.setpoint)
            self.qlbl_update_counter.setText("%s" % self.DAQ_update_counter)
        else:
            self.qgrp.setEnabled(False)
            self.qlbl_offline.setVisible(True)

    # --------------------------------------------------------------------------
    #   GUI functions
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def send_setpoint_from_textbox(self):
        try:
            setpoint = float(self.qled_send_setpoint.text())
        except (TypeError, ValueError):
            setpoint = 0.0
        except:
            raise()

        setpoint = max(setpoint, 0)
        setpoint = min(setpoint, self.dev.max_flow_rate)
        self.qled_send_setpoint.setText("%.2f" % setpoint)

        self.worker_send.queued_instruction(self.dev.send_setpoint, setpoint)
