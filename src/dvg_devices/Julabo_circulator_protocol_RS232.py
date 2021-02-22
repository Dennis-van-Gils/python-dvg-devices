#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RS232 function library for Julabo circulators.
Tested on model FP51-SL.

The circulator allows for three different setpoints (SP_00, SP_01 and SP_02),
but we will only use SP_00 for remote control by this module.

The temperature unit is expected to be in ['C] and will be checked for.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "22-02-2021"
__version__ = "0.2.4"
# pylint: disable=try-except-raise, bare-except

import sys
import numpy as np
import serial

from dvg_debug_functions import print_fancy_traceback as pft
from dvg_devices.BaseDevice import SerialDevice


class Julabo_FP_circulator(SerialDevice):
    class State:
        # Container for the process and measurement variables
        # fmt: off
        version = ""        # Version of the Julabo firmware         (string)
                            # (FP51-SL: `JULABO HIGHTECH FL HL/SL VERSION 4.0`)
        status = np.nan     # Status or error message of the Julabo  (string)
        temp_unit = np.nan  # Temperature unit used by the Julabo  ["C"; "F"]
        running = np.nan    # Is the circulator running?               (bool)

        setpoint = np.nan   # Read-out temperature setpoint #1 (SP_00)   ['C]
        bath_temp = np.nan  # Current bath temperature                   ['C]

        over_temp = np.nan  # High-temperature warning limit             ['C]
        sub_temp = np.nan   # Low-temperature warning limit              ['C]

        # The Julabo has an independent temperature safety circuit. When the
        # safety sensor reading `SafeSens` is above the screw-set excess
        # temperature protection `SafeTemp`, the circulator will switch off.
        safe_sens = np.nan  # Safety sensor temperature reading          ['C]
        safe_temp = np.nan  # Screw-set excess temperature protection    ['C]
        # fmt: on

    def __init__(self, name="Julabo", long_name="Julabo FP circulator"):
        super().__init__(name=name, long_name=long_name)

        # Default serial settings
        self.serial_settings = {
            "baudrate": 4800,
            "bytesize": serial.SEVENBITS,
            "parity": serial.PARITY_EVEN,
            "timeout": 0.5,
            "write_timeout": 0.5,
        }
        self.set_read_termination("\r\n")
        self.set_write_termination("\r")

        self.set_ID_validation_query(
            ID_validation_query=self.ID_validation_query,
            valid_ID_broad="JULABO",
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
        _success, reply = self.query("VERSION")
        broad_reply = reply[:6]  # Expected: "JULABO"
        reply_specific = reply[7:]

        return (broad_reply, reply_specific)

    # --------------------------------------------------------------------------
    #   query_version
    # --------------------------------------------------------------------------

    def query_version(self):
        """Query the version of the Julabo firmware and store it in the class
        member 'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query("VERSION")
        if success:
            self.state.version = reply
            return True

        self.state.version = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_status
    # --------------------------------------------------------------------------

    def query_status(self):
        """Query the status or error message of the Julabo and store it in the
        class member 'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query("STATUS")
        if success:
            self.state.status = reply
            return True

        self.state.status = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_temp_unit
    # --------------------------------------------------------------------------

    def query_temp_unit(self):
        """Query the temperature unit used by the Julabo and store it in the
        class member 'state'. Will be set to numpy.nan if unsuccessful, else
        either "C" or "F".

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query("IN_SP_06")
        if success:
            try:
                num = int(reply)
            except (TypeError, ValueError) as err:
                pft(err)
            else:
                self.state.temp_unit = "C" if num == 0 else "F"
                return True

        self.state.temp_unit = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_running
    # --------------------------------------------------------------------------

    def query_running(self):
        """Query if the Julabo is running and store it in the class member
        'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query("IN_MODE_05")
        if success:
            try:
                ans = bool(int(reply))
            except (TypeError, ValueError) as err:
                pft(err)
            else:
                self.state.running = ans
                return True

        self.state.running = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_bath_temp
    # --------------------------------------------------------------------------

    def query_bath_temp(self):
        """Query the current bath temperature and store it in the class member
        'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query("IN_PV_00")
        if success:
            try:
                num = float(reply)
            except (TypeError, ValueError) as err:
                pft(err)
            else:
                self.state.bath_temp = num
                return True

        self.state.bath_temp = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_setpoint
    # --------------------------------------------------------------------------

    def query_setpoint(self):
        """Query the temperature setpoint #1 and store it in the class member
        'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query("IN_SP_00")
        if success:
            try:
                num = float(reply)
            except (TypeError, ValueError) as err:
                pft(err)
            else:
                self.state.setpoint = num
                return True

        self.state.setpoint = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_over_temp
    # --------------------------------------------------------------------------

    def query_over_temp(self):
        """Query the high-temperature warning limit and store it in the class
        member 'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query("IN_SP_03")
        if success:
            try:
                num = float(reply)
            except (TypeError, ValueError) as err:
                pft(err)
            else:
                self.state.over_temp = num
                return True

        self.state.over_temp = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_sub_temp
    # --------------------------------------------------------------------------

    def query_sub_temp(self):
        """Query the low-temperature warning limit and store it in the class
        member 'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query("IN_SP_04")
        if success:
            try:
                num = float(reply)
            except (TypeError, ValueError) as err:
                pft(err)
            else:
                self.state.sub_temp = num
                return True

        self.state.sub_temp = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_safe_sens
    # --------------------------------------------------------------------------

    def query_safe_sens(self):
        """Query the safety sensor temperature and store it in the class member
        'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query("IN_PV_03")
        if success:
            try:
                num = float(reply)
            except (TypeError, ValueError) as err:
                pft(err)
            else:
                self.state.safe_sens = num
                return True

        self.state.safe_sens = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_safe_temp
    # --------------------------------------------------------------------------

    def query_safe_temp(self):
        """Query the screw-set excess temperature protection and store it in the
        class member 'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query("IN_PV_04")
        if success:
            try:
                num = float(reply)
            except (TypeError, ValueError) as err:
                pft(err)
            else:
                self.state.safe_temp = num
                return True

        self.state.safe_temp = np.nan
        return False

    """
    # --------------------------------------------------------------------------
    #   send_setpoint
    # --------------------------------------------------------------------------

    def send_setpoint(self, setpoint):
        ""Send a new temperature setpoint in [deg C] to the PolyScience bath.

        Args:
            setpoint (float): temperature in [deg C].

        Returns: True if successful, False otherwise.
        ""
        try:
            setpoint = float(setpoint)
        except (TypeError, ValueError):
            # Invalid number
            print("WARNING: Received illegal setpoint value")
            print("Setpoint not updated")
            return False

        if setpoint < MIN_SETPOINT_DEG_C:
            setpoint = MIN_SETPOINT_DEG_C
            print(
                "WARNING: setpoint is capped\nto the lower limit of %.2f 'C"
                % MIN_SETPOINT_DEG_C
            )
        elif setpoint > MAX_SETPOINT_DEG_C:
            setpoint = MAX_SETPOINT_DEG_C
            print(
                "WARNING: setpoint is capped\nto the upper limit of %.2f 'C"
                % MAX_SETPOINT_DEG_C
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
    """
