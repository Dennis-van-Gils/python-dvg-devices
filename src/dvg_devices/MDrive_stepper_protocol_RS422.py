#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RS422 function library for MDrive stepper motors by Novanta IMS (former
Schneider Electric) set up in party mode.

Each MDrive motor has to be flashed using "Novanta Motion Terminal" software
with specific parameters and subroutines set. See the manual
"Programming and Software Reference Manual, MCode, MDrive and MForce Products"
by Novanta IMS.

Required flashed motor parameters:

- No check-sum communication: param CK = 0.
- Escape flag set to [Esc]-key: param ES = 1.
- The echo mode - param EM - must be either: 0 (full-duplex), 1 (half-duplex) or
  3 (print queue). Echo mode EM = 2 is not supported and will result in failing
  to auto-detect the MDrive serial port. This library will change the mode to
  EM = 1 (half-duplex) when method `MDrive_Controller.begin()` has been called.
- All motors must be configured in the so-called 'party mode': param PY = 1.
  Each motor must have been given a unique device name as a single alphanumeric
  character, e.g. param DN = "x", DN = "1", etc. This allows the motors to be
  adressed individually over a single shared serial port.
- User subroutine with label 'F1' should be present within each motor, effecting
  an 'init interface' routine where the MDrive motor should be scripted to stop
  any motion. Advertently, any pending errors of the MDrive get reset by default
  when any subroutine gets executed as per MDrive design.

  Minimal needed MCode::

    LB F1             '--- Init interface
        SL 0          'Stop any movement
        H             'Wait for movement to finish
        BR M0         'Goto: Main loop

- User subroutine with label 'F2' should be present within each motor, effecting
  a 'home' routine where the MDrive motor should be scripted to perform a homing
  operation and have the internal step counter be reset to 0.

  Minimal needed MCode::

    LB F2             '--- Home
        SL 0            'Stop any movement
        H               'Wait for movement to finish
        HM 1            'Home using method 1 (adjust method to your needs)
        H               'Wait for movement to finish
        R1 = P & 1023
        R2 = 1024 - R1
        MR R2           'Optionally: Move tiny amount away from home again
        H               'Wait for movement to finish
        P = 0           'Redefine position to == 0
        BR M0           'Goto: Main loop

- User variable with label 'C0' should be present, indicating the [steps/mm] or
  [steps/rev] calibration factor of the stage the MDrive motor is connected to.
  NOTE: This library only supports integer values for 'C0'. Fractional values
  are not supported.
- User variable with label 'CT' should be present, indicating the movement type
  (0: linear, 1: angular) of the stage the MDrive motor is connected to.

Physical wiring:

- Because we require each motor to operate in party-mode, the physical serial
  wiring looks as follows. Each TX-, TX+, RX- and RX+ wire per motor can be tied
  together, resulting in them sharing the same serial port. A single
  RS422-to-USB adapter can then be used to control all motors via this library.
  The Novanta manual (Hardware Manual MDrive Motion Control, chapter 'Multi-drop
  communication connection`) recommends to have only one ground connection to
  the first motor and not to the other motors to prevent ground loops.
  Termination resistors are necessary when the serial cable exceed 4.5 meters.

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
__date__ = "28-03-2024"
__version__ = "1.0.0"
# pylint: disable=missing-function-docstring, too-many-lines

import sys
import time
from enum import Enum

import numpy as np
import serial

from dvg_debug_functions import dprint, ANSI
from dvg_devices.BaseDevice import SerialDevice

# Print extra debugging info to the terminal? Use only for troubleshooting.
DEBUG = False


class Movement_type(Enum):
    LINEAR = 0
    ANGULAR = 1


def print_warning(msg: str):
    print(f"{ANSI.RED}{msg}{ANSI.WHITE}")


def shortest_path_on_step_circle(
    from_step: int,
    to_step: int,
    steps_per_rev: int,
) -> int:
    """Return the relative integer step distance on a circle consisting of
    `steps_per_rev` steps per full revolution that results in the shortest path
    starting from position `from_step` to ending position `to_step`.

    Returns:
        dist (`int`):
            The relative integer step distance ranging from
            `(-steps_per_rev // 2, steps_per_rev // 2]` where a positive sign
            indicates CCW rotation and a negative sign CW rotation.

    NOTE: No floating point rounding errors. All integer maths.
    """
    # Normalize each to [0, steps_per_rev)
    from_step %= steps_per_rev
    to_step %= steps_per_rev

    dist = (to_step - from_step) % steps_per_rev  # CCW
    dist_CW = steps_per_rev - dist

    if dist > dist_CW:
        dist = -dist_CW

    return dist


def shortest_path_on_unit_circle(from_rev: float, to_rev: float) -> float:
    """Return the relative distance on a unit circumference circle that results
    in the shortest path starting from position `from_rev` to ending position
    `to_rev` expressed in unit revolutions.

    Returns:
        dist (`float`):
            The relative distance ranging from (-0.5, 0.5] on a unit circle
            where a positive sign indicates CCW rotation and a negative sign CW
            rotation.

    NOTE: Floating point rounding errors are unavoidable, e.g.,
    ``shortest_path_on_unit_circle(0.1, 0.3) = 0.19999999999999998``
    """
    # Normalize each to [0, 1)
    from_rev %= 1
    to_rev %= 1

    dist = (to_rev - from_rev) % 1  # CCW
    dist_CW = 1 - dist

    if dist > dist_CW:
        dist = -dist_CW

    return dist


# ------------------------------------------------------------------------------
#   MDrive_Controller
# ------------------------------------------------------------------------------


class MDrive_Controller(SerialDevice):
    """Software controller class to interface with multiple MDrive motors set up
    in party mode over a single serial port.

    Main methods:
    - auto_connect()
    - begin()
    - STOP()
    - RESET()
    - close()

    Main members:
    - ser
    - motors

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

        # Dictionary of all detected motors, addressable by their device name
        self.motors: dict[str, MDrive_Motor] = {}

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

    def begin(
        self,
        device_names_to_scan: str | None = None,
    ):
        """Scan for connected motors, set them up and store them in member
        `MDrive_Controller.motors` as a dictionary of `MDrive_Motor` instances,
        addressable by their device name.

        This method should be called directly after having established a
        serial connection to the motors, e.g. after method
        `MDrive_Controller.auto_connect()`.

        Args:
            device_names_to_scan (`str`, optional):
                List of alphanumeric characters that should be scanned over to
                detect motors by their device name. When omitted, will scan over
                all 62 alphanumeric characters, taking ~7 seconds. To speed up
                the scan, one can limit the list to specific device names if
                they are known a-priori, e.g., "xyza".

                Default: All alphanumeric characters [0-9][a-z][A-Z].
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

        if device_names_to_scan is None:
            device_names_to_scan = (
                "0123456789"
                "abcdefghijklmnopqrstuvwxyz"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            )
            print("Scanning for all motors. Takes ~7 seconds...")
        else:
            print(f"Scanning for motors in list '{device_names_to_scan}'...")

        for scan_DN in device_names_to_scan:
            try:
                success, reply = self.query(
                    scan_DN,
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
                    # Flush possibly remaining '>', '?' chars left in the buffer
                    # when the MDrive is in full-duplex mode (EM = 0).
                    self.flush_serial_in()

                    print(
                        f"{ANSI.YELLOW}  - DETECTED MOTOR '{scan_DN}'"
                        f"{ANSI.WHITE}"
                    )

                    self.motors[scan_DN] = MDrive_Motor(
                        controller=self,
                        device_name=scan_DN,
                    )
                    self.motors[scan_DN].begin()

                    print("")

        # Report
        print("Done scanning for motors. ", end="")
        N_motors = len(self.motors)
        if N_motors == 0:
            print_warning("NO MOTORS DETECTED.\n")
        else:
            pretty_list = ", ".join([f"'{DN}'" for DN in self.motors])
            print(
                f"Detected {N_motors} motor{'s' if N_motors > 1 else ''}: "
                f"{pretty_list}.\n"
            )

    # --------------------------------------------------------------------------
    #   STOP
    # --------------------------------------------------------------------------

    def STOP(self):
        """Emergency stop any motion of all MDrive motors.

        NOTE: To resume normal operation after an emergency stop it is necessary
        to call method `RESET()`.
        """
        if DEBUG:
            dprint("STOP! Sending [Esc] to all MDrive motors.", ANSI.CYAN)

        self.ser.write(b"\x1b")  # [Esc]

        # We flush because multiple MDrives can respond simultaneously, garbling
        # up the serial bit stream. No point in trying to read the reply.
        self.flush_serial_in()

    # --------------------------------------------------------------------------
    #   RESET
    # --------------------------------------------------------------------------

    def RESET(self):
        """Reset all MDrive motors. It allows for normal operation to resume
        after an emergency stop via method `STOP()` was issued. Reset will also
        effect a controlled stop of any motion of all motors.

        NOTE: User subroutine 'F1' will be executed by all MDrive motors.
        """
        if DEBUG:
            dprint("RESET! Sending 'EX F1' to all MDrive motors.", ANSI.CYAN)

        self.ser.write(b"*EX F1\n")

        # We flush because multiple MDrives can respond simultaneously, garbling
        # up the serial bit stream. No point in trying to read the reply.
        self.flush_serial_in()

    # --------------------------------------------------------------------------
    #   close
    # --------------------------------------------------------------------------

    def close(self, ignore_exceptions=False):
        """Controlled-stop any motion of all motors and close the serial port."""
        if self.is_alive:
            self.RESET()
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

    Main members:
    - config
    - state

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
        """Param PN"""
        serial_number: str = ""
        """Param SN"""
        firmware_version: str = ""
        """Param VR"""

        IO_S1: str = ""
        """Setup IO Point 1"""
        IO_S2: str = ""
        """Setup IO Point 2"""
        IO_S3: str = ""
        """Setup IO Point 3"""
        IO_S4: str = ""
        """Setup IO Point 4"""

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

        movement_type: Movement_type = Movement_type.LINEAR
        """Taken from MDrive user variable 'CT'. 0: linear, 1: angular."""
        steps_per_mm: float | int = np.nan
        """Taken from MDrive user variable 'C0'."""
        steps_per_rev: float | int = np.nan
        """Taken from MDrive user variable 'C0'."""

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
        2) Stop all motion and reset any errors by calling subroutine 'F1'.
        3) Retrieve the configuration and initial measurement parameters of each
        motor.

        This method should be called directly after having established a
        serial connection to the motors, e.g. after method
        `MDrive_Controller.auto_connect()`.
        """
        # Set the echo mode to half-duplex. We don't care about the reply.
        self.query("em 1")

        # Stop any motion and reset errors. Calling this subroutine 'F1' is
        # crucial, because the MDrive motor has a strange quirk as follows.
        #
        # In detail: The [Esc]-character we sent to auto-detect the controller
        # seems to prepend any future query replies with '\r\n', i.e. instead
        # of replying to '1pr p' with '0\r\n' the MDrive motor replies with
        # '\r\n0\r\n'. The latter messes up our query methodology and a call to
        # \any\ subroutine seems to fix the issue. We use subroutine 'F1' here.
        self.init_interface()

        self.query_config()
        self.print_config()

        if "F1" in self.config.user_subroutines:
            print("    Found user subroutine F1: 'Init interface'")
        else:
            print_warning(
                "CRITICAL: User subroutine F1 ('Init interface') was not found."
                " Exiting."
            )
            sys.exit(0)

        if "F2" in self.config.user_subroutines:
            print("    Found user subroutine F2: 'Home'")
        else:
            print_warning(
                "CRITICAL: User subroutine F2 ('Home') was not found. Exiting."
            )
            sys.exit(0)

        CT = self.config.user_variables.get("CT")
        if CT is None:
            self.config.movement_type = Movement_type.LINEAR
            print_warning(
                "WARNING: User variable CT as movement type linear/angular was "
                "not found. Defaulting to linear."
            )
        else:
            self.config.movement_type = Movement_type(CT)
            print(f"    Found user variable   CT: {Movement_type(CT)}")

        C0 = self.config.user_variables.get("C0")
        if C0 is None:
            print_warning(
                "WARNING: User variable C0 as step calibration factor was "
                "not found.",
            )
        else:
            if self.config.movement_type == Movement_type.LINEAR:
                self.config.steps_per_mm = C0
                print("    Found user variable   C0: Calibration [steps/mm]")
            else:
                self.config.steps_per_rev = C0
                print("    Found user variable   C0: Calibration [steps/rev]")

        self.print_motion_config()

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

        print("    IO        | ", end="")
        print(f"S1 = {C.IO_S1}")
        print(f"{'':15} S2 = {C.IO_S2}")
        print(f"{'':15} S3 = {C.IO_S3}")
        print(f"{'':15} S4 = {C.IO_S4}")

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

    # --------------------------------------------------------------------------
    #   print_motion_config
    # --------------------------------------------------------------------------

    def print_motion_config(self):
        """Print the motion configuration parameters of the MDrive motor to the
        terminal."""
        C = self.config
        if C.movement_type == Movement_type.LINEAR:
            calib_unit = C.steps_per_mm
            calib_unit_A = "[mm/sec^2]"
            calib_unit_V = "[mm/sec]"
        else:
            calib_unit = C.steps_per_rev
            calib_unit_A = "[rev/sec^2]"
            calib_unit_V = "[rev/sec]"

        print("    Motion    | ")
        print(
            f"{'':5} Acceleration   A  = {C.motion_A:<10} [steps/sec^2] "
            f"= {C.motion_A / calib_unit:<9.4f} {calib_unit_A}"
        )
        print(
            f"{'':5} Deceleration   D  = {C.motion_D:<10} [steps/sec^2] "
            f"= {C.motion_D/calib_unit:<9.4f} {calib_unit_A}"
        )
        print(
            f"{'':5} Initial veloc. VI = {C.motion_VI:<10} [steps/sec]   "
            f"= {C.motion_VI/calib_unit:<9.4f} {calib_unit_V}"
        )
        print(
            f"{'':5} Maximum veloc. VM = {C.motion_VM:<10} [steps/sec]   "
            f"= {C.motion_VM/calib_unit:<9.4f} {calib_unit_V}"
        )
        print(f"{'':5} Microsteps     MS = {C.motion_MS:<10} [microsteps]")
        print(f"{'':5} Limit stop     LM = {C.motion_LM:<10} [mode 1-6]")
        print(f"{'':5} Run current    RC = {C.motion_RC:<10} [0-100 %]")
        print(f"{'':5} Hold current   HC = {C.motion_HC:<10} [0-100 %]")
        print(f"{'':5} Hold delay     HT = {C.motion_HT:<10} [msec]")
        print(f"{'':5} Settling delay MT = {C.motion_MT:<10} [msec]")

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

        NOTE: Calling a subroutine inadvertently will reset any error that might
        be pending inside the MDrive motor. This is by Novanta's design. Both
        parameters 'EF' and 'ER' will be set to 0.

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

    # --------------------------------------------------------------------------
    #   Transformations
    # --------------------------------------------------------------------------

    def steps2mm(self, x: float) -> float:
        return x / self.config.steps_per_mm

    def steps2rev(self, x: float) -> float:
        return x / self.config.steps_per_rev

    def steps2degrees(self, x: float) -> float:
        return x / self.config.steps_per_rev * 360

    def mm2steps(self, x: float) -> float:
        return x * self.config.steps_per_mm

    def rev2steps(self, x: float) -> float:
        return x * self.config.steps_per_rev

    def degrees2steps(self, x: float) -> float:
        return x * self.config.steps_per_rev / 360

    # --------------------------------------------------------------------------
    #   init_interface
    # --------------------------------------------------------------------------

    def init_interface(self) -> bool:
        """Perform an init interface routine by calling user subroutine 'F1'
        which stops any motion and resets any errors. Additionally, the
        measurement and error parameters of the MDrive motor get queried and
        stored inside member `MDrive_Motor.state`.

        Returns ('bool'):
            True if the command was successfully send to the motor, False
            otherwise.
        """
        success, _reply = self.execute_subroutine("F1")
        self.query_state()
        self.query_errors()

        return success

    # --------------------------------------------------------------------------
    #   home
    # --------------------------------------------------------------------------

    def home(self) -> bool:
        """Perform a homing routine by calling user subroutine 'F2'.
        Additionally, the measurement and error parameters of the MDrive motor
        get queried and stored inside member `MDrive_Motor.state`.

        Returns ('bool'):
            True if the command was successfully send to the motor, False
            otherwise.
        """
        success, _reply = self.execute_subroutine("F2")
        self.query_state()
        self.query_errors()

        return success

    # --------------------------------------------------------------------------
    #   Move commands
    # --------------------------------------------------------------------------

    def _move(
        self,
        x: float,
        relative: bool = True,
        in_units_of_step: bool = True,
    ) -> bool:
        """Base method to send a move command ('MA' or 'MR') to the motor.

        Args:
            x (`float`):
                Relative distance to move away from current position, or
                absolute position to move to.

            relative (`bool`, optional):
                When True, move relative distance `x` away from current
                position. When False, move to absolute position `x`.

                Default: True.

            in_units_of_step (`bool`, optional):
                When True, `x` is given in units of [steps]. When False, `x`
                is given in units of [mm] for linear movement and [rev] for
                angular movement.

                Default: True.

        Returns ('bool'):
            True if the command was successfully send to the motor, False
            otherwise.
        """
        C = self.config

        # Ensure x is in units of [steps] from now on
        if not in_units_of_step:
            if C.movement_type == Movement_type.LINEAR:
                x = self.mm2steps(x)
            else:
                x = self.rev2steps(x)

        # Safety check
        if np.isnan(x):
            print_warning(
                "WARNING: _move() tripped because x=nan. Movement got "
                "cancelled."
            )
            return False

        # Calculate movement
        if relative:
            # Relative movement
            distance = int(np.round(x))
            msg = f"MR {distance}"

        else:
            # Absolute movement
            if C.movement_type == Movement_type.LINEAR:
                position = int(np.round(x))
                msg = f"MA {position}"
            else:
                # Special case: Absolute angular movement. Must solve for
                # shortest path, turning it into a relative movement command.

                # Ensure integer math
                if np.isnan(self.state.position):
                    print_warning(
                        "WARNING: _move() tripped because position=nan. "
                        "Movement got cancelled."
                    )
                    return False

                if np.isnan(C.steps_per_rev):
                    print_warning(
                        "WARNING: _move() tripped because steps_per_rev=nan. "
                        "Movement got cancelled."
                    )
                    return False

                distance = shortest_path_on_step_circle(
                    from_step=int(self.state.position),
                    to_step=int(np.round(x)),
                    steps_per_rev=int(C.steps_per_rev),
                )
                msg = f"MR {distance}"

        # Send movement command to motor
        success, _reply = self.query(msg)

        # Query and update movement flag
        self.query_is_moving()

        return success

    def move_absolute_steps(self, x: float) -> bool:
        return self._move(x, relative=False, in_units_of_step=True)

    def move_relative_steps(self, x: float) -> bool:
        return self._move(x, relative=True, in_units_of_step=True)

    def move_absolute_mm(self, x: float) -> bool:
        if not self.config.movement_type == Movement_type.LINEAR:
            print_warning(
                "WARNING: move_absolute_mm() got called while "
                "movement type is angular."
            )
        return self._move(x, relative=False, in_units_of_step=False)

    def move_relative_mm(self, x: float) -> bool:
        if not self.config.movement_type == Movement_type.LINEAR:
            print_warning(
                "WARNING: move_relative_mm() got called while "
                "movement type is angular."
            )
        return self._move(x, relative=True, in_units_of_step=False)

    def move_absolute_rev(self, x: float) -> bool:
        if not self.config.movement_type == Movement_type.ANGULAR:
            print_warning(
                "WARNING: move_absolute_rev() got called while "
                "movement type is linear."
            )
        return self._move(x, relative=False, in_units_of_step=False)

    def move_relative_rev(self, x: float) -> bool:
        if not self.config.movement_type == Movement_type.ANGULAR:
            print_warning(
                "WARNING: move_relative_rev() got called while "
                "movement type is linear."
            )
        return self._move(x, relative=True, in_units_of_step=False)

    # --------------------------------------------------------------------------
    #   Slew commands
    # --------------------------------------------------------------------------

    def _slew(
        self,
        v: float,
        in_units_of_step: bool = True,
    ) -> bool:
        """Base method to send a slew command ('SL') to the motor.

        Args:
            v (`float`):
                Velocity to reach. Takes the acceleration and deceleration
                parameters ('A' and 'D') into account.

            in_units_of_step (`bool`, optional):
                When True, `v` is given in units of [steps/sec]. When False,
                `v` is given in units of [mm/sec] for linear movement and
                [rev/sec] for angular movement.

                Default: True.

        Returns ('bool'):
            True if the command was successfully send to the motor, False
            otherwise.
        """
        C = self.config

        # Ensure v is in units of [steps/sec] from now on
        if not in_units_of_step:
            if C.movement_type == Movement_type.LINEAR:
                v = self.mm2steps(v)
            else:
                v = self.rev2steps(v)

        # Safety check
        if np.isnan(v):
            print_warning(
                "WARNING: _slew() tripped because v=nan. Movement got "
                "cancelled."
            )
            return False

        # Calculate movement
        velocity = int(np.round(v))
        msg = f"SL {velocity}"

        # Send movement command to motor
        success, _reply = self.query(msg)

        # Query and update movement flag
        self.query_is_moving()

        return success

    def slew_steps_per_sec(self, v: float) -> bool:
        return self._slew(v, in_units_of_step=True)

    def slew_mm_per_sec(self, v: float) -> bool:
        if not self.config.movement_type == Movement_type.LINEAR:
            print_warning(
                "WARNING: slew_mm_per_sec() got called while movement type is "
                "angular."
            )
        return self._slew(v, in_units_of_step=False)

    def slew_rev_per_sec(self, v: float) -> bool:
        if not self.config.movement_type == Movement_type.ANGULAR:
            print_warning(
                "WARNING: slew_rev_per_sec() got called while movement type is "
                "linear."
            )
        return self._slew(v, in_units_of_step=False)

    # ------------------------------------------------------------------------------
    #   controlled_stop
    # ------------------------------------------------------------------------------

    def controlled_stop(self) -> bool:
        """Bring the motor to a controlled stop."""
        return self._slew(0)


# ------------------------------------------------------------------------------
#   tests
# ------------------------------------------------------------------------------


def test_shortest_path_on_step_circle():
    spr = 6400  # steps_per_rev

    # Test case 1: Same starting and ending position
    assert shortest_path_on_step_circle(0, 0, spr) == 0
    assert shortest_path_on_step_circle(spr + 10, 10, spr) == 0

    # Test case 2: Shortest path is CCW rotation
    assert shortest_path_on_step_circle(0, spr // 4, spr) == spr // 4
    assert shortest_path_on_step_circle(spr * 3 // 4, 0, spr) == spr // 4

    # Test case 3: Shortest path is CW rotation
    assert shortest_path_on_step_circle(spr // 4, 0, spr) == -spr // 4
    assert shortest_path_on_step_circle(0, spr * 3 // 4, spr) == -spr // 4

    # Test case 4: Shortest path crosses 0 degrees
    assert (
        shortest_path_on_step_circle(spr * 9 // 10, spr // 10, spr)
        == spr * 2 // 10
    )
    assert (
        shortest_path_on_step_circle(spr // 10, spr * 9 // 10, spr)
        == -spr * 2 // 10
    )

    print("All test cases passed!")


def test_shortest_path_on_unit_circle():
    eps = 1e-16  # Max. acceptable rounding error

    # Test case 1: Same starting and ending position
    assert shortest_path_on_unit_circle(0, 0) < eps
    assert shortest_path_on_unit_circle(1.1, 0.1) < eps

    # Test case 2: Shortest path is CCW rotation
    assert shortest_path_on_unit_circle(0, 0.25) - 0.25 < eps
    assert shortest_path_on_unit_circle(0.75, 0) - 0.25 < eps

    # Test case 3: Shortest path is CW rotation
    assert shortest_path_on_unit_circle(0.25, 0) + 0.25 < eps
    assert shortest_path_on_unit_circle(0, 0.75) + 0.25 < eps

    # Test case 4: Shortest path crosses 0 degrees
    assert shortest_path_on_unit_circle(0.9, 0.1) - 0.2 < eps
    assert shortest_path_on_unit_circle(0.1, 0.9) + 0.2 < eps

    print("All test cases passed!")


# ------------------------------------------------------------------------------
#   Main: Will show a demo when run from the terminal
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # test_shortest_path_on_step_circle()
    # test_shortest_path_on_unit_circle()

    mdrive = MDrive_Controller()
    if not mdrive.auto_connect(
        filepath_last_known_port="config/port_MDrive.txt"
    ):
        sys.exit(0)

    # mdrive.begin()
    mdrive.begin(device_names_to_scan="xyza")

    if input("Proceed with motor movement? [y/N]").lower() == "y":
        for DN, motor in mdrive.motors.items():
            # Test: Homing
            # ------------
            print(f"Homing '{DN}'... ", end="")
            sys.stdout.flush()

            motor.home()
            while motor.state.is_moving:
                motor.query_is_moving()
            print("done.")

            # Update full state
            motor.query_state()
            motor.query_errors()

            # Test: Moving
            # ------------
            print(f"Moving '{DN}'... ", end="")
            sys.stdout.flush()
            count = 1

            # motor.move_absolute_mm(20)
            motor.slew_mm_per_sec(10)
            while motor.state.is_moving:
                count += 1
                if count == 100:
                    # mdrive.STOP()
                    # mdrive.RESET()
                    motor.controlled_stop()
                motor.query_is_moving()
            print("done.")

            # Update full state
            motor.query_state()
            motor.query_errors()

    mdrive.close()
