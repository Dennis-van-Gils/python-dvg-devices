#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RS232 function library for an Aim TTi power supply unit (PSU), QL series II.

! NOT FUNCTIONING YET
! WORK IN PROGRESS

"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "20-07-2020"
__version__ = "0.2.1"
# pylint: disable=bare-except, broad-except, try-except-raise

import sys
import numpy as np

from dvg_debug_functions import print_fancy_traceback as pft
from dvg_devices.BaseDevice import SerialDevice


class Aim_TTi_PSU(SerialDevice):
    class State:
        """Container for the process and measurement variables.
        [numpy.nan] values indicate that the parameter is not initialized or
        that the last query was unsuccessful in communication.
        """

        # fmt: off
        V_source = 0        # Voltage to be sourced [V]
        I_limit = 0         # Current limit         [A]
        P_source = 0        # Power to be sourced, when PID controller is on [W]
        ENA_PID = False     # Is the PID controller on the power ouput enabled?

        V_meas = np.nan         # Measured output voltage [V]
        I_meas = np.nan         # Measured output current [A]
        P_meas = np.nan         # Derived output power    [W]

        OVP_level  = np.nan     # Over-voltage protection level [V]
        OCP_level  = np.nan     # Over-current protection level [A]
        ENA_output = False      # Is power output enabled (by software)?
        # fmt: on

        # The error string retreived from the error queue of the device. None
        # indicates no error is left in the queue.
        error = None

        # This list of strings is provided to be able to store all errors from
        # the device queue. This list is populated by calling 'query_error'
        # until no error is left in the queue. This list can then be printed to
        # screen or GUI and the user should 'acknowledge' the list, after which
        # the list can be emptied (=[]) again.
        all_errors = []

        # Questionable condition status registers
        # fmt: off
        status_QC_OV  = False   # Output disabled by over-voltage protection
        status_QC_OC  = False   # Output disabled by over-current protection
        status_QC_PF  = False   # Output disabled because AC power failed
        status_QC_OT  = False   # Output disabled by over-temperature protection
        status_QC_INH = False   # Output turned off by external J1 inhibit signal (ENABLE)
        status_QC_UNR = False   # The output is unregulated

        # Operation condition status registers
        status_OC_WTG = False   # Unit waiting for transient trigger
        status_OC_CV  = False   # Output in constant voltage
        status_OC_CC  = False   # Output in constant current
        # fmt: on

    class Config:
        # fmt: off
        V_source  = 10          # Voltage to be sourced [V]
        I_limit   = 0.5         # Current limit         [A]
        P_source  = 0           # Power   to be sourced [W]
        OVP_level = 12          # Over-voltage protection level [V]
        OCP_level = 1           # Over-current protection level [A]
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
            "timeout": 0.1,
            "write_timeout": 0.1,
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
        self.state.error = None
        self.state.all_errors = []

        if not self.is_alive:
            print("ERROR: Device is not connected yet or already closed.")
            return False

        # Set the appropiate status bits to enable reporting of 'limits'
        # and 'trips':
        #   bit 7: aux output trip
        #   bit 6: aux output current limit
        #   bit 5: output sense trip
        #   bit 4: output thermal trip
        #   bit 3: output over-current trip
        #   bit 2: output over-voltage trip
        #   bit 1: output enters CC mode
        #   bit 0: output enters CV mode           <--- We'll ignore this one
        success = self.set_LSE(1, 254)
        success = self.set_LSE(2, 254)

        success &= self.query_V_source()
        success &= self.query_I_limit()
        success &= self.query_OVP_level()
        success &= self.query_OCP_level()
        # success &= self.query_status_QC()
        # success &= self.query_status_OC()

        # self.query_all_errors_in_queue()

        # self.wait_for_OPC_indefinitely()         # COMMENTED OUT: .stb fails intermittently, perhaps due to the USB isolator
        # self.wait_for_OPC()

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
        else:
            self.idn_str = None
            self.serial_str = None
            self.model_str = None
            return False

    # --------------------------------------------------------------------------
    #   System status related
    # --------------------------------------------------------------------------

    def set_LSE(self, value: int, channel: int = 1) -> bool:
        """Set the value of the Limit Status Enable (LSE) register.

        Returns:
            True if successful, False otherwise.
        """
        return self.write("LSE%d %d")

    # --------------------------------------------------------------------------
    #   Protection related
    # --------------------------------------------------------------------------

    def reset_trip(self) -> bool:
        """Attempt to clear all trip conditions from all outputs.

        Returns:
            True if successful, False otherwise.
        """
        return self.write("TRIPRST")

    def set_OVP_level(self, voltage_V, channel: int = 1) -> bool:
        """
        Returns:
            True if the message was sent successfully, False otherwise.
        """
        try:
            voltage_V = float(voltage_V)
        except (ValueError, TypeError):
            voltage_V = 0.0
        except:
            raise

        self.state.OVP_level = voltage_V
        return self.write("OVP%d %f" % (channel, voltage_V))

    def query_OVP_level(self, channel: int = 1) -> bool:
        """
        Returns:
            True if successful, False otherwise.
        """
        success, reply = self.query("OVP%d?" % channel)
        if success & (reply[:3] == "VP%d" % channel):
            self.state.OVP_level = float(reply[4:])
            return True

        return False

    def set_OCP_level(self, current_A, channel: int = 1) -> bool:
        """
        Returns:
            True if the message was sent successfully, False otherwise.
        """
        try:
            current_A = float(current_A)
        except (ValueError, TypeError):
            current_A = 0.0
        except:
            raise

        self.state.OCP_level = current_A
        return self.write("OCP%d %f" % (channel, current_A))

    def query_OCP_level(self, channel: int = 1) -> bool:
        """
        Returns:
            True if successful, False otherwise.
        """
        success, reply = self.query("OCP%d?" % channel)
        if success & (reply[:3] == "CP%d" % channel):
            self.state.OCP_level = float(reply[4:])
            return True

        return False

    # --------------------------------------------------------------------------
    #   Output related
    # --------------------------------------------------------------------------

    def turn_on(self, channel: int = 1) -> bool:
        """
        Returns: True if the message was sent successfully, False otherwise.
        """
        return self.set_ENA_output(ENA=True, channel=channel)

    def turn_off(self, channel: int = 1) -> bool:
        """
        Returns: True if the message was sent successfully, False otherwise.
        """
        return self.set_ENA_output(ENA=False, channel=channel)

    def set_ENA_output(self, ENA: bool, channel: int = 1) -> bool:
        """
        Returns: True if the message was sent successfully, False otherwise.
        """
        success = self.write("OP%d %d" % (channel, ENA))
        if success:
            self.state.ENA_output = ENA

        return success

    def query_ENA_output(self, channel: int = 1) -> bool:
        """
        Returns: True if the query was received successfully, False otherwise.
        """
        success, reply = self.query("OP%d?" % channel)
        if success:
            self.state.ENA_output = bool(int(reply))
        return success

    def set_V_source(self, voltage_V, channel: int = 1) -> bool:
        """
        Returns: True if the message was sent successfully, False otherwise.
        """
        try:
            voltage_V = float(voltage_V)
        except (ValueError, TypeError):
            voltage_V = 0.0
        except:
            raise

        self.state.V_source = voltage_V
        return self.write("V%d %.3f" % (channel, voltage_V))

    def query_V_source(self, channel: int = 1) -> bool:
        """
        Returns: True if the query was received successfully, False otherwise.
        """
        success, reply = self.query("V%d?" % channel)
        if success & (reply[:2] == "V%d" % channel):
            self.state.V_source = float(reply[3:])
            return True

        return False

    def query_V_meas(self, channel: int = 1) -> bool:
        """
        Returns: True if the query was received successfully, False otherwise.
        """
        success, reply = self.query("V%dO?" % channel)
        if success & (reply[-1:] == "V"):
            self.state.V_meas = float(reply[:-1])
            self.state.P_meas = self.state.I_meas * self.state.V_meas
            return True

        return False

    def set_I_limit(self, current_A, channel: int = 1) -> bool:
        """
        Returns: True if the message was sent successfully, False otherwise.
        """
        try:
            current_A = float(current_A)
        except (ValueError, TypeError):
            current_A = 0.0
        except:
            raise

        self.state.I_limit = current_A
        return self.write("I%d %.4f" % (channel, current_A))

    def query_I_limit(self, channel: int = 1) -> bool:
        """
        Returns: True if the query was received successfully, False otherwise.
        """
        success, reply = self.query("I%d?" % channel)
        if success & (reply[:2] == "I%d" % channel):
            self.state.I_limit = float(reply[3:])
            return True

        return False

    def query_I_meas(self, channel: int = 1) -> bool:
        """
        Returns: True if the query was received successfully, False otherwise.
        """
        success, reply = self.query("I%dO?" % channel)
        if success & (reply[-1:] == "A"):
            self.state.I_meas = float(reply[:-1])
            self.state.P_meas = self.state.I_meas * self.state.V_meas
            return True

        return False

    # --------------------------------------------------------------------------
    #   report
    # --------------------------------------------------------------------------

    def report(self, channel: int = 1):
        """Report to the terminal.
        """
        # print("\nQuestionable condition")
        # print(chr(0x2015) * 26)
        # self.query_status_QC(True)

        # print("\nOperation condition")
        # print(chr(0x2014) * 26)
        # self.query_status_OC(True)

        # print("\nError")
        # print(chr(0x2014) * 26)
        # self.query_error(True)
        # while not self.state.error is None:
        #    self.query_error(True)

        self.query_ENA_output(channel=channel)
        self.query_OVP_level(channel=channel)
        self.query_OCP_level(channel=channel)
        self.query_V_source(channel=channel)
        self.query_I_limit(channel=channel)
        self.query_V_meas(channel=channel)
        self.query_I_meas(channel=channel)

        print("\n  Ouput enabled?: %s" % self.state.ENA_output)
        print("  " + chr(0x2014) * 50)
        print(
            "  OVP level: %4.1f   [V]      OCP level: %4.2f   [A]"
            % (self.state.OVP_level, self.state.OCP_level)
        )
        print(
            "  V source : %6.3f [V]      I limit  : %6.4f [A]"
            % (self.state.V_source, self.state.I_limit)
        )
        print("  " + chr(0x2014) * 50)
        print(
            "  V meas   : %6.3f [V]      I meas   : %6.4f [A]"
            % (self.state.V_meas, self.state.I_meas)
        )
        print("  P meas   : %6.3f [W]" % self.state.P_meas)


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
