#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RS232 function library for Thermo Scientific ThermoFlex recirculating
chillers.

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
__date__ = "15-07-2020"
__version__ = "0.0.6"
# pylint: disable=bare-except, broad-except, try-except-raise

import sys
from typing import Union
import time

import numpy as np

from dvg_debug_functions import print_fancy_traceback as pft
from dvg_devices.BaseDevice import SerialDevice

# RS232 header of binary serial communication
RS232_START = [0xCA, 0x00, 0x01]


class Unit_of_measure:
    # fmt: off
    no_unit = 0
    deg_C   = 1     # Temperature in degrees Celsius
    deg_F   = 2     # Temperature in degrees Fahrenheit
    LPM     = 3     # Flow in liters per minute
    GPM     = 4     # Flow in gallons per minute
    sec     = 5     # Time in seconds
    PSI     = 6     # Pressure in pounds per square inch
    bar     = 7     # Pressure in bars
    MOhm_cm = 8     # Resistivity in mega-Ohms per centimeter
    percent = 9     # Percentage
    Volt    = 10    # Voltage in Volts
    kPa     = 11    # Pressure in kilo-Pascals
    # fmt: on


# Units expected to be used by the chiller
CHILLER_FLOW_UNIT = Unit_of_measure.LPM
CHILLER_TEMP_UNIT = Unit_of_measure.deg_C
CHILLER_PRES_UNIT = Unit_of_measure.bar


class ThermoFlex_chiller(SerialDevice):
    """Containers for the process and measurement variables.
    [numpy.nan] values indicate that the parameter is not initialized or that
    the last query was unsuccessful in communication.
    """

    # fmt: off
    class Units:
        # Container for the units used and expected by the chiller
        temp = np.nan       # Unit of measure index for the temperature
        flow = np.nan       # Unit of measure index for the flow rate
        pres = np.nan       # Unit of measure index for the pressure

    class Values_alarm:
        # Container for the alarm values
        LO_temp = np.nan    # Low temperature limit  ['C]
        HI_temp = np.nan    # High temperature limit ['C]
        LO_flow = np.nan    # Low flow rate limit    [LPM]
        HI_flow = np.nan    # High flow rate limit   [LPM]
        LO_pres = np.nan    # Low pressure limit     [bar]
        HI_pres = np.nan    # High pressure limit    [bar]

    class Values_PID:
        # Container for the PID values
        P = np.nan          # Proportional term      [% span of 100 'C]
        I = np.nan          # Integral term          [repeats/minute]
        D = np.nan          # Derivative term        [minutes]

    class Status_bits:
        # Container for the status bits of the chiller
        running               = np.nan
        RTD1_open             = np.nan
        RTD2_open             = np.nan
        RTD3_open             = np.nan
        high_temp_fixed_fault = np.nan
        low_temp_fixed_fault  = np.nan
        high_temp_fault       = np.nan
        low_temp_fault        = np.nan
        high_pressure_fault   = np.nan
        low_pressure_fault    = np.nan
        phase_monitor_fault   = np.nan
        high_level_fault      = np.nan
        drip_pan_fault        = np.nan
        motor_overload_fault  = np.nan
        LPC_fault             = np.nan
        HPC_fault             = np.nan
        external_EMO_fault    = np.nan
        local_EMO_fault       = np.nan
        low_flow_fault        = np.nan
        low_level_fault       = np.nan
        sense_5V_fault        = np.nan
        invalid_level_fault   = np.nan
        low_fixed_flow_warning      = np.nan
        high_pressure_fault_factory = np.nan
        low_pressure_fault_factory  = np.nan
        powering_up           = np.nan
        powering_down         = np.nan
        fault_tripped         = np.nan

    class State:
        # Container for the process and measurement variables
        setpoint     = np.nan   # Setpoint read out of the chiller         ['C]
        temp         = np.nan   # Temperature measured by the chiller      ['C]
        flow         = np.nan   # Flow rate measured by the chiller        [LPM]
        supply_pres  = np.nan   # Supply pressure measured by the chiller  [bar]
        suction_pres = np.nan   # Suction pressure measured by the chiller [bar]
    # fmt: on

    # --------------------------------------------------------------------------
    #   __init__
    # --------------------------------------------------------------------------

    def __init__(
        self,
        name="chiller",
        long_name="ThermoFlex chiller",
        min_setpoint_degC=10,
        max_setpoint_degC=40,
    ):
        super().__init__(name=name, long_name=long_name)

        # Default serial settings
        self.serial_init_kwargs = {
            "baudrate": 9600,
            "timeout": 1,
            "write_timeout": 1,
        }
        # The chiller does not use any EOL termination characters, hence the
        # device should be given time to have its reply been fully send to the
        # computer's serial-in buffer.
        # 9600 baud is ~ 960 bytes per second
        self.set_read_termination(None, query_wait_time=0.05)
        self.set_write_termination(None)

        self.set_ID_validation_query(
            ID_validation_query=self.ID_validation_query,
            valid_ID_broad=True,
            valid_ID_specific=None,
        )

        # Software limits on the temperature setpoint
        self.min_setpoint_degC = min_setpoint_degC
        self.max_setpoint_degC = max_setpoint_degC

        # Container for the units used and expected by the chiller.
        # Gets updated by calling the alarm value queries (e.g.
        # 'query_alarm_LO_flow()' etc.) or by calling 'begin()'.
        self.units = self.Units()

        # Container for the alarm values.
        # Gets updated by calling the alarm value queries (e.g.
        # 'query_alarm_LO_flow()' etc.) or by calling 'begin()'.
        self.values_alarm = self.Values_alarm()

        # Container for the PID values
        # Gets updated by calling the PID queries (e.g. 'query_PID_P()' etc.)
        # or by calling 'begin()'.
        self.values_PID = self.Values_PID()

        # Container for the status bits (faults and warnings of the chiller).
        # Gets updated by calling 'query_status_bits()' or by calling 'begin()'.
        self.status_bits = self.Status_bits()

        # Container for the process and measurement variables
        self.state = self.State()

    # --------------------------------------------------------------------------
    #   OVERRIDE: query
    # --------------------------------------------------------------------------

    def query(
        self,
        msg: Union[str, bytes],
        raises_on_timeout: bool = False,
        returns_ascii: bool = True,
    ) -> tuple:
        success, reply = super().query(
            msg, raises_on_timeout, returns_ascii=False  # Binary I/O, not ASCII
        )

        # The ThermoFlex is more complex in its replies than the average device.
        # Hence:
        if success:
            if (len(reply) >= 4) and reply[3] == 0x0F:
                # Error reported by chiller
                if reply[5] == 1:
                    pft("Bad command received by chiller", 3)
                elif reply[5] == 2:
                    pft("Bad data received by chiller", 3)
                elif reply[5] == 3:
                    pft("Bad checksum received by chiller", 3)
                success = False
            else:
                # We got a reply back from /a/ device, not necessarily a
                # ThermoFlex chiller.
                success = True

        if reply is None:
            reply = np.nan

        return (success, reply)

    # --------------------------------------------------------------------------
    #   ID_validation_query
    # --------------------------------------------------------------------------

    def ID_validation_query(self) -> (bool, None):
        return (self.query_Ack(), None)

    # --------------------------------------------------------------------------
    #   begin
    # --------------------------------------------------------------------------

    def begin(self):
        """This function should run directly after having established a
        connection to a ThermoFlex chiller.
        """
        # Query alarm values and units and check for proper units
        self.query_alarm_values_and_units()

        if self.units.flow != CHILLER_FLOW_UNIT:
            print("WARNING: chiller uses the wrong flowrate unit")
            sys.exit(0)

        if self.units.temp != CHILLER_TEMP_UNIT:
            print("WARNING: chiller uses the wrong temperature unit")
            sys.exit(0)

        if self.units.pres != CHILLER_PRES_UNIT:
            print("WARNING: chiller uses the wrong pressure unit")
            sys.exit(0)

        # Query PID values
        self.query_PID_values()

        # Query status bits
        self.query_status_bits()

        # Query setpoint
        self.query_setpoint()

    # --------------------------------------------------------------------------
    #   Query functions
    # --------------------------------------------------------------------------

    def query_data_as_float_and_uom(self, msg_bytes):
        """Query the serial device and parse its reply as data bytes decoding a
        float value and an unit of measure index.

        Args:
            msg_bytes (bytes): Message to be sent to the serial device.

        Returns:
            success (bool): True if successful, False otherwise.
            value  (float): The decoded float value. [numpy.nan] if unsuccessful.
            uom      (int): Unit of measure index. [numpy.nan] if unsuccessful.
        """
        value = np.nan
        # print_as_hex(msg_bytes)                     # debug info
        success, ans_bytes = self.query(msg_bytes)
        # print_as_hex(ans_bytes)                     # debug info
        if success:
            value, uom = self.parse_data_bytes(ans_bytes)
        if not np.isnan(value):
            return [True, value, uom]
        else:
            return [False, np.nan, np.nan]

    # --------------------------------------------------------------------------
    #   add_checksum
    # --------------------------------------------------------------------------

    def add_checksum(self, byte_list):
        """The checksum runs over all bytes, except for the leading byte. It is
        a bitwise inversion of the 1 byte sum of bytes. We mimic the overflow of
        the 1 byte sum in Python by using the modulo operator '% 0x100'. The
        inversion is done by using the XOR operator '^ 0xFF'
        =
        Usage example:
          # request setpoint
          msg_bytes = RS232_START + [0x70, 0x00]
          add_checksum(msg_bytes)
          # turn list into bytes ready to be sent
          msg_bytes = bytes(msg_bytes)
        """
        chksum = (sum(byte_list[1:]) % 0x100) ^ 0xFF
        byte_list.append(chksum)
        # print_as_hex(byte_list)                     # debug info

    # --------------------------------------------------------------------------
    #   Parsing
    # --------------------------------------------------------------------------

    def parse_data_bytes(self, ans_bytes):
        """Parse the data bytes.

        The manual states:
            data_bytes[0] : the qualifier byte
              b.0 to b.3 indicates unit of measure index
              b.4 to b.7 indicates precision of measurement
            data_bytes[1:]: value

        Returns:
            value (float): The decoded float value. [numpy.nan] if unsuccessful.
            uom     (int): Unit of measure index. [numpy.nan] if unsuccessful.
        """
        value = np.nan
        uom = np.nan
        try:
            nn = ans_bytes[4]  # Number of data bytes to follow
            data_bytes = ans_bytes[5 : 5 + nn]
            pom = data_bytes[0] >> 4  # Precision of measurement
            uom = data_bytes[0] % 0x10  # Unit of measure index
            int_value = int.from_bytes(
                data_bytes[1:], byteorder="big", signed=False
            )
        except Exception as err:
            pft(err, 3)
        else:
            if pom == 0:
                value = int_value
            elif pom == 1:
                value = int_value * 0.1
            elif pom == 2:
                value = int_value * 0.01
            elif pom == 3:
                value = int_value * 0.001
            elif pom == 4:
                value = int_value * 0.0001

        return (value, uom)

    def parse_status_bits(self, ans_bytes):
        """Parse the status bits, which are indicators for any faults and/or
        warnings of the chiller. This status gets stored in the class member
        'status_bits'.
        """
        nn = ans_bytes[4]  # Number of data bytes to follow
        status_bits = ans_bytes[5 : 5 + nn]
        d1 = np.uint8(status_bits[0])
        d2 = np.uint8(status_bits[1])
        d3 = np.uint8(status_bits[2])
        d4 = np.uint8(status_bits[3])

        [
            self.status_bits.low_temp_fault,
            self.status_bits.high_temp_fault,
            self.status_bits.low_temp_fixed_fault,
            self.status_bits.high_temp_fixed_fault,
            self.status_bits.RTD3_open,
            self.status_bits.RTD2_open,
            self.status_bits.RTD1_open,
            self.status_bits.running,
        ] = np.unpackbits(d1)
        [
            self.status_bits.HPC_fault,
            self.status_bits.LPC_fault,
            self.status_bits.motor_overload_fault,
            self.status_bits.phase_monitor_fault,
            self.status_bits.high_level_fault,
            self.status_bits.drip_pan_fault,
            self.status_bits.low_pressure_fault,
            self.status_bits.high_pressure_fault,
        ] = np.unpackbits(d2)
        [
            self.status_bits.high_pressure_fault_factory,
            self.status_bits.low_fixed_flow_warning,
            self.status_bits.invalid_level_fault,
            self.status_bits.sense_5V_fault,
            self.status_bits.low_level_fault,
            self.status_bits.low_flow_fault,
            self.status_bits.local_EMO_fault,
            self.status_bits.external_EMO_fault,
        ] = np.unpackbits(d3)
        [
            dummy,
            dummy,
            dummy,
            dummy,
            dummy,
            self.status_bits.powering_down,
            self.status_bits.powering_up,
            self.status_bits.low_pressure_fault_factory,
        ] = np.unpackbits(d4)

        self.status_bits.fault_tripped = (
            sum(
                [
                    self.status_bits.high_temp_fixed_fault,
                    self.status_bits.low_temp_fixed_fault,
                    self.status_bits.high_temp_fault,
                    self.status_bits.low_temp_fault,
                    d2,
                    d3,
                    self.status_bits.low_pressure_fault_factory,
                ]
            )
            > 0
        )

        # print(np.unpackbits(d1))
        # print(np.unpackbits(d2))
        # print(np.unpackbits(d3))
        # print(np.unpackbits(d4))

    def parse_ASCII_bytes(self, ans_bytes):
        """Parse the ASCII-encoded text bytes.

        Returns: The decoded text as (str), or None if unsuccessful.
        """
        nn = ans_bytes[4]  # Number of data bytes to follow
        ASCII_bytes = ans_bytes[5 : 5 + nn]
        try:
            ans_str = ASCII_bytes.decode("ascii")
        except UnicodeDecodeError:
            return None
        except:
            return None
        else:
            return ans_str

    # --------------------------------------------------------------------------
    #   ON/OFF
    # --------------------------------------------------------------------------

    def turn_off(self):
        """ Turn the chiller off.

        Returns: The effected on/off state of the chiller, or [numpy.nan] if
        unsuccessful.
        """
        msg_bytes = bytes(
            RS232_START + [0x81, 0x01, 0x00, 0x7C]
        )  # includes checksum
        success, ans_bytes = self.query(msg_bytes)
        if success:
            return bool(ans_bytes[5])  # return resulting on/off state
        else:
            return np.nan

    def turn_on(self):
        """ Turn the chiller on.

        Returns: The effected on/off state of the chiller, or [numpy.nan] if
        unsuccessful.
        """
        msg_bytes = bytes(
            RS232_START + [0x81, 0x01, 0x01, 0x7B]
        )  # includes checksum
        success, ans_bytes = self.query(msg_bytes)
        if success:
            return bool(ans_bytes[5])  # return resulting on/off state
        else:
            return np.nan

    def query_is_on(self):
        """Query the on/off state of the chiller.
        This is identical to the status bit 'status.chiller_running'.

        Returns: The on/off state of the chiller, or [numpy.nan] if
        unsuccessful.
        """
        msg_bytes = bytes(
            RS232_START + [0x81, 0x01, 0x02, 0x7A]
        )  # includes checksum
        success, ans_bytes = self.query(msg_bytes)
        if success:
            return bool(ans_bytes[5])  # return resulting on/off state
        else:
            return np.nan

    # --------------------------------------------------------------------------
    #   query_Ack
    # --------------------------------------------------------------------------

    def query_Ack(self):
        """Query the 'Acknowledge' request (REQ ACK). Basically asking 'Are you
        a ThermoFlex chiller?' to the serial device.

        Returns: True if successful, False otherwise.
        """
        msg_bytes = bytes(RS232_START + [0x00, 0x00, 0xFE])  # includes checksum
        success, ans_bytes = self.query(msg_bytes)
        if success and (
            (ans_bytes == bytes(RS232_START + [0x00, 0x02, 0x00, 0x00, 0xFC]))
            | (ans_bytes == bytes(RS232_START + [0x00, 0x02, 0x00, 0x01, 0xFB]))
        ):
            return True
        else:
            return False

    # --------------------------------------------------------------------------
    #   Request HI/LO alarm values
    # --------------------------------------------------------------------------

    def query_alarm_values_and_units(self):
        """Query all alarm values and store in the class member 'values_alarm'.
        Also stores the units of measure in class member 'units'.
        Each will be set to [numpy.nan] if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        return (
            self.query_alarm_LO_flow()
            & self.query_alarm_LO_temp()
            & self.query_alarm_LO_pres()
            & self.query_alarm_HI_flow()
            & self.query_alarm_HI_temp()
            & self.query_alarm_HI_pres()
        )

    def query_alarm_LO_flow(self):
        """Query the alarm value and store in the class member 'values_alarm'.
        Also stores the unit of measure in class member 'units'.
        Both will be set to [numpy.nan] if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        msg_bytes = bytes(RS232_START + [0x30, 0x00, 0xCE])  # includes checksum
        success, value, units = self.query_data_as_float_and_uom(msg_bytes)
        self.values_alarm.LO_flow = value
        self.units.flow = units
        return success

    def query_alarm_LO_temp(self):
        """Query the alarm value and store in the class member 'values_alarm'.
        Also stores the unit of measure in class member 'units'.
        Will be set to [numpy.nan] if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        msg_bytes = bytes(RS232_START + [0x40, 0x00, 0xBE])  # includes checksum
        success, value, units = self.query_data_as_float_and_uom(msg_bytes)
        self.values_alarm.LO_temp = value
        self.units.temp = units
        return success

    def query_alarm_LO_pres(self):
        """Query the alarm value and store in the class member 'values_alarm'.
        Also stores the unit of measure in class member 'units'.
        Will be set to [numpy.nan] if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        msg_bytes = bytes(RS232_START + [0x48, 0x00, 0xB6])  # includes checksum
        success, value, units = self.query_data_as_float_and_uom(msg_bytes)
        self.values_alarm.LO_pres = value
        self.units.pres = units
        return success

    def query_alarm_HI_flow(self):
        """Query the alarm value and store in the class member 'values_alarm'.
        Also stores the unit of measure in class member 'units'.
        Will be set to [numpy.nan] if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        msg_bytes = bytes(RS232_START + [0x50, 0x00, 0xAE])  # includes checksum
        success, value, units = self.query_data_as_float_and_uom(msg_bytes)
        self.values_alarm.HI_flow = value
        self.units.flow = units
        return success

    def query_alarm_HI_temp(self):
        """Query the alarm value and store in the class member 'values_alarm'.
        Also stores the unit of measure in class member 'units'.
        Will be set to [numpy.nan] if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        msg_bytes = bytes(RS232_START + [0x60, 0x00, 0x9E])  # includes checksum
        success, value, units = self.query_data_as_float_and_uom(msg_bytes)
        self.values_alarm.HI_temp = value
        self.units.temp = units
        return success

    def query_alarm_HI_pres(self):
        """Query the alarm value and store in the class member 'values_alarm'.
        Also stores the unit of measure in class member 'units'.
        Will be set to [numpy.nan] if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        msg_bytes = bytes(RS232_START + [0x68, 0x00, 0x96])  # includes checksum
        success, value, units = self.query_data_as_float_and_uom(msg_bytes)
        self.values_alarm.HI_pres = value
        self.units.pres = units
        return success

    # --------------------------------------------------------------------------
    #   Query PID values
    # --------------------------------------------------------------------------

    def query_PID_values(self):
        """Query all PID values and store in the class member 'values_PID'.
        Each will be set to [numpy.nan] if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        return self.query_PID_P() & self.query_PID_I() & self.query_PID_D()

    def query_PID_P(self):
        """Query the PID value and store in the class member 'values_PID'.
        Will be set to [numpy.nan] if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        msg_bytes = bytes(RS232_START + [0x74, 0x00, 0x8A])  # includes checksum
        success, value, _units = self.query_data_as_float_and_uom(msg_bytes)
        self.values_PID.P = value
        return success

    def query_PID_I(self):
        """Query the PID value and store in the class member 'values_PID'.
        Will be set to [numpy.nan] if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        msg_bytes = bytes(RS232_START + [0x75, 0x00, 0x89])  # includes checksum
        success, value, _units = self.query_data_as_float_and_uom(msg_bytes)
        self.values_PID.I = value
        return success

    def query_PID_D(self):
        """Query the PID value and store in the class member 'values_PID'.
        Will be set to [numpy.nan] if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        msg_bytes = bytes(RS232_START + [0x76, 0x00, 0x88])  # includes checksum
        success, value, _units = self.query_data_as_float_and_uom(msg_bytes)
        self.values_PID.D = value
        return success

    # --------------------------------------------------------------------------
    #   query_status_bits
    # --------------------------------------------------------------------------

    def query_status_bits(self):
        """Query and parse the status bits, which are indicators for any faults
        and/or warnings of the chiller. This status gets stored in the class
        member 'status_bits.

        Returns: True if successful, False otherwise.
        """
        msg_bytes = bytes(RS232_START + [0x09, 0x00, 0xF5])  # included checksum
        success, ans_bytes = self.query(msg_bytes)
        if success:
            self.parse_status_bits(ans_bytes)
        return success

    # --------------------------------------------------------------------------
    #   Query state variables
    # --------------------------------------------------------------------------

    def query_state(self):
        """Query all process and measurement variables and store in the class
        member 'state'.
        Each will be set to [numpy.nan] if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        return (
            self.query_setpoint()
            & self.query_temp()
            & self.query_flow()
            & self.query_supply_pres()
            & self.query_suction_pres()
        )

    def query_setpoint(self):
        """Query and store in the class member 'state':
        The temperature setpoint value read from the chiller.
        Will be set to [numpy.nan] if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        msg_bytes = bytes(RS232_START + [0x70, 0x00, 0x8E])  # includes checksum
        success, value, _units = self.query_data_as_float_and_uom(msg_bytes)
        self.state.setpoint = value
        return success

    def query_temp(self):
        """Query and store in the class member 'state':
        The temperature measured by the chiller.
        Will be set to [numpy.nan] if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        msg_bytes = bytes(RS232_START + [0x20, 0x00, 0xDE])  # includes checksum
        success, value, _units = self.query_data_as_float_and_uom(msg_bytes)
        self.state.temp = value
        return success

    def query_flow(self):
        """Query and store in the class member 'state':
        The flow rate measured by the chiller.
        Will be set to [numpy.nan] if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        msg_bytes = bytes(RS232_START + [0x10, 0x00, 0xEE])  # includes checksum
        success, value, _units = self.query_data_as_float_and_uom(msg_bytes)
        self.state.flow = value
        return success

    def query_supply_pres(self):
        """Query and store in the class member 'state':
        The supply pressure measured by the chiller.
        Will be set to [numpy.nan] if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        msg_bytes = bytes(RS232_START + [0x28, 0x00, 0xD6])  # includes checksum
        success, value, _units = self.query_data_as_float_and_uom(msg_bytes)
        self.state.supply_pres = value
        return success

    def query_suction_pres(self):
        """Query and store in the class member 'state':
        The suction pressure measured by the chiller.
        Will be set to [numpy.nan] if unsuccessful.

        Returns: True if successful, False otherwise.
        """
        msg_bytes = bytes(RS232_START + [0x29, 0x00, 0xD5])  # includes checksum
        success, value, _units = self.query_data_as_float_and_uom(msg_bytes)
        self.state.suction_pres = value
        return success

    # --------------------------------------------------------------------------
    #   query_display_msg
    # --------------------------------------------------------------------------

    def query_display_msg(self):
        """Query the display text shown on the chiller.

        Returns: The display text as (str), or None if unsuccessful.
        """
        msg_bytes = bytes(RS232_START + [0x07, 0x00, 0xF7])  # includes checksum
        success, ans_bytes = self.query(msg_bytes)
        if success:
            return self.parse_ASCII_bytes(ans_bytes)
        else:
            return None

    # --------------------------------------------------------------------------
    #   send_setpoint
    # --------------------------------------------------------------------------

    def send_setpoint(self, temp_deg_C):
        """Send a new temperature setpoint in [deg C.] to the chiller.
        Subsequently, the chiller replies with the currently set setpoint and
        this value will be stored in the class member 'state'.

        Args:
            temp_deg_C (float): temperature in [deg C].

        Returns: True if successful, False otherwise.
        """
        try:
            temp_deg_C = float(temp_deg_C)
        except (TypeError, ValueError):
            # Invalid number
            print("WARNING: Received illegal setpoint value")
            print("Setpoint not updated")
            return False

        if temp_deg_C < self.min_setpoint_degC:
            temp_deg_C = self.min_setpoint_degC
            print(
                "WARNING: setpoint is capped\nto the lower limit of %.1f 'C"
                % self.min_setpoint_degC
            )
        elif temp_deg_C > self.max_setpoint_degC:
            temp_deg_C = self.max_setpoint_degC
            print(
                "WARNING: setpoint is capped\nto the upper limit of %.1f 'C"
                % self.max_setpoint_degC
            )

        # Transform temperature to bytes
        pom = 0.1  # precision of measurement, fixed to 0.1
        temp_bytes = int(np.round(temp_deg_C / pom)).to_bytes(
            2, byteorder="big"
        )
        msg = RS232_START + [0xF0, 0x02] + [temp_bytes[0], temp_bytes[1]]
        self.add_checksum(msg)
        msg_bytes = bytes(msg)

        # Send setpoint to chiller and receive the set setpoint
        success, value, _units = self.query_data_as_float_and_uom(msg_bytes)
        self.state.setpoint = value
        return success


# ------------------------------------------------------------------------------
#   Debug functions
# ------------------------------------------------------------------------------


def print_as_hex(byte_list):
    list(map(lambda x: print(format(x, "02x"), end=" "), byte_list))
    print()


# -----------------------------------------------------------------------------
#   Main: Will show a demo when run from the terminal
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import os

    # Path to the config textfile containing the (last used) RS232 port
    PATH_CONFIG = "config/port_ThermoFlex_chiller.txt"

    # Create connection to ThermoFlex chiller over RS232
    chiller = ThermoFlex_chiller()
    if chiller.auto_connect(filepath_last_known_port=PATH_CONFIG):
        chiller.begin()  # Retrieve necessary parameters
    else:
        time.sleep(1)
        sys.exit(0)

    if os.name == "nt":
        import msvcrt

        running_Windows = True
    else:
        running_Windows = False

    # Prepare
    send_setpoint = 22.0
    do_send_setpoint = False

    # Loop
    done = False
    while not done:
        # Check if a new setpoint has to be send
        if do_send_setpoint:
            chiller.send_setpoint(send_setpoint)
            do_send_setpoint = False

        # Measure and report
        chiller.query_status_bits()  # Faults and warnings
        chiller.query_state()  # State variables

        if running_Windows:
            os.system("cls")
            print("Press Q to quit.")
            print("Press S to enter new setpoint.")
            print("Press O to toggle the chiller on/off.")
        else:
            os.system("clear")
            print("Press Control + C to quit.")
            print("No other keyboard input possible because OS is not Windows.")

        print("\n------------------------")
        print("      ALARM VALUES")
        print("        LO  |  HI")
        print(
            " flow: %4.1f | %4.1f  LPM"
            % (chiller.values_alarm.LO_flow, chiller.values_alarm.HI_flow)
        )
        print(
            " pres: %4.2f | %4.2f  bar"
            % (chiller.values_alarm.LO_pres, chiller.values_alarm.HI_pres)
        )
        print(
            " temp: %4.1f | %4.1f  'C"
            % (chiller.values_alarm.LO_temp, chiller.values_alarm.HI_temp)
        )
        print("------------------------")
        print(" P: %4.1f  %% span 100'C" % chiller.values_PID.P)
        print(" I: %4.2f  repeats/minute" % chiller.values_PID.I)
        print(" D: %4.1f  minutes" % chiller.values_PID.D)
        print("------------------------")
        print(" running         : %i" % chiller.status_bits.running)
        print(" powering up/down: %i" % chiller.status_bits.powering_down)
        print(" fault_tripped   : %i" % chiller.status_bits.fault_tripped)
        print(" MSG: %s" % chiller.query_display_msg())
        print("------------------------")
        print(" setpoint: %6.1f 'C" % chiller.state.setpoint)
        print("------------------------")
        print(" temp    : %6.1f 'C" % chiller.state.temp)
        print(" flow    : %6.1f LPM" % chiller.state.flow)
        print(" supply  : %6.2f bar" % chiller.state.supply_pres)
        print(" suction : %6.2f bar" % chiller.state.suction_pres)
        print("------------------------")
        sys.stdout.flush()

        # Process keyboard input
        if running_Windows:
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b"q":
                    print("\nAre you sure you want to quit [y/n]?")
                    if msvcrt.getch() == b"y":
                        print("Switching off chiller and quitting.")
                        done = True
                elif key == b"s":
                    send_setpoint = input("\nEnter new setpoint [deg C]: ")
                    do_send_setpoint = True
                elif key == b"o":
                    if chiller.status_bits.running:
                        chiller.turn_off()
                    else:
                        chiller.turn_on()

        # Slow down update period
        time.sleep(0.5)

    chiller.turn_off()
    chiller.close()
    time.sleep(1)
