#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt/PySide GUI to interface with a Keysight (former HP or
Agilent) 34970A/34972A data acquisition/switch unit.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "28-10-2022"
__version__ = "1.0.0"
# pylint: disable=bare-except

import os
import sys
import time

# Mechanism to support both PyQt and PySide
# -----------------------------------------

PYQT5 = "PyQt5"
PYQT6 = "PyQt6"
PYSIDE2 = "PySide2"
PYSIDE6 = "PySide6"
QT_LIB_ORDER = [PYQT5, PYSIDE2, PYSIDE6, PYQT6]
QT_LIB = None

# Parse optional cli argument to enfore a QT_LIB
# cli example: python benchmark.py pyside6
if len(sys.argv) > 1:
    arg1 = str(sys.argv[1]).upper()
    for i, lib in enumerate(QT_LIB_ORDER):
        if arg1 == lib.upper():
            QT_LIB = lib
            break

if QT_LIB is None:
    for lib in QT_LIB_ORDER:
        if lib in sys.modules:
            QT_LIB = lib
            break

if QT_LIB is None:
    for lib in QT_LIB_ORDER:
        try:
            __import__(lib)
            QT_LIB = lib
            break
        except ImportError:
            pass

if QT_LIB is None:
    this_file = __file__.split(os.sep)[-1]
    raise ImportError(
        f"{this_file} requires PyQt5, PyQt6, PySide2 or PySide6; "
        "none of these packages could be imported."
    )

# fmt: off
# pylint: disable=import-error, no-name-in-module
if QT_LIB == PYQT5:
    from PyQt5 import QtCore, QtGui, QtWidgets as QtWid    # type: ignore
    from PyQt5.QtCore import pyqtSlot as Slot              # type: ignore
elif QT_LIB == PYQT6:
    from PyQt6 import QtCore, QtGui, QtWidgets as QtWid    # type: ignore
    from PyQt6.QtCore import pyqtSlot as Slot              # type: ignore
elif QT_LIB == PYSIDE2:
    from PySide2 import QtCore, QtGui, QtWidgets as QtWid  # type: ignore
    from PySide2.QtCore import Slot                        # type: ignore
elif QT_LIB == PYSIDE6:
    from PySide6 import QtCore, QtGui, QtWidgets as QtWid  # type: ignore
    from PySide6.QtCore import Slot                        # type: ignore
# pylint: enable=import-error, no-name-in-module
# fmt: on

# \end[Mechanism to support both PyQt and PySide]
# -----------------------------------------------

import pyvisa
import matplotlib.pyplot as plt
import numpy as np
import pyqtgraph as pg

from dvg_pyqtgraph_threadsafe import (
    HistoryChartCurve,
    LegendSelect,
    PlotManager,
)
from dvg_pyqt_controls import (
    create_Toggle_button,
    SS_TEXTBOX_READ_ONLY,
    SS_GROUP,
)
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


# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setWindowTitle("Keysight 3497xA control")
        self.setGeometry(600, 120, 1200, 600)
        self.setStyleSheet(SS_TEXTBOX_READ_ONLY + SS_GROUP)

        # ----------------------------------------------------------------------
        #   Top grid
        # ----------------------------------------------------------------------

        self.qlbl_title = QtWid.QLabel(
            "Keysight 3497xA control",
            font=QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Weight.Bold),
        )
        self.qlbl_cur_date_time = QtWid.QLabel("00-00-0000    00:00:00")
        self.qpbt_record = create_Toggle_button(
            "Click to start recording to file", minimumHeight=40
        )
        self.qpbt_record.setMinimumWidth(400)
        # fmt: off
        self.qpbt_record.clicked.connect(lambda state: log.record(state))  # pylint: disable=unnecessary-lambda
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

        # Placeholder to be populated depending on the number of scan channels
        self.tscurves_mux = list()  # List of `HistoryChartCurve`

        # ----------------------------------------------------------------------
        #   Legend
        # ----------------------------------------------------------------------

        self.qgrp_legend = QtWid.QGroupBox("Legend")

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
            qgrp_history, stretch=0, alignment=QtCore.Qt.AlignmentFlag.AlignTop
        )
        vbox1.addStretch(1)

        # ----------------------------------------------------------------------
        #   Round up full window
        # ----------------------------------------------------------------------

        hbox1 = QtWid.QHBoxLayout()
        hbox1.addWidget(
            mux_qdev.qgrp, stretch=0, alignment=QtCore.Qt.AlignmentFlag.AlignTop
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
#   about_to_quit
# ------------------------------------------------------------------------------


def about_to_quit():
    print("About to quit")
    app.processEvents()
    mux_qdev.quit()
    log.close()

    try:
        mux.close()
    except:
        pass
    try:
        rm.close()
    except:
        pass


# ------------------------------------------------------------------------------
#   DAQ_postprocess_MUX_scan_function
# ------------------------------------------------------------------------------


def DAQ_postprocess_MUX_scan_function():
    """Will be called during an 'worker_DAQ' update, after a mux scan has been
    performed. We use it to parse out the scan readings into separate variables
    and log it to file.
    """
    cur_date_time = QtCore.QDateTime.currentDateTime()
    now = time.perf_counter()

    # DEBUG info
    # dprint("thread: %s" % QtCore.QThread.currentThread().objectName())

    if mux_qdev.is_MUX_scanning:
        readings = mux.state.readings
        for idx in range(N_channels):
            if readings[idx] > INFINITY_CAP:
                readings[idx] = np.nan
    else:
        readings = [np.nan] * N_channels
        mux.state.readings = readings

    # Add readings to charts
    for idx, tscurve in enumerate(window.tscurves_mux):
        tscurve.appendData(now, readings[idx])

    # Log data to file
    log.update(
        filepath="d:/data/mux_%s.txt" % cur_date_time.toString("yyMMdd_HHmmss"),
        mode="w",
    )


# ------------------------------------------------------------------------------
#   File logging
# ------------------------------------------------------------------------------


def write_header_to_log():
    log.write("time [s]\t")
    for i_ in range(N_channels - 1):
        log.write("CH%s\t" % mux.state.all_scan_list_channels[i_])
    log.write("CH%s\n" % mux.state.all_scan_list_channels[-1])


def write_data_to_log():
    log.write("%.3f" % log.elapsed())
    for i_ in range(N_channels):
        if len(mux.state.readings) <= i_:
            log.write("\t%.5e" % np.nan)
        else:
            log.write("\t%.5e" % mux.state.readings[i_])
    log.write("\n")


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # VISA address of the Keysight 3497xA data acquisition/switch unit
    # containing a multiplexer plug-in module. Hence, we simply call this device
    # a 'mux'.
    # MUX_VISA_ADDRESS = "USB0::0x0957::0x2007::-::INSTR"
    MUX_VISA_ADDRESS = "GPIB0::9::INSTR"

    # A scan will be performed by the mux every N milliseconds
    MUX_SCANNING_INTERVAL_MS = 1000  # [ms]

    # Chart history (CH) buffer sizes in [samples].
    # Multiply this with the corresponding SCANNING_INTERVAL constants to get
    # the history size in time.
    CH_SAMPLES_MUX = 1800

    # The chart will be updated at this interval
    UPDATE_INTERVAL_GUI = 1000  # [ms]

    # SCPI commands to be send to the 3497xA to set up the scan cycle.
    """
    scan_list = "(@301:310)"
    MUX_SCPI_COMMANDS = [
        "rout:open %s" % scan_list,
        "conf:temp TC,J,%s" % scan_list,
        "unit:temp C,%s" % scan_list,
        "sens:temp:tran:tc:rjun:type INT,%s" % scan_list,
        "sens:temp:tran:tc:check ON,%s" % scan_list,
        "sens:temp:nplc 1,%s" % scan_list,
        "rout:scan %s" % scan_list,
    ]
    """
    # """
    scan_list = "(@101)"
    MUX_SCPI_COMMANDS = [
        "rout:open %s" % scan_list,
        "conf:res 1e6,%s" % scan_list,
        "sens:res:nplc 1,%s" % scan_list,
        "rout:scan %s" % scan_list,
    ]
    # """

    # --------------------------------------------------------------------------
    #   Connect to Keysight 3497xA (mux)
    # --------------------------------------------------------------------------

    rm = pyvisa.ResourceManager()

    mux = Keysight_3497xA(MUX_VISA_ADDRESS, "MUX")
    if mux.connect(rm):
        mux.begin(MUX_SCPI_COMMANDS)

    # --------------------------------------------------------------------------
    #   Create application
    # --------------------------------------------------------------------------
    QtCore.QThread.currentThread().setObjectName("MAIN")  # For DEBUG info

    app = QtWid.QApplication(sys.argv)
    app.setFont(QtGui.QFont("Arial", 9))
    app.aboutToQuit.connect(about_to_quit)

    # Create PyQt GUI interfaces and communication threads per 3497xA
    mux_qdev = Keysight_3497xA_qdev(
        dev=mux,
        DAQ_interval_ms=MUX_SCANNING_INTERVAL_MS,
        DAQ_postprocess_MUX_scan_function=DAQ_postprocess_MUX_scan_function,
    )
    mux_qdev.set_table_readings_format("%.5e")
    mux_qdev.qgrp.setFixedWidth(420)

    # Create window
    window = MainWindow()

    # --------------------------------------------------------------------------
    #   Create history charts depending on the number of scan channels
    # --------------------------------------------------------------------------

    N_channels = len(mux.state.all_scan_list_channels)

    # Create thread-safe `HistoryChartCurve`s, aka `tscurves`
    cm = plt.get_cmap("gist_rainbow")
    for i in range(N_channels):
        color = cm(1.0 * i / N_channels)  # Color will now be an RGBA tuple
        color = np.array(color) * 255
        pen = pg.mkPen(color=color, width=2)

        window.tscurves_mux.append(
            HistoryChartCurve(
                capacity=CH_SAMPLES_MUX,
                linked_curve=window.pi_mux.plot(
                    pen=pen, name=mux.state.all_scan_list_channels[i]
                ),
            )
        )

    legend = LegendSelect(linked_curves=window.tscurves_mux)
    legend.grid.setVerticalSpacing(0)
    window.qgrp_legend.setLayout(legend.grid)

    # --------------------------------------------------------------------------
    #   File logger
    # --------------------------------------------------------------------------

    log = FileLogger(
        write_header_function=write_header_to_log,
        write_data_function=write_data_to_log,
    )
    log.signal_recording_started.connect(
        lambda filepath: window.qpbt_record.setText(
            "Recording to file: %s" % filepath
        )
    )
    log.signal_recording_stopped.connect(
        lambda: window.qpbt_record.setText("Click to start recording to file")
    )

    # --------------------------------------------------------------------------
    #   Start threads
    # --------------------------------------------------------------------------

    mux_qdev.start()

    # --------------------------------------------------------------------------
    #   Set up timers
    # --------------------------------------------------------------------------

    timer_GUI = QtCore.QTimer()
    timer_GUI.timeout.connect(window.update_GUI)
    timer_GUI.start(UPDATE_INTERVAL_GUI)

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    window.plot_manager.perform_preset(2)  # Init time axis of the history chart
    window.show()
    if QT_LIB in (PYQT5, PYSIDE2):
        sys.exit(app.exec_())
    else:
        sys.exit(app.exec())
