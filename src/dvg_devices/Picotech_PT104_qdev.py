#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt5 module to provide multithreaded communication and periodical data
acquisition for a Picotech PT-104 pt100/1000 temperature logger.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "04-07-2020"  # 0.0.1 was stamped 17-09-2018
__version__ = "0.0.4"  # 0.0.1 corresponds to prototype 1.0.0

import numpy as np

from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets as QtWid

from dvg_utils.dvg_pyqt_controls import SS_GROUP

from dvg_qdeviceio import QDeviceIO, DAQ_trigger
from dvg_devices.Picotech_PT104_protocol_UDP import Picotech_PT104

# Special characters
CHAR_DEG_C = chr(176) + 'C'


class Picotech_PT104_qdev(QDeviceIO):
    """Manages multithreaded communication and periodical data acquisition for
    a Picotech PT-104 pt100/1000 temperature logger referred to as the 'device'.

    In addition, it also provides PyQt5 GUI objects for control of the device.
    These can be incorporated into your application.

    NOTE: Each PT-104 reading takes roughly 720 ms per channel.

    All device output operations will be offloaded to a 'worker', running in
    a newly created thread instead of in the main/GUI thread.

        - Worker_DAQ:
            Periodically acquires data from the device.

    (*): See 'dvg_qdeviceio.QDeviceIO()' for details.

    Args:
        dev:
            Reference to a
            'dvg_devices.Picotech_PT104_protocol_UDP.Picotech_PT104' instance.

        (*) DAQ_interval_ms:
            The minimum interval is determined by the scan rate of the PT-104,
            which takes 720 ms to update a temperature reading of a single
            channel. This minimum interval is not stable and fluctuates. To
            ensure a stable DAQ rate, set 'DAQ_interval_ms' to values
            larger than 720 ms with some head room. 1000 ms, should work fine.

        (*) critical_not_alive_count
        (*) DAQ_timer_type

    Main methods:
        (*) start(...)
        (*) quit()

    Main GUI objects:
        qgrp (PyQt5.QtWidgets.QGroupBox)

    Signals:
        (*) signal_DAQ_updated()
        (*) signal_connection_lost()
    """
    def __init__(self,
                 dev: Picotech_PT104,
                 DAQ_interval_ms=1000,
                 DAQ_timer_type=QtCore.Qt.CoarseTimer,
                 critical_not_alive_count=np.nan,
                 calc_DAQ_rate_every_N_iter=1,
                 debug=False,
                 **kwargs,):
        super().__init__(dev, **kwargs)  # Pass kwargs onto QtCore.QObject()

        self.create_worker_DAQ(
                DAQ_trigger=DAQ_trigger.INTERNAL_TIMER,
                DAQ_function=self.DAQ_function,
                DAQ_interval_ms=DAQ_interval_ms,
                DAQ_timer_type=DAQ_timer_type,
                critical_not_alive_count=critical_not_alive_count,
                calc_DAQ_rate_every_N_iter=calc_DAQ_rate_every_N_iter,
                debug=debug)

        self.create_GUI()
        self.signal_DAQ_updated.connect(self.update_GUI)
        if not self.dev.is_alive:
            self.update_GUI()  # Correctly reflect an offline device

    # --------------------------------------------------------------------------
    #   DAQ_function
    # --------------------------------------------------------------------------

    def DAQ_function(self):
        #print("Obtained interval: %.0f" % self.obtained_DAQ_interval_ms)
        return self.dev.scan_4_wire_temperature()

    # --------------------------------------------------------------------------
    #   create_GUI
    # --------------------------------------------------------------------------

    def create_GUI(self):
        self.qlbl_offline = QtWid.QLabel("OFFLINE", visible=False,
            font=QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Bold),
            alignment=QtCore.Qt.AlignCenter)

        p = {'alignment': QtCore.Qt.AlignRight,
             'minimumWidth': 60}
        self.qled_T_ch1 = QtWid.QLineEdit(**p, readOnly=True)
        self.qled_T_ch2 = QtWid.QLineEdit(**p, readOnly=True)
        self.qled_T_ch3 = QtWid.QLineEdit(**p, readOnly=True)
        self.qled_T_ch4 = QtWid.QLineEdit(**p, readOnly=True)
        self.qlbl_update_counter = QtWid.QLabel("0")

        self.grid = QtWid.QGridLayout()
        self.grid.setVerticalSpacing(4)
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
            self.qled_T_ch1.setText("%.3f" % self.dev.state.ch1_T)
            self.qled_T_ch2.setText("%.3f" % self.dev.state.ch2_T)
            self.qled_T_ch3.setText("%.3f" % self.dev.state.ch3_T)
            self.qled_T_ch4.setText("%.3f" % self.dev.state.ch4_T)
            self.qlbl_update_counter.setText("%s" % self.DAQ_update_counter)
        else:
            self.qgrp.setEnabled(False)
            self.qlbl_offline.setVisible(True)
