#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RS232 function library for a Parker Compax3 traverse controller. Only the ASCII
version is supported, not (yet) the binary version.

Communication errors will be handled as non-fatal. This means it will struggle
on with the script while reporting error messages to the command line output,
as opposed to terminating the program completely.

State variables that read numpy.nan indicate that they are uninitialized or that
the previous query resulted in a communication error.

When this file is directly run from the terminal a demo will be shown.

Dennis van Gils
01-08-2018
"""

import sys
import serial
import serial.tools.list_ports
from pathlib import Path

import numpy as np
from DvG_debug_functions import print_fancy_traceback as pft

# Serial settings
RS232_BAUDRATE = 115200
RS232_TIMEOUT  = 0.4  # [s]
RS232_RTSCTS   = True
TERM_CHAR = '\r'

class Compax3_traverse():
    """Containers for the process and measurement variables
    [numpy.nan] values indicate that the parameter is not initialized or that
    the last query was unsuccessful in communication.
    """
    class Status_word_1():
        # Container for Status word 1
        I0 = np.nan                 # bit 0
        I1 = np.nan                 # bit 1
        I2 = np.nan                 # bit 2
        I3 = np.nan                 # bit 3
        I4 = np.nan                 # bit 4
        I5 = np.nan                 # bit 5
        I6 = np.nan                 # bit 6
        I7 = np.nan                 # bit 7 'open motor holding brake'
        no_error           = np.nan # bit 8
        pos_reached        = np.nan # bit 9
        powerless          = np.nan # bit 10
        powered_stationary = np.nan # bit 11 'standstill'
        zero_pos_known     = np.nan # bit 12
        PSB0 = np.nan               # bit 13
        PSB1 = np.nan               # bit 14
        PSB2 = np.nan               # bit 15

    class State():
        # Container for the process and measurement variables
        cur_pos = np.nan            # position [mm]
        error_msg = np.nan          # error string message

    def __init__(self, name='trav'):
        self.ser = None                 # serial.Serial device instance
        self.name = name
        self.serial_str = None          # Serial number of the Compax3

        # Is the connection to the device alive?
        self.is_alive = False

        # Placeholder for a future mutex instance needed for proper
        # multithreading (e.g. instance of QtCore.Qmutex())
        self.mutex = None

        # Containers for the status, process and measurement variables
        self.status_word_1 = self.Status_word_1()
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
        connection. A query for the Compax3 serial number is send over the port.
        If it gives the proper response (and optionally has a matching serial
        number) it must be the Compax3 traverse we're looking for.

        Args:
            port_str (str): Serial port address to open
            match_serial_str (str, optional): Serial string of the Compax3 to
                establish a connection to. When empty or None then any Compax3
                is accepted. Defaults to None.
            print_trying_message (bool, optional): When True then a 'trying to
                open' message is printed to the terminal. Defaults to True.

        Returns: True if successful, False otherwise.
        """
        self.is_alive = False

        if match_serial_str == '': match_serial_str = None
        if print_trying_message:
            if match_serial_str is None:
                print("Connect to: Compax3 traverse")
            else:
                print("Connect to: Compax3 traverse, serial %s" %
                      match_serial_str)

        print("  @ %-5s: " % port_str, end='')
        try:
            # Open the serial port
            self.ser = serial.Serial(port=port_str,
                                     baudrate=RS232_BAUDRATE,
                                     rtscts=RS232_RTSCTS,
                                     timeout=RS232_TIMEOUT,
                                     write_timeout=RS232_TIMEOUT)
        except serial.SerialException:
            print("Could not open port")
            return False
        except:
            raise
            sys.exit(0)

        try:
            # Query the serial number string.
            # NOTE: this function can finish okay and return False as indication
            # that the device on the serial port gives /a/ reply but it is not a
            # proper reply you would except from a Compax3 traverse. In other
            # words: the device replies but it is not a Compax3 traverse.
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
                # Found any Compax 3 traverse
                print("Success!")
                print("  Name: '%s'\n" % self.name)
                self.is_alive = True
                return True
            elif self.serial_str.lower() == match_serial_str.lower():
                # Found the Compax3 traverse with matching serial
                print("Success!")
                print("  Name: '%s'\n" % self.name)
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
        for the Compax3 serial number is send over all ports. The port that
        gives the proper response (and optionally has a matching serial number)
        must be the Compax3 traverse we're looking for.

        Args:
            match_serial_str (str, optional): Serial string of the Compax3 to
                establish a connection to. When empty or None then any Compax3
                is accepted. Defaults to None.

        Returns: True if successful, False otherwise.
        """
        if match_serial_str == '': match_serial_str = None
        if match_serial_str is None:
            print("Scanning ports for any Compax3 traverse ")
        else:
            print(("Scanning ports for a Compax3 traverse with\n"
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

        Returns: True if successful, False otherwise.
        """
        success  = self.query_error()
        success &= self.query_position()
        success &= self.query_status_word_1()

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
            ans_str (str) : Reply received from the device. [None] if
                            unsuccessful.
        """
        success = False
        ans_str = None

        if not self.is_alive:
            pft("Device is not connected yet or already closed.", 3)
        else:
            try:
                # Send command string to the device as bytes
                self.ser.write((msg_str + TERM_CHAR).encode())
            except (serial.SerialTimeoutException,
                    serial.SerialException) as err:
                # Print error and struggle on
                pft(err, 3)
            except Exception as err:
                pft(err, 3)
                sys.exit(0)
            else:
                try:
                    ans_bytes = self.ser.read_until(TERM_CHAR.encode())
                except (serial.SerialTimeoutException,
                        serial.SerialException) as err:
                    pft(err, 3)
                except Exception as err:
                    pft(err, 3)
                    sys.exit(0)
                else:
                    ans_str = ans_bytes.decode('utf8').strip()
                    if ans_str[0] == '>':
                        # Successfull operation without meaningfull reply
                        success = True
                    elif ans_str[0] == '!':
                        # Error reply
                        print("COMPAX3 COMMUNICATION ERROR: " + ans_str)
                    else:
                        # Successfull operation with meaningfull reply
                        success = True

        return [success, ans_str]

    # --------------------------------------------------------------------------
    #   Higher level queries
    # --------------------------------------------------------------------------

    def query_serial_str(self):
        """Query the serial number and store it in the class member 'serial_str'

        Returns: True if successful, False otherwise.
        """
        # First make sure we're dealing with a Compax3 controller, because we
        # have to exclude the possibility that another device will reply with
        # an error message to the serial number request, which then could be
        # mistaken for /the/ serial number.
        [success, ans_str] = self.query("_?")
        if (success and ans_str.startswith("Compax3")):
            # Now we can query the serial number
            [success, ans_str] = self.query("o1.4")
            if success:
                self.serial_str = ans_str
                return True

        self.serial_str = None
        return False

    def query_position(self):
        """Query the position and store in the class member 'state.cur_pos'
        when successfull. When the communication fails the class member will be
        set to [numpy.nan].

        Returns: True if successful, False otherwise.
        """
        [success, ans_str] = self.query("o680.5")
        if success:
            self.state.cur_pos = float(ans_str)
        else:
            self.state.cur_pos = np.nan

        return success

    def query_error(self):
        """Query the last error and store in the class member 'state.error_msg'
        when successfull. When the communication fails the class member will be
        set to [numpy.nan].

        Returns: True if successful, False otherwise.
        """
        [success, ans_str] = self.query("o550.1")
        if success:
            # Translate error codes to more meaningful messages
            if (ans_str == "1"):
                self.state.error_msg = ""
            elif (ans_str == "17168"):
                self.state.error_msg = ("%s: Motor temperature" % ans_str)
            elif (ans_str == "29472"):
                self.state.error_msg = ("%s: Following error" % ans_str)
            elif (ans_str == "29475"):
                self.state.error_msg = ("%s: Target or actual position "
                                        "exceeds positive end limit" % ans_str)
            elif (ans_str == "29476"):
                self.state.error_msg = ("%s: Target or actual position "
                                        "exceeds negative end limit" % ans_str)
            elif (ans_str == "29479"):
                self.state.error_msg = ("%s: Change of direction during "
                                        "movement" % ans_str)
            else:
                self.state.error_msg = ans_str
        else:
            self.state.error_msg = np.nan

        return success

    def query_status_word_1(self):
        """Query the status word 1 and store in the class member 'status_word_1'
        when successfull. When the communication fails the class member
        'status_word_1' will be populated with [numpy.nan].

        Returns: True if successful, False otherwise.
        """
        [success, ans_str] = self.query("o1000.3")

        if ans_str is None:
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
        else:
            dec_x = int(ans_str)

            # Convert dec to bin string, remove prefix '0b', prefix with 0's to
            # garantuee 16 bits and reverse
            str_bits = ((bin(dec_x)[2:]).zfill(16))[::-1]

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

        return success

    # --------------------------------------------------------------------------
    # --------------------------------------------------------------------------

    def store_motion_profile(self,
                             target_position=0,
                             velocity=10,
                             mode=1,
                             accel=100,
                             decel=100,
                             jerk=1e6,
                             profile_number=2):
        """
        Note:
            Profile_number 0 is reserved for homing.
            Movement mode is fixed to absolute, not relative.
        """
        mode = 1 # Overrule, set movement mode to absolute position

        print("  Profile number: %d" % profile_number)
        print("    pos   = %.2f"   % target_position)
        print("    vel   = %.2f"   % velocity)
        print("    mode  = %d (fixed to absolute)" % mode)
        print("    accel = %.2f"   % accel)
        print("    decel = %.2f"   % decel)
        print("    jerk  = %.2f\n" % jerk)

        [success, ans_str] = self.query(
            "o1901.%d=%.2f" % (profile_number, target_position))
        if success:
            [success, ans_str] = self.query(
                "o1902.%d=%.2f" % (profile_number, velocity))
        if success:
            [success, ans_str] = self.query(
                "o1905.%d=%d"   % (profile_number, mode))
        if success:
            [success, ans_str] = self.query(
                "o1906.%d=%.2f" % (profile_number, accel))
        if success:
            [success, ans_str] = self.query(
                "o1907.%d=%.2f" % (profile_number, decel))
        if success:
            [success, ans_str] = self.query(
                "o1908.%d=%.2f" % (profile_number, jerk))
        if success:
            [success, ans_str] = self.query(
                "o1904.%d=$32"  % (profile_number))  # Store profile

        return success

    def activate_motion_profile(self, profile_number=2):
        """
        """
        # Control word (CW) for activating the passed profile number
        # First send: quit/motor bit (bit 0) high
        #             stop bits (bits 1, 14) high
        #             start bit (bit 13) low
        CW_LO = 0b0100000000000011
        CW_LO = CW_LO + (profile_number << 8)
        [success, ans_str] = self.query("o1100.3=%d" % CW_LO)
        if success:
            # Then send start bit (bit 13) high
            CW_HI = CW_LO + (1 << 13)
            [success, ans_str] = self.query("o1100.3=%d" % CW_HI)

        return success

    def move_to_target_position(self, target_position, profile_number=2):
        """
        Note: Make sure a motion profile with number 'profile_number' is stored
        at least once with 'self.store_motion_profile' before moving.
        """
        # Send new target position
        [success, ans_str] = self.query(
            "o1901.%d=%.2f" % (profile_number, target_position))

        if success:
            self.activate_motion_profile(profile_number=2)

        return success

    def jog_plus(self):
        """
        """
        # Control word (CW) for activating the jog+
        CW_LO = 0b0100000000000011
        [success, ans_str] = self.query("o1100.3=%d" % CW_LO)
        if success:
            # Then send jog+ bit (bit 2) high
            CW_HI = CW_LO + (1 << 2)
            [success, ans_str] = self.query("o1100.3=%d" % CW_HI)

        return success

    def jog_minus(self):
        """
        """
        # Control word (CW) for activating the jog-
        CW_LO = 0b0100000000000011
        [success, ans_str] = self.query("o1100.3=%d" % CW_LO)
        if success:
            # Then send jog- bit (bit 3) high
            CW_HI = CW_LO + (1 << 3)
            [success, ans_str] = self.query("o1100.3=%d" % CW_HI)

        return success

    def stop_motion_but_keep_power(self):
        """
        """
        CW_LO = 0b0100000000000011
        [success, ans_str] = self.query("o1100.3=%d" % CW_LO)

        return success

    def stop_motion_and_remove_power(self):
        """
        """
        [success, ans_str] = self.query("o1100.3=0")

        return success

    def acknowledge_error(self):
        """If the cause of an error is eliminated, the error can be
        acknowledged. This is necessary for the axis to be able to get powered
        again.

        Sends a rising edge on bit 0 of the control word. This will leave the
        axis powered when no new error occurs again.

        Returns: True if successful, False otherwise.
        """
        [success, ans_str] = self.query("o1100.3=0")
        if success:
            [success, ans_str] = self.query("o1100.3=1")

        return success

    def report_status_word_1(self, compact=False):
        """
        """
        if not compact:
            print("Status word 1:")
            print("  %-6s: I0" % self.status_word_1.I0)
            print("  %-6s: I1" % self.status_word_1.I1)
            print("  %-6s: I2" % self.status_word_1.I2)
            print("  %-6s: I3" % self.status_word_1.I3)
            print("  %-6s: I4" % self.status_word_1.I4)
            print("  %-6s: I5" % self.status_word_1.I5)
            print("  %-6s: I6" % self.status_word_1.I6)
            print("  %-6s: I7" % self.status_word_1.I7)
            print("  %-6s: no_error"    % self.status_word_1.no_error)
            print("  %-6s: pos_reached" % self.status_word_1.pos_reached)
            print("  %-6s: powerless"   % self.status_word_1.powerless)
            print("  %-6s: powered_stat"
                  % self.status_word_1.powered_stationary)
            print("  %-6s: zero_pos_known"
                  % self.status_word_1.zero_pos_known)
            print("  %-6s: PSB0" % self.status_word_1.PSB1)
            print("  %-6s: PSB1" % self.status_word_1.PSB1)
            print("  %-6s: PSB2" % self.status_word_1.PSB2)
        else:
            if not self.status_word_1.no_error:
                print("  ERROR!")
            if self.status_word_1.powerless:
                print("  Axis    : unpowered")
            else:
                if self.status_word_1.powered_stationary:
                    print("  Axis    : POWERED STANDSTILL")
                else:
                    print("  Axis    : POWERED")
            if self.status_word_1.zero_pos_known:
                print("  Zero pos: known")
            else:
                print("  Zero pos: UNKNOWN")
            if self.status_word_1.pos_reached:
                print("  Position: REACHED")
            else:
                print("  Position: unreached")
        print("")

# -----------------------------------------------------------------------------
#   read_port_config_file
# -----------------------------------------------------------------------------

def read_port_config_file(filepath):
    """Try to open the config textfile containing   the port to open. Do not panic
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

if __name__ == '__main__':
    import time

    # Specific connection settings of each traverse axis of our setup
    class Trav_connection_params():
        # Serial number of the Compax3 traverse controller to connect to.
        # Set to '' or None to connect to any Compax3.
        serial = None
        # Display name
        name   = "TRAV"
        # Path to the config textfile containing the (last used) RS232 port
        path_config = Path("config/port_Compax3_trav.txt")

    # Horizontal axis
    trav_conn_horz = Trav_connection_params()
    trav_conn_horz.serial = "4409980001"
    trav_conn_horz.name   = "TRAV HORZ"
    trav_conn_horz.path_config = Path("config/port_Compax3_trav_horz.txt")

    # Vertical axis
    trav_conn_vert = Trav_connection_params()
    trav_conn_vert.serial = "4319370001"
    trav_conn_vert.name   = "TRAV VERT"
    trav_conn_vert.path_config = Path("config/port_Compax3_trav_vert.txt")

    # Connect to this specific traverse axis
    #trav_conn = Trav_connection_params()  # Any
    #trav_conn = trav_conn_horz
    trav_conn = trav_conn_vert

    # --------------------------------------------------------------------------
    # --------------------------------------------------------------------------

    # Create connection to Compax3 traverse controller over RS232
    trav = Compax3_traverse(name=trav_conn.name)

    if trav.auto_connect(trav_conn.path_config, trav_conn.serial):
        trav.begin()     # Retrieve necessary parameters
    else:
        time.sleep(1)
        sys.exit(0)

    print("Error msg: %s" % trav.state.error_msg)
    print("Current position: %.2f" % trav.state.cur_pos)
    trav.report_status_word_1(compact=True)

    trav.acknowledge_error()

    print("ERRORS RESET")
    print("ACTIVATE\n")
    time.sleep(0.1)

    trav.query_status_word_1()
    trav.report_status_word_1(compact=True)

    # Update set #2
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
    print("Current position: %.2f" % trav.state.cur_pos)

    trav.query("o1100.3=$400b")      # jog-
    time.sleep(2);
    """

    print("MOVING\n")

    for i in range(14):
        trav.query_position()
        print("Current position: %.2f" % trav.state.cur_pos)
        trav.query_status_word_1()
        trav.report_status_word_1(compact=True)
        time.sleep(0.2)

    trav.query("o1100.3=0")          # disable axis
    #trav.query("o1000.4")            # last executed set #

    print("DEACTIVATE\n")
    time.sleep(1)

    trav.query_error()
    trav.query_position()
    trav.query_status_word_1()

    print("Error msg: %s" % trav.state.error_msg)
    print("Current position: %.2f" % trav.state.cur_pos)
    trav.report_status_word_1(compact=True)

    # Close
    print('')
    trav.close()
    sys.exit(0)
