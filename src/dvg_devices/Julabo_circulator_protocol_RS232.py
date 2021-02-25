#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RS232 function library for Julabo circulators.
Tested on model FP51-SL.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "25-02-2021"
__version__ = "0.2.4"
# pylint: disable=bare-except, broad-except, bad-string-format-type

import time
import numpy as np
import serial

from dvg_debug_functions import print_fancy_traceback as pft
from dvg_devices.BaseDevice import SerialDevice


# The manual states that
# - OUT commands should have a time gap > 250 ms. These are 'send' operations.
# - IN commands should have a time gap > 10 ms. These are 'query' operations.
# This module will enforce these time gaps.
DELAY_COMMAND_IN = 0.01  # [ms]
DELAY_COMMAND_OUT = 0.25  # [ms]


class Julabo_circulator(SerialDevice):
    class State:
        # Container for the process and measurement variables
        # fmt: off
        version = ""         # Version of the Julabo firmware         (string)
                             # FP51-SL: "JULABO HIGHTECH FL HL/SL VERSION 4.0"
        status = np.nan      # Status or error message of the Julabo  (string)
        has_error = np.nan   # True when status is a negative number    (bool)
        temp_unit = np.nan   # Temperature unit used by the Julabo  ("C"; "F")
        running = np.nan     # Is the circulator running?               (bool)

        selected_setpoint = np.nan  # Setpoint used by the Julabo    (1; 2; 3)
        setpoint_1 = np.nan  # Read-out temperature setpoint preset #1  [C; F]
        setpoint_2 = np.nan  # Read-out temperature setpoint preset #2  [C; F]
        setpoint_3 = np.nan  # Read-out temperature setpoint preset #3  [C; F]
        bath_temp = np.nan   # Current bath temperature                 [C; F]
        pt100_temp = np.nan  # Current external Pt100 temperature       [C; F]

        over_temp = np.nan   # High-temperature warning limit           [C; F]
        sub_temp = np.nan    # Low-temperature warning limit            [C; F]

        # The Julabo has an independent temperature safety circuit. When the
        # safety sensor reading `SafeSens` is above the screw-set excess
        # temperature protection `SafeTemp`, the circulator will switch off.
        safe_sens = np.nan   # Safety sensor temperature reading        [C; F]
        safe_temp = np.nan   # Screw-set excess temperature protection  [C; F]

        # Time keeping to slow down communication per manual specs
        t_prev_out = np.nan  # Timestamp of previous OUT command [s]
        t_prev_in = np.nan   # Timestamp of previous IN command [s]
        # fmt: on

    def __init__(self, name="Julabo", long_name="Julabo circulator"):
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
        # Strange Julabo quirk: The first query always times out
        try:
            self.query("VERSION")
        except:
            pass  # Ignore the first time-out

        _success, reply = self.query("VERSION")
        broad_reply = reply[:6]  # Expected: "JULABO"
        reply_specific = reply[7:]

        return (broad_reply, reply_specific)

    # --------------------------------------------------------------------------
    #   begin
    # --------------------------------------------------------------------------

    def begin(self):
        """This function should run directly after having established a
        connection to a Julabo. It retrieves the first readings and settings
        from the Julabo.

        Returns: True if successful, False otherwise.
        """

        success = True

        success &= self.query_version()
        success &= self.query_temp_unit()
        success &= self.query_sub_temp()
        success &= self.query_over_temp()
        success &= self.query_safe_temp()

        success &= self.query_running()
        success &= self.query_selected_setpoint()
        success &= self.query_setpoint_1()
        success &= self.query_setpoint_2()
        success &= self.query_setpoint_3()

        success &= self.query_bath_temp()
        success &= self.query_pt100_temp()
        success &= self.query_safe_sens()
        success &= self.query_status()

        return success

    # --------------------------------------------------------------------------
    #   turn_on/off
    # --------------------------------------------------------------------------

    def turn_off(self):
        """Turn the Julabo off.

        Returns: True if successful, False otherwise.
        """

        if self.write_("OUT_MODE_05 0"):
            self.state.running = False
            return True
        else:
            return False

    def turn_on(self):
        """Turn the Julabo on.

        Returns: True if successful, False otherwise.
        """

        if self.write_("OUT_MODE_05 1"):
            self.state.running = True
            return True
        else:
            return False

    # --------------------------------------------------------------------------
    #   select_setpoint
    # --------------------------------------------------------------------------

    def select_setpoint(self, numero: int):
        """Instruct the Julabo to select another setpoint preset.

        Args:
          numero (int): Setpoint to be used, either 1, 2 or 3.

        Returns: True if successful, False otherwise.
        """

        if not (numero == 1 or numero == 2 or numero == 3):
            pft(
                "WARNING: Received illegal setpoint preset.\n"
                "Must be either 1, 2 or 3."
            )
            return False

        if self.write_("OUT_MODE_01 %i" % (numero - 1)):
            self.state.selected_setpoint = numero
            return True
        else:
            return False

    # --------------------------------------------------------------------------
    #   set_sub_temp
    # --------------------------------------------------------------------------

    def set_sub_temp(self, value: float):
        """Set the low-temperature warning limit. Subsequently, the Julabo is
        queried for the obtained value, which might be different than the one
        requested.

        Returns: True if all communication was successful, False otherwise.
        """

        try:
            value = float(value)
        except (TypeError, ValueError) as err:
            pft(err)
            return False

        if self.write_("OUT_SP_04 %.2f" % value):
            return self.query_sub_temp()
        else:
            return False

    # --------------------------------------------------------------------------
    #   set_over_temp
    # --------------------------------------------------------------------------

    def set_over_temp(self, value: float):
        """Set the high-temperature warning limit. Subsequently, the Julabo is
        queried for the obtained value, which might be different than the one
        requested.

        Returns: True if all communication was successful, False otherwise.
        """

        try:
            value = float(value)
        except (TypeError, ValueError) as err:
            pft(err)
            return False

        if self.write_("OUT_SP_03 %.2f" % value):
            return self.query_over_temp()
        else:
            return False

    # --------------------------------------------------------------------------
    #   set_sendpoint_1
    # --------------------------------------------------------------------------

    def set_setpoint_1(self, value: float):
        """Set the temperature setpoint #1. Subsequently, the Julabo is queried
        for the obtained value, which might be different than the one requested.

        Returns: True if all communication was successful, False otherwise.
        """

        try:
            value = float(value)
        except (TypeError, ValueError) as err:
            pft(err)
            return False

        if self.write_("OUT_SP_00 %.2f" % value):
            return self.query_setpoint_1()
        else:
            return False

    # --------------------------------------------------------------------------
    #   set_sendpoint_2
    # --------------------------------------------------------------------------

    def set_setpoint_2(self, value: float):
        """Set the temperature setpoint #2. Subsequently, the Julabo is queried
        for the obtained value, which might be different than the one requested.

        Returns: True if all communication was successful, False otherwise.
        """

        try:
            value = float(value)
        except (TypeError, ValueError) as err:
            pft(err)
            return False

        if self.write_("OUT_SP_01 %.2f" % value):
            return self.query_setpoint_2()
        else:
            return False

    # --------------------------------------------------------------------------
    #   set_sendpoint_3
    # --------------------------------------------------------------------------

    def set_setpoint_3(self, value: float):
        """Set the temperature setpoint #3. Subsequently, the Julabo is queried
        for the obtained value, which might be different than the one requested.

        Returns: True if all communication was successful, False otherwise.
        """

        try:
            value = float(value)
        except (TypeError, ValueError) as err:
            pft(err)
            return False

        if self.write_("OUT_SP_02 %.2f" % value):
            return self.query_setpoint_3()
        else:
            return False

    # --------------------------------------------------------------------------
    #   query_version
    # --------------------------------------------------------------------------

    def query_version(self):
        """Query the version of the Julabo firmware and store it in the class
        member 'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query_("VERSION")
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
        success, reply = self.query_("STATUS")
        if success:
            self.state.status = reply

            try:
                status_number = int(self.state.status[:3])
            except (TypeError, ValueError) as err:
                self.state.has_error = np.nan
                pft(err)
            else:
                if status_number < 0:
                    self.state.has_error = True
                else:
                    self.state.has_error = False

            return True

        self.state.status = np.nan
        self.state.has_error = np.nan
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
        success, reply = self.query_("IN_SP_06")
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
        success, reply = self.query_("IN_MODE_05")
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
    #   query_sub_temp
    # --------------------------------------------------------------------------

    def query_sub_temp(self):
        """Query the low-temperature warning limit and store it in the class
        member 'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query_("IN_SP_04")
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
    #   query_over_temp
    # --------------------------------------------------------------------------

    def query_over_temp(self):
        """Query the high-temperature warning limit and store it in the class
        member 'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query_("IN_SP_03")
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
    #   query_safe_temp
    # --------------------------------------------------------------------------

    def query_safe_temp(self):
        """Query the screw-set excess temperature protection and store it in the
        class member 'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query_("IN_PV_04")
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

    # --------------------------------------------------------------------------
    #   query_safe_sens
    # --------------------------------------------------------------------------

    def query_safe_sens(self):
        """Query the safety sensor temperature and store it in the class member
        'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query_("IN_PV_03")
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
    #   query_selected_setpoint
    # --------------------------------------------------------------------------

    def query_selected_setpoint(self):
        """Query the selected setpoint preset used by the Julabo (either 1, 2 or
        3) and store it in the class member 'state'. Will be set to numpy.nan if
        unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query_("IN_MODE_01")
        if success:
            try:
                num = int(reply)
            except (TypeError, ValueError) as err:
                pft(err)
            else:
                self.state.selected_setpoint = num + 1
                return True

        self.state.selected_setpoint = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_setpoint_1
    # --------------------------------------------------------------------------

    def query_setpoint_1(self):
        """Query the temperature setpoint #1 and store it in the class member
        'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query_("IN_SP_00")
        if success:
            try:
                num = float(reply)
            except (TypeError, ValueError) as err:
                pft(err)
            else:
                self.state.setpoint_1 = num
                return True

        self.state.setpoint_1 = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_setpoint_2
    # --------------------------------------------------------------------------

    def query_setpoint_2(self):
        """Query the temperature setpoint #2 and store it in the class member
        'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query_("IN_SP_01")
        if success:
            try:
                num = float(reply)
            except (TypeError, ValueError) as err:
                pft(err)
            else:
                self.state.setpoint_2 = num
                return True

        self.state.setpoint_2 = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_setpoint_3
    # --------------------------------------------------------------------------

    def query_setpoint_3(self):
        """Query the temperature setpoint #3 and store it in the class member
        'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query_("IN_SP_02")
        if success:
            try:
                num = float(reply)
            except (TypeError, ValueError) as err:
                pft(err)
            else:
                self.state.setpoint_3 = num
                return True

        self.state.setpoint_3 = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_bath_temp
    # --------------------------------------------------------------------------

    def query_bath_temp(self):
        """Query the current bath temperature and store it in the class member
        'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query_("IN_PV_00")
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
    #   query_pt100_temp
    # --------------------------------------------------------------------------

    def query_pt100_temp(self):
        """Query the current external Pt100 temperature sensor and store it in
        the class member 'state'. Will be set to numpy.nan if no external sensor
        is connected or when communication is unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query_("IN_PV_02")
        if success:
            if reply == "---.--":  # Not connected
                self.state.pt100_temp = np.nan
                return True

            try:
                num = float(reply)
            except (TypeError, ValueError) as err:
                pft(err)
            else:
                self.state.pt100_temp = num
                return True

        self.state.pt100_temp = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_common_readings
    # --------------------------------------------------------------------------

    def query_common_readings(self):
        """Query the most common readings:
        - Running?
        - Bath temperature
        - Pt100 temperature
        - Safe sensor temperature
        - Status

        Returns: True if successful, False otherwise.
        """

        success = True
        success &= self.query_running()
        success &= self.query_bath_temp()
        success &= self.query_pt100_temp()
        success &= self.query_safe_sens()
        success &= self.query_status()

        return success

    # --------------------------------------------------------------------------
    #   report
    # --------------------------------------------------------------------------

    def report(self, update_readings: bool = True):
        """Print info to the terminal, useful for debugging
        """

        C = self.state  # Shorthand notation
        w1 = 10  # Label width
        w2 = 8  # Value width

        # Update readings
        if C.selected_setpoint == 3:
            setpoint = C.setpoint_3
        elif C.selected_setpoint == 2:
            setpoint = C.setpoint_2
        else:
            setpoint = C.setpoint_1

        if update_readings:
            self.query_common_readings()

        # Print to terminal
        print(self.state.version)
        print("%-*s: %-*s" % (w1, "Temp. unit", w2, C.temp_unit), end="")
        print("%-*s: #%-*s" % (w1, "Sel. setp.", w2, C.selected_setpoint))
        print("%-*s: %-*.2f" % (w1, "Sub temp.", w2, C.sub_temp), end="")
        print("%-*s: %-*.2f" % (w1, "Over temp.", w2, C.over_temp))
        print("%-*s  %-*s" % (w1, "", w2, ""), end="")
        print("%-*s: %-*.2f" % (w1, "Safe temp.", w2, C.safe_temp))
        print()
        print("%s" % ("--> RUNNING <--" if C.running else "IDLE"))
        print("%-*s: %-*.2f" % (w1, "Setpoint", w2, setpoint), end="")
        print("%-*s: %-*.2f" % (w1, "Bath temp.", w2, C.bath_temp))
        print("%-*s: %-*.2f" % (w1, "Safe sens", w2, C.safe_sens), end="")
        print("%-*s: %-*.2f" % (w1, "Pt100", w2, C.pt100_temp))
        print()
        print("Status msg: %s" % C.status)

    # --------------------------------------------------------------------------
    #   query_
    # --------------------------------------------------------------------------

    def query_(self, *args, **kwargs) -> tuple:
        """Wrapper for :meth:`dvg_qdevices.query` to add enforcing of time gaps
        between commands as per the Julabo manual.

        Returns:
            :obj:`tuple`:
                - success (:obj:`bool`):
                    True if successful, False otherwise.

                - reply (:obj:`str` | :obj:`bytes` | :obj:`None`):
                    Reply received from the device, either as ASCII string
                    (default) or as bytes when ``returns_ascii`` was set to
                    :const:`False`. :obj:`None` if unsuccessful.
        """

        # fmt: off
        while (
            (time.perf_counter() - self.state.t_prev_in < DELAY_COMMAND_IN) or
            (time.perf_counter() - self.state.t_prev_out < DELAY_COMMAND_OUT)
        ):
            pass
        # fmt: on

        success, reply = super().query(*args, **kwargs)
        self.state.t_prev_in = time.perf_counter()

        return (success, reply)

    # --------------------------------------------------------------------------
    #   write_
    # --------------------------------------------------------------------------

    def write_(self, *args, **kwargs) -> bool:
        """Wrapper for :meth:`dvg_qdevices.write` to add enforcing of time gaps
        between commands as per the Julabo manual.

        Returns: True if successful, False otherwise.
        """

        # fmt: off
        while (
            (time.perf_counter() - self.state.t_prev_in < DELAY_COMMAND_IN) or
            (time.perf_counter() - self.state.t_prev_out < DELAY_COMMAND_OUT)
        ):
            pass
        # fmt: on

        success = super().write(*args, **kwargs)
        self.state.t_prev_out = time.perf_counter()

        return success


# -----------------------------------------------------------------------------
#   Main: Will show a demo when run from the terminal
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import sys

    # Path to the config textfile containing the (last used) RS232 port
    PATH_CONFIG = "config/port_Julabo_circulator.txt"

    # Create connection to Julabo over RS232
    julabo = Julabo_circulator()
    if julabo.auto_connect(filepath_last_known_port=PATH_CONFIG):
        julabo.begin()  # Retrieve necessary parameters
    else:
        time.sleep(1)
        sys.exit(0)

    if os.name == "nt":
        import msvcrt

        running_Windows = True
    else:
        running_Windows = False

    # Prepare
    send_setpoint = 22.0
    do_send_setpoint = False

    # Loop
    done = False
    while not done:
        # Check if a new setpoint has to be send
        if do_send_setpoint:
            if julabo.state.selected_setpoint == 3:
                julabo.set_setpoint_3(send_setpoint)
            elif julabo.state.selected_setpoint == 2:
                julabo.set_setpoint_2(send_setpoint)
            else:
                julabo.set_setpoint_1(send_setpoint)
            do_send_setpoint = False

        # Measure and report
        julabo.query_common_readings()

        if running_Windows:
            os.system("cls")
            julabo.report(update_readings=False)

            print("\nPress Q to quit.")
            print("Press S to enter new setpoint.")
            print("Press O to toggle the Julabo on/off.")
        else:
            os.system("clear")
            julabo.report(update_readings=False)

            print("\nPress Control + C to quit.")
            print("No other keyboard input possible because OS is not Windows.")

        sys.stdout.flush()

        # Process keyboard input
        if running_Windows:
            if msvcrt.kbhit():
                key = msvcrt.getch()

                if key == b"q":
                    print("\nAre you sure you want to quit [y/n]?")
                    if msvcrt.getch() == b"y":
                        print("Switching off Julabo and quitting.")
                        done = True

                elif key == b"s":
                    send_setpoint = input("\nEnter new setpoint: ")

                    try:
                        send_setpoint = float(send_setpoint)
                    except Exception as err:
                        print("Error: Could not parse float value.")
                    else:
                        do_send_setpoint = True

                elif key == b"o":
                    if julabo.state.running:
                        julabo.turn_off()
                    else:
                        julabo.turn_on()

        # Slow down update period
        time.sleep(1)

    julabo.turn_off()
    time.sleep(1)  # Give time to turn off

    julabo.close()
