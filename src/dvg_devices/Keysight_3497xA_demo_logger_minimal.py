#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt5 GUI to interface with a a Keysight (former HP or Agilent)
34970A/34972A data acquisition/switch unit.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "03-08-2020"
__version__ = "0.1.2"
# pylint: disable=bare-except

import sys
import visa
import numpy as np
import time

from PyQt5 import QtCore, QtWidgets as QtWid
from PyQt5.QtCore import QDateTime
import pyqtgraph as pg

from dvg_pyqtgraph_threadsafe import HistoryChartCurve

from dvg_devices.Keysight_3497xA_protocol_SCPI import Keysight_3497xA
from dvg_devices.Keysight_3497xA_qdev import Keysight_3497xA_qdev, INFINITY_CAP

USE_OPENGL = False
if USE_OPENGL:
    print("OpenGL acceleration: Enabled")
    pg.setConfigOptions(useOpenGL=True)
    pg.setConfigOptions(antialias=True)
    pg.setConfigOptions(enableExperimental=True)


class MainWindow(QtWid.QWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setGeometry(300, 120, 1200, 600)
        self.setWindowTitle("Keysight 3497xA control")

        self.gw_mux = pg.GraphicsLayoutWidget()
        self.gw_mux.setBackground([20, 20, 20])
        self.pi_mux = self.gw_mux.addPlot()

        # Placeholder to be populated depending on the number of scan channels
        self.tscurves_mux = list()  # List of `HistoryChartCurve`

        hbox1 = QtWid.QHBoxLayout()
        hbox1.addWidget(mux_qdev.qgrp, stretch=0, alignment=QtCore.Qt.AlignTop)
        hbox1.addWidget(self.gw_mux, stretch=1)

        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(hbox1)
        vbox.addStretch(1)

    @QtCore.pyqtSlot()
    def update_GUI(self):
        for tscurve in self.tscurves_mux:
            tscurve.update()


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


# ------------------------------------------------------------------------------
#   DAQ_postprocess_MUX_scan_function
# ------------------------------------------------------------------------------


def DAQ_postprocess_MUX_scan_function():
    """Will be called during an 'worker_DAQ' update, after a mux scan has been
    performed. We use it to parse out the scan readings into separate variables
    and log it to file.
    """

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
        tscurve.appendData(time.perf_counter(), readings[idx])


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    MUX_VISA_ADDRESS = "USB0::0x0957::0x2007::MY49018071::INSTR"
    MUX_SCANNING_INTERVAL_MS = 1000  # [ms]
    CH_SAMPLES_MUX = 1800
    UPDATE_INTERVAL_GUI = 1000  # [ms]

    # SCPI commands to be send to the 3497xA to set up the scan cycle.
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

    # Connect to Keysight 3497xA (mux)
    rm = visa.ResourceManager()

    mux = Keysight_3497xA(MUX_VISA_ADDRESS, "MUX")
    if mux.connect(rm):
        mux.begin(MUX_SCPI_COMMANDS)

    # Create application
    app = QtWid.QApplication(sys.argv)
    app.aboutToQuit.connect(about_to_quit)

    # Create PyQt GUI interfaces and communication threads per 3497xA
    mux_qdev = Keysight_3497xA_qdev(
        dev=mux,
        DAQ_interval_ms=MUX_SCANNING_INTERVAL_MS,
        DAQ_postprocess_MUX_scan_function=DAQ_postprocess_MUX_scan_function,
        debug=True,
    )
    mux_qdev.set_table_readings_format("%.5e")
    mux_qdev.qgrp.setFixedWidth(420)

    # Create window
    window = MainWindow()

    # Create history charts depending on the number of scan channels
    N_channels = len(mux.state.all_scan_list_channels)

    for i in range(N_channels):
        window.tscurves_mux.append(
            HistoryChartCurve(
                capacity=CH_SAMPLES_MUX,
                linked_curve=window.pi_mux.plot(
                    pen=pg.mkPen(color=[255, 0, 0], width=2),
                    name=mux.state.all_scan_list_channels[i],
                ),
            )
        )

    mux_qdev.start(DAQ_priority=QtCore.QThread.TimeCriticalPriority)

    # Chart timer
    timer_GUI = QtCore.QTimer()
    timer_GUI.timeout.connect(window.update_GUI)
    timer_GUI.start(UPDATE_INTERVAL_GUI)

    window.show()
    sys.exit(app.exec_())
