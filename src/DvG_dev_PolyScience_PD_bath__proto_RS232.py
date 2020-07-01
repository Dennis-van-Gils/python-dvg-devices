#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RS232 function library for PolyScience PD## recirculating baths.
Supported models:
    PD07R-20, PD07R-40, PD7LR-20, PD15R-30, PD15R-40, PD20R-30, PD28R-30,
    PD45R-20, PD07H200, PD15H200, PD20H200, PD28H200, PD15RCAL, PD15HCAL.
Tested on model PD15R-30‐A12E

Dennis_van_Gils
04-09-2018
"""

import serial
import serial.tools.list_ports
import numpy as np
from time import sleep
import sys

# Temperature setpoint limits in software, not on a hardware level
BATH_MIN_SETPOINT_DEG_C = 10     # [deg C]
BATH_MAX_SETPOINT_DEG_C = 87     # [deg C]

# Serial settings
RS232_BAUDRATE = 57600      # Baudrate according to the manual
RS232_TIMEOUT  = 0.5        # [sec]

# ------------------------------------------------------------------------------
#   Class PolyScience_bath
# ------------------------------------------------------------------------------

class PolyScience_bath():
    class State():
        # Container for the process and measurement variables
        setpoint = np.nan     # Setpoint read out of the bath              ['C]
        P1_temp  = np.nan     # Temperature measured by the bath           ['C]
        P2_temp  = np.nan     # Temperature measured by the external probe ['C]

    # --------------------------------------------------------------------------
    #   __init__
    # --------------------------------------------------------------------------

    def __init__(self):
        # serial.Serial device instance
        self.ser = None

        # Placeholder for a future mutex instance needed for proper
        # multithreading (e.g. instance of QtCore.Qmutex())
        self.mutex = None

        # Container for the process and measurement variables
        self.state = self.State()

    # --------------------------------------------------------------------------
    #   close
    # --------------------------------------------------------------------------

    def close(self):
        self.ser.close()

    # --------------------------------------------------------------------------
    #   _readline
    # --------------------------------------------------------------------------

    def _readline(self):
        """Custom method of [serial.Serial.readline] where the termination
        character is fixed to a single carriage return '\r' instead of a newline
        character '\n'.

        Returns: The byte array received from the serial-in buffer
        """

        eol = b'\r'
        leneol = len(eol)
        line = bytearray()
        timeout = serial.Timeout(self.ser.timeout)
        while True:
            c = self.ser.read(1)
            if c:
                line += c
                if line[-leneol:] == eol:
                    break
            else:
                break
            if timeout.expired():
                break
        return bytes(line)

    # --------------------------------------------------------------------------
    #   connect_at_port
    # --------------------------------------------------------------------------

    def connect_at_port(self, port_str, print_trying_message=True):
        """Open the port at address 'port_str' and try to establish a
        connection. A command is send to try to disable the command echo of the
        PolyScience bath ("SE0\r"). If it gives the proper response ("!\r")
        it must be a PolyScience bath.

        Args:
            port_str (str): Serial port address to open
            print_trying_message (bool, optional): When True then a 'trying to
                open' message is printed to the terminal. Defaults to True.

        Returns: True if successful, False otherwise.
        """
        if print_trying_message:
            print("Trying to connect to a PolyScience bath on")

        print("  %-5s: " % port_str, end='')
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
            sys.exit(0)

        try:
            # Disable the command echo of the PolyScience bath.
            # NOTE: this function can finish okay and return False as indication
            # that the device on the serial port gives /a/ reply but it is not a
            # proper reply you would except from a PolyScience bath. In other
            # words: the device replies but it is not a PolyScience bath.
            success = self.disable_command_echo()
        except:
            print("Communication error")
            if self.ser is not None: self.ser.close()
            success = False

        if success:
            # Found a PolyScience bath
            print("Success!\n")
            return True

        print("Wrong or no device")
        if self.ser is not None: self.ser.close()
        return False

    # --------------------------------------------------------------------------
    #   scan_ports
    # --------------------------------------------------------------------------

    def scan_ports(self):
        """Scan over all serial ports and try to establish a connection. A
        command is send to try to disable the command echo of the PolyScience
        bath ("SE0\r"). If it gives the proper response ("!\r") it must be a
        PolyScience bath.

        Returns: True if successful, False otherwise.
        """
        print("Scanning ports for any PolyScience bath")

        # Ports is a list of tuples
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            port_str = p[0]
            if self.connect_at_port(port_str, False):
                return True
            else:
                continue

        # Scanned over all the ports without finding a match
        print("\n  ERROR: Device not found")
        return False

    # --------------------------------------------------------------------------
    #   auto_connect
    # --------------------------------------------------------------------------

    def auto_connect(self, config_path):
        """TO DO: write explaination
        """
        # Try to open the config file containing the port to open. Do not panic
        # if the file does not exist or cannot be read. We will then scan over
        # all ports as alternative.
        port_str = read_port_config_file(config_path)

        # If the config file was read successfully then we can try to open the
        # port listed in the config file and connect to the device.
        if port_str is not None:
            success = self.connect_at_port(port_str)
        else:
            success = False

        # Check if we failed establishing a connection
        if not success:
            # Now scan over all ports and try to connect to the device
            success = self.scan_ports()
            if success:
                # Store the result of a successful connection after a port scan
                # in the config file. Do not panic if we cannot create the
                # config file.
                write_port_config_file(config_path, self.ser.portstr)

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

        try:
            # Send command string to the device as bytes
            self.ser.write(msg_str.replace(' ', '').encode())
        except serial.SerialTimeoutException:
            print("ERROR: serial.write() timed out in query()")
        except serial.SerialException:
            print("ERROR: serial.write() failed in query()")
        except:
            raise
            sys.exit(0)
        else:
            try:
                # Read all bytes in the line that is terminated with a carriage
                # return character or until time-out has occured
                #sleep(.1)  # DEBUG
                ans_bytes = self._readline()
            except serial.SerialTimeoutException:
                print("ERROR: _readline() timed out in query()")
            except serial.SerialException:
                print("ERROR: _readline() failed in query()")
            except:
                raise
                sys.exit(0)
            else:
                # Convert bytes into string and remove termination chars and
                # spaces
                ans_str = ans_bytes.decode().strip()
                success = True

        return [success, ans_str]

    # --------------------------------------------------------------------------
    #   disable_command_echo
    # --------------------------------------------------------------------------

    def disable_command_echo(self):
        """Disable the command echo of the PolyScience bath.

        Returns: True if successful, False otherwise.
        """
        [success, ans] = self.query("SE0\r")
        if success and ans == "!":
            return True
        else:
            return False

    # --------------------------------------------------------------------------
    #   query_P1_temp
    # --------------------------------------------------------------------------

    def query_P1_temp(self):
        """Query the bath temperature and store it in the class member 'state'.
        Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        [success, ans] = self.query("RT\r")
        if success:
            try:
                num = float(ans)
            except (TypeError, ValueError) as e:
                print("ERROR: %s" % sys._getframe(0).f_code.co_name)
                print(e)
            else:
                self.state.P1_temp = num
                return True

        self.state.P1_temp = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_P2_temp
    # --------------------------------------------------------------------------

    def query_P2_temp(self):
        """Query the external probe and store it in the class member 'state'.
        Will be set to numpy.nan if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        [success, ans] = self.query("RR\r")
        if success:
            try:
                num = float(ans)
            except (TypeError, ValueError) as e:
                print("ERROR: %s" % sys._getframe(0).f_code.co_name)
                print(e)
            else:
                self.state.P2_temp = num
                return True

        self.state.P2_temp = np.nan
        return False

    # --------------------------------------------------------------------------
    #   query_setpoint
    # --------------------------------------------------------------------------

    def query_setpoint(self):
        """Query the temperature setpoint in [deg C] set at the PolyScience bath
        and store it in the class member 'state'. Will be set to numpy.nan if
        unsuccessful.

        Returns: True if successful, False otherwise.
        """
        [success, ans] = self.query("RS\r")
        #print("query_setpoint returns: %s" % ans)  # DEBUG
        if success:
            try:
                num = float(ans)
            except (TypeError, ValueError) as e:
                print("ERROR: %s" % sys._getframe(0).f_code.co_name)
                print(e)
            else:
                self.state.setpoint = num
                return True

        self.state.setpoint = np.nan
        return False

    # --------------------------------------------------------------------------
    #   send_setpoint
    # --------------------------------------------------------------------------

    def send_setpoint(self, setpoint):
        """Send a new temperature setpoint in [deg C] to the PolyScience bath.

        Args:
            setpoint (float): temperature in [deg C].

        Returns: True if successful, False otherwise.
        """
        try:
            setpoint = float(setpoint)
        except (TypeError, ValueError):
            # Invalid number
            print("WARNING: Received illegal setpoint value")
            print("Setpoint not updated")
            return False

        if setpoint < BATH_MIN_SETPOINT_DEG_C:
            setpoint = BATH_MIN_SETPOINT_DEG_C
            print("WARNING: setpoint is capped\nto the lower limit of %.2f 'C" %
                  BATH_MIN_SETPOINT_DEG_C)
        elif setpoint > BATH_MAX_SETPOINT_DEG_C:
            setpoint = BATH_MAX_SETPOINT_DEG_C
            print("WARNING: setpoint is capped\nto the upper limit of %.2f 'C" %
                  BATH_MAX_SETPOINT_DEG_C)

        [success, ans] = self.query("SS%.2f\r" % setpoint)
        #print("send_setpoint returns: %s" % ans)  # DEBUG
        if success and ans == "!":      # Also check status reply
            return True
        elif success and ans == "?":
            print("WARNING @ send_setpoint")
            print("PolyScience bath might be in stand-by mode.")
            return False
        else:
            return False

# ------------------------------------------------------------------------------
#   read_port_config_file
# ------------------------------------------------------------------------------

def read_port_config_file(filepath):
    """Try to open the config textfile containing the port to open. Do not panic
    if the file does not exist or cannot be read.

    Args:
        path (pathlib.Path): path to the config file,
            e.g. Path("configs/port.txt")

    Returns: The port name string when the config file is read out successfully,
        None otherwise.
    """
    if filepath.is_file():
        try:
            with filepath.open() as f:
                port_str = f.readline().strip()
            return port_str
        except:
            pass    # Do not panic and remain silent

    return None

# ------------------------------------------------------------------------------
#   write_port_config_file
# ------------------------------------------------------------------------------

def write_port_config_file(filepath, port_str):
    """Try to write the port name string to the config textfile. Do not panic if
    the file cannot be created.

    Returns: True when successful, False otherwise.
    """
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
    from pathlib import Path
    import os

    # Path to the config textfile containing the (last used) RS232 port
    PATH_CONFIG = Path("config/port_PolyScience.txt")

    # Create a PolyScience_bath class instance
    bath = PolyScience_bath()

    # Were we able to connect to a PolyScience bath?
    if bath.auto_connect(PATH_CONFIG):
        # TO DO: display internal settings of the PolyScience bath, like
        # its temperature limits, etc.
        pass
    else:
        sleep(1)
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
    send_setpoint = 15.0
    do_send_setpoint = False

    bath.query_setpoint()
    print("\nSet: %6.2f 'C" % bath.state.setpoint)

    # Loop
    done = False
    while not done:
        # Check if a new setpoint has to be send
        if do_send_setpoint:
            bath.send_setpoint(send_setpoint)
            # The bath needs time to process and update its setpoint, which is
            # found to be up to 1 seconds (!) long. Hence, we sleep.
            sleep(1)
            bath.query_setpoint()
            print("\nSet: %6.2f 'C" % bath.state.setpoint)
            do_send_setpoint = False

        # Measure and report the temperatures
        bath.query_P1_temp()
        bath.query_P2_temp()
        print("\rP1 : %6.2f 'C" % bath.state.P1_temp, end='')
        print("  P2 : %6.2f 'C" % bath.state.P2_temp, end='')
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
                    send_setpoint = input("\nEnter new setpoint ['C]: ")
                    do_send_setpoint = True

        # Slow down update period
        sleep(0.5)

    bath.ser.close()
    sleep(1)