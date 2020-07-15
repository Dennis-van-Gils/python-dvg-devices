#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Module to communicate with an Arduino(-like) device over a serial connection.
* Provides automatic scanning over all serial ports for the Arduino.
* Mimicks the [PyVISA](https://pypi.org/project/PyVISA/) library  by providing
  ``query`` and ``query_ascii_values`` methods, which write a message to the
  Arduino and return back its reply.

The Arduino should be programmed to respond to a so-called 'identity' query over
the serial connection. It must reply to ``query('id?')`` with an ASCII string
response. Choosing a unique identity response per each Arduino in your project
allows for auto-connecting to these Arduinos without specifying the serial port.

Only ASCII based communication is supported so-far. Binary encoded communication
will be possible as well after a few modifications to this library have been
made (work in progress).

#### On the Arduino side
I also provide a C++ library for the Arduino(-like) device. It provides
listening to a serial port for commands and act upon them. This library can be
used in conjunction (but not required) with this Python library.
See [DvG_SerialCommand](https://github.com/Dennis-van-Gils/DvG_SerialCommand).

Classes:
    Arduino(...):
        Manages serial communication with an Arduino(-like) device.

        Methods:
            close():
                Close the serial connection.
            connect_at_port(...)
                Try to establish a connection on this serial port.
            scan_ports(...)
                Scan over all serial ports and try to establish a connection.
            auto_connect(...)
                Try the last used serial port, or scan over all when it fails.
            write(...)
                Write a string to the serial port.
            query(...)
                Write a string to the serial port and return the reply.
            query_ascii_values(...)
                Write a string to the serial port and return the reply, parsed
                into a list of floats.

        Important member:
            ser: serial.Serial instance belonging to the Arduino
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "15-07-2020"
__version__ = "0.0.5"

import sys

from dvg_devices.BaseDevice import SerialDevice


class Arduino(SerialDevice):
    def __init__(
        self, name="Ard_1", long_name="Arduino", connect_to_specific_ID=None,
    ):
        super().__init__(
            name=name, long_name=long_name,
        )

        # Default serial settings
        self.serial_settings = {
            "baudrate": 9600,
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

    readings = ard.query_ascii_values("?")[1]
    print(readings)

    # print(ard.query("?")[1])
    # print(ard.query("?")[1])
    # print(ard.query("?")[1])
    # print(ard.query_ascii_values("?", "\t"))

    ard.close()
