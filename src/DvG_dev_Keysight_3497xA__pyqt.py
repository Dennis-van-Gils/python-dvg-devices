#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt5 module to provide multithreaded communication and periodical data
acquisition for a Keysight (former HP or Agilent) 34970A/34972A data
acquisition/switch unit. Different boards can be installed inside such a unit.
This library is intended to be used with multiplexer board(s), as it will
scan over the board's input channels to retrieve the readings. Hence, we also
refer to this device as a multiplexer, or mux.
"""
__author__      = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__         = ""
__date__        = "18-09-2018"
__version__     = "1.0.0"

from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets as QtWid

from DvG_pyqt_controls import (create_Toggle_button,
                               SS_TEXTBOX_ERRORS,
                               SS_TEXTBOX_READ_ONLY,
                               SS_GROUP)
from DvG_debug_functions import dprint, print_fancy_traceback as pft

import DvG_dev_Keysight_3497xA__fun_SCPI as K3497xA_functions
import DvG_dev_Base__pyqt_lib            as Dev_Base_pyqt_lib

# Monospace font
FONT_MONOSPACE = QtGui.QFont("Monospace", 12, weight=QtGui.QFont.Bold)
FONT_MONOSPACE.setStyleHint(QtGui.QFont.TypeWriter)

FONT_MONOSPACE_SMALL = QtGui.QFont("Monospace", 9)
FONT_MONOSPACE_SMALL.setStyleHint(QtGui.QFont.TypeWriter)

# Infinity cap: values reported by the 3497xA greater than this will be
# displayed as 'inf'
INFINITY_CAP = 9.8e37

# Short-hand alias for DEBUG information
def get_tick(): return QtCore.QDateTime.currentMSecsSinceEpoch()

# Show debug info in terminal? Warning: Slow! Do not leave on unintentionally.
DEBUG_worker_DAQ  = False
DEBUG_worker_send = False

# ------------------------------------------------------------------------------
#   K3497xA_pyqt
# ------------------------------------------------------------------------------

class K3497xA_pyqt(Dev_Base_pyqt_lib.Dev_Base_pyqt, QtCore.QObject):
    """Manages multithreaded communication and periodical data acquisition for
    a Keysight (former HP or Agilent) 34970A/34972A data acquisition/switch
    unit, referred to as the 'device'. Different boards can be installed inside
    such a unit. This library is intended to be used with multiplexer board(s),
    as it will scan over the board's input channels to retrieve the readings.
    Hence, we also refer to this device as a multiplexer, or mux.

    In addition, it also provides PyQt5 GUI objects for control of the device.
    These can be incorporated into your application.

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
            Reference to a 'DvG_dev_Keysight_3497xA__fun_SCPI.K3497xA' instance.

        (*) DAQ_update_interval_ms
        (*) DAQ_critical_not_alive_count
        (*) DAQ_timer_type

        DAQ_postprocess_MUX_data_function (optional, default=None):
            Reference to a user-supplied function that will be called during
            an 'worker_DAQ' update, after a mux scan has been performed. Hence,
            you can use this function to, e.g., parse out the scan readings into
            separate variables and post-process this data or log it.

    Main methods:
        (*) start_thread_worker_DAQ(...)
        (*) start_thread_worker_send(...)
        (*) close_all_threads()

        set_table_readings_format:
            TO DO: write description

    Inner-class instances:
        (*) worker_DAQ
        (*) worker_send

    Main data attributes:
        is_MUX_scanning (read-only bool):
            True when the multiplexer is fetching new scan data every DAQ
            update, False otherwise. Do not set this variable directly. Use
            the slots 'start_MUX_scan' and 'stop_MUX_scan', instead.

    Main GUI objects:
        qgrp (PyQt5.QtWidgets.QGroupBox)

    Signals:
        (*) signal_DAQ_updated()
        (*) signal_connection_lost()

    Slots:
        start_MUX_scan():
            Enable scanning and fetching data of the multiplexer during an
            'worker_DAQ' update.

        stop_MUX_scan():
            Disable scanning and fetching data of the multiplexer during an
            'worker_DAQ' update.
    """
    def __init__(self,
                 dev: K3497xA_functions.K3497xA,
                 DAQ_update_interval_ms=1000,
                 DAQ_critical_not_alive_count=3,
                 DAQ_timer_type=QtCore.Qt.CoarseTimer,
                 DAQ_postprocess_MUX_scan_function=None,
                 parent=None):
        super(K3497xA_pyqt, self).__init__(parent=parent)

        self.attach_device(dev)

        self.create_worker_DAQ(
                DAQ_update_interval_ms=DAQ_update_interval_ms,
                DAQ_function_to_run_each_update=self.DAQ_update,
                DAQ_critical_not_alive_count=DAQ_critical_not_alive_count,
                DAQ_timer_type=DAQ_timer_type,
                DEBUG=DEBUG_worker_DAQ)

        self.create_worker_send(
                alt_process_jobs_function=self.alt_process_jobs_function,
                DEBUG=DEBUG_worker_send)

        self.DAQ_postprocess_MUX_scan_function = (
                DAQ_postprocess_MUX_scan_function)
        self.is_MUX_scanning = False

        # String format to use for the readings in the table widget.
        # When type is a single string, all rows will use this format.
        # When type is a list of strings, rows will be formatted consecutively.
        self.table_readings_format = "%.3e"

        self.create_GUI()
        self.signal_DAQ_updated.connect(self.update_GUI)

        # Populate the table view with QTableWidgetItems.
        # I.e. add the correct number of rows to the table depending on the
        # full scan list.
        self.populate_table_readings()

        # Populate the textbox with the SCPI setup commands
        self.populate_SCPI_commands()

        # Update GUI immediately, instead of waiting for the first refresh
        self.update_GUI()

    # --------------------------------------------------------------------------
    #   start_scanning
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def start_MUX_scan(self):
        """
        # [DISABLED CODE]
        # Recreate the worker timer and acquire new samples immediately,
        # instead of waiting for the next tick to occur of the 'old' timer.
        # NOTE: Would love to stop the old timer first, but for some strange
        # reason the very first Qtimer appears to be running in another
        # thread than the 'worker_state' thread, eventhough the routine in
        # K3497xA_pyqt.__init__ has finished moving the worker_state thread.
        # When timer is running in another thread than 'this' one, an
        # exception is thrown py Python saying we can't stop the timer from
        # another thread. Hence, I reassign a new Qtimer and hope that the
        # old timer is garbage collected all right.
        self.timer.stop()  # Does not work 100% of the time!
        """

        self.is_MUX_scanning = True
        self.signal_DAQ_updated.emit()      # Show we are scanning
        QtWid.QApplication.processEvents()

        """
        # [DISABLED CODE]
        # Disabled the recreation of the timer, because of not
        # understood behavior. The first time iteration of every newly
        # created QTimer seems to be running in the MAIN thread while
        # subsequent iterations take place in the Worker_state thread.
        # This might lead to program instability? Not sure. Simply disabled
        # for now.
        self.timer = QtCore.QTimer()            # Create new timer
        self.timer.setInterval(self.scanning_interval_ms)
        self.timer.timeout.connect(self.update)
        self.timer.start()
        self.update()  # Kickstart at t = 0, because timer doesn't fire now
        """

    # --------------------------------------------------------------------------
    #   stop_scanning
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def stop_MUX_scan(self):
        self.is_MUX_scanning = False
        self.signal_DAQ_updated.emit()      # Show we stopped scanning
        QtWid.QApplication.processEvents()

    # --------------------------------------------------------------------------
    #   DAQ_update
    # --------------------------------------------------------------------------

    def DAQ_update(self):
        tick = get_tick()

        # Clear input and output buffers of the device. Seems to resolve
        # intermittent communication time-outs.
        self.dev.device.clear()

        success = True
        if self.is_MUX_scanning:
            success &= self.dev.init_scan()                 # Init scan

            if success:
                self.dev.wait_for_OPC()                     # Wait for OPC
                if self.worker_DAQ.DEBUG:
                    tock = get_tick()
                    dprint("opc? in: %i" % (tock - tick))
                    tick = tock

                success &= self.dev.fetch_scan()            # Fetch scan
                if self.worker_DAQ.DEBUG:
                    tock = get_tick()
                    dprint("fetc in: %i" % (tock - tick))
                    tick = tock

            if success:
                self.dev.wait_for_OPC()                     # Wait for OPC
                if self.worker_DAQ.DEBUG:
                    tock = get_tick()
                    dprint("opc? in: %i" % (tock - tick))
                    tick = tock

        if success:
            # Do not throw additional timeout exceptions when .init_scan()
            # might have already failed. Hence this check for no success.
            self.dev.query_all_errors_in_queue()            # Query errors
            if self.worker_DAQ.DEBUG:
                tock = get_tick()
                dprint("err? in: %i" % (tock - tick))
                tick = tock

            # The next statement seems to trigger timeout, but very
            # intermittently (~once per 20 minutes). After this timeout,
            # everything times out.
            #self.dev.wait_for_OPC()
            #if self.worker_DAQ.DEBUG:
            #    tock = get_tick()
            #    dprint("opc? in: %i" % (tock - tick))
            #    tick = tock

            # NOTE: Another work-around to intermittent time-outs might
            # be sending self.dev.clear() every iter to clear the input and
            # output buffers. This is now done at the start of this function.

        # Optional user-supplied function to run. You can use this function to,
        # e.g., parse out the scan readings into separate variables and
        # post-process this data or log it.
        if not (self.DAQ_postprocess_MUX_scan_function is None):
            self.DAQ_postprocess_MUX_scan_function()

        if self.worker_DAQ.DEBUG:
            tock = get_tick()
            dprint("extf in: %i" % (tock - tick))
            tick = tock

        return success

    # --------------------------------------------------------------------------
    #   alt_process_jobs_function
    # --------------------------------------------------------------------------

    def alt_process_jobs_function(self, func, args):
        # Send I/O operation to the device
        try:
            func(*args)
            self.dev.wait_for_OPC()                         # Wait for OPC
        except Exception as err:
            pft(err)

    # --------------------------------------------------------------------------
    #   create_GUI
    # --------------------------------------------------------------------------

    def create_GUI(self):
        p = {'alignment': QtCore.Qt.AlignCenter, 'font': FONT_MONOSPACE}
        p2 = {'alignment': QtCore.Qt.AlignCenter + QtCore.Qt.AlignVCenter}
        #self.qlbl_mux = QtWid.QLabel("Keysight 34972a", **p2)
        self.qlbl_mux_state = QtWid.QLabel("Offline", **p)
        self.qpbt_start_scan = create_Toggle_button("Start scan")

        self.qpte_SCPI_commands = QtWid.QPlainTextEdit('', readOnly=True,
                                                       lineWrapMode=False)
        self.qpte_SCPI_commands.setStyleSheet(SS_TEXTBOX_READ_ONLY)
        self.qpte_SCPI_commands.setMaximumHeight(152)
        self.qpte_SCPI_commands.setMinimumWidth(200)
        self.qpte_SCPI_commands.setFont(FONT_MONOSPACE_SMALL)

        p = {'alignment': QtCore.Qt.AlignRight, 'readOnly': True}
        self.qled_scanning_interval_ms = QtWid.QLineEdit("", **p)
        self.qled_obtained_interval_ms = QtWid.QLineEdit("", **p)

        self.qpte_errors = QtWid.QPlainTextEdit('', lineWrapMode=False)
        self.qpte_errors.setStyleSheet(SS_TEXTBOX_ERRORS)
        self.qpte_errors.setMaximumHeight(90)

        self.qpbt_ackn_errors    = QtWid.QPushButton("Acknowledge errors")
        self.qpbt_reinit         = QtWid.QPushButton("Reinitialize")
        self.qlbl_update_counter = QtWid.QLabel("0")
        self.qpbt_debug_test     = QtWid.QPushButton("Debug test")

        self.qpbt_start_scan.clicked.connect(self.process_qpbt_start_scan)
        self.qpbt_ackn_errors.clicked.connect(self.process_qpbt_ackn_errors)
        self.qpbt_reinit.clicked.connect(self.process_qpbt_reinit)
        self.qpbt_debug_test.clicked.connect(self.process_qpbt_debug_test)

        i = 0
        p = {'alignment': QtCore.Qt.AlignLeft + QtCore.Qt.AlignVCenter}

        grid = QtWid.QGridLayout()
        grid.setVerticalSpacing(4)
        #grid.addWidget(self.qlbl_mux                      , i, 0, 1, 3); i+=1
        grid.addWidget(QtWid.QLabel("Only scan when necessary.", **p2)
                                                          , i, 0, 1, 2); i+=1
        grid.addWidget(QtWid.QLabel("It wears down the multiplexer.", **p2)
                                                          , i, 0, 1, 2); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 3)              , i, 0)      ; i+=1
        grid.addWidget(self.qlbl_mux_state                , i, 0, 1, 2); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 3)              , i, 0)      ; i+=1
        grid.addWidget(self.qpbt_start_scan               , i, 0, 1, 2); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 4)              , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("SCPI scan commands:"), i, 0, 1, 2); i+=1
        grid.addWidget(self.qpte_SCPI_commands            , i, 0, 1, 2); i+=1
        grid.addWidget(QtWid.QLabel("Scanning interval [ms]"), i, 0)
        grid.addWidget(self.qled_scanning_interval_ms     , i, 1)      ; i+=1
        grid.addWidget(QtWid.QLabel("Obtained [ms]")      , i, 0)
        grid.addWidget(self.qled_obtained_interval_ms     , i, 1)      ; i+=1
        grid.addWidget(self.qpbt_reinit                   , i, 0, 1, 2); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 12)             , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Errors:")            , i, 0, 1, 2); i+=1
        grid.addWidget(self.qpte_errors                   , i, 0, 1, 2); i+=1
        grid.addWidget(self.qpbt_ackn_errors              , i, 0, 1, 2); i+=1
        grid.addWidget(self.qlbl_update_counter           , i, 0, 1, 2); i+=1
        #grid.addWidget(self.qpbt_debug_test               , i, 0, 1, 2); i+=1

        #  Table widget containing the readings of the current scan cycle
        # ----------------------------------------------------------------
        self.qtbl_readings = QtWid.QTableWidget(columnCount=1)
        self.qtbl_readings.setHorizontalHeaderLabels(["Readings"])
        self.qtbl_readings.horizontalHeaderItem(0).setFont(FONT_MONOSPACE_SMALL)
        self.qtbl_readings.verticalHeader().setFont(FONT_MONOSPACE_SMALL)
        self.qtbl_readings.verticalHeader().setDefaultSectionSize(24);
        self.qtbl_readings.setFont(FONT_MONOSPACE_SMALL)
        #self.qtbl_readings.setMinimumHeight(600)
        self.qtbl_readings.setFixedWidth(180)
        self.qtbl_readings.setColumnWidth(0, 100)

        grid.addWidget(self.qtbl_readings, 0, 2, i, 1)

        self.qgrp = QtWid.QGroupBox("%s" % self.dev.name)
        self.qgrp.setStyleSheet(SS_GROUP)
        self.qgrp.setLayout(grid)

    # --------------------------------------------------------------------------
    #   update_GUI
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def update_GUI(self):
        """NOTE: 'self.dev.mutex' is not being locked, because we are only
        reading 'state' for displaying purposes. We can do this because 'state'
        members are written and read atomicly, with the only exception being
        'str_all_errors', and it bears no consequences to read wrongly.
        Not locking the mutex might speed up the program.
        """
        if self.dev.is_alive:
            if (self.is_MUX_scanning):
                self.qlbl_mux_state.setText("Scanning")
                self.qpbt_start_scan.setChecked(True)
            else:
                self.qlbl_mux_state.setText("Idle")
                self.qpbt_start_scan.setChecked(False)

            self.qpte_errors.setReadOnly(self.dev.state.all_errors != [])
            self.qpte_errors.setStyleSheet(SS_TEXTBOX_ERRORS)
            self.qpte_errors.setPlainText(
                    "%s" % '\n'.join(self.dev.state.all_errors))

            self.qled_obtained_interval_ms.setText(
                    "%.0f" % self.obtained_DAQ_update_interval_ms)
            self.qlbl_update_counter.setText("%s" % self.DAQ_update_counter)

            for i in range(len(self.dev.state.all_scan_list_channels)):
                if i >= len(self.dev.state.readings):
                    break
                reading = self.dev.state.readings[i]
                if reading > INFINITY_CAP:
                    self.qtbl_readings.item(i, 0).setData(
                            QtCore.Qt.DisplayRole, "Inf")
                else:
                    if type(self.table_readings_format) == list:
                        try:
                            str_format = self.table_readings_format[i]
                        except IndexError:
                            str_format = self.table_readings_format[0]
                    elif type(self.table_readings_format) == str:
                        str_format = self.table_readings_format

                    self.qtbl_readings.item(i, 0).setData(
                            QtCore.Qt.DisplayRole, str_format % reading)
        else:
            self.qlbl_mux_state.setText("Offline")
            self.qgrp.setEnabled(False)

    # --------------------------------------------------------------------------
    #   populate_SCPI_commands
    # --------------------------------------------------------------------------

    def populate_SCPI_commands(self):
        self.qpte_SCPI_commands.setPlainText(
                "%s" % '\n'.join(self.dev.SCPI_setup_commands))
        self.qled_scanning_interval_ms.setText(
                "%i" % self.worker_DAQ.update_interval_ms)

    # --------------------------------------------------------------------------
    #   Table widget related
    # --------------------------------------------------------------------------

    def populate_table_readings(self):
        self.qtbl_readings.setRowCount(
                len(self.dev.state.all_scan_list_channels))
        self.qtbl_readings.setVerticalHeaderLabels(
                self.dev.state.all_scan_list_channels)

        for i in range(len(self.dev.state.all_scan_list_channels)):
            item = QtWid.QTableWidgetItem("nan")
            item.setTextAlignment(QtCore.Qt.AlignRight + QtCore.Qt.AlignCenter)
            self.qtbl_readings.setItem(i, 0, item)

    def set_table_readings_format(self, format_str):
        # String format to use for the readings in the table widget
        # When type is a single string, all rows will use this format.
        # When type is a list of strings, rows will be formatted consecutively.
        self.table_readings_format = format_str

    # --------------------------------------------------------------------------
    #   GUI functions
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def process_qpbt_start_scan(self):
        if self.qpbt_start_scan.isChecked():
            self.start_MUX_scan()
        else:
            self.stop_MUX_scan()

    @QtCore.pyqtSlot()
    def process_qpbt_ackn_errors(self):
        # Lock the dev mutex because string operations are not atomic
        locker = QtCore.QMutexLocker(self.dev.mutex)
        self.dev.state.all_errors = []
        self.qpte_errors.setPlainText('')
        self.qpte_errors.setReadOnly(False) # To change back to regular colors
        locker.unlock()

    @QtCore.pyqtSlot()
    def process_qpbt_reinit(self):
        str_msg = ("Are you sure you want reinitialize the multiplexer?\n\n"
                   "This would abort the current scan, reset the device\n"
                   "and resend the SCPI scan command list.")
        reply = QtWid.QMessageBox.question(None,
                ("Reinitialize %s" % self.dev.name), str_msg,
                QtWid.QMessageBox.Yes | QtWid.QMessageBox.No,
                QtWid.QMessageBox.No)

        if reply == QtWid.QMessageBox.Yes:
            self.qpbt_start_scan.setChecked(False)
            self.stop_MUX_scan()
            self.worker_send.add_to_queue(self.dev.wait_for_OPC)
            self.worker_send.add_to_queue(self.dev.begin)
            self.worker_send.process_queue()

    @QtCore.pyqtSlot()
    def process_qpbt_debug_test(self):
        self.worker_send.queued_instruction(self.dev.write, "junk")
