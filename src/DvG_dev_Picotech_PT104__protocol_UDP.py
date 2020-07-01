#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
"""
__author__      = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__         = ""
__date__        = "15-09-2018"
__version__     = "1.0.0"

import socket
import numpy as np

# ITS-90 resistance-temperature relation for PT100/PT1000
# R_t = R_0 * (1 + A*t + B*t^2 + C*(t-100)*t^3)
# R_t: resistance at T 'C   [Ohm]
# R_0: resistance at 0 'C   [Ohm]
# t  : temperature          ['C]
A = 3.9083e-3
B = -5.775e-7
C = -4.183e-12  # when below 0 'C, C = 0 when above 0 'C

# Acceptable temperature range
T_MIN = -200    # ['C]
T_MAX = 800     # ['C]

# Acceptable resistance range, used to determine if a PT100 or PT1000
# probe is present
R_MIN = 18      # [Ohm]
R_MAX = 3760    # [Ohm]

# Timeout on the socket communication
# Keep the timeout shorter than the scan rate of ~ 720 ms otherwise the method
# 'scan_4_wire_temperature' will break.
SOCKET_TIMEOUT = 0.5 # 0.5 [s]

DEBUG = False

# ------------------------------------------------------------------------------
#   Class PT104
# ------------------------------------------------------------------------------

class PT104():
    class Eeprom():
        # Container for the PT-104 specific values retreived from it's
        # memory
        serial     = None
        calib_date = None
        ch1_calib  = None
        ch2_calib  = None
        ch3_calib  = None
        ch4_calib  = None
        MAC        = None
        checksum   = None

    class State():
        # Container for the process and measurement variables
        # Resistance readings of channels 1 to 4 [Ohm]
        ch1_R = np.nan
        ch2_R = np.nan
        ch3_R = np.nan
        ch4_R = np.nan
        # Temperature readings of channels 1 to 4 ['C]
        ch1_T = np.nan
        ch2_T = np.nan
        ch3_T = np.nan
        ch4_T = np.nan

    # --------------------------------------------------------------------------
    #   __init__
    # --------------------------------------------------------------------------

    def __init__(self, name="PT104"):
        self.name = name
        self._ip_address = None
        self._port       = None
        self._sock       = None
        self._eeprom     = self.Eeprom()

        # List corresponding to channels 1 to 4, where
        #    0: channel off
        #    1: channel on
        self._ENA_channels = [0, 0, 0, 0]

        # List corresponding to channels 1 to 4, where
        #    0: 1x gain
        #    1: 21x gain (for 375 Ohm range)
        self._gain_channels = [0, 0, 0, 0]

        # Resistance at 0 'C of channels 1 to 4 [Ohm]
        # For a PT100  probe this should be 100.000 Ohm
        # For a PT1000 probe this should be 1000.000 Ohm
        self.ch1_R_0 = 100
        self.ch2_R_0 = 100
        self.ch3_R_0 = 100
        self.ch4_R_0 = 100

        # Is the connection to the device alive?
        self.is_alive = False

        # Container for the measurement variables
        self.state = self.State()

    # --------------------------------------------------------------------------
    #   close
    # --------------------------------------------------------------------------

    def close(self):
        self._sock.close()
        self.is_alive = False

    # --------------------------------------------------------------------------
    #   connect
    # --------------------------------------------------------------------------

    def connect(self, ip_address="10.10.100.2", port=1234):
        """
        Returns: True if successful, False otherwise.
        """
        self._ip_address = ip_address
        self._port       = port

        print("Connect to: PicoTech PT-104")
        print("  @ ip=%s:%i : " % (ip_address, port), end='')

        # Open UDP socket
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(SOCKET_TIMEOUT)     # timeout on commands

        # Try to acquire a lock to the PT-104
        success = self.lock()

        if success:
            print("Success!\n")
            self.is_alive = True
        else:
            print("FAILED!\n")
            self.is_alive = False

        return success

    # --------------------------------------------------------------------------
    #   begin
    # --------------------------------------------------------------------------

    def begin(self):
        """
        Returns: True if successful, False otherwise.
        """
        success = self.lock()
        success &= self.read_EEPROM()
        return success

    # --------------------------------------------------------------------------
    #   UDP_send
    # --------------------------------------------------------------------------

    def UDP_send(self, msg_bytes):
        """
        msg_bytes (bytes): Message to be sent over the UDP port.
        """
        self._sock.sendto(msg_bytes, (self._ip_address, self._port))

    # --------------------------------------------------------------------------
    #   UDP_recv
    # --------------------------------------------------------------------------

    def UDP_recv(self):
        """Receive one UDP packet at a time when available.

        Returns:
            success (bool):
                True if a packet was received successfully, False otherwise.

            ans_bytes:
                UDP packet received from the device. None if unsuccessful.
        """
        success = False
        ans_bytes = None

        try:
            ans_bytes = self._sock.recv(4096)
            success = True
        except socket.timeout as err:
            #print("ERROR: socket.recv() timed out in query()")
            pass  # Stay silent and continue
        except:
            raise

        return (success, ans_bytes)

    # --------------------------------------------------------------------------
    #   UDP_query_and_check
    # --------------------------------------------------------------------------

    def UDP_query_and_check(self, msg_bytes, check_ans_bytes):
        """
        Args:
            msg_bytes (bytes):
                Message to be sent over the UDP port.

        Returns:
            success (bool):
                True if successful, False otherwise.
            ans_bytes (bytes):
                Reply received from the device. None if unsuccessful.
        """
        self.UDP_send(msg_bytes)

        # Try up to 3 times at maximum to receive the respective response
        # UDP packet belonging to above sent UDP packet.
        for i in range(3):
            [success, ans_bytes] = self.UDP_recv()
            if success:
                if ans_bytes[:len(check_ans_bytes)] == check_ans_bytes:
                    return (True, ans_bytes)
                else:
                    print("Failed %s: received %s" % (msg_bytes, ans_bytes))

        return (False, None)

    # --------------------------------------------------------------------------
    #   PT-104 functions
    #   Will return True when successful, False when failed
    # --------------------------------------------------------------------------

    def lock(self):
        success, ans = self.UDP_query_and_check(b"lock\r",
                                                b"Lock Success")
        return success

    def set_mains_rejection_50Hz(self):
        success, ans = self.UDP_query_and_check(bytes([0x30, 0x00]),
                                                b"Mains Changed")
        return success

    def set_mains_rejection_60Hz(self):
        success, ans = self.UDP_query_and_check(bytes([0x30, 0x01]),
                                                b"Mains Changed")
        return success

    def keep_alive(self):
        success, ans = self.UDP_query_and_check(bytes([0x34]),
                                                b"Alive")
        if not success: print("PT104 is not alive anymore.")
        return success

    def read_EEPROM(self):
        success, ans = self.UDP_query_and_check(bytes([0x32]),
                                                b"Eeprom")

        if success:
            # Parse
            ans        = ans[7:]   # Discard the first 7 bytes reading 'Eeprom='
            serial     = ans[19:29].decode("UTF8")
            calib_date = ans[29:37].decode("UTF8")
            ch1_calib  = int.from_bytes(ans[37:41], byteorder='little')
            ch2_calib  = int.from_bytes(ans[41:45], byteorder='little')
            ch3_calib  = int.from_bytes(ans[45:49], byteorder='little')
            ch4_calib  = int.from_bytes(ans[49:53], byteorder='little')
            MAC        = ':'.join("%02x" % b for b in ans[53:59])
            checksum   = ' '.join("0x%02x" % b for b in ans[126:128])

            self._eeprom.serial     = serial
            self._eeprom.calib_date = calib_date
            self._eeprom.ch1_calib  = ch1_calib
            self._eeprom.ch2_calib  = ch2_calib
            self._eeprom.ch3_calib  = ch3_calib
            self._eeprom.ch4_calib  = ch4_calib
            self._eeprom.MAC        = MAC
            self._eeprom.checksum   = checksum

            return True
        else:
            return False

    def start_conversion(self, ENA_channels = [1, 0, 0, 0],
                               gain_channels = [1, 0, 0, 0]):
        """
        Starts the continuous acquisition of measurements over channels 1 to 4
        ENA_channel is a list corresponding to channels 1 to 4, where
            0: channel off
            1: channel on
        gain_channels is a list corresponding to channels 1 to 4, where
            0: 1x gain
            1: 21x gain (for 375 Ohm range)
        """
        self._ENA_channels  = ENA_channels
        self._gain_channels = gain_channels

        data_byte = 0
        data_byte += ENA_channels[0]
        data_byte += ENA_channels[1]  * 2
        data_byte += ENA_channels[2]  * 4
        data_byte += ENA_channels[3]  * 8
        data_byte += gain_channels[0] * 16
        data_byte += gain_channels[1] * 32
        data_byte += gain_channels[2] * 64
        data_byte += gain_channels[3] * 128

        success, ans = self.UDP_query_and_check(bytes([0x31, data_byte]),
                                                b"Converting")
        return success

    # --------------------------------------------------------------------------
    #   report_EEPROM
    # --------------------------------------------------------------------------

    def report_EEPROM(self):
        print("EEPROM")
        print("  serial    : %s" % self._eeprom.serial)
        print("  calib_date: %s" % self._eeprom.calib_date)
        print("  ch1_calib : %s" % self._eeprom.ch1_calib)
        print("  ch2_calib : %s" % self._eeprom.ch2_calib)
        print("  ch3_calib : %s" % self._eeprom.ch3_calib)
        print("  ch4_calib : %s" % self._eeprom.ch4_calib)
        print("  MAC       : %s" % self._eeprom.MAC)
        print("  checksum  : %s" % self._eeprom.checksum)

    # --------------------------------------------------------------------------
    #   scan_4_wire_temperature
    # --------------------------------------------------------------------------

    def scan_4_wire_temperature(self):
        """Reads the UDP port for any message, presumably the measurement of the
        channels reported by the PT104, after conversion has initiated.
        These readings are transformed into resistance (Ohm) using the
        calibration constants retreived from EEPROM, and again transformed to
        temperature ('C) using the ITS-90 resistance-temperature relation
        for PT100/PT1000. Four-wire measurements are assumed.

        Returns: True if successful, False otherwise.
        """

        ## Send keep alive signal. We care about the reply later.
        self.UDP_send(bytes([0x34]))

        (success, ans) = self.UDP_recv()
        while success:
            if (ans[0] == 0 or ans[0] == 4 or ans[0] == 8 or ans[0] == 12):
                # Packet containing temperature reading

                ch = ans[0]/4 + 1    # Determine the channel number being reported
                a_0 = int.from_bytes(ans[1:5]  , byteorder='big')
                a_1 = int.from_bytes(ans[6:10] , byteorder='big')
                a_2 = int.from_bytes(ans[11:15], byteorder='big')
                a_3 = int.from_bytes(ans[16:20], byteorder='big')

                if DEBUG:
                    print("CH %i" % ch)

                if   (ch==1): calib = self._eeprom.ch1_calib; R_0 = self.ch1_R_0
                elif (ch==2): calib = self._eeprom.ch2_calib; R_0 = self.ch2_R_0
                elif (ch==3): calib = self._eeprom.ch3_calib; R_0 = self.ch3_R_0
                elif (ch==4): calib = self._eeprom.ch4_calib; R_0 = self.ch4_R_0

                # Transform readings to resistance [Ohm]
                if (a_1 - a_0) == 0:
                    R_T = np.nan
                else:
                    R_T = ((calib * (a_3 - a_2)) / (a_1 - a_0) / 1e6)

                if np.isnan(R_T):
                    # No probe is present on the channel
                    T = np.nan
                elif (R_T < R_MIN) | (R_T > R_MAX):
                    # No probe is present on the channel
                    T = np.nan
                else:
                    # Tranform resistance to temperature ['C]
                    T = ITS90_Ohm_to_degC(R_0, R_T)

                    # Significant numbers + 1
                    T = np.round(T*1e4)/1e4

                if   (ch == 1): self.state.ch1_R = R_T; self.state.ch1_T = T
                elif (ch == 2): self.state.ch2_R = R_T; self.state.ch2_T = T
                elif (ch == 3): self.state.ch3_R = R_T; self.state.ch3_T = T
                elif (ch == 4): self.state.ch4_R = R_T; self.state.ch4_T = T

            elif ans[:5] == b"Alive":
                # Packet containing alive response. Stay silent.
                pass

            else:
                # Other packet?
                print("  %s" % ans)
                return False

            # Receive a possible next packet from the UDP in-buffer
            (success, ans) = self.UDP_recv()

        # No more packets
        return True

# ------------------------------------------------------------------------------
#   ITS90 transform functions
# ------------------------------------------------------------------------------

def ITS90_degC_to_Ohm(R_0, T):
    # ITS-90 resistance-temperature relation
    # R_T = R_0 * (1 + A*T + B*T^2 + C*(T-100)*T^3)
    # R_T: resistance at T 'C   [Ohm]
    # R_0: resistance at 0 'C   [Ohm]
    # T  : temperature          ['C]
    # A = 3.9083e-3
    # B = -5.775e-7
    # C = -4.183e-12  # when below 0 'C, C = 0 when above 0 'C
    return R_0 * (1 + A*T + B*T**2 + C*(T - 100)*T**3)

def ITS90_Ohm_to_degC(R_0, R_T):
    # ITS-90 resistance-temperature relation
    # R_T = R_0 * (1 + A*T + B*T^2 + C*(T-100)*T^3)
    # R_T: resistance at T 'C   [Ohm]
    # R_0: resistance at 0 'C   [Ohm]
    # T  : temperature          ['C]
    # A = 3.9083e-3
    # B = -5.775e-7
    # C = -4.183e-12  # when below 0 'C, C = 0 when above 0 'C

    if (R_T >= R_0):
        # We are in the range T >= 0'C
        # Hence, simply solve quadratic equation because C = 0
        sqrt_arg = A**2 - 4*B*(1 - R_T/R_0)
        if sqrt_arg < 0:
            return np.nan
        else:
            T = (-A + np.sqrt(sqrt_arg)) / (2*B)

    else:
        # We are in the range T < 0'C, hence we need to solve a quartic
        # equation. Difficult to solve by algebra. We do it numerically
        # up to a certain convergence error. A convergence of
        # 0.1 milli-Kelvin is more than sufficient for the PT-104 logger.
        CONV = 1e-4         # [K]
        # Restrict the number of iterations. We have convergence at
        # CONV = 1e-4 within 20 iterations for a PT100 sensor
        MAX_ITER = 40

        # Start iteration loop
        T_lo = T_MIN        # Lower bound temperature   ['C]
        T_hi = 0            # Upper bound temperature   ['C]
        T_g  = -1.0         # Initial guess temperature ['C]

        i = 0               # Iteration counter
        diff = 2 * CONV     # = 2 * CONV assures at least 1 iteration
        while (diff > CONV):
            # Calculate resistance corresponding to the guessed temperature T_g
            R_g = ITS90_degC_to_Ohm(R_0, T_g)

            # How far are we off the reported R_T?
            diff = R_T - R_g

            if ((diff > 0) & (abs(diff) > CONV)):
                T_lo = T_g
            elif ((diff <= 0) & (abs(diff) > CONV)):
                T_hi = T_g
                diff = -diff

            # Next best guess
            T_g = (T_hi + T_lo) / 2.

            i += 1
            if i > MAX_ITER:
                print("WARNING: Loop in ITS90_Ohm_to_degC() terminated after "
                      "%d iterations" % MAX_ITER)
                break

        # We have reached convergence
        T = T_g

    if T > T_MAX:
        print("WARNING: Temperature is out of range because > %.0f 'C" % T_MAX)
    elif T <= T_MIN + 1e-4:
        print("WARNING: Temperature is out of range because <= %.0f 'C" % T_MIN)

    return T

# ------------------------------------------------------------------------------
#   Debug functions
# ------------------------------------------------------------------------------

def print_as_hex(byte_list):
    list(map(lambda x: print(format(x, '02x'), end=' '), byte_list))
    print()

# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == '__main__':
    import sys

    IP_ADDRESS = "10.10.100.2"
    PORT       = 1234

    ENA_channels  = [1, 1, 0, 0]
    gain_channels = [1, 1, 0, 0]

    # Initialise PT104 instance
    pt104 = PT104()

    # Connect over UDP port and try to achieve a lock
    if pt104.connect(IP_ADDRESS, PORT):
        pt104.begin()
        pt104.report_EEPROM()
    else:
        print("ERROR: Could not connect to PT-104 and acquire a lock.")
        sys.exit(0)

    # Start the conversion (DAQ)
    if pt104.start_conversion(ENA_channels, gain_channels):
        print("\nConverting")
    else:
        print("\nERROR: Failed start_conversion()")

    # Continuous reading as fast as possible
    print("\nT1 ['C]\tT2 ['C]")
    while 1:
        pt104.scan_4_wire_temperature()
        print("\r%.3f\t%.3f" % (pt104.state.ch1_T, pt104.state.ch2_T), end='')
