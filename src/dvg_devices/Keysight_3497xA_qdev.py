#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt/PySide module to provide multithreaded communication and periodical data
acquisition for a Keysight (former HP or Agilent) 34970A/34972A data
acquisition/switch unit. Different boards can be installed inside such a unit.
This library is intended to be used with multiplexer board(s), as it will
scan over the board's input channels to retrieve the readings. Hence, we also
refer to this device as a multiplexer, or mux.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "27-06-2024"
__version__ = "1.5.0"
# pylint: disable=missing-function-docstring, broad-except, multiple-statements

import time
from typing import Union, List

from qtpy import QtCore, QtGui, QtWidgets as QtWid
from qtpy.QtCore import Slot  # type: ignore

import dvg_pyqt_controls as controls
from dvg_debug_functions import dprint, print_fancy_traceback as pft
from dvg_qdeviceio import QDeviceIO, DAQ_TRIGGER
from dvg_devices.Keysight_3497xA_protocol_SCPI import Keysight_3497xA

# Monospace font
FONT_MONOSPACE = QtGui.QFont("Monospace", 12, weight=QtGui.QFont.Weight.Bold)
FONT_MONOSPACE.setStyleHint(QtGui.QFont.StyleHint.TypeWriter)

FONT_MONOSPACE_SMALL = QtGui.QFont("Monospace", 9)
FONT_MONOSPACE_SMALL.setStyleHint(QtGui.QFont.StyleHint.TypeWriter)

# Infinity cap: values reported by the 3497xA greater than this will be
# displayed as 'inf'
INFINITY_CAP = 9.8e37


class Keysight_3497xA_qdev(QDeviceIO):
    """Manages multithreaded communication and periodical data acquisition for
    a Keysight (former HP or Agilent) 34970A/34972A data acquisition/switch
    unit, referred to as the 'device'. Different boards can be installed inside
    such a unit. This library is intended to be used with multiplexer board(s),
    as it will scan over the board's input channels to retrieve the readings.
    Hence, we also refer to this device as a multiplexer, or mux.

    In addition, it also provides PyQt/PySide GUI objects for control of the
    device. These can be incorporated into your application.

    All device I/O operations will be offloaded to 'workers', each running in
    a newly created thread.

    (*): See 'dvg_qdeviceio.QDeviceIO()' for details.

    Args:
        dev:
            Reference to a
            'dvg_devices.Keysight_3497xA_protocol_SCPI.Keysight_3497xA'
            instance.

        DAQ_postprocess_MUX_data_function (optional, default=None):
            Reference to a user-supplied function that will be called during
            an 'worker_DAQ' update, after a mux scan has been performed. Hence,
            you can use this function to, e.g., parse out the scan readings into
            separate variables and post-process this data or log it.

        debug:
            Show debug info in terminal? Warning: Slow! Do not leave on
            unintentionally.

    Main methods:
        set_table_readings_format:
            TO DO: write description

    Main data attributes:
        is_MUX_scanning (read-only bool):
            True when the multiplexer is fetching new scan data every DAQ
            update, False otherwise. Do not set this variable directly. Use
            the slots 'start_MUX_scan' and 'stop_MUX_scan', instead.

    Main GUI objects:
        qgrp (PyQt5.QtWidgets.QGroupBox)

    Slots:
        start_MUX_scan():
            Enable scanning and fetching data of the multiplexer during an
            'worker_DAQ' update.

        stop_MUX_scan():
            Disable scanning and fetching data of the multiplexer during an
            'worker_DAQ' update.
    """

    def __init__(
        self,
        dev: Keysight_3497xA,
        DAQ_interval_ms=1000,
        DAQ_timer_type=QtCore.Qt.TimerType.CoarseTimer,
        critical_not_alive_count=3,
        DAQ_postprocess_MUX_scan_function=None,
        debug=False,
        **kwargs,
    ):
        super().__init__(dev, **kwargs)  # Pass kwargs onto QtCore.QObject()
        self.dev: Keysight_3497xA  # Enforce type: removes `_NoDevice()`

        self.create_worker_DAQ(
            DAQ_trigger=DAQ_TRIGGER.INTERNAL_TIMER,
            DAQ_function=self.DAQ_function,
            DAQ_interval_ms=DAQ_interval_ms,
            DAQ_timer_type=DAQ_timer_type,
            critical_not_alive_count=critical_not_alive_count,
            debug=debug,
        )

        self.create_worker_jobs(jobs_function=self.jobs_function, debug=debug)

        self.DAQ_postprocess_MUX_scan_function = (
            DAQ_postprocess_MUX_scan_function
        )
        self.is_MUX_scanning: bool = False

        # String format to use for the readings in the table widget.
        # When type is a single string, all rows will use this format.
        # When type is a list of strings, rows will be formatted consecutively.
        self.table_readings_format: Union[str, List[str]] = ".5e"

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

    @Slot()
    def start_MUX_scan(self):
        # TODO: Stop and restart the worker_DAQ timer, such that a scan is
        # immediately begun, instead of waiting for the next occuring `tick`.
        # Stopping and starting that timer should occur from within the
        # worker_DAQ thread, hence implement a `timer_restart` slot in
        # :class:`dvg-qdeviceio.Worker_DAQ`.

        self.is_MUX_scanning = True
        self.signal_DAQ_updated.emit()  # Show we are scanning
        QtWid.QApplication.processEvents()

    # --------------------------------------------------------------------------
    #   stop_scanning
    # --------------------------------------------------------------------------

    @Slot()
    def stop_MUX_scan(self):
        self.is_MUX_scanning = False
        self.signal_DAQ_updated.emit()  # Show we stopped scanning
        QtWid.QApplication.processEvents()

    # --------------------------------------------------------------------------
    #   DAQ_function
    # --------------------------------------------------------------------------

    def DAQ_function(self) -> bool:
        tick = time.perf_counter()
        print_debug = self.worker_DAQ.debug

        # Clear input and output buffers of the device. Seems to resolve
        # intermittent communication time-outs.
        if self.dev.device is not None:
            self.dev.device.clear()

        success = True
        if self.is_MUX_scanning:
            success &= self.dev.init_scan()  # Init scan

            if success:
                self.dev.wait_for_OPC()  # Wait for OPC
                if print_debug:
                    tock = time.perf_counter()
                    dprint(f"opc? in: {(tock - tick)*1000:4.0f} msec")
                    tick = tock

                success &= self.dev.fetch_scan()  # Fetch scan
                if print_debug:
                    tock = time.perf_counter()
                    dprint(f"fetc in: {(tock - tick)*1000:4.0f} msec")
                    tick = tock

            if success:
                self.dev.wait_for_OPC()  # Wait for OPC
                if print_debug:
                    tock = time.perf_counter()
                    dprint(f"opc? in: {(tock - tick)*1000:4.0f} msec")
                    tick = tock

        if success:
            # Do not throw additional timeout exceptions when .init_scan()
            # might have already failed. Hence this check for no success.
            self.dev.query_all_errors_in_queue()  # Query errors
            if print_debug:
                tock = time.perf_counter()
                dprint(f"err? in: {(tock - tick)*1000:4.0f} msec")
                tick = tock

            # The next statement seems to trigger timeout, but very
            # intermittently (~once per 20 minutes). After this timeout,
            # everything times out.
            # self.dev.wait_for_OPC()
            # if print_debug:
            #    tock = time.perf_counter()
            #    dprint(f"opc? in: {(tock - tick)*1000:4.0f} msec")
            #    tick = tock

            # NOTE: Another work-around to intermittent time-outs might
            # be sending self.dev.clear() every iter to clear the input and
            # output buffers. This is now done at the start of this function.

        # Optional user-supplied function to run. You can use this function to,
        # e.g., parse out the scan readings into separate variables and
        # post-process this data or log it.
        if self.DAQ_postprocess_MUX_scan_function is not None:
            self.DAQ_postprocess_MUX_scan_function()

        if print_debug:
            tock = time.perf_counter()
            dprint(f"extf in: {(tock - tick)*1000:4.0f} msec")
            tick = tock

        return success

    # --------------------------------------------------------------------------
    #   jobs_function
    # --------------------------------------------------------------------------

    def jobs_function(self, func, args):
        # Send I/O operation to the device
        try:
            func(*args)
            self.dev.wait_for_OPC()  # Wait for OPC
        except Exception as err:
            pft(err)

    # --------------------------------------------------------------------------
    #   create_GUI
    # --------------------------------------------------------------------------

    def create_GUI(self):
        p = {
            "alignment": QtCore.Qt.AlignmentFlag.AlignCenter,
            "font": FONT_MONOSPACE,
        }
        p2 = {
            "parent": None,
            "alignment": QtCore.Qt.AlignmentFlag(
                QtCore.Qt.AlignmentFlag.AlignCenter
                | QtCore.Qt.AlignmentFlag.AlignVCenter
            ),
        }
        # self.qlbl_mux = QtWid.QLabel("Keysight 34972a", **p2)
        self.qlbl_mux_state = QtWid.QLabel("Offline", **p)
        self.qpbt_start_scan = controls.create_Toggle_button("Start scan")

        self.qpte_SCPI_commands = QtWid.QPlainTextEdit("")
        self.qpte_SCPI_commands.setReadOnly(True)
        self.qpte_SCPI_commands.setLineWrapMode(
            QtWid.QPlainTextEdit.LineWrapMode.NoWrap
        )
        self.qpte_SCPI_commands.setStyleSheet(controls.SS_TEXTBOX_READ_ONLY)
        self.qpte_SCPI_commands.setMaximumHeight(152)
        self.qpte_SCPI_commands.setMinimumWidth(200)
        self.qpte_SCPI_commands.setFont(FONT_MONOSPACE_SMALL)

        p = {"alignment": QtCore.Qt.AlignmentFlag.AlignRight, "readOnly": True}
        self.qled_scanning_interval_ms = QtWid.QLineEdit("", **p)
        self.qled_obtained_interval_ms = QtWid.QLineEdit("", **p)

        self.qpte_errors = QtWid.QPlainTextEdit("")
        self.qpte_errors.setLineWrapMode(
            QtWid.QPlainTextEdit.LineWrapMode.NoWrap
        )
        self.qpte_errors.setStyleSheet(controls.SS_TEXTBOX_ERRORS)
        self.qpte_errors.setMaximumHeight(90)

        # fmt: off
        self.qpbt_ackn_errors    = QtWid.QPushButton("Acknowledge errors")
        self.qpbt_reinit         = QtWid.QPushButton("Reinitialize")
        self.qlbl_update_counter = QtWid.QLabel("0")
        self.qpbt_debug_test     = QtWid.QPushButton("Debug test")
        # fmt: on

        self.qpbt_start_scan.clicked.connect(self.process_qpbt_start_scan)
        self.qpbt_ackn_errors.clicked.connect(self.process_qpbt_ackn_errors)
        self.qpbt_reinit.clicked.connect(self.process_qpbt_reinit)
        self.qpbt_debug_test.clicked.connect(self.process_qpbt_debug_test)

        i = 0
        grid = QtWid.QGridLayout()
        grid.setVerticalSpacing(4)
        # fmt: off
        # grid.addWidget(self.qlbl_mux                    , i, 0, 1, 3); i+=1
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
        # grid.addWidget(self.qpbt_debug_test             , i, 0, 1, 2); i+=1
        # fmt: on

        #  Table widget containing the readings of the current scan cycle
        # ----------------------------------------------------------------
        self.qtbl_readings = QtWid.QTableWidget()
        self.qtbl_readings.setColumnCount(1)
        self.qtbl_readings.setHorizontalHeaderLabels(["Readings"])
        self.qtbl_readings.horizontalHeaderItem(0).setFont(FONT_MONOSPACE_SMALL)
        self.qtbl_readings.verticalHeader().setFont(FONT_MONOSPACE_SMALL)
        self.qtbl_readings.verticalHeader().setDefaultSectionSize(24)
        self.qtbl_readings.setFont(FONT_MONOSPACE_SMALL)
        # self.qtbl_readings.setMinimumHeight(600)
        self.qtbl_readings.setFixedWidth(180)
        self.qtbl_readings.setColumnWidth(0, 110)

        grid.addWidget(self.qtbl_readings, 0, 2, i, 1)

        self.qgrp = QtWid.QGroupBox(f"{self.dev.name}")
        self.qgrp.setLayout(grid)

    # --------------------------------------------------------------------------
    #   update_GUI
    # --------------------------------------------------------------------------

    @Slot()
    def update_GUI(self):
        """NOTE: 'self.dev.mutex' is not being locked, because we are only
        reading 'state' for displaying purposes. We can do this because 'state'
        members are written and read atomicly, with the only exception being
        'str_all_errors', and it bears no consequences to read wrongly.
        Not locking the mutex might speed up the program.
        """
        if not self.dev.is_alive:
            self.qlbl_mux_state.setText("Offline")
            self.qgrp.setEnabled(False)
            return

        if self.is_MUX_scanning:
            self.qlbl_mux_state.setText("Scanning")
            self.qpbt_start_scan.setChecked(True)
        else:
            self.qlbl_mux_state.setText("Idle")
            self.qpbt_start_scan.setChecked(False)

        self.qpte_errors.setReadOnly(self.dev.state.all_errors != [])
        self.qpte_errors.setStyleSheet(controls.SS_TEXTBOX_ERRORS)
        self.qpte_errors.setPlainText(
            f"{chr(10).join(self.dev.state.all_errors)}"
        )

        self.qled_obtained_interval_ms.setText(
            f"{self.obtained_DAQ_interval_ms:.0f}"
        )
        self.qlbl_update_counter.setText(f"{self.update_counter_DAQ}")

        for i in range(len(self.dev.state.all_scan_list_channels)):
            if i >= len(self.dev.state.readings):
                break
            reading = self.dev.state.readings[i]
            if reading > INFINITY_CAP:
                self.qtbl_readings.item(i, 0).setData(
                    QtCore.Qt.ItemDataRole.DisplayRole, "Inf"
                )
            else:
                if isinstance(self.table_readings_format, list):
                    try:
                        str_format = self.table_readings_format[i]
                    except IndexError:
                        str_format = self.table_readings_format[0]
                elif isinstance(self.table_readings_format, str):
                    str_format = self.table_readings_format

                self.qtbl_readings.item(i, 0).setData(
                    QtCore.Qt.ItemDataRole.DisplayRole,
                    f"{reading:{str_format}}",
                )

    # --------------------------------------------------------------------------
    #   populate_SCPI_commands
    # --------------------------------------------------------------------------

    def populate_SCPI_commands(self):
        self.qpte_SCPI_commands.setPlainText(
            f"{chr(10).join(self.dev.SCPI_setup_commands)}"
        )
        self.qled_scanning_interval_ms.setText(
            f"{self.worker_DAQ._DAQ_interval_ms}"  # pylint: disable=protected-access
        )

    # --------------------------------------------------------------------------
    #   Table widget related
    # --------------------------------------------------------------------------

    def populate_table_readings(self):
        self.qtbl_readings.setRowCount(
            len(self.dev.state.all_scan_list_channels)
        )
        self.qtbl_readings.setVerticalHeaderLabels(
            self.dev.state.all_scan_list_channels
        )

        for i in range(len(self.dev.state.all_scan_list_channels)):
            item = QtWid.QTableWidgetItem("nan")
            item.setTextAlignment(
                QtCore.Qt.AlignmentFlag.AlignRight
                | QtCore.Qt.AlignmentFlag.AlignCenter
            )
            self.qtbl_readings.setItem(i, 0, item)

    def set_table_readings_format(self, format_str: str):
        # String format to use for the readings in the table widget.
        # When type is a single string, all rows will use this format.
        # When type is a list of strings, rows will be formatted consecutively.
        # I.e. format_str = ".2f", or format_str = [".2f", ".1e"]

        # Backwards compatibility fix. We have to remove any '%' characters that
        # the end-user might have supplied when using the old-style formatting
        # using %. The old `format_str` argument used "%.2f", for example. We
        # now rely on f-strings for formatting.
        format_str = format_str.replace("%", "")

        self.table_readings_format = format_str

    # --------------------------------------------------------------------------
    #   GUI functions
    # --------------------------------------------------------------------------

    @Slot()
    def process_qpbt_start_scan(self):
        if self.qpbt_start_scan.isChecked():
            self.start_MUX_scan()
        else:
            self.stop_MUX_scan()

    @Slot()
    def process_qpbt_ackn_errors(self):
        # Lock the dev mutex because string operations are not atomic
        locker = QtCore.QMutexLocker(self.dev.mutex)  # type: ignore
        self.dev.state.all_errors = []
        self.qpte_errors.setPlainText("")
        self.qpte_errors.setReadOnly(False)  # To change back to regular colors
        locker.unlock()

    @Slot()
    def process_qpbt_reinit(self):
        title = f"Reinitialize {self.dev.name}"
        msg = (
            "Are you sure you want reinitialize the multiplexer?\n\n"
            "This would abort the current scan, reset the device\n"
            "and resend the SCPI scan command list."
        )
        msgbox = QtWid.QMessageBox()
        msgbox.setIcon(QtWid.QMessageBox.Icon.Question)
        msgbox.setWindowTitle(title)
        msgbox.setText(msg)
        msgbox.setStandardButtons(
            QtWid.QMessageBox.StandardButton.Yes
            | QtWid.QMessageBox.StandardButton.No
        )
        msgbox.setDefaultButton(QtWid.QMessageBox.StandardButton.No)
        reply = msgbox.exec()

        if reply == QtWid.QMessageBox.StandardButton.Yes:
            self.qpbt_start_scan.setChecked(False)
            self.stop_MUX_scan()
            self.add_to_jobs_queue(self.dev.wait_for_OPC)
            self.add_to_jobs_queue(self.dev.begin)
            self.process_jobs_queue()

    @Slot()
    def process_qpbt_debug_test(self):
        self.send(self.dev.write, "junk")
