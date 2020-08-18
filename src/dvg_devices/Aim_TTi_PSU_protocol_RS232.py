#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RS232 function library for an Aim TTi power supply unit (PSU), QL series II.

Note:
    * Only one channel implemented (channel 1)
    * Limited error reporting
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "18-08-2020"
__version__ = "0.2.1"
# pylint: disable=bare-except, broad-except, try-except-raise

import os
import sys
import time
from typing import AnyStr
from pathlib import Path

import numpy as np

from dvg_debug_functions import print_fancy_traceback as pft
from dvg_devices.BaseDevice import SerialDevice


class Aim_TTi_PSU(SerialDevice):
    class State:
        """Container for the process and measurement variables.
        """

        # fmt: off
        V_source = 0            # Voltage to be sourced         [V]
        I_source = 0            # Current to be sourced (limit) [A]

        V_meas = np.nan         # Measured output voltage [V]
        I_meas = np.nan         # Measured output current [A]
        P_meas = np.nan         # Derived output power    [W]

        OVP_level  = np.nan     # Over-voltage protection level [V]
        OCP_level  = np.nan     # Over-current protection level [A]
        ENA_output = False      # Is power output enabled (by software)?

        # Limit Event Status Register (LSR)
        LSR_is_tripped = False    # True if any LSR tripped, ignoring mode
        LSR_TRIP_AUX = False      # Aux output trip                   , bit 7
        LSR_MODE_AUX_CC = False   # Aux output constant-current mode  , bit 6
        LSR_TRIP_SENSE = False    # Sense trip                        , bit 5
        LSR_TRIP_OTP = False      # Over-temperature trip             , bit 4
        LSR_TRIP_OCP = False      # Over-current trip                 , bit 3
        LSR_TRIP_OVP = False      # Over-voltage trip                 , bit 2
        LSR_MODE_CC = False       # Constant-current mode             , bit 1
        LSR_MODE_CV = False       # Constant-voltage mode             , bit 0
        # fmt: on

    class Config:
        # fmt: off
        V_source  = 10   # Voltage to be sourced         [V]
        I_source  = 0.5  # Current to be sourced (limit) [A]
        OVP_level = 12   # Over-voltage protection level [V]
        OCP_level = 1    # Over-current protection level [A]
        # fmt: on

    # --------------------------------------------------------------------------
    #   __init__
    # --------------------------------------------------------------------------

    def __init__(
        self,
        name: str = "PSU",
        long_name: str = "Aim TTi power supply",
        path_config: str = (os.getcwd() + "/config/settings_Aim_TTi_PSU.txt"),
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

        # Location of the configuration file
        self.path_config = Path(path_config)

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
        success = self.query_IDN()
        return (success, self.serial_str)

    # --------------------------------------------------------------------------
    #   begin
    # --------------------------------------------------------------------------

    def begin(self):
        """This function should run directly after having established a
        connection to the device.

        Returns: True if successful, False otherwise.
        """
        if not self.is_alive:
            print("ERROR: Device is not connected yet or already closed.")
            return False

        success = self.set_LSE(value=255)  # Report on all trips and modes
        success &= self.query_OVP_level()
        success &= self.query_OCP_level()
        success &= self.query_V_source()
        success &= self.query_I_source()
        success &= self.query_LSR()

        return success

    # --------------------------------------------------------------------------
    #   reinitialize
    # --------------------------------------------------------------------------

    def reinitialize(self):
        """Reinitialize the PSU, including clear and reset

        Returns: True if all messages were sent and received successfully,
            False otherwise.
        """

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

        success &= self.set_LSE(value=255)  # Report on all trips and modes
        success &= self.query_OVP_level()
        success &= self.query_OCP_level()
        success &= self.query_V_source()
        success &= self.query_I_source()
        success &= self.query_LSR()

        return success

    # --------------------------------------------------------------------------
    #   query_IDN
    # --------------------------------------------------------------------------

    def query_IDN(self) -> bool:
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
        """Query and parse the Limit Event Status Register (LSR). This holds
        the protection trips and output modes.

        Returns: True if successful, False otherwise.
        """
        # We will ignore the first read-out, because it apparently always lags
        # one behind.
        self.query("LSR%d?" % channel)

        success, reply = self.query("LSR%d?" % channel)
        if success:
            # fmt: off
            status_code = int(reply)
            self.state.LSR_TRIP_AUX    = bool(status_code & 128)
            self.state.LSR_MODE_AUX_CC = bool(status_code & 64)
            self.state.LSR_TRIP_SENSE  = bool(status_code & 32)
            self.state.LSR_TRIP_OTP    = bool(status_code & 16)
            self.state.LSR_TRIP_OCP    = bool(status_code & 8)
            self.state.LSR_TRIP_OVP    = bool(status_code & 4)
            self.state.LSR_MODE_CC     = bool(status_code & 2)
            self.state.LSR_MODE_CV     = bool(status_code & 1)

            self.state.LSR_is_tripped = (
                self.state.LSR_TRIP_AUX
                or self.state.LSR_TRIP_SENSE
                or self.state.LSR_TRIP_OTP
                or self.state.LSR_TRIP_OCP
                or self.state.LSR_TRIP_OVP
            )

            if verbose:
                if self.state.LSR_TRIP_AUX    : print("  AUX TRIP")
                if self.state.LSR_MODE_AUX_CC : print("  AUX CC mode")
                if self.state.LSR_TRIP_SENSE  : print("  SENSE TRIP")
                if self.state.LSR_TRIP_OTP    : print("  OVER-TEMPERATURE TRIP")
                if self.state.LSR_TRIP_OCP    : print("  OVER-CURRENT TRIP")
                if self.state.LSR_TRIP_OVP    : print("  OVER-VOLTAGE TRIP")
                if self.state.LSR_MODE_CC     : print("  CC mode")
                if self.state.LSR_MODE_CV     : print("  CV mode")
            # fmt: on

        return success

    # --------------------------------------------------------------------------
    #   Protection related
    # --------------------------------------------------------------------------

    def reset_trips(self) -> bool:
        """Attempt to clear all trip conditions from all outputs.

        Returns: True if successful, False otherwise.
        """
        return self.write_and_wait_for_opc("triprst")

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

    def reset_trips_and_turn_on(self, channel: int = 1) -> bool:
        """Returns: True if the message was sent successfully, False otherwise.
        """
        if self.write_and_wait_for_opc("triprst;*opc;OP%d 1" % channel):
            self.state.ENA_output = True
            return True

        return False

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

    # --------------------------------------------------------------------------
    #   read_config_file
    # --------------------------------------------------------------------------

    def read_config_file(self):
        """Try to open the config textfile containing:
            * V_source   # Voltage to be sourced         [V]
            * I_source   # Current to be sourced (limit) [A]
            * OVP_level  # Over-voltage protection level [V]
            * OCP_level  # Over-current protection level [A]
        Do not panic if the file does not exist or cannot be read.

        Returns: True if successful, False otherwise.
        """
        if self.path_config.is_file():
            try:
                with self.path_config.open() as f:
                    self.config.V_source = float(f.readline().strip())
                    self.config.I_source = float(f.readline().strip())
                    self.config.OVP_level = float(f.readline().strip())
                    self.config.OCP_level = float(f.readline().strip())

                return True
            except:
                pass  # Do not panic and remain silent

        return False

    # --------------------------------------------------------------------------
    #   write_config_file
    # --------------------------------------------------------------------------

    def write_config_file(self):
        """Try to write the config textfile containing:
             * V_source   # Voltage to be sourced         [V]
             * I_source   # Current to be sourced (limit) [A]
             * OVP_level  # Over-voltage protection level [V]
             * OCP_level  # Over-current protection level [A]
        Do not panic if the file does not exist or cannot be read.

        Returns: True if successful, False otherwise.
        """

        if not self.path_config.parent.is_dir():
            # Subfolder does not exists yet. Create.
            try:
                self.path_config.parent.mkdir()
            except:
                pass  # Do not panic and remain silent

        try:
            # Write the config file
            self.path_config.write_text(
                "%.3f\n%.3f\n%.1f\n%.2f"
                % (
                    self.state.V_source,
                    self.state.I_source,
                    self.state.OVP_level,
                    self.state.OCP_level,
                )
            )
        except:
            pass  # Do not panic and remain silent
        else:
            return True

        return False


# ------------------------------------------------------------------------------
#   Main: Will show a demo when run from the terminal
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    # Serial number of the Aim TTi PSU to connect to.
    # Set to '' or None to connect to any Aim TTi PSU.
    # SERIAL_PSU = "527254"
    SERIAL_PSU = None

    # Path to the textfile containing the (last used) RS232 port
    PATH_PORT = "config/port_Aim_TTi_PSU.txt"

    # Create connection to Aim TTi PSU over RS232
    psu = Aim_TTi_PSU(connect_to_serial_number=SERIAL_PSU)

    if psu.auto_connect(PATH_PORT):
        psu.begin()  # Retrieve necessary parameters
        print("  IDN: %s" % psu.idn_str)

        psu.report()
        psu.close()

    sys.exit(0)
