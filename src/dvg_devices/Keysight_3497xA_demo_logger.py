#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt5 GUI to interface with a a Keysight (former HP or Agilent)
34970A/34972A data acquisition/switch unit.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "02-07-2020"  # 0.0.1 was stamped 14-09-2018
__version__ = "0.0.3"  # 0.0.1 corresponds to prototype 1.0.0

import sys

import visa
import matplotlib.pyplot as plt
import numpy as np

from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets as QtWid
from PyQt5.QtCore import QDateTime
import pyqtgraph as pg

from dvg_utils.dvg_pyqt_controls import (create_Toggle_button,
                               SS_TEXTBOX_READ_ONLY,
                               SS_GROUP)
from dvg_utils.dvg_pyqt_charthistory import ChartHistory
from dvg_utils.dvg_pyqt_filelogger import FileLogger

from dvg_devices.Keysight_3497xA_protocol_SCPI import Keysight_3497xA
from dvg_devices.Keysight_3497xA_qdev import Keysight_3497xA_qdev, INFINITY_CAP

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------

class MainWindow(QtWid.QWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setGeometry(600, 120, 1200, 600)
        self.setWindowTitle("Keysight 3497xA control")

        # ----------------------------------------------------------------------
        #   Top grid
        # ----------------------------------------------------------------------

        self.qlbl_title = QtWid.QLabel("Keysight 3497xA control",
                font=QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Bold))
        self.qlbl_cur_date_time = QtWid.QLabel("00-00-0000    00:00:00")
        self.qpbt_record = create_Toggle_button(
                "Click to start recording to file", minimumHeight=40)
        self.qpbt_record.setMinimumWidth(400)

        self.qpbt_exit = QtWid.QPushButton("Exit")
        self.qpbt_exit.clicked.connect(self.close)
        self.qpbt_exit.setMinimumHeight(30)

        grid_top = QtWid.QGridLayout()
        grid_top.addWidget(self.qlbl_title        , 0, 0, QtCore.Qt.AlignCenter)
        grid_top.addWidget(self.qpbt_exit         , 0, 2, QtCore.Qt.AlignRight)
        grid_top.addWidget(self.qlbl_cur_date_time, 1, 0, QtCore.Qt.AlignCenter)
        grid_top.addWidget(self.qpbt_record       , 2, 0, QtCore.Qt.AlignCenter)
        grid_top.setColumnMinimumWidth(0, 420)
        grid_top.setColumnStretch(1, 1)

        # ----------------------------------------------------------------------
        #   Chart: Mux readings
        # ----------------------------------------------------------------------

        # GraphicsWindow
        self.gw_mux = pg.GraphicsWindow()
        self.gw_mux.setBackground([20, 20, 20])

        # PlotItem
        self.pi_mux = self.gw_mux.addPlot()
        self.pi_mux.setTitle(
          '<span style="font-size:12pt">Mux readings</span>')
        self.pi_mux.setLabel('bottom',
          '<span style="font-size:12pt">history (min)</span>')
        self.pi_mux.setLabel('left',
          '<span style="font-size:12pt">misc. units</span>')
        self.pi_mux.showGrid(x=1, y=1)
        self.pi_mux.setMenuEnabled(True)
        self.pi_mux.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
        self.pi_mux.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
        self.pi_mux.setAutoVisible(y=True)

        # Viewbox properties for the legend
        vb = self.gw_mux.addViewBox(enableMenu=False)
        vb.setMaximumWidth(80)

        # Legend
        self.legend = pg.LegendItem()
        self.legend.setParentItem(vb)
        self.legend.anchor((0,0), (0,0), offset=(1, 10))
        self.legend.setFixedWidth(75)
        self.legend.setScale(1)

        # ----------------------------------------------------------------------
        #   Show curves selection
        # ----------------------------------------------------------------------

        qgrp_show_curves = QtWid.QGroupBox("Show")
        qgrp_show_curves.setStyleSheet(SS_GROUP)
        self.grid_show_curves = QtWid.QGridLayout()
        self.grid_show_curves.setVerticalSpacing(0)
        qgrp_show_curves.setLayout(self.grid_show_curves)

        # ----------------------------------------------------------------------
        #   Chart history time range selection
        # ----------------------------------------------------------------------

        p = {'maximumWidth': 70}
        self.qpbt_history_1 = QtWid.QPushButton("00:30", **p)
        self.qpbt_history_2 = QtWid.QPushButton("01:00", **p)
        self.qpbt_history_3 = QtWid.QPushButton("03:00", **p)
        self.qpbt_history_4 = QtWid.QPushButton("05:00", **p)
        self.qpbt_history_5 = QtWid.QPushButton("10:00", **p)
        self.qpbt_history_6 = QtWid.QPushButton("30:00", **p)

        self.qpbt_history_clear = QtWid.QPushButton("clear", **p)
        self.qpbt_history_clear.clicked.connect(self.clear_all_charts)

        grid = QtWid.QGridLayout()
        grid.setVerticalSpacing(0)
        grid.addWidget(self.qpbt_history_1, 0, 0)
        grid.addWidget(self.qpbt_history_2, 1, 0)
        grid.addWidget(self.qpbt_history_3, 2, 0)
        grid.addWidget(self.qpbt_history_4, 3, 0)
        grid.addWidget(self.qpbt_history_5, 4, 0)
        grid.addWidget(self.qpbt_history_6, 5, 0)
        grid.addWidget(self.qpbt_history_clear, 6, 0)

        qgrp_history = QtWid.QGroupBox("History")
        qgrp_history.setStyleSheet(SS_GROUP)
        qgrp_history.setLayout(grid)

        # ----------------------------------------------------------------------
        #   Bottom grid
        # ----------------------------------------------------------------------

        vbox1 = QtWid.QVBoxLayout()
        vbox1.addWidget(qgrp_show_curves, stretch=0,
                        alignment=QtCore.Qt.AlignTop)
        vbox1.addWidget(qgrp_history, stretch=0, alignment=QtCore.Qt.AlignTop)
        vbox1.addStretch(1)

        hbox1 = QtWid.QHBoxLayout()
        hbox1.addWidget(mux_qdev.qgrp, stretch=0, alignment=QtCore.Qt.AlignTop)
        hbox1.addWidget(self.gw_mux, stretch=1)
        hbox1.addLayout(vbox1)

        # ----------------------------------------------------------------------
        #   Round up full window
        # ----------------------------------------------------------------------

        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(grid_top)
        vbox.addLayout(hbox1)
        vbox.addStretch(1)

    @QtCore.pyqtSlot()
    def clear_all_charts(self):
        str_msg = "Are you sure you want to clear all charts?"
        reply = QtWid.QMessageBox.warning(self, "Clear charts", str_msg,
                                          QtWid.QMessageBox.Yes |
                                          QtWid.QMessageBox.No,
                                          QtWid.QMessageBox.No)

        if reply == QtWid.QMessageBox.Yes:
            [CH.clear() for CH in self.CHs_mux]

# ------------------------------------------------------------------------------
#   update_GUI
# ------------------------------------------------------------------------------

@QtCore.pyqtSlot()
def update_GUI():
    cur_date_time = QDateTime.currentDateTime()
    window.qlbl_cur_date_time.setText(cur_date_time.toString("dd-MM-yyyy") +
                                      "    " +
                                      cur_date_time.toString("HH:mm:ss"))

    # Update curves
    [CH.update_curve() for CH in window.CHs_mux]

    # Show or hide curve depending on checkbox
    for i in range(N_channels):
        window.CHs_mux[i].curve.setVisible(
                window.chkbs_show_curves[i].isChecked())

# ------------------------------------------------------------------------------
# ------------------------------------------------------------------------------

@QtCore.pyqtSlot()
def process_qpbt_history_1():
    change_history_axes(time_axis_factor=1e3,      # transform [msec] to [sec]
                        time_axis_range=-30,       # [sec]
                        time_axis_label=
                        '<span style="font-size:12pt">history (sec)</span>')

@QtCore.pyqtSlot()
def process_qpbt_history_2():
    change_history_axes(time_axis_factor=1e3,      # transform [msec] to [sec]
                        time_axis_range=-60,       # [sec]
                        time_axis_label=
                        '<span style="font-size:12pt">history (sec)</span>')

@QtCore.pyqtSlot()
def process_qpbt_history_3():
    change_history_axes(time_axis_factor=60e3,     # transform [msec] to [min]
                        time_axis_range=-3,        # [min]
                        time_axis_label=
                        '<span style="font-size:12pt">history (min)</span>')

@QtCore.pyqtSlot()
def process_qpbt_history_4():
    change_history_axes(time_axis_factor=60e3,     # transform [msec] to [min]
                        time_axis_range=-5,        # [min]
                        time_axis_label=
                        '<span style="font-size:12pt">history (min)</span>')

@QtCore.pyqtSlot()
def process_qpbt_history_5():
    change_history_axes(time_axis_factor=60e3,     # transform [msec] to [min]
                        time_axis_range=-10,       # [min]
                        time_axis_label=
                        '<span style="font-size:12pt">history (min)</span>')

@QtCore.pyqtSlot()
def process_qpbt_history_6():
    change_history_axes(time_axis_factor=60e3,     # transform [msec] to [min]
                        time_axis_range=-30,       # [min]
                        time_axis_label=
                        '<span style="font-size:12pt">history (min)</span>')

def change_history_axes(time_axis_factor, time_axis_range, time_axis_label):
    window.pi_mux.setXRange(time_axis_range, 0)
    window.pi_mux.setLabel('bottom', time_axis_label)

    for i in range(N_channels):
        window.CHs_mux[i].x_axis_divisor = time_axis_factor

@QtCore.pyqtSlot()
def process_qpbt_show_all_curves():
    # First: if any curve is hidden --> show all
    # Second: if all curves are shown --> hide all

    any_hidden = False
    for i in range(N_channels):
        if (not window.chkbs_show_curves[i].isChecked()):
            window.chkbs_show_curves[i].setChecked(True)
            any_hidden = True

    if (not any_hidden):
        for i in range(N_channels):
            window.chkbs_show_curves[i].setChecked(False)

@QtCore.pyqtSlot()
def process_qpbt_record():
    if (window.qpbt_record.isChecked()):
        file_logger.starting = True
    else:
        file_logger.stopping = True

@QtCore.pyqtSlot(str)
def set_text_qpbt_record(text_str):
    window.qpbt_record.setText(text_str)

# ------------------------------------------------------------------------------
#   about_to_quit
# ------------------------------------------------------------------------------

def about_to_quit():
    print("About to quit")
    app.processEvents()
    mux_qdev.quit()
    file_logger.close_log()

    try: mux.close()
    except: pass
    try: rm.close()
    except: pass

# ------------------------------------------------------------------------------
#   DAQ_postprocess_MUX_scan_function
# ------------------------------------------------------------------------------

def DAQ_postprocess_MUX_scan_function():
    """Will be called during an 'worker_DAQ' update, after a mux scan has been
    performed. We use it to parse out the scan readings into separate variables
    and log it to file.
    """
    cur_date_time = QDateTime.currentDateTime()
    epoch_time = cur_date_time.toMSecsSinceEpoch()

    # DEBUG info
    #dprint("thread: %s" % QtCore.QThread.currentThread().objectName())

    if mux_qdev.is_MUX_scanning:
        readings = mux.state.readings
        for i in range(N_channels):
            if readings[i] > INFINITY_CAP:
                readings[i] = np.nan
    else:
        readings = [np.nan] * N_channels
        mux.state.readings = readings

    # Add readings to charts
    for i in range(N_channels):
        window.CHs_mux[i].add_new_reading(epoch_time, readings[i])

    # ----------------------------------------------------------------------
    #   Logging to file
    # ----------------------------------------------------------------------

    if file_logger.starting:
        fn_log = ("d:/data/mux_" +
                  cur_date_time.toString("yyMMdd_HHmmss") + ".txt")
        if file_logger.create_log(epoch_time, fn_log, mode='w'):
            file_logger.signal_set_recording_text.emit(
                "Recording to file: " + fn_log)

            # Header
            file_logger.write("time[s]\t")
            for i in range(N_channels - 1):
                file_logger.write("CH%s\t" %
                                  mux.state.all_scan_list_channels[i])
            file_logger.write("CH%s\n" %
                              mux.state.all_scan_list_channels[-1])

    if file_logger.stopping:
        file_logger.signal_set_recording_text.emit(
            "Click to start recording to file")
        file_logger.close_log()

    if file_logger.is_recording:
        log_elapsed_time = (epoch_time - file_logger.start_time)/1e3  # [sec]

        # Add new data to the log
        file_logger.write("%.3f" % log_elapsed_time)
        for i in range(N_channels):
            if len(mux.state.readings) <= i:
                file_logger.write("\t%.5e" % np.nan)
            else:
                file_logger.write("\t%.5e" % mux.state.readings[i])
        file_logger.write("\n")

# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == '__main__':
    # VISA address of the Keysight 3497xA data acquisition/switch unit
    # containing a multiplexer plug-in module. Hence, we simply call this device
    # a 'mux'.
    #MUX_VISA_ADDRESS = "USB0::0x0957::0x2007::MY49018071::INSTR"
    MUX_VISA_ADDRESS = "GPIB0::9::INSTR"

    # A scan will be performed by the mux every N milliseconds
    MUX_SCANNING_INTERVAL_MS = 1000       # [ms]

    # Chart history (CH) buffer sizes in [samples].
    # Multiply this with the corresponding SCANNING_INTERVAL constants to get
    # the history size in time.
    CH_SAMPLES_MUX = 1800

    # The chart will be updated at this interval
    UPDATE_INTERVAL_GUI = 1000          # [ms]

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
                "rout:scan %s" % scan_list]
    """
    scan_list = "(@101)"
    MUX_SCPI_COMMANDS = [
                "rout:open %s" % scan_list,
                "conf:res 1e5,%s" % scan_list,
                "sens:res:nplc 1,%s" % scan_list,
                "rout:scan %s" % scan_list]

    # --------------------------------------------------------------------------
    #   Connect to Keysight 3497xA (mux)
    # --------------------------------------------------------------------------

    rm = visa.ResourceManager()

    mux = Keysight_3497xA(MUX_VISA_ADDRESS, "MUX")
    if mux.connect(rm):
        mux.begin(MUX_SCPI_COMMANDS)

    # --------------------------------------------------------------------------
    #   Create application
    # --------------------------------------------------------------------------
    QtCore.QThread.currentThread().setObjectName('MAIN')    # For DEBUG info

    app = 0    # Work-around for kernel crash when using Spyder IDE
    app = QtWid.QApplication(sys.argv)
    app.setFont(QtGui.QFont("Arial", 9))
    app.setStyleSheet(SS_TEXTBOX_READ_ONLY)
    app.aboutToQuit.connect(about_to_quit)

    # Create PyQt GUI interfaces and communication threads per 3497xA
    mux_qdev = Keysight_3497xA_qdev(
            dev=mux,
            DAQ_interval_ms=MUX_SCANNING_INTERVAL_MS,
            DAQ_postprocess_MUX_scan_function=DAQ_postprocess_MUX_scan_function)
    mux_qdev.set_table_readings_format("%.5e")
    mux_qdev.qgrp.setFixedWidth(420)

    # Create window
    window = MainWindow()

    # --------------------------------------------------------------------------
    #   Create pens and chart histories depending on the number of scan channels
    # --------------------------------------------------------------------------

    N_channels = len(mux.state.all_scan_list_channels)

    # Pen styles for plotting
    PENS = [None] * N_channels
    cm = plt.get_cmap('gist_rainbow')
    params = {'width': 2}
    for i in range(N_channels):
        color = cm(1.*i/N_channels)  # color will now be an RGBA tuple
        color = np.array(color) * 255
        PENS[i] = pg.mkPen(color=color, **params)

    # Create Chart Histories (CH) and PlotDataItems and link them together
    # Also add legend entries
    window.CHs_mux = [None] * N_channels
    window.chkbs_show_curves = [None] * N_channels
    for i in range(N_channels):
        window.CHs_mux[i] = ChartHistory(CH_SAMPLES_MUX,
                                         window.pi_mux.plot(pen=PENS[i]))
        window.legend.addItem(window.CHs_mux[i].curve,
                              name=mux.state.all_scan_list_channels[i])

        # Add checkboxes for showing the curves
        window.chkbs_show_curves[i] = QtWid.QCheckBox(
                parent=window,
                text=mux.state.all_scan_list_channels[i],
                checked=True)
        window.grid_show_curves.addWidget(window.chkbs_show_curves[i], i, 0)

    window.qpbt_show_all_curves = QtWid.QPushButton("toggle", maximumWidth=70)
    window.qpbt_show_all_curves.clicked.connect(process_qpbt_show_all_curves)
    window.grid_show_curves.addWidget(window.qpbt_show_all_curves,
                                      N_channels, 0)

    # --------------------------------------------------------------------------
    #   File logger
    # --------------------------------------------------------------------------

    file_logger = FileLogger()
    file_logger.signal_set_recording_text.connect(set_text_qpbt_record)

    # --------------------------------------------------------------------------
    #   Start threads
    # --------------------------------------------------------------------------

    mux_qdev.start(DAQ_priority=QtCore.QThread.TimeCriticalPriority)

    # --------------------------------------------------------------------------
    #   Connect remaining signals from GUI
    # --------------------------------------------------------------------------

    window.qpbt_history_1.clicked.connect(process_qpbt_history_1)
    window.qpbt_history_2.clicked.connect(process_qpbt_history_2)
    window.qpbt_history_3.clicked.connect(process_qpbt_history_3)
    window.qpbt_history_4.clicked.connect(process_qpbt_history_4)
    window.qpbt_history_5.clicked.connect(process_qpbt_history_5)
    window.qpbt_history_6.clicked.connect(process_qpbt_history_6)
    window.qpbt_record.clicked.connect(process_qpbt_record)

    # --------------------------------------------------------------------------
    #   Set up timers
    # --------------------------------------------------------------------------

    timer_GUI = QtCore.QTimer()
    timer_GUI.timeout.connect(update_GUI)
    timer_GUI.start(UPDATE_INTERVAL_GUI)

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    # Init the time axis of the strip charts
    process_qpbt_history_3()

    window.show()
    sys.exit(app.exec_())
