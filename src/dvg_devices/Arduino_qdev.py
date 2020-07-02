#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt5 module to provide multithreaded communication and periodical data
acquisition for an Arduino(-like) device.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "02-07-2020"  # 0.0.1 was stamped 11-12-2018
__version__ = "0.0.3"  # 0.0.1 corresponds to prototype 1.2.0

from PyQt5 import QtCore

from dvg_qdeviceio import QDeviceIO, DAQ_trigger
from dvg_devices.Arduino_protocol_serial import Arduino


class Arduino_qdev(QDeviceIO, QtCore.QObject):
    """Manages multithreaded communication and periodical data acquisition for
    an Arduino(-like) device.

    All device I/O operations will be offloaded to 'workers', each running in
    a newly created thread instead of in the main/GUI thread.

        - Worker_DAQ:
            Periodically acquires data from the device.

        - Worker_jobs:
            Maintains a thread-safe queue where desired device I/O operations
            can be put onto, and sends the queued operations first in first out
            (FIFO) to the device.

    (*): See 'dvg_qdeviceio.QDeviceIO()' for details.

    Args:
        dev:
            Reference to a 'dvg_devices.Arduino_protocol_serial.Arduino' instance.

        debug:
            Show debug info in terminal? Warning: Slow! Do not leave on
            unintentionally.

        (*) DAQ_function
        (*) DAQ_interval_ms
        (*) DAQ_timer_type
        (*) critical_not_alive_count

    Main methods:
        (*) start(...)
        (*) close()

        queued_write(...):
            Write a message to the Arduino via the worker_jobs queue.

    Main data attributes:
        (*) update_counter_DAQ
        (*) obtained_DAQ_interval_ms
        (*) obtained_DAQ_rate_Hz

    Signals:
        (*) signal_DAQ_updated()
        (*) signal_connection_lost()
    """

    def __init__(
        self,
        dev: Arduino,
        DAQ_trigger=DAQ_trigger.INTERNAL_TIMER,
        DAQ_function=None,
        DAQ_interval_ms=100,
        DAQ_timer_type=QtCore.Qt.PreciseTimer,
        critical_not_alive_count=1,
        calc_DAQ_rate_every_N_iter=10,
        debug=False,
        parent=None,
    ):
        super(Arduino_qdev, self).__init__(parent=parent)

        self.attach_device(dev)

        self.create_worker_DAQ(
            DAQ_trigger=DAQ_trigger,
            DAQ_function=DAQ_function,
            DAQ_interval_ms=DAQ_interval_ms,
            DAQ_timer_type=DAQ_timer_type,
            critical_not_alive_count=critical_not_alive_count,
            calc_DAQ_rate_every_N_iter=calc_DAQ_rate_every_N_iter,
            debug=debug,
        )

        self.create_worker_jobs(debug=debug)

    # --------------------------------------------------------------------------
    #   queued_write
    # --------------------------------------------------------------------------

    def queued_write(self, msg_str):
        """Send I/O operation 'write' with argument 'msg_str' to the Arduino via
        the worker_jobs queue and process the queue.
        """
        self.send(self.dev.write, msg_str)
