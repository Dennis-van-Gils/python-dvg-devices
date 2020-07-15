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
__date__ = "13-07-2020"  # 0.0.1 was stamped 15-08-2019
__version__ = "0.0.5"  # 0.0.1 corresponds to prototype 1.0.2
# pylint: disable=bare-except, broad-except, try-except-raise

# Ready for subclassing SerialDevice with method `query`

import sys

from dvg_debug_functions import print_fancy_traceback as pft
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
        _success, reply = self.query("id?")
        # Expected: reply = "Arduino, [specific ID]"

        reply = reply.split(",")
        reply_broad = reply[0].strip()  # Expected reply_broad = "Arduino"
        reply_specific = reply[1].strip() if len(reply) > 1 else None

        return (reply_broad, reply_specific)

    # --------------------------------------------------------------------------
    #   query_ascii_values
    # --------------------------------------------------------------------------

    def query_ascii_values(self, msg_str="", separator="\t"):
        """Send a message to the serial device and subsequently read the reply.
        Expects a reply from the Arduino in the form of an ASCII string
        containing a list of numeric values. These values will be parsed into a
        list of floats and returned.

        Returns:
            success (bool):
                True if successful, False otherwise.
            ans_floats (list):
                Reply received from the device and parsed into a list of floats.
                [None] if unsuccessful.
        """
        [success, ans_str] = self.query(msg_str)

        if success and not ans_str == "":
            try:
                ans_floats = list(map(float, ans_str.split(separator)))
            except ValueError as err:
                # Print error and struggle on
                pft(err, 3)
            except Exception as err:
                pft(err, 3)
                sys.exit(0)
            else:
                return [True, ans_floats]

        return [False, []]


# ------------------------------------------------------------------------------
#   Main: Will show a demo when run from the terminal
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    ard = Arduino(
        name="Ard_1",
        # connect_to_specific_ID="Waveform generator"
    )

    ard.auto_connect()
    # ard.scan_ports()

    if not ard.is_alive:
        sys.exit(0)

    # print(ard.query("?")[1])
    # print(ard.query("?")[1])
    # print(ard.query("?")[1])
    # print(ard.query_ascii_values("?", "\t"))

    ard.close()
