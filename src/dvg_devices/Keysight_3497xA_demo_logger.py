#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt/PySide GUI to interface with a Keysight (former HP or
Agilent) 34970A/34972A data acquisition/switch unit.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "21-01-2025"
__version__ = "1.5.1"
print(__url__)
# pylint: disable=wrong-import-position, missing-function-docstring, bare-except

import sys
import time

import qtpy
from qtpy import QtCore, QtGui, QtWidgets as QtWid
from qtpy.QtCore import Slot  # type: ignore

import pyvisa
import matplotlib.pyplot as plt
import numpy as np
import pyqtgraph as pg

from dvg_pyqtgraph_threadsafe import (
    ThreadSafeCurve,
    HistoryChartCurve,
    LegendSelect,
    PlotManager,
)
import dvg_pyqt_controls as controls
from dvg_pyqt_filelogger import FileLogger
from dvg_devices.Keysight_3497xA_protocol_SCPI import Keysight_3497xA
from dvg_devices.Keysight_3497xA_qdev import Keysight_3497xA_qdev, INFINITY_CAP

TRY_USING_OPENGL = True
if TRY_USING_OPENGL:
    try:
        import OpenGL.GL as gl  # pylint: disable=unused-import
    except:  # pylint: disable=bare-except
        print("OpenGL acceleration: Disabled")
        print("To install: `conda install pyopengl` or `pip install pyopengl`")
    else:
        print("OpenGL acceleration: Enabled")
        pg.setConfigOptions(useOpenGL=True)
        pg.setConfigOptions(antialias=True)
        pg.setConfigOptions(enableExperimental=True)

# Global pyqtgraph configuration
# pg.setConfigOptions(leftButtonPan=False)
pg.setConfigOption("foreground", "#EEE")

# VISA address of the Keysight 3497xA data acquisition/switch unit containing a
# multiplexer plug-in module. Hence, we simply call this device a 'mux'.
# MUX_VISA_ADDRESS = "USB0::0x0957::0x2007::MY49018071::INSTR"
MUX_VISA_ADDRESS = "GPIB0::9::INSTR"

# SCPI commands to be send to the mux to set up the scan cycle.
"""
scan_list = "(@101:110)"
MUX_SCPI_COMMANDS = [
            f"rout:open {scan_list}",
            f"conf:temp TC,J,{scan_list}",
            f"unit:temp C,{scan_list}",
            f"sens:temp:tran:tc:rjun:type INT,{scan_list}",
            f"sens:temp:tran:tc:check ON,{scan_list}",
            f"sens:temp:nplc 1,{scan_list}",
            f"rout:scan {scan_list}",
]
"""

scan_list = "(@101:110)"
MUX_SCPI_COMMANDS = [
    f"rout:open {scan_list}",
    f"conf:res 1e6,{scan_list}",
    f"sens:res:nplc 1,{scan_list}",
    f"rout:scan {scan_list}",
]

# fmt: off
DAQ_INTERVAL_MS   = 1000  # [ms] Update interval for the mux to perform a scan
CHART_INTERVAL_MS = 1000  # [ms] Update interval for all charts
CHART_CAPACITY    = 1800  # [samples]
# fmt: on

# Show debug info in terminal? Warning: Slow! Do not leave on unintentionally.
DEBUG = False

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(
        self,
        qdev: Keysight_3497xA_qdev,
        qlog: FileLogger,
        parent=None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)

        self.qdev = qdev
        self.qlog = qlog

        self.setWindowTitle("Keysight 3497xA control")
        self.setGeometry(40, 60, 1200, 0)
        self.setFont(QtGui.QFont("Arial", 9))
        self.setStyleSheet(
            controls.SS_TEXTBOX_READ_ONLY
            + controls.SS_GROUP
            + controls.SS_HOVER
        )

        self.timer_GUI = QtCore.QTimer()
        self.timer_GUI.timeout.connect(self.update_GUI)

        # ----------------------------------------------------------------------
        #   Top grid
        # ----------------------------------------------------------------------

        self.qlbl_title = QtWid.QLabel("Keysight 3497xA control")
        self.qlbl_title.setFont(
            QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Weight.Bold)
        )
        self.qlbl_cur_date_time = QtWid.QLabel("00-00-0000    00:00:00")
        self.qpbt_record = controls.create_Toggle_button(
            "Click to start recording to file", minimumHeight=40
        )
        self.qpbt_record.setMinimumWidth(400)
        # fmt: off
        self.qpbt_record.clicked.connect(lambda state: qlog.record(state))  # pylint: disable=unnecessary-lambda
        # fmt: on

        self.qpbt_exit = QtWid.QPushButton("Exit")
        self.qpbt_exit.clicked.connect(self.close)
        self.qpbt_exit.setMinimumHeight(30)

        grid_top = QtWid.QGridLayout()
        # fmt: off
        grid_top.addWidget(self.qlbl_title        , 0, 0, QtCore.Qt.AlignmentFlag.AlignCenter)
        grid_top.addWidget(self.qpbt_exit         , 0, 2, QtCore.Qt.AlignmentFlag.AlignRight)
        grid_top.addWidget(self.qlbl_cur_date_time, 1, 0, QtCore.Qt.AlignmentFlag.AlignCenter)
        grid_top.addWidget(self.qpbt_record       , 2, 0, QtCore.Qt.AlignmentFlag.AlignCenter)
        # fmt: on
        grid_top.setColumnMinimumWidth(0, 420)
        grid_top.setColumnStretch(1, 1)

        # ----------------------------------------------------------------------
        #   Chart: Mux readings
        # ----------------------------------------------------------------------

        # GraphicsLayoutWidget
        self.gw_mux = pg.GraphicsLayoutWidget()

        p = {"color": "#EEE", "font-size": "12pt"}
        self.pi_mux = self.gw_mux.addPlot()
        self.pi_mux.setClipToView(True)
        self.pi_mux.showGrid(x=1, y=1)
        self.pi_mux.setTitle("Mux readings", **p)
        self.pi_mux.setLabel("bottom", "history (min)", **p)
        self.pi_mux.setLabel("left", "misc. units", **p)
        self.pi_mux.setMenuEnabled(True)
        self.pi_mux.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
        self.pi_mux.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
        self.pi_mux.setAutoVisible(y=True)

        # ----------------------------------------------------------------------
        #   Create history charts depending on the number of scan channels
        # ----------------------------------------------------------------------

        self.tscurves_mux: list[ThreadSafeCurve] = []

        cm = plt.get_cmap("gist_rainbow")
        for idx, channel in enumerate(qdev.dev.state.all_scan_list_channels):
            color = cm(1.0 * idx / qdev.dev.state.N_channels)  # RGBA tuple
            color = np.array(color) * 255
            pen = pg.mkPen(color=color, width=2)

            self.tscurves_mux.append(
                HistoryChartCurve(
                    capacity=CHART_CAPACITY,
                    linked_curve=self.pi_mux.plot(pen=pen, name=channel),
                )
            )

        # ----------------------------------------------------------------------
        #   Legend
        # ----------------------------------------------------------------------

        legend = LegendSelect(linked_curves=self.tscurves_mux)
        legend.grid.setVerticalSpacing(0)

        self.qgrp_legend = QtWid.QGroupBox("Legend")
        self.qgrp_legend.setLayout(legend.grid)

        # ----------------------------------------------------------------------
        #   PlotManager
        # ----------------------------------------------------------------------

        self.plot_manager = PlotManager(parent=self)
        self.plot_manager.add_autorange_buttons(linked_plots=self.pi_mux)
        self.plot_manager.add_preset_buttons(
            linked_plots=self.pi_mux,
            linked_curves=self.tscurves_mux,
            presets=[
                {
                    "button_label": "0:30",
                    "x_axis_label": "history (sec)",
                    "x_axis_divisor": 1,
                    "x_axis_range": (-30, 0),
                },
                {
                    "button_label": "01:00",
                    "x_axis_label": "history (sec)",
                    "x_axis_divisor": 1,
                    "x_axis_range": (-60, 0),
                },
                {
                    "button_label": "03:00",
                    "x_axis_label": "history (min)",
                    "x_axis_divisor": 60,
                    "x_axis_range": (-3, 0),
                },
                {
                    "button_label": "05:00",
                    "x_axis_label": "history (min)",
                    "x_axis_divisor": 60,
                    "x_axis_range": (-5, 0),
                },
                {
                    "button_label": "10:00",
                    "x_axis_label": "history (min)",
                    "x_axis_divisor": 60,
                    "x_axis_range": (-10, 0),
                },
                {
                    "button_label": "30:00",
                    "x_axis_label": "history (min)",
                    "x_axis_divisor": 60,
                    "x_axis_range": (-30, 0),
                },
            ],
        )
        self.plot_manager.add_clear_button(linked_curves=self.tscurves_mux)

        qgrp_history = QtWid.QGroupBox("History")
        qgrp_history.setLayout(self.plot_manager.grid)

        # ----------------------------------------------------------------------
        #   Right-panel grid
        # ----------------------------------------------------------------------

        vbox1 = QtWid.QVBoxLayout()
        vbox1.addWidget(
            self.qgrp_legend,
            stretch=0,
            alignment=QtCore.Qt.AlignmentFlag.AlignTop,
        )
        vbox1.addWidget(
            qgrp_history,
            stretch=0,
            alignment=QtCore.Qt.AlignmentFlag.AlignTop,
        )
        vbox1.addStretch(1)

        # ----------------------------------------------------------------------
        #   Round up full window
        # ----------------------------------------------------------------------

        hbox1 = QtWid.QHBoxLayout()
        hbox1.addWidget(
            qdev.qgrp,
            stretch=0,
            alignment=QtCore.Qt.AlignmentFlag.AlignTop,
        )
        hbox1.addWidget(self.gw_mux, stretch=1)
        hbox1.addLayout(vbox1)

        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(grid_top)
        vbox.addLayout(hbox1)
        vbox.addStretch(1)

    # --------------------------------------------------------------------------
    #   Handle controls
    # --------------------------------------------------------------------------

    @Slot()
    def update_GUI(self):
        cur_date_time = QtCore.QDateTime.currentDateTime()
        self.qlbl_cur_date_time.setText(
            cur_date_time.toString("dd-MM-yyyy")
            + "    "
            + cur_date_time.toString("HH:mm:ss")
        )

        # Update curves
        for tscurve in self.tscurves_mux:
            tscurve.update()


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":

    # --------------------------------------------------------------------------
    #   Connect to Keysight 3497xA (mux)
    # --------------------------------------------------------------------------

    rm = pyvisa.ResourceManager()
    mux = Keysight_3497xA(MUX_VISA_ADDRESS, "MUX")

    try:
        if mux.connect(rm, visa_timeout=4000):
            mux.begin(MUX_SCPI_COMMANDS)
    except ValueError as e:
        # No connection could be made to the VISA device because module
        # dependencies are missing. Print error, not raise and continue to
        # show the GUI.
        print(e)

    # --------------------------------------------------------------------------
    #   Create application
    # --------------------------------------------------------------------------

    main_thread = QtCore.QThread.currentThread()
    if isinstance(main_thread, QtCore.QThread):
        main_thread.setObjectName("MAIN")  # For DEBUG info

    if qtpy.PYQT6 or qtpy.PYSIDE6:
        sys.argv += ["-platform", "windows:darkmode=0"]
    app = QtWid.QApplication(sys.argv)
    app.setStyle("Fusion")

    # --------------------------------------------------------------------------
    #   Set up communication threads for the mux
    # --------------------------------------------------------------------------

    def postprocess_mux_fun():
        """Will be called during an 'worker_DAQ' update, after a mux scan has
        been performed. We use it to parse out the scan readings into separate
        variables and log it to file.
        """
        cur_date_time = QtCore.QDateTime.currentDateTime()
        now = time.perf_counter()

        # DEBUG info
        # dprint(f"thread: {QtCore.QThread.currentThread().objectName()}")

        if mux_qdev.is_MUX_scanning:
            readings = mux.state.readings
            for idx in range(mux.state.N_channels):
                if readings[idx] > INFINITY_CAP:
                    readings[idx] = np.nan
        else:
            readings = [np.nan] * mux.state.N_channels
            mux.state.readings = readings

        # Add readings to charts
        for idx, tscurve in enumerate(window.tscurves_mux):
            tscurve.appendData(now, readings[idx])

        # Log data to file
        log.update(
            filepath=f"data_mux_{cur_date_time.toString('yyMMdd_HHmmss')}.txt",
            mode="w",
        )

    mux_qdev = Keysight_3497xA_qdev(
        dev=mux,
        DAQ_interval_ms=DAQ_INTERVAL_MS,
        DAQ_postprocess_MUX_scan_function=postprocess_mux_fun,
        debug=DEBUG,
    )
    # mux_qdev.set_table_readings_format(".5e")
    mux_qdev.start()

    # --------------------------------------------------------------------------
    #   File logger
    # --------------------------------------------------------------------------

    def write_header_to_log():
        ch_labels = [f"CH{ch}" for ch in mux.state.all_scan_list_channels]
        log.write("time [s]\t")
        log.write(f"{chr(9).join(ch_labels)}")  # [TAB]-delimited
        log.write("\n")

    def write_data_to_log():
        log.write(f"{log.elapsed():.3f}")
        for idx, _ch in enumerate(mux.state.all_scan_list_channels):
            if len(mux.state.readings) <= idx:
                log.write(f"\t{np.nan:.5e}")
            else:
                log.write(f"\t{mux.state.readings[idx]:.5e}")
        log.write("\n")

    log = FileLogger(
        write_header_function=write_header_to_log,
        write_data_function=write_data_to_log,
    )
    log.signal_recording_started.connect(
        lambda filepath: window.qpbt_record.setText(
            f"Recording to file: {filepath}"
        )
    )
    log.signal_recording_stopped.connect(
        lambda: window.qpbt_record.setText("Click to start recording to file")
    )

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    def about_to_quit():
        print("About to quit")
        app.processEvents()
        mux_qdev.quit()
        try:
            mux.close()
        except:
            pass
        try:
            rm.close()
        except:
            pass

    app.aboutToQuit.connect(about_to_quit)

    window = MainWindow(qdev=mux_qdev, qlog=log)
    window.plot_manager.perform_preset(2)  # Init time axis of the history chart
    window.timer_GUI.start(CHART_INTERVAL_MS)
    window.show()

    sys.exit(app.exec())
