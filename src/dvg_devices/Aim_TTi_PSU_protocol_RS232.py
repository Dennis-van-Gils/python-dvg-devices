#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RS232 function library for an Aim TTi power supply unit (PSU), QL series II.

! NOT FUNCTIONING YET
! WORK IN PROGRESS

Note:
    * Only one channel (channel 1) implemented
    * Limited error reporting

"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "17-08-2020"
__version__ = "0.2.1"
# pylint: disable=bare-except, broad-except, try-except-raise

import sys
import time
from typing import AnyStr

import numpy as np

from dvg_debug_functions import print_fancy_traceback as pft
from dvg_devices.BaseDevice import SerialDevice

# Show debug information in terminal?
DEBUG = True


class Aim_TTi_PSU(SerialDevice):
    class State:
        """Container for the process and measurement variables.
        [numpy.nan] values indicate that the parameter is not initialized or
        that the last query was unsuccessful in communication.
        """

        # fmt: off
        V_source = 0        # Voltage to be sourced         [V]
        I_source = 0        # Current to be sourced (limit) [A]
        P_source = 0        # Power to be sourced, when PID controller is on [W]
        ENA_PID = False     # Is the PID controller on the power ouput enabled?

        V_meas = np.nan         # Measured output voltage [V]
        I_meas = np.nan         # Measured output current [A]
        P_meas = np.nan         # Derived output power    [W]

        OVP_level  = np.nan     # Over-voltage protection level [V]
        OCP_level  = np.nan     # Over-current protection level [A]
        ENA_output = False      # Is power output enabled (by software)?
        # fmt: on

        """ NOT IMPLEMENTED YET
        # The error string retreived from the error queue of the device. None
        # indicates no error is left in the queue.
        error = None

        # This list of strings is provided to be able to store all errors from
        # the device queue. This list is populated by calling 'query_error'
        # until no error is left in the queue. This list can then be printed to
        # screen or GUI and the user should 'acknowledge' the list, after which
        # the list can be emptied (=[]) again.
        all_errors = []
        """

        # Limit Event Status Register (LSR)
        # fmt: off
        status_LSR_AUX_TRP = False  # Aux output trip                   , bit 7
        status_LSR_AUX_CC = False   # Aux output constant-current mode  , bit 6
        status_LSR_SN = False       # Sense trip                        , bit 5
        status_LSR_OT = False       # Over-temperature trip             , bit 4
        status_LSR_OCP = False      # Over-current trip                 , bit 3
        status_LSR_OVP = False      # Over-voltage trip                 , bit 2
        status_LSR_CC = False       # Constant-current mode             , bit 1
        status_LSR_CV = False       # Constant-voltage mode             , bit 0
        # fmt: on

    class Config:
        # fmt: off
        V_source  = 10   # Voltage to be sourced         [V]
        I_source  = 0.5  # Current to be sourced (limit) [A]
        P_source  = 0    # Power   to be sourced         [W]
        OVP_level = 12   # Over-voltage protection level [V]
        OCP_level = 1    # Over-current protection level [A]
        # fmt: on

    # --------------------------------------------------------------------------
    #   __init__
    # --------------------------------------------------------------------------

    def __init__(
        self,
        name="PSU",
        long_name="Aim TTi power supply",
        connect_to_serial_number=None,
    ):
        super().__init__(name=name, long_name=long_name)

        # Default serial settings
        self.serial_settings = {
            "baudrate": 9600,  # baudrate gets ignored
            "timeout": 0.2,
            "write_timeout": 0.2,
        }
        self.set_read_termination("\r\n")
        self.set_write_termination("\r\n")

        self.set_ID_validation_query(
            ID_validation_query=self.ID_validation_query,
            valid_ID_broad=True,
            valid_ID_specific=connect_to_serial_number,
        )

        # Container for the process and measurement variables
        self.state = self.State()
        self.config = self.Config()

        self.idn_str = None  # Identity response of the device
        self.serial_str = None  # Serial number of the device
        self.model_str = None  # Model of the device

    # --------------------------------------------------------------------------
    #   write_and_wait_for_opc
    # --------------------------------------------------------------------------

    def write_and_wait_for_opc(
        self, msg: AnyStr, raises_on_timeout: bool = False
    ) -> bool:
        """For proper synchronization we have to wait for the Operation Complete
        status of the device for the majority of the `set` commands. Hence this
        method.
        """
        success = self.write(msg=msg, raises_on_timeout=raises_on_timeout)
        if success:
            self.wait_for_OPC()  # Crucial!

        return success

    # --------------------------------------------------------------------------
    #   ID_validation_query
    # --------------------------------------------------------------------------

    def ID_validation_query(self) -> (bool, str):
        success = self.query_idn()
        return (success, self.serial_str)

    # --------------------------------------------------------------------------
    #   begin
    # --------------------------------------------------------------------------

    def begin(self):
        """This function should run directly after having established a
        connection to the device.

        Returns: True if successful, False otherwise.
        """
        # Clear errors
        # self.state.error = None
        # self.state.all_errors = []

        if not self.is_alive:
            print("ERROR: Device is not connected yet or already closed.")
            return False

        success = self.set_LSE(value=255)  # Report all limits and trips
        success &= self.query_OVP_level()
        success &= self.query_OCP_level()
        success &= self.query_V_source()
        success &= self.query_I_source()
        success &= self.query_LSR()
        # self.query_all_errors_in_queue()

        return success

    # --------------------------------------------------------------------------
    #   reinitialize
    # --------------------------------------------------------------------------

    def reinitialize(self):
        """Reinitialize the PSU, including clear and reset

        Returns: True if all messages were sent and received successfully,
            False otherwise.
        """
        # Clear errors
        # self.state.error = None
        # self.state.all_errors = []

        if not self.is_alive:
            print("ERROR: Device is not connected yet or already closed.")
            return False

        # Clear device's input and output buffers
        self.ser.flushInput()
        self.ser.flushOutput()

        success = self.clear_and_reset()
        success &= self.set_OVP_level(self.config.OVP_level)
        success &= self.set_OCP_level(self.config.OCP_level)
        success &= self.set_V_source(self.config.V_source)
        success &= self.set_I_source(self.config.I_source)
        self.state.P_source = self.config.P_source
        self.state.ENA_PID = False

        success &= self.query_OVP_level()
        success &= self.query_OCP_level()
        success &= self.query_V_source()
        success &= self.query_I_source()
        success &= self.query_LSR()
        # self.query_all_errors_in_queue()

        return success

    # --------------------------------------------------------------------------
    #   query_idn
    # --------------------------------------------------------------------------

    def query_idn(self) -> bool:
        """Query the identity, serial and model number and store it in the class
        members.

        Returns: True if successful, False otherwise.
        """
        success, reply = self.query("*idn?")
        if success and reply[:19] == "THURLBY THANDAR, QL":
            self.idn_str = reply
            self.serial_str = reply.split(",")[2].strip()
            self.model_str = reply.split(",")[1].strip()
            return True

        self.idn_str = None
        self.serial_str = None
        self.model_str = None
        return False

    # --------------------------------------------------------------------------
    #   System status related
    # --------------------------------------------------------------------------

    def clear_and_reset(self) -> bool:
        """Clear device status and reset. Return when this operation has
        completed on the device. Blocking.

        Returns: True if the message was sent successfully, False otherwise.
        """

        if not self.is_alive:
            print("ERROR: Device is not connected yet or already closed.")
            return False

        # Send clear and reset
        success = self.write("*cls;*rst")
        if success:
            # For some reason '*opc?' will not wait for operation complete
            # after a '*cls;*rst'. Hence, we will sleep instead.
            time.sleep(0.2)  # Crucial!

        return success

    def wait_for_OPC(self):
        """'Operation complete' query, used for event synchronization. Will wait
        for all device operations to complete or until a timeout is triggered.
        Blocking.

        Returns: True if successful, False otherwise.
        """
        # Returns an ASCII "1" when all pending overlapped operations have been
        # completed.
        success, reply = self.query("*opc?")
        if success and reply == "1":
            return True

        pft("Warning: *opc? timed out at device %s" % self.name)
        return False

    def set_LSE(self, value: int, channel: int = 1) -> bool:
        """Set the value of the Limit Event Status Enable Register (LSE).

        Args:
            value (int): (0-255)
                * bit 7: Aux output trip
                * bit 6: Aux output constant-current mode
                * bit 5: Sense trip
                * bit 4: Over-temperature trip
                * bit 3: Over-current trip
                * bit 2: Over-voltage trip
                * bit 1: Constant-current mode
                * bit 0: Constant-voltage mode

        Returns: True if successful, False otherwise.
        """
        return self.write_and_wait_for_opc("LSE%d %d" % (channel, value))

    def query_LSR(self, verbose: bool = False, channel: int = 1) -> bool:
        """Query and parse the Limit Event Status Register (LSR).

        Returns: True if successful, False otherwise.
        """
        # We will ignore the first read-out, because it apparently always lags
        # one behind.
        self.query("LSR%d?" % channel)

        success, reply = self.query("LSR%d?" % channel)
        if success:
            # fmt: off
            status_code = int(reply)
            self.state.status_LSR_AUX_TRP = bool(status_code & 128)
            self.state.status_LSR_AUX_CC  = bool(status_code & 64)
            self.state.status_LSR_SN      = bool(status_code & 32)
            self.state.status_LSR_OT      = bool(status_code & 16)
            self.state.status_LSR_OCP     = bool(status_code & 8)
            self.state.status_LSR_OVP     = bool(status_code & 4)
            self.state.status_LSR_CC      = bool(status_code & 2)
            self.state.status_LSR_CV      = bool(status_code & 1)

            if verbose:
                if self.state.status_LSR_AUX_TRP: print("  AUX TRIP")
                if self.state.status_LSR_AUX_CC : print("  AUX CC mode")
                if self.state.status_LSR_SN     : print("  SENSE TRIP")
                if self.state.status_LSR_OT     : print("  OT TRIP")
                if self.state.status_LSR_OCP    : print("  OCP TRIP")
                if self.state.status_LSR_OVP    : print("  OVP TRIP")
                if self.state.status_LSR_CC     : print("  CC mode")
                if self.state.status_LSR_CV     : print("  CV mode")
            # fmt: on

        return success

    # --------------------------------------------------------------------------
    #   Protection related
    # --------------------------------------------------------------------------

    def reset_trip(self) -> bool:
        """Attempt to clear all trip conditions from all outputs.

        Returns: True if successful, False otherwise.
        """
        return self.write_and_wait_for_opc("TRIPRST")

    def set_OVP_level(self, voltage_V, channel: int = 1) -> bool:
        """Returns: True if the message was sent successfully, False otherwise.
        """
        try:
            voltage_V = float(voltage_V)
        except (ValueError, TypeError):
            voltage_V = 0.0
        except:
            raise

        if self.write_and_wait_for_opc("OVP%d %f" % (channel, voltage_V)):
            self.state.OVP_level = voltage_V
            return True

        return False

    def set_OCP_level(self, current_A, channel: int = 1) -> bool:
        """Returns: True if the message was sent successfully, False otherwise.
        """
        try:
            current_A = float(current_A)
        except (ValueError, TypeError):
            current_A = 0.0
        except:
            raise

        if self.write_and_wait_for_opc("OCP%d %f" % (channel, current_A)):
            self.state.OCP_level = current_A
            return True

        return False

    def query_OVP_level(self, channel: int = 1) -> bool:
        """Returns: True if successful, False otherwise.
        """
        success, reply = self.query("OVP%d?" % channel)
        if success:
            if reply[:3] == "VP%d" % channel:
                self.state.OVP_level = float(reply[4:])
                return True
            else:
                pft("Received incorrect reply: %s" % reply)

        return False

    def query_OCP_level(self, channel: int = 1) -> bool:
        """Returns: True if successful, False otherwise.
        """
        success, reply = self.query("OCP%d?" % channel)
        if success:
            if reply[:3] == "CP%d" % channel:
                self.state.OCP_level = float(reply[4:])
                return True
            else:
                pft("Received incorrect reply: %s" % reply)

        return False

    # --------------------------------------------------------------------------
    #   Output related
    # --------------------------------------------------------------------------

    def turn_on(self, channel: int = 1) -> bool:
        """Returns: True if the message was sent successfully, False otherwise.
        """
        return self.set_ENA_output(ENA=True, channel=channel)

    def turn_off(self, channel: int = 1) -> bool:
        """Returns: True if the message was sent successfully, False otherwise.
        """
        return self.set_ENA_output(ENA=False, channel=channel)

    def set_ENA_output(self, ENA: bool, channel: int = 1) -> bool:
        """Returns: True if the message was sent successfully, False otherwise.
        """
        if self.write_and_wait_for_opc("OP%d %d" % (channel, ENA)):
            self.state.ENA_output = ENA
            return True

        return False

    def set_V_source(self, voltage_V, channel: int = 1) -> bool:
        """Returns: True if the message was sent successfully, False otherwise.
        """
        try:
            voltage_V = float(voltage_V)
        except (ValueError, TypeError):
            voltage_V = 0.0
        except:
            raise

        if self.write_and_wait_for_opc("V%d %.3f" % (channel, voltage_V)):
            self.state.V_source = voltage_V
            return True

        return False

    def set_I_source(self, current_A, channel: int = 1) -> bool:
        """Returns: True if the message was sent successfully, False otherwise.
        """
        try:
            current_A = float(current_A)
        except (ValueError, TypeError):
            current_A = 0.0
        except:
            raise

        if self.write_and_wait_for_opc("I%d %.4f" % (channel, current_A)):
            self.state.I_source = current_A
            return True

        return False

    def query_ENA_output(self, channel: int = 1) -> bool:
        """Returns: True if the query was received successfully, False otherwise.
        """
        success, reply = self.query("OP%d?" % channel)
        if success:
            self.state.ENA_output = bool(int(reply))

        return success

    def query_V_source(self, channel: int = 1) -> bool:
        """Returns: True if the query was received successfully, False otherwise.
        """
        success, reply = self.query("V%d?" % channel)
        if success:
            if reply[:2] == "V%d" % channel:
                self.state.V_source = float(reply[3:])
                return True

            pft("Received incorrect reply: %s" % reply)

        return False

    def query_V_meas(self, channel: int = 1) -> bool:
        """Returns: True if the query was received successfully, False otherwise.
        """
        success, reply = self.query("V%dO?" % channel)
        if success:
            if reply[-1:] == "V":
                self.state.V_meas = float(reply[:-1])
                self.state.P_meas = self.state.I_meas * self.state.V_meas
                return True

            pft("Received incorrect reply: %s" % reply)

        return False

    def query_I_source(self, channel: int = 1) -> bool:
        """Returns: True if the query was received successfully, False otherwise.
        """
        success, reply = self.query("I%d?" % channel)
        if success:
            if reply[:2] == "I%d" % channel:
                self.state.I_source = float(reply[3:])
                return True

            pft("Received incorrect reply: %s" % reply)

        return False

    def query_I_meas(self, channel: int = 1) -> bool:
        """Returns: True if the query was received successfully, False otherwise.
        """
        success, reply = self.query("I%dO?" % channel)
        if success:
            if reply[-1:] == "A":
                self.state.I_meas = float(reply[:-1])
                self.state.P_meas = self.state.I_meas * self.state.V_meas
                return True

            pft("Received incorrect reply: %s" % reply)

        return False

    # --------------------------------------------------------------------------
    #   Speed tests for debugging
    # --------------------------------------------------------------------------

    def speed_test(self):
        """Results: Each iteration takes 80 ms to finish.
        """
        self.turn_off()  # Disable output for safety

        tic = time.perf_counter()
        for i in range(100):
            print("%d %.3f" % (i, time.perf_counter() - tic))
            self.set_V_source(i % 10)

        print(time.perf_counter() - tic)
        self.report()

    def speed_test2(self):
        """Results: Each iteration takes 8 ms to finish.
        """

        tic = time.perf_counter()
        for i in range(100):
            print(
                "%d %.3f %.3f %.3f"
                % (
                    i,
                    time.perf_counter() - tic,
                    self.state.V_meas,
                    self.state.I_meas,
                )
            )
            self.query_V_meas()
            self.query_I_meas()

        print(time.perf_counter() - tic)
        self.report()

    # --------------------------------------------------------------------------
    #   report
    # --------------------------------------------------------------------------

    def report(self, channel: int = 1):
        """Report to the terminal.
        """
        # print("\nError")
        # print(chr(0x2014) * 26)
        # self.query_error(True)
        # while not self.state.error is None:
        #    self.query_error(True)

        self.query_LSR(verbose=True, channel=channel)
        self.query_ENA_output(channel=channel)
        self.query_OVP_level(channel=channel)
        self.query_OCP_level(channel=channel)
        self.query_V_source(channel=channel)
        self.query_I_source(channel=channel)
        self.query_V_meas(channel=channel)
        self.query_I_meas(channel=channel)

        print("")
        print(
            "  %-3s         %4.1f OVP     %4.2f OCP"
            % (
                ("ON" if self.state.ENA_output else "OFF"),
                self.state.OVP_level,
                self.state.OCP_level,
            )
        )
        print("  " + chr(0x2014) * 46)

        print(
            "  Source      %6.3f V     %6.4f A"
            % (self.state.V_source, self.state.I_source)
        )
        print("  " + chr(0x2014) * 46)
        print(
            "  Measure     %6.3f V     %6.4f A     %6.3f W"
            % (self.state.V_meas, self.state.I_meas, self.state.P_meas)
        )


# ------------------------------------------------------------------------------
#   Main: Will show a demo when run from the terminal
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Serial number of the Aim TTi PSU to connect to.
    # Set to '' or None to connect to any Aim TTi PSU.
    # SERIAL_PSU = "527254"
    SERIAL_PSU = None

    # Path to the config textfile containing the (last used) RS232 port
    PATH_CONFIG = "config/port_Aim_TTi_PSU.txt"

    # Create connection to Aim TTi PSU over RS232
    psu = Aim_TTi_PSU(connect_to_serial_number=SERIAL_PSU)

    if psu.auto_connect(PATH_CONFIG):
        psu.begin()  # Retrieve necessary parameters
        print("  IDN: %s" % psu.idn_str)

    psu.report()
    psu.close()

    sys.exit(0)
