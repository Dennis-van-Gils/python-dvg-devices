#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RS232 function library for Julabo circulators.
Tested on model FP51-SL.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "23-05-2024"
__version__ = "1.4.0"
# pylint: disable=broad-except, missing-function-docstring, multiple-statements

import time
import serial
from typing import Union, Tuple

import numpy as np

from dvg_debug_functions import print_fancy_traceback as pft
from dvg_devices.BaseDevice import SerialDevice


# The manual states that
# - OUT commands should have a time gap > 250 ms. These are 'send' operations.
# - IN commands should have a time gap > 10 ms. These are 'query' operations.
# This module will enforce these time gaps.
DELAY_COMMAND_IN = 0.02  # [s] 0.02 tested stable
DELAY_COMMAND_OUT = 0.3  # [s] 0.3 tested stable


class Julabo_circulator(SerialDevice):
    class State:
        """Container for the process and measurement variables."""

        # fmt: off
        version: str = ""    # Version of the Julabo firmware
                             # FP51-SL: "JULABO HIGHTECH FL HL/SL VERSION 4.0"
        temp_unit: str = ""  # Temperature unit used by the Julabo  ("C"; "F")
        status   : Union[float, str] = np.nan  # Status or error message of the Julabo
        has_error: Union[float, bool] = np.nan  # True when status is a negative number
        running  : Union[float, bool] = np.nan  # Is the circulator running?

        setpoint_preset = np.nan # Active setpoint preset in the Julabo (1; 2; 3)
        setpoint = np.nan    # Read-out temp. setpoint of active preset [C; F]
        setpoint_1 = np.nan  # Read-out temp. setpoint preset #1        [C; F]
        setpoint_2 = np.nan  # Read-out temp. setpoint preset #2        [C; F]
        setpoint_3 = np.nan  # Read-out temp. setpoint preset #3        [C; F]
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

    def ID_validation_query(self) -> Tuple[str, Union[str, None]]:
        # Strange Julabo quirk: The first query always times out
        try:
            self.query("VERSION")
        except Exception:
            pass  # Ignore the first time-out

        _success, reply = self.query("VERSION")
        if isinstance(reply, str):
            broad_reply = reply[:6]  # Expected: "JULABO"
            reply_specific = reply[7:]
        else:
            broad_reply = ""
            reply_specific = None

        return broad_reply, reply_specific

    # --------------------------------------------------------------------------
    #   begin
    # --------------------------------------------------------------------------

    def begin(self) -> bool:
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
        success &= self.query_setpoint_preset()
        success &= self.query_setpoint()
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

    def turn_off(self) -> bool:
        """Turn the Julabo off.

        Returns: True if successful, False otherwise.
        """

        if self.write_("OUT_MODE_05 0"):
            self.state.running = False
            return True

        return False

    def turn_on(self) -> bool:
        """Turn the Julabo on.

        Returns: True if successful, False otherwise.
        """

        if self.write_("OUT_MODE_05 1"):
            self.state.running = True
            return True

        return False

    # --------------------------------------------------------------------------
    #   set_sub_temp
    # --------------------------------------------------------------------------

    def set_sub_temp(self, value: float) -> bool:
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

        if self.write_(f"OUT_SP_04 {value:.2f}"):
            return self.query_sub_temp()

        return False

    # --------------------------------------------------------------------------
    #   set_over_temp
    # --------------------------------------------------------------------------

    def set_over_temp(self, value: float) -> bool:
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

        if self.write_(f"OUT_SP_03 {value:.2f}"):
            return self.query_over_temp()

        return False

    # --------------------------------------------------------------------------
    #   set_setpoint_preset
    # --------------------------------------------------------------------------

    def set_setpoint_preset(self, n: int) -> bool:
        """Instruct the Julabo to select another setpoint preset.

        Args:
          n (:obj:`int`): Setpoint to be used, either 1, 2 or 3.

        Returns: True if successful, False otherwise.
        """

        if not n in (1, 2, 3):
            pft(
                "WARNING: Received illegal setpoint preset.\n"
                "Must be either 1, 2 or 3."
            )
            return False

        if self.write_(f"OUT_MODE_01 {(n - 1):d}"):
            self.state.setpoint_preset = n
            return True

        return False

    # --------------------------------------------------------------------------
    #   set_sendpoint
    # --------------------------------------------------------------------------

    def set_setpoint(self, value: float) -> bool:
        """Set the temperature setpoint #1, #2 or #3, depending on which one is
        currently the active preset. Subsequently, the Julabo is queried for the
        obtained value, which might be different than the one requested.

        Returns: True if all communication was successful, False otherwise.
        """

        success = False

        if self.state.setpoint_preset == 1:
            success = self.set_setpoint_1(value)
            self.state.setpoint = self.state.setpoint_1
        elif self.state.setpoint_preset == 2:
            success = self.set_setpoint_2(value)
            self.state.setpoint = self.state.setpoint_2
        elif self.state.setpoint_preset == 3:
            success = self.set_setpoint_3(value)
            self.state.setpoint = self.state.setpoint_3

        return success

    # --------------------------------------------------------------------------
    #   set_sendpoint_1
    # --------------------------------------------------------------------------

    def set_setpoint_1(self, value: float) -> bool:
        """Set the temperature setpoint #1. Subsequently, the Julabo is queried
        for the obtained value, which might be different than the one requested.

        Returns: True if all communication was successful, False otherwise.
        """

        try:
            value = float(value)
        except (TypeError, ValueError) as err:
            pft(err)
            return False

        if self.write_(f"OUT_SP_00 {value:.2f}"):
            return self.query_setpoint_1()

        return False

    # --------------------------------------------------------------------------
    #   set_sendpoint_2
    # --------------------------------------------------------------------------

    def set_setpoint_2(self, value: float) -> bool:
        """Set the temperature setpoint #2. Subsequently, the Julabo is queried
        for the obtained value, which might be different than the one requested.

        Returns: True if all communication was successful, False otherwise.
        """

        try:
            value = float(value)
        except (TypeError, ValueError) as err:
            pft(err)
            return False

        if self.write_(f"OUT_SP_01 {value:.2f}"):
            return self.query_setpoint_2()

        return False

    # --------------------------------------------------------------------------
    #   set_sendpoint_3
    # --------------------------------------------------------------------------

    def set_setpoint_3(self, value: float) -> bool:
        """Set the temperature setpoint #3. Subsequently, the Julabo is queried
        for the obtained value, which might be different than the one requested.

        Returns: True if all communication was successful, False otherwise.
        """

        try:
            value = float(value)
        except (TypeError, ValueError) as err:
            pft(err)
            return False

        if self.write_(f"OUT_SP_02 {value:.2f}"):
            return self.query_setpoint_3()

        return False

    # --------------------------------------------------------------------------
    #   query_version
    # --------------------------------------------------------------------------

    def query_version(self) -> bool:
        """Query the version of the Julabo firmware and store it in the class
        member 'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query_("VERSION")
        if isinstance(reply, str):
            self.state.version = reply
            return True

        self.state.version = ""
        return False

    # --------------------------------------------------------------------------
    #   query_status
    # --------------------------------------------------------------------------

    def query_status(self) -> bool:
        """Query the status or error message of the Julabo and store it in the
        class member 'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query_("STATUS")
        if isinstance(reply, str):
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

    def query_temp_unit(self) -> bool:
        """Query the temperature unit used by the Julabo and store it in the
        class member 'state'. Will be set to "" if unsuccessful, else either "C"
        or "F".

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query_("IN_SP_06")
        if isinstance(reply, str):
            try:
                num = int(reply)
            except (TypeError, ValueError) as err:
                pft(err)
            else:
                self.state.temp_unit = "C" if num == 0 else "F"
                return True

        self.state.temp_unit = ""
        return False

    # --------------------------------------------------------------------------
    #   query_running
    # --------------------------------------------------------------------------

    def query_running(self) -> bool:
        """Query if the Julabo is running and store it in the class member
        'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query_("IN_MODE_05")
        if isinstance(reply, str):
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

    def query_sub_temp(self) -> bool:
        """Query the low-temperature warning limit and store it in the class
        member 'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query_("IN_SP_04")
        if isinstance(reply, str):
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

    def query_over_temp(self) -> bool:
        """Query the high-temperature warning limit and store it in the class
        member 'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query_("IN_SP_03")
        if isinstance(reply, str):
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

    def query_safe_temp(self) -> bool:
        """Query the screw-set excess temperature protection and store it in the
        class member 'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query_("IN_PV_04")
        if isinstance(reply, str):
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

    def query_safe_sens(self) -> bool:
        """Query the safety sensor temperature and store it in the class member
        'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query_("IN_PV_03")
        if isinstance(reply, str):
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
    #   query_setpoint_preset
    # --------------------------------------------------------------------------

    def query_setpoint_preset(self) -> bool:
        """Query the setpoint preset currently used by the Julabo (#1, #2 or #3)
        and store it in the class member 'state'. Will be set to numpy.nan
        if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query_("IN_MODE_01")
        if isinstance(reply, str):
            try:
                num = int(reply)
            except (TypeError, ValueError) as err:
                pft(err)
            else:
                self.state.setpoint_preset = num + 1
                return True

        self.state.setpoint_preset = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_setpoint
    # --------------------------------------------------------------------------

    def query_setpoint(self) -> bool:
        """Query the temperature setpoint #1, #2 or #3, depending on which one
        is currently the active preset, and store it in the class member
        'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        success = False

        if self.state.setpoint_preset == 1:
            success = self.query_setpoint_1()
            self.state.setpoint = self.state.setpoint_1
        elif self.state.setpoint_preset == 2:
            success = self.query_setpoint_2()
            self.state.setpoint = self.state.setpoint_2
        elif self.state.setpoint_preset == 3:
            success = self.query_setpoint_3()
            self.state.setpoint = self.state.setpoint_3

        return success

    # --------------------------------------------------------------------------
    #   query_setpoint_1
    # --------------------------------------------------------------------------

    def query_setpoint_1(self) -> bool:
        """Query the temperature setpoint #1 and store it in the class member
        'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query_("IN_SP_00")
        if isinstance(reply, str):
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

    def query_setpoint_2(self) -> bool:
        """Query the temperature setpoint #2 and store it in the class member
        'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query_("IN_SP_01")
        if isinstance(reply, str):
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

    def query_setpoint_3(self) -> bool:
        """Query the temperature setpoint #3 and store it in the class member
        'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query_("IN_SP_02")
        if isinstance(reply, str):
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

    def query_bath_temp(self) -> bool:
        """Query the current bath temperature and store it in the class member
        'state'. Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query_("IN_PV_00")
        if isinstance(reply, str):
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

    def query_pt100_temp(self) -> bool:
        """Query the current external Pt100 temperature sensor and store it in
        the class member 'state'. Will be set to numpy.nan if no external sensor
        is connected or when communication is unsuccessful.

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query_("IN_PV_02")
        if isinstance(reply, str):
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

    def query_common_readings(self) -> bool:
        """Query the most common readings:
        - Running?
        - Setpoint
        - Bath temperature
        - Pt100 temperature
        - Safe sensor temperature
        - Status

        Returns: True if successful, False otherwise.
        """

        success = True
        success &= self.query_running()
        success &= self.query_setpoint()
        success &= self.query_bath_temp()
        success &= self.query_pt100_temp()
        success &= self.query_safe_sens()
        success &= self.query_status()

        return success

    # --------------------------------------------------------------------------
    #   report
    # --------------------------------------------------------------------------

    def report(self, update_readings: bool = True):
        """Print info to the terminal, useful for debugging"""

        C = self.state  # Shorthand notation
        w1 = 10  # Label width
        w2 = 8  # Value width

        # Update readings
        if update_readings:
            self.query_common_readings()

        # Print to terminal
        print(self.state.version)
        print(f"{'Temp. unit':<{w1}s}: {C.temp_unit:<{w2}s}", end="")
        print(f"{'Sel. setp.':<{w1}s}: {C.setpoint_preset:<{w2}.0f}")
        print(f"{'Sub temp.':<{w1}s}: {C.sub_temp:<{w2}.2f}", end="")
        print(f"{'Over temp.':<{w1}s}: {C.over_temp:<{w2}.2f}")
        print(f"{'':<{w1}s}  {'':<{w2}s}", end="")
        print(f"{'Safe temp.':<{w1}s}: {C.safe_temp:<{w2}.2f}")
        print()
        if not isinstance(C.running, bool):
            print("COMMUNICATION ERROR")
        else:
            print("--> RUNNING <--" if C.running else "IDLE")
        print(f"{'Setpoint':<{w1}s}: {C.setpoint:<{w2}.2f}", end="")
        print(f"{'Bath temp.':<{w1}s}: { C.bath_temp:<{w2}.2f}")
        print(f"{'Safe sens':<{w1}s}: {C.safe_sens:<{w2}.2f}", end="")
        print(f"{'Pt100':<{w1}s}: {C.pt100_temp:<{w2}.2f}")
        print()
        print(f"Status msg: {C.status}")

    # --------------------------------------------------------------------------
    #   query_
    # --------------------------------------------------------------------------

    def query_(self, *args, **kwargs) -> Tuple[bool, Union[str, bytes, None]]:
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

        return success, reply

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
            julabo.set_setpoint(send_setpoint)
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

                if key in (b"q", b"Q"):
                    print("\nAre you sure you want to quit [y/n]?")
                    if msvcrt.getch() == b"y":
                        print("Switching off Julabo and quitting.")
                        done = True

                elif key in (b"s", b"S"):
                    user_input = input("\nEnter new setpoint: ")

                    try:
                        send_setpoint = float(user_input)
                    except Exception:
                        print("Error: Could not parse float value.")
                    else:
                        do_send_setpoint = True

                elif key in (b"o", b"O"):
                    if julabo.state.running:
                        julabo.turn_off()
                    else:
                        julabo.turn_on()

        # Slow down update period
        time.sleep(0.5)

    julabo.turn_off()
    time.sleep(1)  # Give time to turn off

    julabo.close()
