#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RS232 function library for an MDrive stepper controller designed by Rindert
Nauta of the TCO department of the University of Twente.

The MDrive controller is a custom-build hardware interface with a user-control
panel that interfaces with multiple MDrive stepper motors. It allows for stand-
alone control of each motor via push buttons, rotary knobs and a LCD screen. The
controller is based on a PIC microcontroller with source-code programmed by
Rindert Nauta. The source code is unknown, but the API is mostly known. The
controller allows for direct pass-through via serial RS232 and USB to a host PC,
allowing motor control via scripting, bypassing the user-control panel.

The MDrive controller requires each attached MDrive motor to be flashed (using
"Novanta Motion Terminal" software) with specific parameters and subroutines
set. Holding down the 'Home' button during power on will set the RS232 port in
direct pass-through mode to each attached motor, allowing them to be flashed via
a PC.

See the manual "MCode Programming and Software Reference: MDrive, MForce and
AccuStep Motion Control Products" by IMS Inc. & Schneider Electric.

Required flashed motor parameters:
- No check-sum communication (param CK = 0)
- Echoing full-duplex        (param EM = 0)
  NOTE: EM must be 0 for Rindert Nauta's build-in controller to work correctly,
  but for this module we need EM = 1 (half-duplex). We'll adjust the EM
  parameter during method `begin()`.
- All motors are configured in the so-called 'party mode', i.e. param PY = 1,
  and each motor has been given a unique device name as a single integer digit,
  i.e. param DN = "1", DN = "2", etc.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "19-02-2024"
__version__ = "1.0.0"

import sys

import numpy as np
import serial

from dvg_devices.BaseDevice import SerialDevice

# ------------------------------------------------------------------------------
#   MDrive_Controller
# ------------------------------------------------------------------------------


class MDrive_Controller(SerialDevice):
    def __init__(
        self,
        name="MDrive",
        long_name="MDrive controller",
    ):
        super().__init__(name=name, long_name=long_name)

        # Default serial settings: 9600 8-N-1
        self.serial_settings = {
            "baudrate": 9600,
            "timeout": 0.1,
            "write_timeout": 0.1,
            "parity": "N",
        }
        self.set_read_termination("\n")
        self.set_write_termination("\n")

        self.set_ID_validation_query(
            ID_validation_query=self.ID_validation_query,
            valid_ID_broad="MDrive",
            valid_ID_specific=None,
        )

        # List of `MDrive_Motor` instances, one for each attached motor
        self.motors: list[MDrive_Motor] = []

    # --------------------------------------------------------------------------
    #   flush_serial_out
    # --------------------------------------------------------------------------

    def flush_serial_out(self):
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
        r"""We are going to send the escape character "\x1b" which stops all
        current motion of the MDrive controller to which we expect any of the
        following replies::

          b"#\r\n>"   Reply when in full-duplex (EM = 0) without queued error
          b"#\r\n?"   Reply when in full-duplex (EM = 0) with queued error
          b"\r\n"     Reply when in half-duplex (EM = 1)
        """
        _success, reply = self.query("\x1b", returns_ascii=False)  # [Esc]
        if isinstance(reply, bytes):
            if reply[:2] == b"\r\n" or reply[:3] == b"#\r\n":
                # We have to flush the serial out buffer of the MDrive
                # controller, because the [Esc] command can leave garbage behind
                # in the buffer.
                self.flush_serial_out()
                return "MDrive", None

        return "", None

    # --------------------------------------------------------------------------
    #   begin
    # --------------------------------------------------------------------------

    def begin(self):
        """This method should be called directly after having established a
        serial connection to the MDrive controller (e.g. via `auto_connect()`).

        The following will happen:
        1) Scan for any attached motors and store them in the motor list.
        2) Set the echo mode to half-duplex (EM = 1) for each motor.
        """

        # 1) Fast scanning for attached motors
        """
        Expected replies when motor is attached:
          b"[IDX]\r\n>"  Reply when in full-duplex (EM = 0) without queued error
          b"[IDX]\r\n?"  Reply when in full-duplex (EM = 0) with queued error
          b"\r\n"        Reply when in half-duplex (EM = 1)
        Expected replies when motor not found:
          b""            Reply for both half- and full-duplex
          or a serial read time-out.
        """
        print("Scanning for attached motors...")
        for motor_idx in range(10):
            print(f"  {motor_idx}: ", end="")

            try:
                success, _reply = self.query(
                    f"{motor_idx}", raises_on_timeout=True
                )
            except serial.SerialException:
                # Due to a serial read time-out, or an empty bytes b"" reply.
                # In both cases: There is no motor attached.
                print("no motor")
            else:
                if success:
                    print("motor detected")
                    self.motors.append(
                        MDrive_Motor(
                            controller=self,
                            device_name=f"{motor_idx}",
                        )
                    )
                    # Ditch any possible remaining '>', '?' chars in the buffer
                    self.flush_serial_out()

        """
        # 3) Init each motor and reset any errors in the queue
        # Now we start caring about the query reply
        for motor_idx in self.motor_idxs:
            self.execute_motor_subroutine(motor_idx, "f1")
        """

    # --------------------------------------------------------------------------
    #   close
    # --------------------------------------------------------------------------

    def close(self, ignore_exceptions=False):
        """Restore the echo mode back to full-duplex (EM = 0) for all attached
        motors and close the serial port."""
        for motor in self.motors:
            self.write(f"{motor.device_name}em 0")
            self.flush_serial_out()

        super().close(ignore_exceptions)

    # --------------------------------------------------------------------------
    #   query_half_duplex
    # --------------------------------------------------------------------------

    def query_half_duplex(self, msg: str) -> tuple[bool, str]:
        r"""Wrapped version of method `query()` that requires all MDrive motors
        to be set up in half-duplex mode (EM = 1), which should be the case
        when a call to method `begin()` has been performed.

        This method will check for a proper reply coming back from the MDrive
        controller, i.e. the raw reply should end with bytes b'\r\n'. When
        serial communication has failed or the proper end bytes are not received
        a warning message will be printed to the terminal, but the program will
        continue on.

        Send a message to the MDrive controller and subsequently read the reply.

        Args:
            msg (`str`):
                ASCII string to be sent to the MDrive controller.

        Returns:
            `tuple`:
                success (`bool`):
                    True if successful, False otherwise.

                reply (`str`):
                    Reply received from the device as an ASCII string.
        """
        success, reply = self.query(msg, returns_ascii=False)
        if isinstance(reply, bytes) and reply[-2:] == b"\r\n":
            reply = reply.decode().strip("\r\n")
            reply = reply.replace("\r", "\t")
            reply = reply.replace("\n", "\t")
            return success, reply

        print(f"MDRIVE COMMUNICATION ERROR: {reply}")
        return False, ""


# ------------------------------------------------------------------------------
#   MDrive_Motor
# ------------------------------------------------------------------------------


class MDrive_Motor:
    class Config:
        # Container for the configuration parameters
        # fmt: off
        serial_number    = ""           # Param SN
        firmware_version = ""           # Param VR
        user_variables: list[str] = []  # Param UV
        # fmt: on

    class State:
        # Container for the measurement variables
        # [numpy.nan] values indicate that the parameter is not initialized or
        # that the last query was unsuccessful in communication.

        # fmt: off
        cur_pos = np.nan                # Param P : Position [mm]
        cur_speed = np.nan              # Param V : Velocity [mm/s]
        error_msg = np.nan              # Param ??: Error string message
        # fmt: on

    def __init__(self, controller: MDrive_Controller, device_name: str):
        self.controller = controller
        self.device_name = device_name  # Param DN

        self.config = self.Config()
        self.state = self.State()

        # Set the echo mode to half-duplex. We don't care about the query reply.
        _success, _reply = self.controller.query_half_duplex(
            f"{device_name}em 1"
        )

        # Short-hand
        self.query = self.controller.query_half_duplex

        # self.query_config()

    # --------------------------------------------------------------------------
    #   query_config
    # --------------------------------------------------------------------------

    def query_config(self):
        """Query the configuration parameters of the MDrive motor and store
        these inside member `config`.

        Queried configuration parameters:
        - Serial number (SN)
        - Firmware version (VR)
        - User variables (UV)
        """

        # Serial number
        success, reply = self.query(f"{self.device_name}pr sn")
        if success:
            self.config.serial_number = reply

        # Firmware version
        success, reply = self.query(f"{self.device_name}pr vr")
        if success:
            self.config.firmware_version = reply

        # User variables
        # This query is a special case, because the MDrive controller seems to
        # treat each user variable that is defined in the MDrive motor as a
        # single reply. It buffers all these separate replies internally and
        # pops a single reply of the stack for each subsequent query. Hence, we
        # send a single query for the user variables and have to empty out the
        # reply buffer by sending blank queries until emptied.
        replies: list[str] = []
        success, reply = self.query(f"{self.device_name}pr uv")
        while success and reply != "":
            replies.append(reply)
            success, reply = self.query("")

        if success:
            self.config.user_variables = replies

    # --------------------------------------------------------------------------
    #   execute_subroutine
    # --------------------------------------------------------------------------

    def execute_subroutine(self, subroutine_label: str):
        """Execute a subroutine or program as flashed into the MDrive motor.

        Args:
            subroutine_label (`str`):
                Label of the subroutine or program as flashed into the MDrive
                motor to be executed.

        Returns:
            `tuple`:
                success (`bool`):
                    True if successful, False otherwise.

                reply (`str`):
                    Reply received from the device as an ASCII string.
        """
        return self.query(f"{self.device_name}ex {subroutine_label}")


# ------------------------------------------------------------------------------
#   Main: Will show a demo when run from the terminal
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    dev = MDrive_Controller()
    if not dev.auto_connect():
        sys.exit(0)

    dev.begin()

    for my_motor in dev.motors:
        my_success, my_reply = my_motor.execute_subroutine("f1")
        if my_success:
            print(f"{my_motor.device_name}ex f1: {my_reply}")

        my_motor.query_config()
        print(my_motor.config.user_variables)

    my_success, my_reply = dev.query_half_duplex('1PR "MV",MV,"P",P,"V",V')
    if my_success:
        print(f"success: {my_reply}")

    dev.query_half_duplex("1mr 512000")

    dev.close()
