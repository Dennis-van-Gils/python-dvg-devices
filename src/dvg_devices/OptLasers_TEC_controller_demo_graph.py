#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Multithreaded PyQt/PySide GUI to interface with an OptLasers thermoelectric
cooler (TEC) controller.
"""

__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "17-08-2026"
__version__ = "1.7.1"
print(__url__)
# pylint: disable=wrong-import-position, missing-function-docstring

import sys
import time

import qtpy
from qtpy import QtCore, QtGui, QtWidgets as QtWid
from qtpy.QtCore import Slot  # type: ignore
import pyqtgraph as pg

from dvg_pyqtgraph_threadsafe import (
    HistoryChartCurve,
    LegendSelect,
    PlotManager,
)
import dvg_pyqt_controls as controls
from dvg_devices.OptLasers_TEC_controller_protocol_RS232 import OptLasersTEC
from dvg_devices.OptLasers_TEC_controller_qdev import OptLasersTEC_qdev

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

CHART_INTERVAL_MS = 1000  # [ms] Update interval for all charts
CHART_CAPACITY = 3600  # [samples]

# Show debug info in terminal? Warning: Slow! Do not leave on unintentionally.
DEBUG = False

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):

    def __init__(self, qdev: OptLasersTEC_qdev, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setWindowTitle("OptLasers TEC controller")
        self.setGeometry(40, 60, 0, 0)
        self.setFont(QtGui.QFont("Arial", 9))
        self.setStyleSheet(
            controls.SS_TEXTBOX_READ_ONLY
            + controls.SS_GROUP
            + controls.SS_HOVER
        )

        self.timer_charts = QtCore.QTimer()
        self.timer_charts.timeout.connect(self.update_charts)

        # ----------------------------------------------------------------------
        #   Top grid
        # ----------------------------------------------------------------------

        self.qpbt_exit = QtWid.QPushButton("Exit")
        self.qpbt_exit.clicked.connect(self.close)
        self.qpbt_exit.setMinimumHeight(30)

        grid_top = QtWid.QGridLayout()
        grid_top.addWidget(
            self.qpbt_exit, 0, 1, QtCore.Qt.AlignmentFlag.AlignRight
        )

        # ----------------------------------------------------------------------
        #   Chart
        # ----------------------------------------------------------------------

        self.gw_tec = pg.GraphicsLayoutWidget()
        self.gw_tec.setMinimumWidth(600)

        p = {"color": "#EEE", "font-size": "12pt"}
        self.pi_tec = self.gw_tec.addPlot()
        self.pi_tec.setClipToView(True)
        self.pi_tec.showGrid(x=1, y=1)
        self.pi_tec.setTitle("TEC temperatures", **p)
        self.pi_tec.setLabel("bottom", "history (min)", **p)
        self.pi_tec.setLabel("left", f"{chr(176)}C", **p)
        self.pi_tec.setMenuEnabled(True)
        self.pi_tec.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
        self.pi_tec.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
        self.pi_tec.setAutoVisible(y=True)

        self.tscurve_T_set = HistoryChartCurve(
            capacity=CHART_CAPACITY,
            linked_curve=self.pi_tec.plot(
                pen=pg.mkPen(color=controls.COLOR_PEN_TURQUOISE, width=2),
                name="T_set",
            ),
        )
        self.tscurve_T_meas = HistoryChartCurve(
            capacity=CHART_CAPACITY,
            linked_curve=self.pi_tec.plot(
                pen=pg.mkPen(color=controls.COLOR_PEN_PINK, width=2),
                name="T_meas",
            ),
        )

        self.tscurves_tec = [self.tscurve_T_set, self.tscurve_T_meas]

        # ----------------------------------------------------------------------
        #   Legend
        # ----------------------------------------------------------------------

        legend = LegendSelect(linked_curves=self.tscurves_tec)
        legend.grid.setVerticalSpacing(0)

        self.qgrp_legend = QtWid.QGroupBox("Legend")
        self.qgrp_legend.setLayout(legend.grid)

        # ----------------------------------------------------------------------
        #   PlotManager
        # ----------------------------------------------------------------------

        self.plot_manager = PlotManager(parent=self)
        self.plot_manager.add_autorange_buttons(linked_plots=self.pi_tec)
        self.plot_manager.add_preset_buttons(
            linked_plots=self.pi_tec,
            linked_curves=self.tscurves_tec,
            presets=[
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
                {
                    "button_label": "30:00",
                    "x_axis_label": "history (min)",
                    "x_axis_divisor": 60,
                    "x_axis_range": (-60, 0),
                },
            ],
        )
        self.plot_manager.add_clear_button(linked_curves=self.tscurves_tec)

        qgrp_history = QtWid.QGroupBox("History")
        qgrp_history.setLayout(self.plot_manager.grid)

        # ----------------------------------------------------------------------
        #   Right-panel
        # ----------------------------------------------------------------------

        p = {"stretch": 0, "alignment": QtCore.Qt.AlignmentFlag.AlignLeft}
        vbox1 = QtWid.QVBoxLayout()
        vbox1.addWidget(qdev.qgrp, **p)
        vbox1.addWidget(self.qgrp_legend, **p)
        vbox1.addWidget(qgrp_history, **p)
        vbox1.addStretch(1)

        # ----------------------------------------------------------------------
        #   Round up full window
        # ----------------------------------------------------------------------

        hbox1 = QtWid.QHBoxLayout()
        hbox1.addWidget(self.gw_tec, stretch=1)
        hbox1.addLayout(vbox1)

        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(grid_top)
        vbox.addLayout(hbox1)

    # --------------------------------------------------------------------------
    #   update_charts
    # --------------------------------------------------------------------------

    @Slot()
    def update_charts(self):
        for tscurve in self.tscurves_tec:
            tscurve.update()


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":

    # --------------------------------------------------------------------------
    #   Connect to and set up OptLasers TEC controller
    # --------------------------------------------------------------------------

    tec = OptLasersTEC(debug=DEBUG)
    tec.auto_connect()

    if tec.is_alive:
        tec.begin()

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
    #   Set up communication threads for the TEC controller
    # --------------------------------------------------------------------------

    def add_TEC_readings_to_charts():
        now = time.perf_counter()
        window.tscurve_T_set.appendData(now, tec.state.T_set)
        window.tscurve_T_meas.appendData(now, tec.state.T_meas)

    tec_qdev = OptLasersTEC_qdev(
        dev=tec,
        debug=DEBUG,
    )
    tec_qdev.signal_DAQ_updated.connect(add_TEC_readings_to_charts)
    tec_qdev.start()

    # --------------------------------------------------------------------------
    #   Start the main GUI event loop
    # --------------------------------------------------------------------------

    def about_to_quit():
        print("About to quit")
        app.processEvents()
        tec_qdev.quit()
        tec.close()

    app.aboutToQuit.connect(about_to_quit)

    window = MainWindow(qdev=tec_qdev)
    window.plot_manager.perform_preset(2)
    window.timer_charts.start(CHART_INTERVAL_MS)
    window.show()

    sys.exit(app.exec())
