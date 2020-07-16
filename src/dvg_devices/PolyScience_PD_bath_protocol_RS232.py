#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RS232 function library for PolyScience PD## recirculating baths.
Supported models:
    PD07R-20, PD07R-40, PD7LR-20, PD15R-30, PD15R-40, PD20R-30, PD28R-30,
    PD45R-20, PD07H200, PD15H200, PD20H200, PD28H200, PD15RCAL, PD15HCAL.
Tested on model PD15R-30‐A12E
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "15-07-2020"
__version__ = "0.0.6"
# pylint: disable=try-except-raise, bare-except

import sys
import numpy as np

from dvg_devices.BaseDevice import SerialDevice

# Temperature setpoint limits in software, not on a hardware level
BATH_MIN_SETPOINT_DEG_C = 10  # [deg C]
BATH_MAX_SETPOINT_DEG_C = 87  # [deg C]


class PolyScience_PD_bath(SerialDevice):
    class State:
        # Container for the process and measurement variables
        # fmt: off
        setpoint = np.nan  # Setpoint read out of the bath              ['C]
        P1_temp = np.nan   # Temperature measured by the bath           ['C]
        P2_temp = np.nan   # Temperature measured by the external probe ['C]
        # fmt: on

    def __init__(self, name="Bath", long_name="PolyScience PD bath"):
        super().__init__(name=name, long_name=long_name)

        # Default serial settings
        self.serial_settings = {
            "baudrate": 57600,
            "timeout": 0.5,
            "write_timeout": 0.5,
        }
        self.set_read_termination("\r")
        self.set_write_termination("\r")

        self.set_ID_validation_query(
            ID_validation_query=self.ID_validation_query,
            valid_ID_broad="!",
            valid_ID_specific=None,
        )

        # Container for the process and measurement variables
        self.state = self.State()

    # --------------------------------------------------------------------------
    #   ID_validation_query
    # --------------------------------------------------------------------------

    def ID_validation_query(self) -> (str, str):
        # We'll use the `Disable command echo` of the PolyScience bath and check
        # for the proper reply '!'.
        _success, reply = self.query("SE0")
        broad_reply = reply.strip()  # Expected: "!"

        return (broad_reply, None)

    # --------------------------------------------------------------------------
    #   query_P1_temp
    # --------------------------------------------------------------------------

    def query_P1_temp(self):
        """Query the bath temperature and store it in the class member 'state'.
        Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query("RT")
        if success:
            try:
                num = float(reply)
            except (TypeError, ValueError) as err:
                print("ERROR: %s" % sys._getframe(0).f_code.co_name)
                print(err)
            else:
                self.state.P1_temp = num
                return True

        self.state.P1_temp = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_P2_temp
    # --------------------------------------------------------------------------

    def query_P2_temp(self):
        """Query the external probe and store it in the class member 'state'.
        Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query("RR")
        if success:
            try:
                num = float(reply)
            except (TypeError, ValueError) as err:
                print("ERROR: %s" % sys._getframe(0).f_code.co_name)
                print(err)
            else:
                self.state.P2_temp = num
                return True

        self.state.P2_temp = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_setpoint
    # --------------------------------------------------------------------------

    def query_setpoint(self):
        """Query the temperature setpoint in [deg C] set at the PolyScience bath
        and store it in the class member 'state'. Will be set to numpy.nan if
        unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query("RS")
        # print("query_setpoint returns: %s" % reply)  # DEBUG
        if success:
            try:
                num = float(reply)
            except (TypeError, ValueError) as err:
                print("ERROR: %s" % sys._getframe(0).f_code.co_name)
                print(err)
            else:
                self.state.setpoint = num
                return True

        self.state.setpoint = np.nan
        return False

    # --------------------------------------------------------------------------
    #   send_setpoint
    # --------------------------------------------------------------------------

    def send_setpoint(self, setpoint):
        """Send a new temperature setpoint in [deg C] to the PolyScience bath.

        Args:
            setpoint (float): temperature in [deg C].

        Returns: True if successful, False otherwise.
        """
        try:
            setpoint = float(setpoint)
        except (TypeError, ValueError):
            # Invalid number
            print("WARNING: Received illegal setpoint value")
            print("Setpoint not updated")
            return False

        if setpoint < BATH_MIN_SETPOINT_DEG_C:
            setpoint = BATH_MIN_SETPOINT_DEG_C
            print(
                "WARNING: setpoint is capped\nto the lower limit of %.2f 'C"
                % BATH_MIN_SETPOINT_DEG_C
            )
        elif setpoint > BATH_MAX_SETPOINT_DEG_C:
            setpoint = BATH_MAX_SETPOINT_DEG_C
            print(
                "WARNING: setpoint is capped\nto the upper limit of %.2f 'C"
                % BATH_MAX_SETPOINT_DEG_C
            )

        success, reply = self.query("SS%.2f" % setpoint)
        # print("send_setpoint returns: %s" % reply)  # DEBUG
        if success and reply == "!":  # Also check status reply
            return True
        elif success and reply == "?":
            print("WARNING @ send_setpoint")
            print("PolyScience bath might be in stand-by mode.")
            return False
        else:
            return False


# ------------------------------------------------------------------------------
#   Main: Will show a demo when run from the terminal
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import time

    # Path to the config textfile containing the (last used) RS232 port
    PATH_CONFIG = "config/port_PolyScience.txt"

    bath = PolyScience_PD_bath()
    if bath.auto_connect(filepath_last_known_port=PATH_CONFIG):
        # TO DO: display internal settings of the PolyScience bath, like
        # its temperature limits, etc.
        pass
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
    send_setpoint = 15.0
    do_send_setpoint = False

    bath.query_setpoint()
    print("\nSet: %6.2f 'C" % bath.state.setpoint)

    # Loop
    done = False
    while not done:
        # Check if a new setpoint has to be send
        if do_send_setpoint:
            bath.send_setpoint(send_setpoint)
            # The bath needs time to process and update its setpoint, which is
            # found to be up to 1 seconds (!) long. Hence, we sleep.
            time.sleep(1)
            bath.query_setpoint()
            print("\nSet: %6.2f 'C" % bath.state.setpoint)
            do_send_setpoint = False

        # Measure and report the temperatures
        bath.query_P1_temp()
        bath.query_P2_temp()
        print("\rP1 : %6.2f 'C" % bath.state.P1_temp, end="")
        print("  P2 : %6.2f 'C" % bath.state.P2_temp, end="")
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
                    send_setpoint = input("\nEnter new setpoint ['C]: ")
                    do_send_setpoint = True

        # Slow down update period
        time.sleep(0.5)

    bath.close()
    time.sleep(1)
