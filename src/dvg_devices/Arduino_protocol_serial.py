#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Provides higher-level general I/O methods for communicating with an
Arduino(-like) board over the serial connection.

The Arduino could be programmed to respond to a so-called 'identity' query over
the serial connection. It must reply to ASCII command "id?" with an ASCII string
response. Choosing a unique identity response per each Arduino in your project
allows for auto-connecting to your Arduino without having to specify the serial
port.

#### On the Arduino side
I also provide a C++ library for the Arduino(-like) device. It provides
listening to a serial port for commands and act upon them. This library can be
used in conjunction (but not required) with this Python module.
See https://github.com/Dennis-van-Gils/DvG_SerialCommand.

    Class Arduino(...):
        Manages serial communication with an Arduino(-like) device.

        Most important methods:
            connect_at_port(...)
            scan_ports(...)
            auto_connect(...)
            close()

            write(...)
            query(...)
            query_ascii_values(...)

See https://python-dvg-devices.readthedocs.io/en/latest/api-serialdevice.html
for the documentation of all the methods and attributes that are available.
Instances of this class will tie in nicely with
https://python-dvg-qdeviceio.readthedocs.io.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "15-07-2020"
__version__ = "0.0.6"

import sys

from dvg_devices.BaseDevice import SerialDevice


class Arduino(SerialDevice):
    def __init__(
        self, name="Ard_1", long_name="Arduino", connect_to_specific_ID=None,
    ):
        super().__init__(name=name, long_name=long_name)

        # Default serial settings
        self.serial_settings = {
            "baudrate": 115200,
            "timeout": 2,
            "write_timeout": 2,
        }
        self.set_read_termination("\n")
        self.set_write_termination("\n")

        self.set_ID_validation_query(
            ID_validation_query=self.ID_validation_query,
            valid_ID_broad="Arduino",
            valid_ID_specific=connect_to_specific_ID,
        )

    # --------------------------------------------------------------------------
    #   ID_validation_query
    # --------------------------------------------------------------------------

    def ID_validation_query(self) -> (str, str):
        # Expected: reply = "Arduino, [specific ID]"
        _success, reply = self.query("id?")
        reply = reply.split(",")
        reply_broad = reply[0].strip()  # "Arduino"
        reply_specific = reply[1].strip() if len(reply) > 1 else None

        return (reply_broad, reply_specific)


# ------------------------------------------------------------------------------
#   Main: Will show a demo when run from the terminal
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    ard = Arduino(name="Ard_1", connect_to_specific_ID="Wave generator")

    ard.serial_settings["baudrate"] = 115200
    ard.auto_connect()
    # ard.scan_ports()

    if not ard.is_alive:
        sys.exit(0)

    _success, readings = ard.query_ascii_values("?")
    print(readings)

    _success, reply = ard.query("?")
    print(reply)

    ard.close()
