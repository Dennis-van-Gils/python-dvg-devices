#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt/PySide module to provide multithreaded communication and periodical data
acquisition for a Picotech PT-104 pt100/1000 temperature logger.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "14-09-2022"
__version__ = "1.0.0"

# Mechanism to support both PyQt and PySide
# -----------------------------------------
import os
import sys

QT_LIB = os.getenv("PYQTGRAPH_QT_LIB")
PYSIDE = "PySide"
PYSIDE2 = "PySide2"
PYSIDE6 = "PySide6"
PYQT4 = "PyQt4"
PYQT5 = "PyQt5"
PYQT6 = "PyQt6"

# pylint: disable=import-error, no-name-in-module
# fmt: off
if QT_LIB is None:
    libOrder = [PYQT5, PYSIDE2, PYSIDE6, PYQT6]
    for lib in libOrder:
        if lib in sys.modules:
            QT_LIB = lib
            break

if QT_LIB is None:
    for lib in libOrder:
        try:
            __import__(lib)
            QT_LIB = lib
            break
        except ImportError:
            pass

if QT_LIB is None:
    raise Exception(
        "Picotech_PT104_qdev requires PyQt5, PyQt6, PySide2 or PySide6; "
        "none of these packages could be imported."
    )

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

# fmt: on
# pylint: enable=import-error, no-name-in-module
# \end[Mechanism to support both PyQt and PySide]
# -----------------------------------------------

import numpy as np

from dvg_pyqt_controls import SS_GROUP

from dvg_qdeviceio import QDeviceIO, DAQ_TRIGGER
from dvg_devices.Picotech_PT104_protocol_UDP import Picotech_PT104

# Special characters
CHAR_DEG_C = chr(176) + "C"


class Picotech_PT104_qdev(QDeviceIO):
    """Manages multithreaded communication and periodical data acquisition for
    a Picotech PT-104 pt100/1000 temperature logger referred to as the 'device'.

    In addition, it also provides PyQt/PySide GUI objects for control of the
    device. These can be incorporated into your application.

    NOTE: Each PT-104 reading takes roughly 720 ms per channel.

    All device I/O operations will be offloaded to 'workers', each running in
    a newly created thread.

    (*): See 'dvg_qdeviceio.QDeviceIO()' for details.

    Args:
        dev:
            Reference to a
            'dvg_devices.Picotech_PT104_protocol_UDP.Picotech_PT104'
            instance.

        (*) DAQ_interval_ms:
            The minimum interval is determined by the scan rate of the PT-104,
            which takes 720 ms to update a temperature reading of a single
            channel. This minimum interval is not stable and fluctuates. To
            ensure a stable DAQ rate, set 'DAQ_interval_ms' to values
            larger than 720 ms with some head room. 1000 ms, should work fine.

        debug:
            Show debug info in terminal? Warning: Slow! Do not leave on
            unintentionally.

    Main GUI objects:
        qgrp (PyQt5.QtWidgets.QGroupBox)
    """

    def __init__(
        self,
        dev: Picotech_PT104,
        DAQ_interval_ms=1000,
        DAQ_timer_type=QtCore.Qt.TimerType.CoarseTimer,
        critical_not_alive_count=np.nan,
        debug=False,
        **kwargs,
    ):
        super().__init__(dev, **kwargs)  # Pass kwargs onto QtCore.QObject()

        self.create_worker_DAQ(
            DAQ_trigger=DAQ_TRIGGER.INTERNAL_TIMER,
            DAQ_function=self.DAQ_function,
            DAQ_interval_ms=DAQ_interval_ms,
            DAQ_timer_type=DAQ_timer_type,
            critical_not_alive_count=critical_not_alive_count,
            debug=debug,
        )

        self.create_GUI()
        self.signal_DAQ_updated.connect(self.update_GUI)
        if not self.dev.is_alive:
            self.update_GUI()  # Correctly reflect an offline device

    # --------------------------------------------------------------------------
    #   DAQ_function
    # --------------------------------------------------------------------------

    def DAQ_function(self):
        # print("Obtained interval: %.0f" % self.obtained_DAQ_interval_ms)
        return self.dev.scan_4_wire_temperature()

    # --------------------------------------------------------------------------
    #   create_GUI
    # --------------------------------------------------------------------------

    def create_GUI(self):
        self.qlbl_offline = QtWid.QLabel(
            "OFFLINE",
            visible=False,
            font=QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Weight.Bold),
            alignment=QtCore.Qt.AlignmentFlag.AlignCenter,
        )

        p = {
            "alignment": QtCore.Qt.AlignmentFlag.AlignRight,
            "minimumWidth": 60,
        }
        self.qled_T_ch1 = QtWid.QLineEdit(**p, readOnly=True)
        self.qled_T_ch2 = QtWid.QLineEdit(**p, readOnly=True)
        self.qled_T_ch3 = QtWid.QLineEdit(**p, readOnly=True)
        self.qled_T_ch4 = QtWid.QLineEdit(**p, readOnly=True)
        self.qlbl_update_counter = QtWid.QLabel("0")

        self.grid = QtWid.QGridLayout()
        self.grid.setVerticalSpacing(4)
        # fmt: off
        self.grid.addWidget(self.qlbl_offline       , 0, 0, 1, 3)
        self.grid.addWidget(QtWid.QLabel("Ch 1")    , 1, 0)
        self.grid.addWidget(self.qled_T_ch1         , 1, 1)
        self.grid.addWidget(QtWid.QLabel(CHAR_DEG_C), 1, 2)
        self.grid.addWidget(QtWid.QLabel("Ch 2")    , 2, 0)
        self.grid.addWidget(self.qled_T_ch2         , 2, 1)
        self.grid.addWidget(QtWid.QLabel(CHAR_DEG_C), 2, 2)
        self.grid.addWidget(QtWid.QLabel("Ch 3")    , 3, 0)
        self.grid.addWidget(self.qled_T_ch3         , 3, 1)
        self.grid.addWidget(QtWid.QLabel(CHAR_DEG_C), 3, 2)
        self.grid.addWidget(QtWid.QLabel("Ch 4")    , 4, 0)
        self.grid.addWidget(self.qled_T_ch4         , 4, 1)
        self.grid.addWidget(QtWid.QLabel(CHAR_DEG_C), 4, 2)
        self.grid.addWidget(self.qlbl_update_counter, 5, 0, 1, 3)
        # fmt: on

        self.qgrp = QtWid.QGroupBox("%s" % self.dev.name)
        self.qgrp.setStyleSheet(SS_GROUP)
        self.qgrp.setLayout(self.grid)

    # --------------------------------------------------------------------------
    #   update_GUI
    # --------------------------------------------------------------------------

    @Slot()
    def update_GUI(self):
        """NOTE: 'self.dev.mutex' is not being locked, because we are only
        reading 'state' for displaying purposes. We can do this because 'state'
        members are written and read atomicly.
        Not locking the mutex might speed up the program.
        """
        if self.dev.is_alive:
            self.qled_T_ch1.setText("%.3f" % self.dev.state.ch1_T)
            self.qled_T_ch2.setText("%.3f" % self.dev.state.ch2_T)
            self.qled_T_ch3.setText("%.3f" % self.dev.state.ch3_T)
            self.qled_T_ch4.setText("%.3f" % self.dev.state.ch4_T)
            self.qlbl_update_counter.setText("%s" % self.update_counter_DAQ)
        else:
            self.qgrp.setEnabled(False)
            self.qlbl_offline.setVisible(True)
