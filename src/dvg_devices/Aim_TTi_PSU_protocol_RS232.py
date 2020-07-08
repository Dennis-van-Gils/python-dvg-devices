#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RS232 function library for an Aim TTi power supply unit (PSU), QL series II.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "08-07-2020"
__version__ = "0.0.5"
# pylint: disable=bare-except, broad-except, try-except-raise

import sys
import struct
from pathlib import Path

import serial
import serial.tools.list_ports
import numpy as np

from dvg_debug_functions import print_fancy_traceback as pft

# Serial settings
RS232_TIMEOUT = 0.1  # [sec]
TERM_CHAR = "\r\n"


class Aim_TTi_PSU:
    class State:
        """Container for the process and measurement variables.
        [numpy.nan] values indicate that the parameter is not initialized or
        that the last query was unsuccessful in communication.
        """

        # fmt: off
        V_source = 0        # Voltage to be sourced [V]
        I_source = 0        # Current to be sourced [A]
        P_source = 0        # Power to be sourced, when PID controller is on [W]
        ENA_PID = False     # Is the PID controller on the power ouput enabled?

        V_meas = np.nan         # Measured output voltage [V]
        I_meas = np.nan         # Measured output current [A]
        P_meas = np.nan         # Derived output power    [W]

        OVP_level  = np.nan     # Over-voltage protection level [V]
        ENA_OCP    = False      # Is over-current protection enabled?
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
        V_source  = 120         # Voltage to be sourced [V]
        I_source  = 1           # Current to be sourced [A]
        P_source  = 0           # Power   to be sourced [W]
        OVP_level = 126         # Over-voltage protection level [V]
        ENA_OCP   = True        # Is over-current protection enabled?
        # fmt: on

    # --------------------------------------------------------------------------
    #   __init__
    # --------------------------------------------------------------------------

    def __init__(self, name="PSU"):
        self.ser = None  # serial.Serial device instance
        self.name = name
        self.idn = None  # The identity of the device ("*IDN?")
        self.serial_str = None  # Serial number of the device
        self.model_str = None  # Model of the device

        # Is the connection to the device alive?
        self.is_alive = False

        # Container for the process and measurement variables
        self.state = self.State()
        self.config = self.Config()

    # --------------------------------------------------------------------------
    #   close
    # --------------------------------------------------------------------------

    def close(self, ignore_exceptions=False):
        """Close the serial port
        """
        if self.ser is not None:
            try:
                self.ser.close()
            except:
                if ignore_exceptions:
                    pass
                else:
                    raise

        self.is_alive = False

    # --------------------------------------------------------------------------
    #   connect_at_port
    # --------------------------------------------------------------------------

    def connect_at_port(
        self, port_str, match_serial_str=None, print_trying_message=True
    ):
        """Open the port at address 'port_str' and try to establish a
        connection. A query for the serial number is send over the port. If it
        gives the proper response (and optionally has a matching serial number)
        it must be the Aim TTi PSU we're looking for.

        Args:
            port_str (str): Serial port address to open
            match_serial_str (str, optional): Serial string of the device to
                establish a connection to. When empty or None then any Aim TTi
                PSU is accepted. Defaults to None.
            print_trying_message (bool, optional): When True then a 'trying to
                open' message is printed to the terminal. Defaults to True.

        Returns: True if successful, False otherwise.
        """
        self.is_alive = False

        if match_serial_str == "":
            match_serial_str = None
        if print_trying_message:
            if match_serial_str is None:
                print("Connect to: Aim TTi PSU")
            else:
                print("Connect to: Aim TTi PSU, serial %s" % match_serial_str)

        print("  @ %-5s: " % port_str, end="")
        try:
            # Open the serial port
            self.ser = serial.Serial(
                port=port_str,
                baudrate=9600,  # baudrate gets ignored
                timeout=RS232_TIMEOUT,
                write_timeout=RS232_TIMEOUT,
            )
        except serial.SerialException:
            print("Could not open port")
            return False
        except:
            raise

        try:
            # Query the serial number string.
            # NOTE: this function can finish okay and return False as indication
            # that the device on the serial port gives /a/ reply but it is not a
            # proper reply you would except from a Aim TTi PSU. In other
            # words: the device replies but it is not a Aim TTi PSU.
            self.is_alive = True
            success = self.query_serial_str()
        except:
            print("Communication error")
            if self.ser is not None:
                self.ser.close()
            self.is_alive = False
            return False

        if success:
            print("serial %s: " % self.serial_str, end="")
            if match_serial_str is None:
                # Found any Aim TTi device
                print("Success!\n")
                self.is_alive = True
                return True
            elif self.serial_str.lower() == match_serial_str.lower():
                # Found the Aim TTi device with matching serial
                print("Success!\n")
                self.is_alive = True
                return True

        print("Wrong or no device")
        if self.ser is not None:
            self.ser.close()
        self.is_alive = False
        return False

    # --------------------------------------------------------------------------
    #   scan_ports
    # --------------------------------------------------------------------------

    def scan_ports(self, match_serial_str=None):
        """Scan over all serial ports and try to establish a connection. A query
        for the device serial number is send over all ports. The port that gives
        the proper response (and optionally has a matching serial number) must
        be the Aim TTi PSU we're looking for.

        Args:
            match_serial_str (str, optional): Serial string of the Aim TTi PSU
                to establish a connection to. When empty or None then any
                Aim TTi PSU is accepted. Defaults to None.

        Returns: True if successful, False otherwise.
        """
        if match_serial_str == "":
            match_serial_str = None
        if match_serial_str is None:
            print("Scanning ports for any Aim TTi PSU")
        else:
            print(
                ("Scanning ports for a Aim TTi PSU with\n" "serial number '%s'")
                % match_serial_str
            )

        # Ports is a list of tuples
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            port_str = p[0]
            if self.connect_at_port(port_str, match_serial_str, False):
                return True
            else:
                continue

        # Scanned over all the ports without finding a match
        print("\n  ERROR: Device not found")
        return False

    # --------------------------------------------------------------------------
    #   auto_connect
    # --------------------------------------------------------------------------

    def auto_connect(self, path_config, match_serial_str=None):
        """TO DO: write explaination
        """
        # Try to open the config file containing the port to open. Do not panic
        # if the file does not exist or cannot be read. We will then scan over
        # all ports as alternative.
        port_str = read_port_config_file(path_config)

        # If the config file was read successfully then we can try to open the
        # port listed in the config file and connect to the device.
        if port_str is not None:
            success = self.connect_at_port(port_str, match_serial_str)
        else:
            success = False

        # Check if we failed establishing a connection
        if not success:
            # Now scan over all ports and try to connect to the device
            success = self.scan_ports(match_serial_str)
            if success:
                # Store the result of a successful connection after a port scan
                # in the config file. Do not panic if we cannot create the
                # config file.
                write_port_config_file(path_config, self.ser.portstr)

        return success

    # --------------------------------------------------------------------------
    #   begin
    # --------------------------------------------------------------------------

    def begin(self):
        """This function should run directly after having established a
        connection to the device.

        Returns: True if successful, False otherwise.
        """
        success = False

        return success

    # --------------------------------------------------------------------------
    #   query
    # --------------------------------------------------------------------------

    def query(self, msg_str):
        """Send a command to the serial device and subsequently read the reply.

        Args:
            msg_str (str): Message to be sent to the serial device.

        Returns:
            success (bool): True if successful, False otherwise.
            ans_str (str): Reply received from the device. None if unsuccessful.
        """
        success = False
        ans_str = None

        if not self.is_alive:
            pft("Device is not connected yet or already closed.", 3)
            return [success, ans_str]

        try:
            # Send command string to the device as bytes
            self.ser.write((msg_str + TERM_CHAR).encode())
        except (serial.SerialTimeoutException, serial.SerialException,) as err:
            # Print error and struggle on
            pft(err, 3)
        except Exception as err:
            pft(err, 3)
            sys.exit(0)
        else:
            try:
                ans_bytes = self.ser.read_until(TERM_CHAR.encode())
            except (
                serial.SerialTimeoutException,
                serial.SerialException,
            ) as err:
                pft(err, 3)
            except Exception as err:
                pft(err, 3)
                sys.exit(0)
            else:
                # Convert bytes into string and remove termination chars and
                # spaces
                ans_str = ans_bytes.decode().strip()
                success = True

        return [success, ans_str]

    # --------------------------------------------------------------------------
    #   query_serial_str
    # --------------------------------------------------------------------------

    def query_serial_str(self):
        """Query the serial number and store it in the class member 'serial_str'

        Returns: True if successful, False otherwise.
        """
        [success, ans] = self.query("*idn?")
        if success and ans[:19] == "THURLBY THANDAR, QL":
            self.idn = ans
            self.serial_str = ans.split(",")[2].strip()
            self.model_str = ans.split(",")[1].strip()
            return True
        else:
            self.idn = None
            self.serial_str = None
            self.model_str = None
            return False


# -----------------------------------------------------------------------------
#   read_port_config_file
# -----------------------------------------------------------------------------


def read_port_config_file(filepath):
    """Try to open the config textfile containing the port to open. Do not panic
    if the file does not exist or cannot be read.

    Args:
        filepath (pathlib.Path): path to the config file,
            e.g. Path("config/port.txt")

    Returns: The port name string when the config file is read out successfully,
        None otherwise.
    """
    if isinstance(filepath, Path):
        if filepath.is_file():
            try:
                with filepath.open() as f:
                    port_str = f.readline().strip()
                return port_str
            except:
                pass  # Do not panic and remain silent

    return None


# -----------------------------------------------------------------------------
#   write_port_config_file
# -----------------------------------------------------------------------------


def write_port_config_file(filepath, port_str):
    """Try to write the port name string to the config textfile. Do not panic if
    the file cannot be created.

    Args:
        filepath (pathlib.Path): path to the config file,
            e.g. Path("config/port.txt")
        port_str (string): COM port string to save to file
    Returns: True when successful, False otherwise.
    """
    if isinstance(filepath, Path):
        if not filepath.parent.is_dir():
            # Subfolder does not exists yet. Create.
            try:
                filepath.parent.mkdir()
            except:
                pass  # Do not panic and remain silent

        try:
            # Write the config file
            filepath.write_text(port_str)
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

    # Path to the config textfile containing the (last used) RS232 port
    PATH_CONFIG = Path("config/port_Aim_TTi_PSU.txt")

    # Create connection to Aim TTi PSU over RS232
    psu = Aim_TTi_PSU()

    if psu.auto_connect(PATH_CONFIG, SERIAL_PSU):
        # mfc.begin()  # Retrieve necessary parameters
        print("  Serial: %s" % psu.serial_str)
        print("  Model : %s" % psu.model_str)
        psu.close()

    sys.exit(0)
