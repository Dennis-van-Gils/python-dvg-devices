#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RS232 function library for Bronkhorst mass flow controllers (MFC) using the
FLOW-BUS protocol.

Only the ASCII version is supported, not the enhanced binary version. This
library sends and receives messages to/from all nodes (code 80), hence just one
MFC is assumed per port.

When this module is directly run from the terminal a demo will be shown.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "23-05-2024"
__version__ = "1.4.0"
# pylint: disable=missing-function-docstring

import sys
import struct
from typing import Union, Tuple

import numpy as np

from dvg_devices.BaseDevice import SerialDevice


class Bronkhorst_MFC(SerialDevice):
    class State:
        """Container for the process and measurement variables"""

        setpoint: float = np.nan
        """Setpoint read out of the MFC  [ln/min]"""
        flow_rate: float = np.nan
        """Flow rate measured by the MFC [ln/min]"""

    def __init__(
        self,
        name="MFC",
        long_name="Bronkhorst MFC",
        connect_to_serial_number=None,
    ):
        super().__init__(name=name, long_name=long_name)

        # Default serial settings
        self.serial_settings = {
            "baudrate": 38400,
            "timeout": 0.1,
            "write_timeout": 0.1,
        }
        self.set_read_termination("\r\n")
        self.set_write_termination("\r\n")

        self.set_ID_validation_query(
            ID_validation_query=self.ID_validation_query,
            valid_ID_broad="8002716300",
            valid_ID_specific=connect_to_serial_number,
        )

        # Container for the process and measurement variables
        self.state = self.State()

        # fmt: off
        self.serial_str: str = ""  # Serial number of the MFC
        self.model_str : str = ""  # Model of the MFC
        self.fluid_name: str = ""  # Fluid for which the MFC is calibrated
        self.max_flow_rate: float = np.nan  # Max. capacity [ln/min]
        # fmt: on

    # --------------------------------------------------------------------------
    #   ID_validation_query
    # --------------------------------------------------------------------------

    def ID_validation_query(self) -> Tuple[str, Union[str, None]]:
        _success, reply = self.query(":0780047163716300")
        if isinstance(reply, str):
            broad_reply = reply[3:13]  # Expected: "8002716300"
            specific_reply = bytearray.fromhex(reply[13:-2]).decode()  # Serial
        else:
            broad_reply = ""
            specific_reply = None

        return broad_reply, specific_reply

    # --------------------------------------------------------------------------
    #   begin
    # --------------------------------------------------------------------------

    def begin(self):
        """This function should run directly after having established a
        connection to the device.

        Query the serial number, model, fluid and the maximum mass flow rate of
        the MFC and store these in the class member 'state's. The max flow rate
        is mandatory to be known, because it is used to set and read the
        setpoint, and to read the flow rate.

        Returns: True if successful, False otherwise.
        """
        success = self.query_serial_str()
        success &= self.query_model_str()
        success &= self.query_fluid_name()
        success &= self.query_max_flow_rate()
        success &= self.query_setpoint()
        success &= self.query_flow_rate()
        return success

    # --------------------------------------------------------------------------
    #   query_serial_str
    # --------------------------------------------------------------------------

    def query_serial_str(self) -> bool:
        """Query the serial number and store it in the class member 'serial_str'

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query(":0780047163716300")
        if isinstance(reply, str) and reply[3:13] == "8002716300":
            self.serial_str = bytearray.fromhex(reply[13:-2]).decode()
            return True

        self.serial_str = ""
        return False

    # --------------------------------------------------------------------------
    #   query_model_str
    # --------------------------------------------------------------------------

    def query_model_str(self) -> bool:
        """Query the model name of the MFC and store it in the class member
        'state'.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query(":0780047162716200")
        if isinstance(reply, str):
            self.model_str = bytearray.fromhex(reply[13:-2]).decode()
            return True

        self.model_str = ""
        return False

    # --------------------------------------------------------------------------
    #   query_fluid_name
    # --------------------------------------------------------------------------

    def query_fluid_name(self) -> bool:
        """Query the fluid name that the MFC is calibrated for and store it in
        the class member 'state'.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query(":078004017101710A")
        if isinstance(reply, str):
            self.fluid_name = bytearray.fromhex(reply[13:-2]).decode()
            return True

        self.fluid_name = ""
        return False

    # --------------------------------------------------------------------------
    #   query_max_flow_rate
    # --------------------------------------------------------------------------

    def query_max_flow_rate(self) -> bool:
        """Query the maximum mass flow rate in [ln/min] of the MFC and store it
        in the class member 'state'. This value is mandatory to be known, because it is
        used to set and read the setpoint, and to read the flow rate.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query(":068004014D014D")
        if isinstance(reply, str):
            self.max_flow_rate = hex_to_32bit_IEEE754_float(reply[11:])
            return True

        self.max_flow_rate = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_setpoint
    # --------------------------------------------------------------------------

    def query_setpoint(self) -> bool:
        """Query the mass flow rate setpoint in [ln/min] set at the MFC and
        store it in the class member 'state' 'state'. Will be set to None if
        unsuccessful.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query(":06800401210121")
        if isinstance(reply, str):
            try:
                num = int(reply[-4:], 16)
            except ValueError:
                pass
            else:
                self.state.setpoint = num / 32000.0 * self.max_flow_rate
                return True

        self.state.setpoint = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_flow_rate
    # --------------------------------------------------------------------------

    def query_flow_rate(self) -> bool:
        """Query the mass flow rate in [ln/min] measured by the MFC and
        store it in the class member 'state'. Will be set to None if
        unsuccessful.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query(":06800401210120")
        if isinstance(reply, str):
            try:
                num = int(reply[-4:], 16)
            except ValueError:
                pass
            else:
                self.state.flow_rate = num / 32000.0 * self.max_flow_rate
                return True

        self.state.flow_rate = np.nan
        return False

    # --------------------------------------------------------------------------
    #   send_setpoint
    # --------------------------------------------------------------------------

    def send_setpoint(self, setpoint: float) -> bool:
        """Send a new mass flow rate setpoint in [ln/min] to the MFC.

        Args:
            setpoint (float): mass flow rate in [ln/min].

        Returns: True if successful, False otherwise.
        """
        # Transform setpoint and limit
        setpoint = int(setpoint / self.max_flow_rate * 32000)
        setpoint = max(0, min(setpoint, 32000))

        _success, reply = self.query(f":0680010121{setpoint:04x}")
        if isinstance(reply, str) and reply[5:].strip() == "000005":
            return True  # Also checked status reply

        return False


# ------------------------------------------------------------------------------
#   hex_to_32bit_IEEE754_float
# ------------------------------------------------------------------------------


def hex_to_32bit_IEEE754_float(hex_str) -> float:
    """Transform a string containing a hexidecimal representation of a 32-bits
    IEEE754-formatted float value to a float
    """
    return (struct.unpack("f", struct.pack("i", int(hex_str, 16))))[0]


# ------------------------------------------------------------------------------
#   Main: Will show a demo when run from the terminal
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import time

    # Config file containing COM port address
    PATH_CONFIG = "config/port_Bronkhorst_MFC_1.txt"

    # Serial number of the Bronkhorst MFC to connect to.
    # Set to '' or None to connect to any Bronkhorst MFC.
    # SERIAL_MFC = "M16216843A"
    SERIAL_MFC = None

    # Create connection to Bronkhorst MFC over RS232
    mfc = Bronkhorst_MFC(connect_to_serial_number=SERIAL_MFC)
    if mfc.auto_connect(filepath_last_known_port=PATH_CONFIG):
        mfc.begin()  # Retrieve necessary parameters
        print(f"  Serial  : {mfc.serial_str}")
        print(f"  Model   : {mfc.model_str}")
        print(f"  Fluid   : {mfc.fluid_name}")
        print(f"  Capacity: {mfc.max_flow_rate:.2f} ln/min")
    else:
        time.sleep(1)
        sys.exit(0)

    if os.name == "nt":
        import msvcrt

        running_Windows = True
        print("\nPress Q to quit.")
        print("Press S to enter new setpoint.")
    else:
        running_Windows = False
        print("\nPress Control + C to quit.")
        print("No other keyboard input possible because OS is not Windows.")

    # Prepare
    send_setpoint = 0.0
    do_send_setpoint = False

    mfc.query_setpoint()
    print(f"\nSetpoint       : {mfc.state.setpoint:6.2f} ln/min")

    # Loop
    done = False
    while not done:
        # Check if a new setpoint has to be send
        if do_send_setpoint:
            mfc.send_setpoint(send_setpoint)
            mfc.query_setpoint()
            print(f"\nSetpoint       : {mfc.state.setpoint:6.2f} ln/min")
            do_send_setpoint = False

        # Measure and report the flow rate
        mfc.query_flow_rate()
        print(f"\rMeas. flow rate: {mfc.state.flow_rate:6.2f} ln/min", end="")
        sys.stdout.flush()

        # Process keyboard input
        if running_Windows:
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b"q":
                    print("\nAre you sure you want to quit [y/n]?")
                    if msvcrt.getch() == b"y":
                        print("Quitting.")
                        done = True
                    else:
                        do_send_setpoint = True  # Esthestics
                elif key == b"s":
                    input_str = input("\nEnter new setpoint [ln/min]: ")
                    try:
                        input_float = float(input_str)
                    except ValueError:
                        input_float = 0.0
                    send_setpoint = input_float
                    do_send_setpoint = True

        # Slow down update period
        time.sleep(0.02)

    mfc.close()
    time.sleep(1)
