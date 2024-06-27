#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RS232 function library for a Parker Compax3 servo controller. Only the ASCII
version is supported, not (yet) the binary version.

Communication errors will be handled as non-fatal. This means it will struggle
on with the script while reporting error messages to the command line output,
as opposed to terminating the program completely.

State variables that read numpy.nan indicate that they are uninitialized or that
the previous query resulted in a communication error.

When this module is directly run from the terminal a demo will be shown.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "23-05-2024"
__version__ = "1.5.0"
# pylint: disable=missing-function-docstring, pointless-string-statement

import sys
from typing import Union, Tuple

import numpy as np

from dvg_devices.BaseDevice import SerialDevice


class Compax3_servo(SerialDevice):
    class Status_word_1:
        """[numpy.nan] values indicate that the parameter is not initialized or
        that the last query was unsuccessful in communication."""

        # fmt: off
        I0                : Union[float, bool] = np.nan  # bit 0
        I1                : Union[float, bool] = np.nan  # bit 1
        I2                : Union[float, bool] = np.nan  # bit 2
        I3                : Union[float, bool] = np.nan  # bit 3
        I4                : Union[float, bool] = np.nan  # bit 4
        I5                : Union[float, bool] = np.nan  # bit 5
        I6                : Union[float, bool] = np.nan  # bit 6
        I7                : Union[float, bool] = np.nan  # bit 7 'open motor holding brake'
        no_error          : Union[float, bool] = np.nan  # bit 8
        pos_reached       : Union[float, bool] = np.nan  # bit 9
        powerless         : Union[float, bool] = np.nan  # bit 10
        powered_stationary: Union[float, bool] = np.nan  # bit 11 'standstill'
        zero_pos_known    : Union[float, bool] = np.nan  # bit 12
        PSB0              : Union[float, bool] = np.nan  # bit 13
        PSB1              : Union[float, bool] = np.nan  # bit 14
        PSB2              : Union[float, bool] = np.nan  # bit 15
        # fmt: on

    class State:
        """[numpy.nan] values indicate that the parameter is not initialized or
        that the last query was unsuccessful in communication."""

        # fmt: off
        cur_pos: float = np.nan  # position [mm]
        error_msg: str = ""      # error string message
        # fmt: on

    def __init__(
        self,
        name="trav",
        long_name="Compax3 servo",
        connect_to_serial_number=None,
    ):
        super().__init__(name=name, long_name=long_name)

        # Default serial settings
        self.serial_settings = {
            "baudrate": 115200,
            "timeout": 0.4,
            "write_timeout": 0.4,
            "rtscts": True,
        }
        self.set_read_termination("\r")
        self.set_write_termination("\r")

        self.set_ID_validation_query(
            ID_validation_query=self.ID_validation_query,
            valid_ID_broad="Compax3",
            valid_ID_specific=connect_to_serial_number,
        )

        # Containers for the status, process and measurement variables
        self.status_word_1 = self.Status_word_1()
        self.state = self.State()

        self.serial_str = ""  # Serial number of the Compax3

    # --------------------------------------------------------------------------
    #   OVERRIDE: query
    # --------------------------------------------------------------------------

    def query(
        self,
        msg: Union[str, bytes],
        raises_on_timeout: bool = False,
        returns_ascii: bool = True,
    ) -> Tuple[bool, Union[str, bytes, None]]:
        success, reply = super().query(msg, raises_on_timeout, returns_ascii)

        # The Compax3 is more complex in its replies than the average device.
        # Hence:
        if isinstance(reply, str):
            if reply[0] == ">":
                # Successful operation without meaningful reply
                pass
            elif reply[0] == "!":
                # Error reply
                print("COMPAX3 COMMUNICATION ERROR: " + reply)
                success = False
            else:
                # Successful operation with meaningful reply
                pass

        return success, reply

    # --------------------------------------------------------------------------
    #   ID_validation_query
    # --------------------------------------------------------------------------

    def ID_validation_query(self) -> Tuple[str, Union[str, None]]:
        broad_reply = ""
        specific_reply = None

        _success, reply = self.query("_?")
        if isinstance(reply, str):
            broad_reply = reply[:7]  # Expected: "Compax3"

        _success, reply = self.query("o1.4")
        if isinstance(reply, str):
            specific_reply = reply  # Serial number

        return broad_reply, specific_reply

    # --------------------------------------------------------------------------
    #   begin
    # --------------------------------------------------------------------------

    def begin(self):
        """This function should run directly after having established a
        connection to the device.

        Returns: True if successful, False otherwise.
        """
        success = self.query_serial_str()
        success &= self.query_error()
        success &= self.query_position()
        success &= self.query_status_word_1()
        return success

    # --------------------------------------------------------------------------
    #   Higher level queries
    # --------------------------------------------------------------------------

    def query_serial_str(self) -> bool:
        """Query the serial number and store it in the class member 'serial_str'

        Returns: True if successful, False otherwise.
        """
        # First make sure we're dealing with a Compax3 controller, because we
        # have to exclude the possibility that another device will reply with
        # an error message to the serial number request, which then could be
        # mistaken for /the/ serial number.
        _success, reply = self.query("_?")
        if isinstance(reply, str) and reply.startswith("Compax3"):
            # Now we can query the serial number
            _success, reply = self.query("o1.4")
            if isinstance(reply, str):
                self.serial_str = reply
                return True

        self.serial_str = ""
        return False

    def query_position(self) -> bool:
        """Query the position and store in the class member 'state.cur_pos'
        when successful. When the communication fails the class member will be
        set to [numpy.nan].

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query("o680.5")
        if isinstance(reply, str):
            self.state.cur_pos = float(reply)
            return True

        self.state.cur_pos = np.nan
        return False

    def query_error(self) -> bool:
        """Query the last error and store in the class member 'state.error_msg'
        when successful. When the communication fails the class member will be
        set to [numpy.nan].

        Returns: True if successful, False otherwise.
        """
        _success, reply = self.query("o550.1")
        if isinstance(reply, str):
            # Translate error codes to more meaningful messages
            if reply == "1":
                self.state.error_msg = ""
            elif reply == "17168":
                self.state.error_msg = f"{reply}: Motor temperature"
            elif reply == "29472":
                self.state.error_msg = f"{reply}: Following error"
            elif reply == "29475":
                self.state.error_msg = (
                    f"{reply}: Target or actual position "
                    "exceeds positive end limit"
                )
            elif reply == "29476":
                self.state.error_msg = (
                    f"{reply}: Target or actual position "
                    "exceeds negative end limit"
                )
            elif reply == "29479":
                self.state.error_msg = (
                    f"{reply}: Change of direction during " "movement"
                )
            else:
                self.state.error_msg = reply
            return True

        self.state.error_msg = ""
        return False

    def query_status_word_1(self) -> bool:
        """Query the status word 1 and store in the class member 'status_word_1'
        when successful. When the communication fails the class member
        'status_word_1' will be populated with [numpy.nan].

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query("o1000.3")

        if reply is None:
            # fmt: off
            self.status_word_1.I0 = np.nan
            self.status_word_1.I1 = np.nan
            self.status_word_1.I2 = np.nan
            self.status_word_1.I3 = np.nan
            self.status_word_1.I4 = np.nan
            self.status_word_1.I5 = np.nan
            self.status_word_1.I6 = np.nan
            self.status_word_1.I7 = np.nan
            self.status_word_1.no_error           = np.nan
            self.status_word_1.pos_reached        = np.nan
            self.status_word_1.powerless          = np.nan
            self.status_word_1.powered_stationary = np.nan
            self.status_word_1.zero_pos_known     = np.nan
            self.status_word_1.PSB0 = np.nan
            self.status_word_1.PSB1 = np.nan
            self.status_word_1.PSB2 = np.nan
            # fmt: on
        else:
            dec_x = int(reply)

            # Convert dec to bin string, remove prefix '0b', prefix with 0's to
            # garantuee 16 bits and reverse
            str_bits = ((bin(dec_x)[2:]).zfill(16))[::-1]

            # fmt: off
            self.status_word_1.I0 = bool(int(str_bits[0]))
            self.status_word_1.I1 = bool(int(str_bits[1]))
            self.status_word_1.I2 = bool(int(str_bits[2]))
            self.status_word_1.I3 = bool(int(str_bits[3]))
            self.status_word_1.I4 = bool(int(str_bits[4]))
            self.status_word_1.I5 = bool(int(str_bits[5]))
            self.status_word_1.I6 = bool(int(str_bits[6]))
            self.status_word_1.I7 = bool(int(str_bits[7]))
            self.status_word_1.no_error           = bool(int(str_bits[8]))
            self.status_word_1.pos_reached        = bool(int(str_bits[9]))
            self.status_word_1.powerless          = bool(int(str_bits[10]))
            self.status_word_1.powered_stationary = bool(int(str_bits[11]))
            self.status_word_1.zero_pos_known     = bool(int(str_bits[12]))
            self.status_word_1.PSB0 = bool(int(str_bits[13]))
            self.status_word_1.PSB1 = bool(int(str_bits[14]))
            self.status_word_1.PSB2 = bool(int(str_bits[15]))
            # fmt: on

        return success

    # --------------------------------------------------------------------------
    # --------------------------------------------------------------------------

    def store_motion_profile(
        self,
        target_position=0,
        velocity=10,
        mode=1,
        accel=100,
        decel=100,
        jerk=1e6,
        profile_number=2,
    ) -> bool:
        """
        Note:
            Profile_number 0 is reserved for homing.
            Movement mode is fixed to absolute, not relative.
        """
        mode = 1  # Overrule, set movement mode to absolute position
        p = profile_number  # Shorthand

        print(f"  Profile number: {p}")
        print(f"    pos   = {target_position:.2f}")
        print(f"    vel   = {velocity:.2f}")
        print(f"    mode  = {mode:d} (fixed to absolute)")
        print(f"    accel = {accel:.2f}")
        print(f"    decel = {decel:.2f}")
        print(f"    jerk  = {jerk:.2f}\n")

        success, _reply = self.query(f"o1901.{p:d}={target_position:.2f}")
        if success:
            success, _reply = self.query(f"o1902.{p:d}={velocity:.2f}")
        if success:
            success, _reply = self.query(f"o1905.{p:d}={mode:d}")
        if success:
            success, _reply = self.query(f"o1906.{p:d}={accel:.2f}")
        if success:
            success, _reply = self.query(f"o1907.{p:d}={decel:.2f}")
        if success:
            success, _reply = self.query(f"o1908.{p:d}={jerk:.2f}")
        if success:
            success, _reply = self.query(f"o1904.{p:d}=$32")  # Store profile

        return success

    def activate_motion_profile(self, profile_number=2) -> bool:
        # Control word (CW) for activating the passed profile number
        # First send: quit/motor bit (bit 0) high
        #             stop bits (bits 1, 14) high
        #             start bit (bit 13) low
        CW_LO = 0b0100000000000011
        CW_LO = CW_LO + (profile_number << 8)
        success, _reply = self.query(f"o1100.3={CW_LO:d}")
        if success:
            # Then send start bit (bit 13) high
            CW_HI = CW_LO + (1 << 13)
            success, _reply = self.query(f"o1100.3={CW_HI:d}")

        return success

    def move_to_target_position(
        self, target_position, profile_number=2
    ) -> bool:
        """
        Note: Make sure a motion profile with number 'profile_number' is stored
        at least once with 'self.store_motion_profile' before moving.
        """
        # Send new target position
        success, _reply = self.query(
            f"o1901.{profile_number:d}={target_position:.2f}"
        )

        if success:
            self.activate_motion_profile(profile_number=2)

        return success

    def jog_plus(self) -> bool:
        # Control word (CW) for activating the jog+
        CW_LO = 0b0100000000000011
        success, _reply = self.query(f"o1100.3={CW_LO:d}")
        if success:
            # Then send jog+ bit (bit 2) high
            CW_HI = CW_LO + (1 << 2)
            success, _reply = self.query(f"o1100.3={CW_HI:d}")

        return success

    def jog_minus(self) -> bool:
        # Control word (CW) for activating the jog-
        CW_LO = 0b0100000000000011
        success, _reply = self.query(f"o1100.3={CW_LO:d}")
        if success:
            # Then send jog- bit (bit 3) high
            CW_HI = CW_LO + (1 << 3)
            success, _reply = self.query(f"o1100.3={CW_HI:d}")

        return success

    def stop_motion_but_keep_power(self) -> bool:
        CW_LO = 0b0100000000000011
        success, _reply = self.query(f"o1100.3={CW_LO:d}")

        return success

    def stop_motion_and_remove_power(self) -> bool:
        success, _reply = self.query("o1100.3=0")

        return success

    def acknowledge_error(self) -> bool:
        """If the cause of an error is eliminated, the error can be
        acknowledged. This is necessary for the axis to be able to get powered
        again.

        Sends a rising edge on bit 0 of the control word. This will leave the
        axis powered when no new error occurs again.

        Returns: True if successful, False otherwise.
        """
        success, _reply = self.query("o1100.3=0")
        if success:
            success, _reply = self.query("o1100.3=1")

        return success

    def report_status_word_1(self, compact=False):
        SW = self.status_word_1  # Shorthand
        if not compact:
            print("Status word 1:")
            print(f"  {SW.I0:-6s}: I0")
            print(f"  {SW.I1:-6s}: I1")
            print(f"  {SW.I2:-6s}: I2")
            print(f"  {SW.I3:-6s}: I3")
            print(f"  {SW.I4:-6s}: I4")
            print(f"  {SW.I5:-6s}: I5")
            print(f"  {SW.I6:-6s}: I6")
            print(f"  {SW.I7:-6s}: I7")
            print(f"  {SW.no_error:-6s}: no_error")
            print(f"  {SW.pos_reached:-6s}: pos_reached")
            print(f"  {SW.powerless:-6s}: powerless")
            print(f"  {SW.powered_stationary:-6s}: powered_stat")
            print(f"  {SW.zero_pos_known:-6s}: zero_pos_known")
            print(f"  {SW.PSB0:-6s}: PSB0")
            print(f"  {SW.PSB1:-6s}: PSB1")
            print(f"  {SW.PSB2:-6s}: PSB2")
        else:
            if not SW.no_error:
                print("  ERROR!")
            if SW.powerless:
                print("  Axis    : unpowered")
            else:
                if SW.powered_stationary:
                    print("  Axis    : POWERED STANDSTILL")
                else:
                    print("  Axis    : POWERED")
            if SW.zero_pos_known:
                print("  Zero pos: known")
            else:
                print("  Zero pos: UNKNOWN")
            if SW.pos_reached:
                print("  Position: REACHED")
            else:
                print("  Position: unreached")
        print("")


# ------------------------------------------------------------------------------
#   Main: Will show a demo when run from the terminal
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    import time

    # Specific connection settings of each traverse axis of our setup
    class Trav_connection_params:
        # Serial number of the Compax3 servo controller to connect to.
        # Set to "" to connect to any Compax3.
        serial = ""
        # Display name
        name = "TRAV"
        # Path to the config textfile containing the (last used) RS232 port
        path_config = "config/port_Compax3_servo.txt"

    # Horizontal axis
    trav_conn_horz = Trav_connection_params()
    trav_conn_horz.serial = "4409980001"
    trav_conn_horz.name = "TRAV HORZ"
    trav_conn_horz.path_config = "config/port_Compax3_servo_horz.txt"

    # Vertical axis
    trav_conn_vert = Trav_connection_params()
    trav_conn_vert.serial = "4319370001"
    trav_conn_vert.name = "TRAV VERT"
    trav_conn_vert.path_config = "config/port_Compax3_servo_vert.txt"

    # Connect to this specific traverse axis
    # trav_conn = Trav_connection_params()  # Any
    # trav_conn = trav_conn_horz
    trav_conn = trav_conn_vert

    # --------------------------------------------------------------------------
    # --------------------------------------------------------------------------

    # Create connection to Compax3 servo controller over RS232
    trav = Compax3_servo(
        name=trav_conn.name,
        connect_to_serial_number=trav_conn.serial,
    )

    if trav.auto_connect(filepath_last_known_port=trav_conn.path_config):
        trav.begin()  # Retrieve necessary parameters
    else:
        time.sleep(1)
        sys.exit(0)

    print(f"Error msg: {trav.state.error_msg}")
    print(f"Current position: {trav.state.cur_pos:.2f}")
    trav.report_status_word_1(compact=True)

    trav.acknowledge_error()

    print("ERRORS RESET")
    print("ACTIVATE\n")
    time.sleep(0.1)

    trav.query_status_word_1()
    trav.report_status_word_1(compact=True)

    # Update set #2
    # fmt: off
    trav.query("o1901.2=-180.0")     # target position
    trav.query("o1902.2=100.0")      # velocity
    trav.query("o1905.2=1")          # mode: 1 (MoveAbs), 2 (MoveRel)
    trav.query("o1906.2=100")        # accel
    trav.query("o1907.2=100")        # decel
    trav.query("o1908.2=1000000")    # jerk
    trav.query("o1904.2=$32")        # store profile

    trav.query("o1100.3=16899")      # set #2, start bit low
    trav.query("o1100.3=25091")      # set #2, start bit high

    """
    trav.query("o1100.3=$4003")      # set #0, homing, start bit low
    trav.query("o1100.3=$6003")      # set #0, homing, start bit high
    """

    """
    trav.query("o1100.3=$4007")      # jog+
    time.sleep(2);

    trav.query_position()
    print(f"Current position: {trav.state.cur_pos:.2f}")

    trav.query("o1100.3=$400b")      # jog-
    time.sleep(2);
    """
    # fmt: on

    print("MOVING\n")

    for i in range(14):
        trav.query_position()
        print(f"Current position: {trav.state.cur_pos:.2f}")
        trav.query_status_word_1()
        trav.report_status_word_1(compact=True)
        time.sleep(0.2)

    trav.query("o1100.3=0")  # disable axis
    # trav.query("o1000.4")   # last executed set #

    print("DEACTIVATE\n")
    time.sleep(1)

    trav.query_error()
    trav.query_position()
    trav.query_status_word_1()

    print(f"Error msg: {trav.state.error_msg}")
    print(f"Current position: {trav.state.cur_pos:.2f}")
    trav.report_status_word_1(compact=True)

    # Close
    print("")
    trav.close()
    sys.exit(0)
