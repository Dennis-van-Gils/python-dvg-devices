#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RS422 function library for MDrive stepper motors by Novanta IMS (former
Schneider Electric) set up in party mode.

Each MDrive motor has to be flashed using "Novanta Motion Terminal" software
with specific parameters and subroutines set. See the manual
"MCode Programming and Software Reference: MDrive, MForce and AccuStep Motion
Control Products" by IMS Inc. & Schneider Electric.

Required flashed motor parameters:
- No check-sum communication: param CK = 0.
- Escape flag set to [Esc]-key: param ES = 1.
- The echo mode - param EM - must be either: 0 (full-duplex), 1 (half-duplex) or
  3 (print queue). Echo mode EM = 2 is not supported and will result in failing
  to auto-detect the MDrive serial port. This library will change the mode to
  EM = 1 (half-duplex) when method `MDrive_Controller.begin()` has been called.
- All motors must be configured in the so-called 'party mode': param PY = 1.
  Each motor must have been given a unique device name as a single integer
  digit, e.g. param DN = "1", DN = "2", etc. This allows the motors to be
  adressed individually over a single shared serial port.
- User subroutine with label 'F1' should be present within each motor, effecting
  an 'init interface' routine, resetting all errors and stopping any motion.
- User variable with label 'C0' should be present, indicating the [steps/mm]
  calibration of the linear stage to which the MDrive is connected to.
- TODO: Add support for rotary stages. Perhaps by adding user variable 'TY'
  which signals either TY = 0 (linear stage, default) or TY = 1 (rotary stage).
  The 'C0' parameter, when TY = 1, can now be interpreted as calibration factor
  of the rotary stage in [steps/deg].

Physical wiring:
- Because we require each motor to operate in party-mode, the physical serial
  wiring looks as follows. Each TX-, TX+, RX- and RX+ wire per motor can be tied
  together, resulting in them sharing the same serial port. A single
  RS422-to-USB adapter can then be used to control all motors via this library.
  The Novanta manual (MDrive Motion Control, chapter 'Multi-drop communication
  connection`) recommends to have only one ground connection to motor 1 and
  not to the other motors to prevent ground loops. Termination resistors are
  necessary when the serial cable exceed 4.5 meters.

NOTE: Regarding the obsolete MDrive stepper control box designed by Rindert
Nauta of the TCO department of the University of Twente. It is a custom-build
hardware interface with a user-control panel that interfaces with multiple
MDrive stepper motors. It allows for stand-alone control of each motor via push
buttons, rotary knobs and a LCD screen. The controller is based on a PIC
microcontroller with source-code programmed by Rindert Nauta. The source code is
unknown, but the API is mostly known. The controller allows for direct
pass-through via serial RS232 and USB to a host PC, allowing motor control via
scripting, bypassing the user-control panel. Holding down the 'Home' button
during power on will set the RS232 port in direct pass-through mode to each
attached motor, allowing them to be flashed via a PC.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "07-03-2024"
__version__ = "1.0.0"

import sys
import time

import numpy as np
import serial

from dvg_debug_functions import dprint, ANSI
from dvg_devices.BaseDevice import SerialDevice

# Print extra debugging info to the terminal? Use only for troubleshooting.
DEBUG = False

# ------------------------------------------------------------------------------
#   MDrive_Controller
# ------------------------------------------------------------------------------


class MDrive_Controller(SerialDevice):
    """Software controller class to interface with multiple MDrive motors set up
    in party mode over a single serial port.

    Main methods:
    - auto_connect()
    - begin()
    - close()

    Main members:
    - ser (`serial.Serial` instance)
    - motors (`list` of `MDrive_Motor` instances)

    Inherits from `dvg_devices.BaseDevice.SerialDevice`. See there for more info
    on other arguments, methods and members.
    """

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
    #   flush_serial_in
    # --------------------------------------------------------------------------

    def flush_serial_in(self):
        """Silently flush the serial in buffer of the OS."""
        try:
            # Ensure the MDrive has had enough time to write any pending bits
            # into the serial buffer of the OS
            time.sleep(0.1)

            reply = self.ser.read_all()
            if DEBUG:
                dprint(f"flush: {reply}", ANSI.CYAN)
        except:  # pylint: disable=bare-except
            pass

    # --------------------------------------------------------------------------
    #   ID_validation_query
    # --------------------------------------------------------------------------

    def ID_validation_query(
        self,
    ) -> tuple[str | bytes | None, str | bytes | None]:
        r"""Sends the escape character "\x1b" which stops all current motion of
        the MDrive motors to which we expect any of the following replies::

          b"#\r\n>"   Reply when in full-duplex (EM = 0) without queued error
          b"#\r\n?"   Reply when in full-duplex (EM = 0) with queued error
          b"\r\n"     Reply when in half-duplex (EM = 1)
        """
        # `self.query()` reads until the '\n' character is encountered
        _, reply = self.query("\x1b", returns_ascii=False)  # Sending [Esc]
        if DEBUG:
            dprint(f"\nID   : {reply}", ANSI.CYAN)

        if isinstance(reply, bytes):
            if reply[:2] == b"\r\n" or reply[:3] == b"#\r\n":
                # We have to flush the serial in buffer of the OS, because there
                # might still be pending characters to be read. Namely '>' or
                # '?', which we will ignore. Sometimes the remaining bits get
                # garbled up, preventing decoding into ASCII characters. This
                # could happen when multiple motors respond simultaneously on
                # the same serial port, garbling up the ASCII bit stream.
                self.flush_serial_in()

                # ID validation successful
                return "MDrive", None

        # ID validation failed
        return "", None

    # --------------------------------------------------------------------------
    #   begin
    # --------------------------------------------------------------------------

    def begin(self):
        """Scan for all connected motors, set them up and store them in member
        `MDrive_Controller.motors` as a list of `MDrive_Motor` instances.

        This method should be called directly after having established a
        serial connection to the motors, e.g. after method
        `MDrive_Controller.auto_connect()`.
        """

        # Step 1: Scan for attached motors
        """
        Expected replies when motor is attached:
          b"[DN]\r\n>"  Reply when in full-duplex (EM = 0) without queued error
          b"[DN]\r\n?"  Reply when in full-duplex (EM = 0) with queued error
          b"\r\n"       Reply when in half-duplex (EM = 1)
        Expected replies when motor not found:
          b""           Reply for both half- and full-duplex
          or a serial read time-out.
        """
        print("Scanning for attached motors...")
        for motor_idx in range(10):
            try:
                success, reply = self.query(
                    f"{motor_idx}",
                    raises_on_timeout=True,
                    returns_ascii=False,
                )
                if DEBUG:
                    dprint(f"scan : {reply}", ANSI.CYAN)
            except serial.SerialException:
                # Due to a serial read time-out, or an empty bytes b"" reply.
                # In both cases: There is no motor attached.
                pass
            else:
                if success:
                    self.motors.append(
                        MDrive_Motor(
                            controller=self,
                            device_name=f"{motor_idx}",
                        )
                    )

                    # Flush possibly remaining '>', '?' chars left in the buffer
                    # when the MDrive is in full-duplex mode (EM = 0).
                    self.flush_serial_in()

        if not self.motors:
            print("NO MOTORS DETECTED")
        else:
            for motor in self.motors:
                print(f"  - Detected motor '{motor.device_name}'")
                motor.begin()
                motor.print_config()
                print("")

    # --------------------------------------------------------------------------
    #   close
    # --------------------------------------------------------------------------

    def close(self, ignore_exceptions=False):
        """Stop any motion of all MDrive motors and close the serial port."""
        if DEBUG:
            dprint("Sending [Esc] to the MDrive motors.", ANSI.CYAN)

        self.ser.write(b"\x1b")  # Sending [Esc] using low-level communication
        self.flush_serial_in()  # We don't care about the reply, hence flush

        super().close(ignore_exceptions)

    # --------------------------------------------------------------------------
    #   query_half_duplex
    # --------------------------------------------------------------------------

    def query_half_duplex(self, msg: str) -> tuple[bool, str]:
        r"""Send a message over the MDrive serial port and subsequently read the
        reply.

        Wrapped version of method `dvg_devices.BaseDevice.SerialDevice.query()`
        that requires all MDrive motors to be set up in half-duplex mode
        (EM = 1), which should be the case when a call to method `begin()` has
        been performed.

        This method will check for a proper reply coming back from the MDrive
        motor, i.e. the raw reply should end with bytes b'\r\n'. When serial
        communication has failed or the proper end bytes are not received
        a warning message will be printed to the terminal, but the program will
        continue on.

        Args:
            msg (`str`):
                ASCII string to be sent over the MDrive serial port.

        Returns:
            `tuple`:
                success (`bool`):
                    True if successful, False otherwise.

                reply (`str`):
                    Reply received from the device as an ASCII string.
        """
        _, reply = self.query(msg, returns_ascii=False)

        if DEBUG:
            dprint(f"msg: {msg}", ANSI.GREEN)
            dprint(f"└> {reply}", ANSI.YELLOW)

        if isinstance(reply, bytes) and reply[-2:] == b"\r\n":
            try:
                reply = reply[:-2].decode()
                return True, reply

            except UnicodeDecodeError:
                dprint("MDRIVE COMMUNICATION ERROR", ANSI.RED)
                dprint(f"  Trying to send: {msg}")
                dprint(f"  Received reply: {reply}")
                return False, ""

        dprint("MDRIVE COMMUNICATION ERROR", ANSI.RED)
        dprint(f"  Trying to send: {msg}")
        dprint(f"  Received reply: {reply}")
        return False, ""


# ------------------------------------------------------------------------------
#   MDrive_Motor
# ------------------------------------------------------------------------------


class MDrive_Motor:
    """Class to manage communication with a single MDrive motor set up in party
    mode.

    Main methods:
    - begin()
    - query()
    - query_config()
    - query_errors()
    - query_state()
    - query_is_moving()
    - execute_subroutine()

    Main members:
    - config (`dataclass` container)
    - state (`dataclass` container)

    Args:
        controller (`MDrive_Controller`):
            Parent controller in charge of the serial port to which the MDrive
            motor is connected to.

        device_name (`str`):
            Device name of this particular MDrive motor (param DN).
    """

    class Config:
        """Container for the MDrive motor configuration parameters."""

        part_number: str = ""
        "Param PN"
        serial_number: str = ""
        """Param SN"""
        firmware_version: str = ""
        """Param VR"""

        user_variables: dict[str, int] = {}
        """Param UV: Dictionary of user variables"""
        user_subroutines: dict[str, int] = {}
        """Param UV: Dictionary of user subroutines"""

        motion_A: float | int = np.nan
        """Acceleration [steps/sec^2]"""
        motion_D: float | int = np.nan
        """Deceleration [steps/sec^2]"""
        motion_HC: float | int = np.nan
        """Hold current [0-100 %]"""
        motion_HT: float | int = np.nan
        """Hold current delay time [msec]"""
        motion_LM: float | int = np.nan
        """Limit stop modes [1-6]"""
        motion_MS: float | int = np.nan
        """Microstep resolution select [microsteps per full motor step]"""
        motion_MT: float | int = np.nan
        """Motor settling delay time [msec]"""
        motion_RC: float | int = np.nan
        """Run current [0-100 %]"""
        motion_VI: float | int = np.nan
        """Initial velocity [steps/sec]"""
        motion_VM: float | int = np.nan
        """Maximum velocity [steps/sec]"""

        IO_S1: str = ""
        """Setup IO Point 1"""
        IO_S2: str = ""
        """Setup IO Point 2"""
        IO_S3: str = ""
        """Setup IO Point 3"""
        IO_S4: str = ""
        """Setup IO Point 4"""

    class State:
        """Container for the MDrive motor measurement variables."""

        position: float | int = np.nan
        """Param P: Read position [steps]"""
        velocity: float | int = np.nan
        """Param V: Read current velocity [steps/sec]"""
        is_moving: bool = False
        """Param MV: Moving flag [True/False]"""
        is_velocity_changing: bool = False
        """Param VC: Velocity changing flag [True/False]"""

        has_error: bool = False
        """Param EF: Error flag [True/False]"""
        error: int = 0
        """Param ER: Error number"""

    def __init__(self, controller: MDrive_Controller, device_name: str):
        self.controller = controller
        self.device_name = device_name  # Param DN
        self.config = self.Config()
        self.state = self.State()

    # --------------------------------------------------------------------------
    #   query
    # --------------------------------------------------------------------------

    def query(self, msg: str) -> tuple[bool, str]:
        r"""Send a message to this particular MDrive motor and subsequently read
        the reply.

        NOTE: The message string will automatically be prepended with the device
        name of this particular motor, which is assumed to be configured in
        party mode (PY = 1) and half-duplex mode (EM = 1). This is the case when
        `MDrive_Controller.begin()` has ran successfully.

        Args:
            msg (`str`):
                ASCII string to be sent to the MDrive motor.

        Returns:
            `tuple`:
                success (`bool`):
                    True if successful, False otherwise.

                reply (`str`):
                    Reply received from the device as an ASCII string.
        """
        return self.controller.query_half_duplex(f"{self.device_name}{msg}")

    # --------------------------------------------------------------------------
    #   begin
    # --------------------------------------------------------------------------

    def begin(self):
        """Set up the MDrive motor for operation.

        The following will take place:
        1) Set the echo mode to half-duplex (EM = 1).
        2) Reset any errors by calling subroutine 'F1'.
        3) Retrieve the configuration and initial measurement parameters of each
        motor.

        This method should be called directly after having established a
        serial connection to the motors, e.g. after method
        `MDrive_Controller.auto_connect()`.
        """
        # Set the echo mode to half-duplex. We don't care about the reply.
        self.query("em 1")

        # Reset motor. Running this subroutine 'F1' is crucial, because the
        # MDrive user-control box from TCO has a strange quirk that needs this
        # reset to continue "normal" operation.
        # In detail: The [Esc]-character we sent to auto-detect the controller
        # seems to prepend any future query replies with '\r\n', i.e. instead
        # of replying to '1pr p' with '0\r\n' the controller replies with
        # '\r\n0\r\n'. The latter messes up our query methodology and a call to
        # subroutine 'F1' seems to fix the issue.
        # TODO: Investigate if this subroutine is still necessary to be called
        # when /not/ using the user-control box of TCO, but using a direct
        # RS422-to-USB adapter instead.
        self.execute_subroutine("F1")

        self.query_config()
        self.query_state()
        self.query_errors()

    # --------------------------------------------------------------------------
    #   query_config
    # --------------------------------------------------------------------------

    def query_config(self):
        """Query the configuration parameters of the MDrive motor and store
        these inside member `MDrive_Motor.config`.
        """
        # Part number
        success, reply = self.query("pr pn")
        if success:
            self.config.part_number = reply

        # Serial number
        success, reply = self.query("pr sn")
        if success:
            self.config.serial_number = reply

        # Firmware version
        success, reply = self.query("pr vr")
        if success:
            self.config.firmware_version = reply

        # User variables
        # This query is a special case, because the MDrive motor will return
        # all defined user variables in one go, each delimited by '\r\n'
        # characters. Hence, we send a single query for requesting all user
        # variables and then have to empty out the serial in buffer, line for
        # line, until we find the last empty '\r\n' line.
        lines: list[str] = []  # E.g. lines = ("V1 = G 512000", "SU = 100")
        success, reply = self.query("pr uv")
        while isinstance(reply, str) and reply != "":
            lines.append(reply)
            reply = self.controller.ser.read_until(b"\n")

            if DEBUG:
                dprint(f"   {reply}", ANSI.YELLOW)

            try:
                reply = reply.decode().strip()
            except UnicodeDecodeError:
                dprint("MDRIVE COMMUNICATION ERROR", ANSI.RED)
                dprint(f"  `query_config()` failed to decode reply: {reply}")
                reply = ""

        if success:
            # Parse each line into a dict pair: name & int value
            dict_vars = {}
            dict_subr = {}
            for line in lines:
                parts = line.split("=")
                dict_key = parts[0].strip()
                dict_val = parts[1].strip()
                if dict_val[0] == "G":
                    dict_vars[dict_key] = int(dict_val[1:].strip())
                else:
                    dict_subr[dict_key] = int(dict_val)

            self.config.user_variables = dict_vars
            self.config.user_subroutines = dict_subr

        # Motion variables
        success, reply = self.query('pr A,"_"D,"_"HC,"_"HT')
        if success:
            parts = reply.split("_")
            self.config.motion_A = int(parts[0].strip())
            self.config.motion_D = int(parts[1].strip())
            self.config.motion_HC = int(parts[2].strip())
            self.config.motion_HT = int(parts[3].strip())

        success, reply = self.query('pr LM,"_"MS,"_"MT,"_"RC')
        if success:
            parts = reply.split("_")
            self.config.motion_LM = int(parts[0].strip())
            self.config.motion_MS = int(parts[1].strip())
            self.config.motion_MT = int(parts[2].strip())
            self.config.motion_RC = int(parts[3].strip())

        success, reply = self.query('pr VI,"_"VM')
        if success:
            parts = reply.split("_")
            self.config.motion_VI = int(parts[0].strip())
            self.config.motion_VM = int(parts[1].strip())

        # IO variables
        success, reply = self.query('pr S1,"_"S2,"_"S3,"_"S4')
        if success:
            parts = reply.split("_")
            self.config.IO_S1 = parts[0].strip()
            self.config.IO_S2 = parts[1].strip()
            self.config.IO_S3 = parts[2].strip()
            self.config.IO_S4 = parts[3].strip()

    # --------------------------------------------------------------------------
    #   print_config
    # --------------------------------------------------------------------------

    def print_config(self):
        """Print the configuration parameters of the MDrive motor to the
        terminal."""
        C = self.config
        print(f"    Part no.  | {C.part_number}")
        print(f"    Serial    | {C.serial_number}")
        print(f"    Firmware  | {C.firmware_version}")

        print("    User subr | ", end="")
        if len(C.user_subroutines) == 0:
            print("[empty]")
        else:
            print(", ".join(C.user_subroutines.keys()))

        print("    User vars | ", end="")
        if len(C.user_variables) == 0:
            print("[empty]")
        else:
            for idx, (key, val) in enumerate(C.user_variables.items()):
                if idx > 0:
                    print(" " * 16, end="")
                print(f"{key} = {val}")

        print("    Motion    | ", end="")
        print(f"A  = {C.motion_A:<10} [steps/sec^2]")
        print(f"{'':15} D  = {C.motion_D:<10} [steps/sec^2]")
        print(f"{'':15} HC = {C.motion_HC:<10} [0-100 %]")
        print(f"{'':15} HT = {C.motion_HT:<10} [msec]")
        print(f"{'':15} LM = {C.motion_LM:<10} [1-6]")
        print(f"{'':15} MS = {C.motion_MS:<10} [microsteps]")
        print(f"{'':15} MT = {C.motion_MT:<10} [msec]")
        print(f"{'':15} RC = {C.motion_RC:<10} [0-100 %]")
        print(f"{'':15} VI = {C.motion_VI:<10} [steps/sec]")
        print(f"{'':15} VM = {C.motion_VM:<10} [steps/sec]")

        print("    IO        | ", end="")
        print(f"S1 = {C.IO_S1}")
        print(f"{'':15} S2 = {C.IO_S2}")
        print(f"{'':15} S3 = {C.IO_S3}")
        print(f"{'':15} S4 = {C.IO_S4}")

    # --------------------------------------------------------------------------
    #   query_errors
    # --------------------------------------------------------------------------

    def query_errors(self):
        """Query the error parameters of the MDrive motor and store these inside
        member `MDrive_Motor.state`.

        Updates:
        - state.has_error
        - state.error

        Query takes ~0.024 s @ 9600 baud.
        """
        success, reply = self.query('pr EF,"_"ER')
        if success:
            parts = reply.split("_")
            if len(parts) != 2:
                dprint("MDRIVE COMMUNICATION ERROR", ANSI.RED)
                dprint(f"  `query_errors()` failed to split reply: {reply}")
                return

            try:
                self.state.has_error = bool(int(parts[0].strip()))
                self.state.error = int(parts[1].strip())
            except ValueError:
                dprint("MDRIVE COMMUNICATION ERROR", ANSI.RED)
                dprint(f"  `query_errors()` failed to parse reply: {reply}")

    # --------------------------------------------------------------------------
    #   query_state
    # --------------------------------------------------------------------------

    def query_state(self):
        """Query the measurement parameters of the MDrive motor and store these
        inside member `MDrive_Motor.state`.

        Updates:
        - state.position
        - state.velocity
        - state.is_moving
        - state.is_velocity_changing

        Query takes ~0.050 s @   9600 baud with TCO box.
        Query takes ~0.062 s @   9600 baud with direct RS422-USB cable.
        Query takes ~0.016 s @ 115200 baud with direct RS422-USB cable.
        """
        success, reply = self.query('pr P,"_"V,"_"MV,"_"VC')
        if success:
            parts = reply.split("_")
            if len(parts) != 4:
                dprint("MDRIVE COMMUNICATION ERROR", ANSI.RED)
                dprint(f"  `query_state()` failed to split reply: {reply}")
                return

            try:
                self.state.position = int(parts[0].strip())
                self.state.velocity = int(parts[1].strip())
                self.state.is_moving = bool(int(parts[2].strip()))
                self.state.is_velocity_changing = bool(int(parts[3].strip()))
            except ValueError:
                dprint("MDRIVE COMMUNICATION ERROR", ANSI.RED)
                dprint(f"  `query_state()` failed to parse reply: {reply}")

    # --------------------------------------------------------------------------
    #   query_is_moving
    # --------------------------------------------------------------------------

    def query_is_moving(self):
        """Query the `is_moving` parameter of the MDrive motor and store this
        inside member `MDrive_Motor.state`.

        Updates:
        - state.is_moving

        Query takes ~0.013 s @   9600 baud with TCO box.
        Query takes ~0.016 s @   9600 baud with direct RS422-USB cable.
        Query takes ~0.016 s @ 115200 baud with direct RS422-USB cable.
        """
        success, reply = self.query("pr MV")
        if success:
            try:
                self.state.is_moving = bool(int(reply.strip()))
            except ValueError:
                dprint("MDRIVE COMMUNICATION ERROR", ANSI.RED)
                dprint(f"  `query_is_moving()` failed to parse reply: {reply}")

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
        return self.query(f"ex {subroutine_label}")


# ------------------------------------------------------------------------------
#   Main: Will show a demo when run from the terminal
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    dev = MDrive_Controller()
    if not dev.auto_connect():
        sys.exit(0)

    dev.begin()

    for my_motor in dev.motors:
        # my_motor = dev.motors[motor_idx]

        # Test: Homing
        # ------------

        print("Homing... ", end="")
        sys.stdout.flush()

        my_motor.execute_subroutine("F2")
        count = 1
        t0 = time.perf_counter()
        my_motor.query_state()
        while my_motor.state.is_moving:
            count += 1
            my_motor.query_state()

        t1 = time.perf_counter()
        print(f"done.\nTime per `query_state()`    : {(t1 - t0)/count:.3f} s")

        # Test: Moving
        # ------------

        print("Moving... ", end="")
        sys.stdout.flush()

        my_motor.query("ma 64000")
        count = 1
        t0 = time.perf_counter()
        my_motor.query_is_moving()
        while my_motor.state.is_moving:
            count += 1
            my_motor.query_is_moving()

        t1 = time.perf_counter()
        print(f"done.\nTime per `query_is_moving()`: {(t1 - t0)/count:.3f} s")

    dev.close()
