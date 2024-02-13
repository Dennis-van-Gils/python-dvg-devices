#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RS232 function library for a MDrive stepper controller designed by TCO of the
University of Twente.

Assumptions on the flashed motor parameters:
- no check-sum communication: CK 0
- echoing full-duplex       : EM 0
  NOTE: EM must be 0 for Rindert Nauta's build-in controller to work correctly,
  but for this module we need EM = 1 (half-duplex). We'll adjust the EM
  parameter during method `begin()`.

Very minimal functionality.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "08-02-2024"
__version__ = "1.0.0"

import sys

import numpy as np
import serial

from dvg_devices.BaseDevice import SerialDevice


class MDrive_Motor:

    class State:
        # Container for the process and measurement variables
        # [numpy.nan] values indicate that the parameter is not initialized or
        # that the last query was unsuccessful in communication.

        # fmt: off
        cur_pos = np.nan            # position [mm]
        cur_speed = np.nan          # velocity [mm/s]
        error_msg = np.nan          # error string message
        # fmt: on


class MDrive_Controller(SerialDevice):
    motor_idxs: list[str] = []
    motors = list[MDrive_Motor]

    def __init__(
        self,
        name="MDrive",
        long_name="MDrive controller",
    ):
        super().__init__(name=name, long_name=long_name)

        # Default serial settings: 9600 8-N-1
        self.serial_settings = {
            "baudrate": 9600,
            "timeout": 0.4,
            "write_timeout": 0.4,
            "parity": "N",
        }
        self.set_read_termination("\n")
        self.set_write_termination("\n")

        self.set_ID_validation_query(
            ID_validation_query=self.ID_validation_query,
            valid_ID_broad="MDrive",
            valid_ID_specific=None,
        )

        # Containers for the status, process and measurement variables
        # self.state = self.State()

    # --------------------------------------------------------------------------
    #   flush_serial_out_MDrive
    # --------------------------------------------------------------------------

    def flush_serial_out_MDrive(self):
        """Silently flush out the serial out buffer of the MDrive controller."""
        try:
            self.query("", raises_on_timeout=True, returns_ascii=False)
        except:  # pylint: disable=bare-except
            pass

    # --------------------------------------------------------------------------
    #   ID_validation_query
    # --------------------------------------------------------------------------

    def ID_validation_query(
        self,
    ) -> tuple[str | bytes | None, str | bytes | None]:
        """We are going to send the escape character "\x1b" which stops all
        current motion of the MDrive controller to which we expect any of the
        following replies:
          b"\r\n"     Reply when in half-duplex (EM = 1)
          b"#\r\n>"   Reply when in full-duplex (EM = 0) without queued error
          b"#\r\n?"   Reply when in full-duplex (EM = 0) with queued error
        """
        _success, reply = self.query("\x1b", returns_ascii=False)  # [Esc]
        if isinstance(reply, bytes):
            if reply[:2] == b"\r\n" or reply[:3] == b"#\r\n":
                # We have to flush the serial out buffer of the MDrive
                # controller, because the [Esc] command can leave garbage behind
                # in the buffer.
                self.flush_serial_out_MDrive()
                return "MDrive", None

        return "", None

    # --------------------------------------------------------------------------
    #   query_half_duplex
    # --------------------------------------------------------------------------

    def query_half_duplex(self, msg: str) -> tuple[bool, str | bytes | None]:
        """Wrapped version of method `query()` that requires all MDrive motors
        to be set up in half-duplex mode, which should be the case after a call
        to method `begin()` has been performed.

        This method will check for a proper reply coming back from the MDrive
        motor, i.e. the raw reply should end with bytes b'\r\n'. When serial
        communication has failed or the proper end bytes are not received, a
        warning message will be printed to the terminal but the program will
        continue on.
        """
        success, reply = self.query(msg, returns_ascii=False)
        if success and reply[-2:] == b"\r\n":
            return success, reply.decode().strip()

        print(f"COMMUNICATION ERROR: {reply}")
        return False, None

    # --------------------------------------------------------------------------
    #
    # --------------------------------------------------------------------------

    def execute_motor_subroutine(self, motor_idx: str, subroutine_label: str):
        """TODO"""
        msg = f"{motor_idx}ex {subroutine_label}"
        success, reply = self.query(msg, returns_ascii=False)
        if not (success and reply == b"\r\n"):
            print("Communication error")

    # --------------------------------------------------------------------------
    #   begin
    # --------------------------------------------------------------------------

    def begin(self):
        """The following will happen:
        1) Scan for any attached motors and store them in the motor list
        2) Set the echo mode to half-duplex (EM = 1)
        3) Init each motor and reset any errors in the queue
        """

        # 1) Fast scanning for attached motors
        """
        Expected replies when motor is attached:
          b"\r\n"        Reply when in half-duplex (EM = 1)
          b"[IDX]\r\n>"  Reply when in full-duplex (EM = 0) without queued error
          b"[IDX]\r\n?"  Reply when in full-duplex (EM = 0) with queued error
        Expected replies when motor not found:
          b""            Reply for both half- and full-duplex
          or a serial read time-out
        """
        orig_timeout = self.ser.timeout
        self.ser.timeout = 0.1
        print("Scanning for attached motors...")
        for motor_idx in range(10):
            print(f"  {motor_idx}: ", end="")

            try:
                success, _reply = self.query(
                    f"{motor_idx}", raises_on_timeout=True
                )
            except serial.SerialException:
                # Due to a serial read time-out, or an empty bytes b"" reply.
                # In both cases: there is no motor attached.
                print("no motor")
            else:
                if success:
                    print("motor detected")
                    self.motor_idxs.append(f"{motor_idx}")
                    # Ditch any possible remaining '>', '?' chars in the buffer
                    self.flush_serial_out_MDrive()

        self.ser.timeout = orig_timeout

        # 2) Set the echo mode to half-duplex (EM = 1)
        # We don't care about the query reply, yet
        for motor_idx in self.motor_idxs:
            _success, _reply = self.query(f"{motor_idx}em 1")

        """
        # 3) Init each motor and reset any errors in the queue
        # Now we start caring about the query reply
        for motor_idx in self.motor_idxs:
            self.execute_motor_subroutine(motor_idx, "f1")
        """


# ------------------------------------------------------------------------------
#   Main: Will show a demo when run from the terminal
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    dev = MDrive_Controller()
    if not dev.auto_connect():
        sys.exit(0)

    dev.begin()

    my_success, my_reply = dev.query_half_duplex("1ex f1")
    if my_success:
        print(f"success: {my_reply}")

    my_success, my_reply = dev.query_half_duplex('1PR "MV",MV,"P",P,"V",V')
    if my_success:
        print(f"success: {my_reply}")

    dev.close()
