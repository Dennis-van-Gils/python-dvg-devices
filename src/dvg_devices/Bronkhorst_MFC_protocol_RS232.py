#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RS232 function library for Bronkhorst mass flow controllers (MFC) using the
FLOW-BUS protocol.

Only the ASCII version is supported, not the enhanced binary version. This
library sends and receives messages to/from all nodes (code 80), hence just one
MFC is assumed per port.

When this module is directly run from the terminal a demo will be shown.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "02-07-2020"  # 0.0.1 was stamped 25-07-2018
__version__ = "0.0.3"  # 0.0.1 corresponds to prototype 1.0.0

import sys
import serial
import serial.tools.list_ports
import struct
from pathlib import Path

from dvg_debug_functions import print_fancy_traceback as pft

# Serial settings
RS232_BAUDRATE = 38400      # Baudrate according to the manual
RS232_TIMEOUT  = 0.1        # [sec]

class Bronkhorst_MFC():
    class State():
        # Container for the process and measurement variables
        setpoint  = None        # Setpoint read out of the MFC    [ln/min]
        flow_rate = None        # Flow rate measured by the MFC   [ln/min]

    # --------------------------------------------------------------------------
    #   __init__
    # --------------------------------------------------------------------------

    def __init__(self, name='MFC'):
        self.ser = None                 # serial.Serial device instance
        self.name = name
        self.serial_str = None          # Serial number of the MFC
        self.model_str  = None          # Model of the MFC
        self.fluid_name = None          # Fluid for which the MFC is calibrated
        self.max_flow_rate = None       # Max. capacity [ln/min]

        # Is the connection to the device alive?
        self.is_alive = False

        # Container for the process and measurement variables
        self.state = self.State()

    # --------------------------------------------------------------------------
    #   close
    # --------------------------------------------------------------------------

    def close(self):
        if not self.is_alive:
            pass    # Remain silent
        else:
            self.ser.close()
            self.is_alive = False

    # --------------------------------------------------------------------------
    #   connect_at_port
    # --------------------------------------------------------------------------

    def connect_at_port(self, port_str, match_serial_str=None,
                        print_trying_message=True):
        """Open the port at address 'port_str' and try to establish a
        connection. A query for the Bronkhorst serial number is send over the
        port. If it gives the proper response (and optionally has a matching
        serial number) it must be the Bronkhorst MFC we're looking for.

        Args:
            port_str (str): Serial port address to open
            match_serial_str (str, optional): Serial string of the MFC to
                establish a connection to. When empty or None then any MFC is
                accepted. Defaults to None.
            print_trying_message (bool, optional): When True then a 'trying to
                open' message is printed to the terminal. Defaults to True.

        Returns: True if successful, False otherwise.
        """
        self.is_alive = False

        if match_serial_str == '': match_serial_str = None
        if print_trying_message:
            if match_serial_str is None:
                print("Connect to: Bronkhorst MFC")
            else:
                print("Connect to: Bronkhorst MFC, serial %s" %
                      match_serial_str)

        print("  @ %-5s: " % port_str, end='')
        try:
            # Open the serial port
            self.ser = serial.Serial(port=port_str,
                                     baudrate=RS232_BAUDRATE,
                                     timeout=RS232_TIMEOUT,
                                     write_timeout=RS232_TIMEOUT)
        except serial.SerialException:
            print("Could not open port")
            return False
        except:
            raise

        try:
            # Query the serial number string.
            # NOTE: this function can finish okay and return False as indication
            # that the device on the serial port gives /a/ reply but it is not a
            # proper reply you would except from a Bronkhorst MFC. In other
            # words: the device replies but it is not a Bronkhorst MFC.
            self.is_alive = True
            success = self.query_serial_str()
        except:
            print("Communication error")
            if self.ser is not None: self.ser.close()
            self.is_alive = False
            return False

        if success:
            print("serial %s: " % self.serial_str, end='')
            if match_serial_str is None:
                # Found any Bronkhorst MFC device
                print("Success!\n")
                self.is_alive = True
                return True
            elif self.serial_str.lower() == match_serial_str.lower():
                # Found the Bronkhorst MFC with matching serial
                print("Success!\n")
                self.is_alive = True
                return True

        print("Wrong or no device")
        if self.ser is not None: self.ser.close()
        self.is_alive = False
        return False

    # --------------------------------------------------------------------------
    #   scan_ports
    # --------------------------------------------------------------------------

    def scan_ports(self, match_serial_str=None):
        """Scan over all serial ports and try to establish a connection. A query
        for the Bronkhorst serial number is send over all ports. The port that
        gives the proper response (and optionally has a matching serial number)
        must be the Bronkhorst MFC we're looking for.

        Args:
            match_serial_str (str, optional): Serial string of the MFC to
                establish a connection to. When empty or None then any MFC is
                accepted. Defaults to None.

        Returns: True if successful, False otherwise.
        """
        if match_serial_str == '': match_serial_str = None
        if match_serial_str is None:
            print("Scanning ports for any Bronkhorst MFC")
        else:
            print(("Scanning ports for a Bronkhorst MFC with\n"
                   "serial number '%s'") % match_serial_str)

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

        Query the model, fluid and the maximum mass flow rate of the MFC
        and store these in the class member 'state's. The max flow rate is
        mandatory to be known, because it is used to set and read the setpoint,
        and to read the flow rate.

        Returns: True if successful, False otherwise.
        """
        success = False
        success &= self.query_model_str()
        success &= self.query_fluid_name()
        success &= self.query_max_flow_rate()
        success &= self.query_setpoint()
        success &= self.query_flow_rate()
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
            print("ERROR: Device is not connected yet or already closed.")
        else:
            try:
                # Send command string to the device as bytes
                self.ser.write(msg_str.replace(' ', '').encode())
            except (serial.SerialTimeoutException,
                    serial.SerialException) as err:
                # Print error and struggle on
                pft(err, 3)
            except:
                raise
            else:
                try:
                    # Read all bytes in the line that is terminated with a
                    # newline character or until time-out has occured
                    ans_bytes = self.ser.readline()
                except (serial.SerialTimeoutException,
                        serial.SerialException) as err:
                    pft(err, 3)
                except:
                    raise
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
        [success, ans] = self.query(":07 80 04 71 63 71 63 00\r\n")
        if success and ans[3:13] == "8002716300":
            self.serial_str = bytearray.fromhex(ans[13:-2]).decode()
            return True
        else:
            self.serial_str = None
            return False

    # --------------------------------------------------------------------------
    #   query_model_str
    # --------------------------------------------------------------------------

    def query_model_str(self):
        """Query the model name of the MFC and store it in the class member 'state'.

        Returns: True if successful, False otherwise.
        """
        [success, ans] = self.query(":07 80 04 71 62 71 62 00\r\n")
        if success:
            self.model_str = bytearray.fromhex(ans[13:-2]).decode()
            return True
        else:
            self.model_str = None
            return False

    # --------------------------------------------------------------------------
    #   query_fluid_name
    # --------------------------------------------------------------------------

    def query_fluid_name(self):
        """Query the fluid name that the MFC is calibrated for and store it in
        the class member 'state'.

        Returns: True if successful, False otherwise.
        """
        [success, ans] = self.query(":07 80 04 01 71 01 71 0A\r\n")
        if success:
            self.fluid_name = bytearray.fromhex(ans[13:-2]).decode()
            return True
        else:
            self.fluid_name = None
            return False

    # --------------------------------------------------------------------------
    #   query_max_flow_rate
    # --------------------------------------------------------------------------

    def query_max_flow_rate(self):
        """Query the maximum mass flow rate in [ln/min] of the MFC and store it
        in the class member 'state'. This value is mandatory to be known, because it is
        used to set and read the setpoint, and to read the flow rate.

        Returns: True if successful, False otherwise.
        """
        [success, ans] = self.query(":06 80 04 01 4D 01 4D\r\n")
        if success:
            self.max_flow_rate = hex_to_32bit_IEEE754_float(ans[11:])
            return True
        else:
            self.max_flow_rate = None
            return False

    # --------------------------------------------------------------------------
    #   query_setpoint
    # --------------------------------------------------------------------------

    def query_setpoint(self):
        """Query the mass flow rate setpoint in [ln/min] set at the MFC and
        store it in the class member 'state' 'state'. Will be set to None if
        unsuccessful.

        Returns: True if successful, False otherwise.
        """
        [success, ans] = self.query(":06 80 04 01 21 01 21\r\n")
        if success:
            try:
                num = int(ans[-4:], 16)
            except ValueError:
                pass
            else:
                self.state.setpoint = num / 32000.0 * self.max_flow_rate
                return True

        self.state.setpoint = None
        return False

    # --------------------------------------------------------------------------
    #   query_flow_rate
    # --------------------------------------------------------------------------

    def query_flow_rate(self):
        """Query the mass flow rate in [ln/min] measured by the MFC and
        store it in the class member 'state'. Will be set to None if
        unsuccessful.

        Returns: True if successful, False otherwise.
        """
        [success, ans] = self.query(":06 80 04 01 21 01 20\r\n")
        if success:
            try:
                num = int(ans[-4:], 16)
            except ValueError:
                pass
            else:
                self.state.flow_rate = num / 32000.0 * self.max_flow_rate
                return True

        self.state.flow_rate = None
        return False

    # --------------------------------------------------------------------------
    #   send_setpoint
    # --------------------------------------------------------------------------

    def send_setpoint(self, setpoint):
        """Send a new mass flow rate setpoint in [ln/min] to the MFC.

        Args:
            setpoint (float): mass flow rate in [ln/min].

        Returns: True if successful, False otherwise.
        """
        try:
            setpoint = float(setpoint)
        except (TypeError, ValueError):
            setpoint = 0.0

        # Transform setpoint and limit
        setpoint = int(setpoint / self.max_flow_rate * 32000)
        setpoint = max(0, min(setpoint, 32000))

        [success, ans] = self.query(":06 80 01 01 21 %04x \r\n" % setpoint)
        if success and ans[5:].strip() == "000005":  # Also check status reply
            return True
        else:
            return False

# ------------------------------------------------------------------------------
#   hex_to_32bit_IEEE754_float
# ------------------------------------------------------------------------------

def hex_to_32bit_IEEE754_float(hex_str):
    """Transform a string containing a hexidecimal representation of a 32-bits
    IEEE754-formatted float value to a float
    """
    return (struct.unpack('f', struct.pack('i', int(hex_str, 16))))[0]

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
                pass    # Do not panic and remain silent

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
                pass    # Do not panic and remain silent

        try:
            # Write the config file
            filepath.write_text(port_str)
        except:
            pass        # Do not panic and remain silent
        else:
            return True

    return False

# ------------------------------------------------------------------------------
#   Main: Will show a demo when run from the terminal
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import time

    # Serial number of the Bronkhorst MFC to connect to.
    # Set to '' or None to connect to any Bronkhorst MFC.
    #SERIAL_MFC = "M16216843A"
    SERIAL_MFC = None

    # Path to the config textfile containing the (last used) RS232 port
    PATH_CONFIG = Path("config/port_Bronkhorst_MFC_1.txt")

    # Create connection to Bronkhorst MFC over RS232
    mfc = Bronkhorst_MFC()

    if mfc.auto_connect(PATH_CONFIG, SERIAL_MFC):
        mfc.begin()     # Retrieve necessary parameters
        print("  Serial  : %s" % mfc.serial_str)
        print("  Model   : %s" % mfc.model_str)
        print("  Fluid   : %s" % mfc.fluid_name)
        print("  Capacity: %.2f ln/min" % mfc.max_flow_rate)
    else:
        time.sleep(1)
        sys.exit(0)

    if os.name == "nt":
        import msvcrt
        running_Windows = True
        print("\nPress Q to quit.")
        print("Press S to enter new setpoint.")
    else:
        running_Windows = False
        print("\nPress Control + C to quit.")
        print("No other keyboard input possible because OS is not Windows.")

    # Prepare
    send_setpoint = 0.0
    do_send_setpoint = False

    mfc.query_setpoint()
    print("\nSetpoint       : %6.2f ln/min" % mfc.state.setpoint)

    # Loop
    done = False
    while not done:
        # Check if a new setpoint has to be send
        if do_send_setpoint:
            mfc.send_setpoint(send_setpoint)
            mfc.query_setpoint()
            print("\nSetpoint       : %6.2f ln/min" % mfc.state.setpoint)
            do_send_setpoint = False

        # Measure and report the flow rate
        mfc.query_flow_rate()
        print("\rMeas. flow rate: %6.2f ln/min" % mfc.state.flow_rate, end='')
        sys.stdout.flush()

        # Process keyboard input
        if running_Windows:
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b'q':
                    print("\nAre you sure you want to quit [y/n]?")
                    if msvcrt.getch() == b'y':
                        print("Quitting.")
                        done = True
                    else:
                        do_send_setpoint = True  # Esthestics
                elif key == b's':
                    send_setpoint = input("\nEnter new setpoint [ln/min]: ")
                    do_send_setpoint = True

        # Slow down update period
        time.sleep(0.02)

    mfc.ser.close()
    time.sleep(1)
