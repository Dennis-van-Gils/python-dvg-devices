#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Modbus RTU protocol (RS485) function library for a Xylem Hydrovar HVL
variable speed pump controller.

This module supports just one slave device on the Modbus, not multiple.

When this module is directly run from the terminal a demo will be shown.

Reference documents:
(1) Hydrovar HVL 2.015 - 4.220 | Modbus Protocol & Parameters
    HVL Software Version: 2.10, 2.20
    cod. 001085110 rev. B ed. 01/2018
(2) Hydrovar HVL 2.015 - 4.220 | Installation, Operation, and Maintenance Manual
    cod. 001085102 rev. A ed. 01/2016
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "27-06-2024"
__version__ = "1.5.0"
# pylint: disable=missing-function-docstring, too-many-lines

import sys
from enum import IntEnum
import time
from typing import Union, Tuple

import numpy as np

from dvg_debug_functions import print_fancy_traceback as pft
from dvg_devices.BaseDevice import SerialDevice
from dvg_devices.XylemHydrovarHVL_CRC_tools import pretty_hex, crc16

# ------------------------------------------------------------------------------
#   accurate_delay_ms
# ------------------------------------------------------------------------------


def accurate_delay_ms(delay):
    """Accurate time delay in milliseconds, useful for delays < 10 ms.
    The standard `time.sleep()` will not work reliably for such small time
    delays and usually has a minimum delay of up to 10 to 20 ms depending
    on the OS.
    """
    _ = time.perf_counter() + delay / 1000
    while time.perf_counter() < _:
        pass


# ------------------------------------------------------------------------------
#   Enumerations
# ------------------------------------------------------------------------------


class HVL_Mode(IntEnum):
    CONTROLLER = 0  # Regulate motor frequency to maintain a pressure setpoint
    ACTUATOR = 3  # Fixed motor frequency


class HVL_FuncCode(IntEnum):
    # Implemented:
    READ = 0x03  # Read the contents of a single register
    WRITE = 0x06  # Write a value into a single register

    # Not implemented:
    WRITE_CONT = 0x10  # Write values into a block of contiguous registers


class HVL_DType(IntEnum):
    U08 = 0
    U16 = 1
    U32 = 2
    S08 = 3
    S16 = 4
    B0 = 5  # 8 bits bitmap
    B1 = 6  # 16 bits bitmap
    B2 = 7  # 32 bits bitmap


# ------------------------------------------------------------------------------
#   HVL_Register
# ------------------------------------------------------------------------------


class HVL_Register:
    """Placeholder for a single Modbus register adress and its datum type. To be
    populated from Table 5, ref (1).
    """

    def __init__(self, address: int, datum_type: HVL_DType):
        self.address = address
        self.datum_type = datum_type


# List of registers (incomplete list, just the bare necessities).
# Taken from Table 5, ref. (1)
# fmt: off

# M00: Main menu
HVLREG_STOP_START    = HVL_Register(0x0031, HVL_DType.U08)  # RW    P-
HVLREG_ACTUAL_VALUE  = HVL_Register(0x0032, HVL_DType.S16)  # R     P-
HVLREG_EFF_REQ_VAL   = HVL_Register(0x0037, HVL_DType.U16)  # R     P03
HVLREG_START_VALUE   = HVL_Register(0x0038, HVL_DType.U08)  # RW    P04

# M20: Status
HVLREG_ENABLE_DEVICE = HVL_Register(0x0061, HVL_DType.U08)  # RW    P24

# M40: Diagnostics
HVLREG_TEMP_INVERTER = HVL_Register(0x0085, HVL_DType.S08)  # R     P43
HVLREG_CURR_INVERTER = HVL_Register(0x0087, HVL_DType.U16)  # R     P44
HVLREG_VOLT_INVERTER = HVL_Register(0x0088, HVL_DType.U16)  # R     P45
HVLREG_OUTPUT_FREQ   = HVL_Register(0x0033, HVL_DType.S16)  # R     P46

# M100: Basic settings
HVLREG_MODE          = HVL_Register(0x008b, HVL_DType.U08)  # RW    P105

# M200: Conf. inverter
HVLREG_MAX_FREQ      = HVL_Register(0x009d, HVL_DType.U16)  # RW    P245
HVLREG_MIN_FREQ      = HVL_Register(0x009e, HVL_DType.U16)  # RW    P250
HVLREG_MOTOR_NOM_CURR= HVL_Register(0x011a, HVL_DType.U32)  # R     P268

# M600: Error
HVLREG_ERROR_RESET   = HVL_Register(0x00d3, HVL_DType.U08)  # RW    P615

# M800: Required values
HVLREG_C_REQ_VAL_1   = HVL_Register(0x00e5, HVL_DType.U08)  # RW    P805
HVLREG_C_REQ_VAL_2   = HVL_Register(0x00e6, HVL_DType.U08)  # RW    P810
HVLREG_SW_REQ_VAL    = HVL_Register(0x00e7, HVL_DType.U08)  # RW    P815
HVLREG_REQ_VAL_1     = HVL_Register(0x00e8, HVL_DType.U16)  # RW    P820
HVLREG_ACTUAT_FREQ_1 = HVL_Register(0x00ea, HVL_DType.U16)  # RW    P830

# M1000: Test run
HVLREG_TEST_RUN      = HVL_Register(0x00f9, HVL_DType.U08)  # RW    P1005

# M1200: RS-485 Interface
HVLREG_ADDRESS       = HVL_Register(0x010d, HVL_DType.U08)  # RW    P1205

# Special status bits
HVLREG_ERRORS_H3     = HVL_Register(0x012d, HVL_DType.B2)   # R     P-
HVLREG_DEV_STATUS_H4 = HVL_Register(0x01c1, HVL_DType.B1)   # R     P-

# fmt: on

# ------------------------------------------------------------------------------
#   XylemHydrovarHVL
# ------------------------------------------------------------------------------


class XylemHydrovarHVL(SerialDevice):
    class State:
        """Container for the process and measurement variables"""

        # fmt: off
        pump_is_on         = False   # (bool)   Excludes coasting down
        pump_is_running    = False   # (bool)   True with any physical movement
        pump_is_enabled    = False   # (bool)   Inverter input terminal 18
        hvl_mode           = HVL_Mode.CONTROLLER  # (HVL_Mode)          P105

        actual_pressure    = np.nan  # [bar]
        wanted_pressure    = 0.0     # [bar]                            P820

        actual_frequency   = np.nan  # [Hz]                             P46
        wanted_frequency   = 0.0     # [Hz]                             P830

        min_frequency      = np.nan  # [Hz]                             P250
        max_frequency      = np.nan  # [Hz]                             P245
        nom_motor_current  = np.nan  # [A]                              P268

        inverter_temp      = np.nan  # ['C]                             P43
        inverter_volt      = np.nan  # [V]                              P45
        inverter_curr_A    = np.nan  # [A]                              P44
        inverter_curr_pct  = np.nan  # [% FS]     derived: P44 / P268 * 100
        # fmt: on

    class ErrorStatus:
        """Container for the Error Status bits (H3)"""

        # fmt: off
        overcurrent       = False  # bit 00, error 11
        overload          = False  # bit 01, error 12
        overvoltage       = False  # bit 02, error 13
        phase_loss        = False  # bit 03, error 16
        inverter_overheat = False  # bit 04, error 14
        motor_overheat    = False  # bit 05, error 15
        lack_of_water     = False  # bit 06, error 21
        minimum_threshold = False  # bit 07, error 22
        act_val_sensor_1  = False  # bit 08, error 23
        act_val_sensor_2  = False  # bit 09, error 24
        setpoint_1_low_mA = False  # bit 10, error 25
        setpoint_2_low_mA = False  # bit 11, error 26
        # fmt: on

        def has_error(self) -> bool:
            error_list = (
                self.overcurrent,
                self.overload,
                self.overvoltage,
                self.phase_loss,
                self.inverter_overheat,
                self.motor_overheat,
                self.lack_of_water,
                self.minimum_threshold,
                self.act_val_sensor_1,
                self.act_val_sensor_2,
                self.setpoint_1_low_mA,
                self.setpoint_2_low_mA,
            )

            return bool(np.any(error_list))

        def report(self):
            """Report the last read error status to the terminal."""

            if not self.has_error():
                print("No errors")
                return

            print("ERRORS DETECTED")
            print("---------------")
            if self.overcurrent:
                print("- #11: OVERCURRENT")
            if self.overload:
                print("- #12: OVERLOAD")
            if self.overvoltage:
                print("- #13: OVERVOLTAGE")
            if self.phase_loss:
                print("- #16: PHASE LOSS")
            if self.inverter_overheat:
                print("- #14: INVERTER OVERHEAT")
            if self.motor_overheat:
                print("- #15: MOTOR OVERHEAT")
            if self.lack_of_water:
                print("- #21: LACK OF WATER")
            if self.minimum_threshold:
                print("- #22: MINIMUM THRESHOLD")
            if self.act_val_sensor_1:
                print("- #23: ACT VAL SENSOR 1")
            if self.act_val_sensor_2:
                print("- #24: ACT VAL SENSOR 2")
            if self.setpoint_1_low_mA:
                print("- #25: SETPOINT 1 I<4 mA")
            if self.setpoint_2_low_mA:
                print("- #26: SETPOINT 2 I<4 mA")

    class DeviceStatus:
        """Container for the Extended Device Status bits (H4).

        Explanation
        -----------
        external_ON_OFF_terminal_enabled:
          Directly linked to the inverter input terminal 18 'ON_OFF'. Will in
          effect enable or disable running the pump.

        device_is_enabled_with_start_button:
          Gets set by ModBus commands 'pump stop' and 'pump start'. Immediate
          response.

        motor_is_running:
          Autonomously set by the inverter as long as movement of the motor
          drive shaft is detected. Includes coasting up and down.
        """

        # fmt: off
        device_is_preset                    = False  # bit 00
        device_is_ready_for_regulation      = False  # bit 01
        device_has_an_error                 = False  # bit 02
        device_has_a_warning                = False  # bit 03
        external_ON_OFF_terminal_enabled    = False  # bit 04
        device_is_enabled_with_start_button = False  # bit 05
        motor_is_running                    = False  # bit 06
        solo_run_ON_OFF                     = False  # bit 14
        inverter_STOP_START                 = False  # bit 15
        # fmt: on

        def report(self):
            """Report the last read device status to the terminal."""

            w = ".<38"  # Width specifier
            print("DEVICE STATUS")
            print("-------------")
            # fmt: off
            print(f"{'- Device is preset':{w}s} {self.device_is_preset}")
            print(f"{'- Device is ready for regulation':{w}s} "
                  f"{self.device_is_ready_for_regulation}")
            print(f"{'- Device has an error':{w}s} {self.device_has_an_error}")
            print(f"{'- Device has a warning':{w}s} {self.device_has_a_warning}")
            print(f"{'- External ON/OFF terminal enabled':{w}s} "
                  f"{self.external_ON_OFF_terminal_enabled}")
            print(f"{'- Device is enabled with start button':{w}s} "
                  f"{self.device_is_enabled_with_start_button}")
            print(f"{'- Motor is running':{w}s} {self.motor_is_running}")
            print(f"{'- Solo-Run ON/OFF':{w}s} {self.solo_run_ON_OFF}")
            print(f"{'- Inverter STOP/START':{w}s} {self.inverter_STOP_START}")
            # fmt: on

    # --------------------------------------------------------------------------
    #   XylemHydrovarHVL
    # --------------------------------------------------------------------------

    def __init__(
        self,
        name: str = "HVL",
        long_name: str = "Xylem Hydrovar HVL pump controller",
        connect_to_modbus_slave_address: int = 0x01,
        max_pressure_setpoint_bar: float = 3,
    ):
        super().__init__(name=name, long_name=long_name)

        # Default for RTU is 9600-8N1
        self.serial_settings = {
            "baudrate": 115200,
            "bytesize": 8,
            "parity": "N",
            "stopbits": 1,
            "timeout": 0.2,
            "write_timeout": 0.2,
        }
        self.set_read_termination("")
        self.set_write_termination("")

        self.set_ID_validation_query(
            ID_validation_query=self.ID_validation_query,
            valid_ID_broad=True,
            valid_ID_specific=connect_to_modbus_slave_address,
        )

        # Software-limited maximum pressure setpoint
        self.max_pressure_setpoint_bar = max_pressure_setpoint_bar

        # Container for the process and measurement variables
        self.state = self.State()
        self.error_status = self.ErrorStatus()
        self.device_status = self.DeviceStatus()

        # Modbus slave address of the device (P1205)
        self.modbus_slave_address = connect_to_modbus_slave_address

        # Modbus demands minimum time between messages
        self._tick_last_msg = time.perf_counter()

    # --------------------------------------------------------------------------
    #   ID_validation_query
    # --------------------------------------------------------------------------

    def ID_validation_query(self) -> Tuple[bool, Union[int, None]]:
        # We're using a query on the Modbus slave address (P1205) as ID
        # validation
        success, data_val = self._RTU_read(HVLREG_ADDRESS)
        return success, data_val

    # --------------------------------------------------------------------------
    #   _calculate_silent_period
    # --------------------------------------------------------------------------

    def _calculate_silent_period(self) -> float:
        """Calculate the silent period length between messages. It should
        correspond to the time to send 3.5 characters.

        Source:
            https://github.com/pyhys/minimalmodbus/blob/master/minimalmodbus.py

        Returns:
            The number of seconds that should pass between each message on the
            bus.
        """
        BITTIMES_PER_CHARACTERTIME = 11
        MIN_SILENT_CHARACTERTIMES = 3.5
        MIN_SILENT_TIME_SECONDS = 0.00175  # See Modbus standard

        bittime = 1 / float(self.ser.baudrate)
        return max(
            bittime * BITTIMES_PER_CHARACTERTIME * MIN_SILENT_CHARACTERTIMES,
            MIN_SILENT_TIME_SECONDS,
        )

    # --------------------------------------------------------------------------
    #   _RTU_read
    # --------------------------------------------------------------------------

    def _RTU_read(self, hvlreg: HVL_Register) -> Tuple[bool, Union[int, None]]:
        """Send a 'read' RTU command over Modbus to the slave device.

        Args:
            hvlreg (HVL_Register):
                `HVL_Register` object containing Modbus address to read from and
                its datum type.

        Returns: (tuple)
            success (bool):
                True if successful, False otherwise.

            data_val (int | None):
                Read data value as raw integer. `None` if unsuccessful.
        """
        if not self.is_alive:
            pft("Device is not connected yet or already closed.", 3)
            return False, None  # --> leaving

        # Construct 'read' command
        byte_cmd = bytearray(8)
        byte_cmd[0] = self.modbus_slave_address
        byte_cmd[1] = HVL_FuncCode.READ
        byte_cmd[2] = (hvlreg.address & 0xFF00) >> 8  # address HI
        byte_cmd[3] = hvlreg.address & 0x00FF  # address LO

        # NOTE: A 'point' is a single register. According to the ModBus
        # specification a single register is always 2 bytes == 16 bits long.
        # 1 point == 1 register == 2 bytes == 16 bits
        byte_cmd[4] = 0x00  # no. of points HI

        # no. of points LO
        if hvlreg.datum_type in (HVL_DType.U32, HVL_DType.B2):
            byte_cmd[5] = 0x02  # 2 points == 32 bits
        else:
            byte_cmd[5] = 0x01  # 1 point == 16 bits

        byte_cmd[6:] = crc16(byte_cmd[:6])

        # Slow down message rate according to Modbus specification
        silent_period = self._calculate_silent_period()
        time_since_last_msg = time.perf_counter() - self._tick_last_msg
        if time_since_last_msg < silent_period:
            accurate_delay_ms((silent_period - time_since_last_msg) * 1000)

        # Send command and read reply
        if hvlreg.datum_type in (HVL_DType.U32, HVL_DType.B2):
            N_expected_reply_bytes = 9
        else:
            N_expected_reply_bytes = 7

        success, reply = self.query_bytes(
            msg=byte_cmd,
            N_bytes_to_read=N_expected_reply_bytes,
        )
        self._tick_last_msg = time.perf_counter()

        # Parse the returned data value
        data_val = None
        if success and isinstance(reply, bytes):
            if len(reply) == N_expected_reply_bytes:
                # All is correct
                byte_count = reply[2]
                if byte_count == 2:
                    data_val = (reply[3] << 8) + reply[4]
                elif byte_count == 4:  # HVL_DType.U32, HVL_DType.B2
                    data_val = (
                        (reply[3] << 32)
                        + (reply[4] << 16)
                        + (reply[5] << 8)
                        + (reply[6])
                    )
                elif byte_count == 8 and hvlreg == HVLREG_MOTOR_NOM_CURR:
                    # HVL reports P268 (nominal motor current) as 8 bytes long,
                    # although it is listed in the manual as 32 bits == 4 bytes
                    # long. Only 4 bytes follow though. Very strange.
                    data_val = (
                        (reply[3] << 32)
                        + (reply[4] << 16)
                        + (reply[5] << 8)
                        + (reply[6])
                    )
                else:
                    pft(
                        f"Unsupported byte count. Got {byte_count}, "
                        "but only 2 and 4 are implemented."
                    )
                    print(f"Reply received: {pretty_hex(reply)}")
                    return False, None  # --> leaving

                if hvlreg.datum_type == HVL_DType.S08:
                    if data_val >= (1 << 7):
                        data_val = data_val - (1 << 8)
                elif hvlreg.datum_type == HVL_DType.S16:
                    if data_val >= (1 << 15):
                        data_val = data_val - (1 << 16)

        if not success and isinstance(reply, bytes):
            # Probably received a Modbus exception.
            # TODO: Test for and parse Modbus exceptions.
            print(f"Reply received: {pretty_hex(reply)}")

        return success, data_val

    # --------------------------------------------------------------------------
    #   _RTU_write
    # --------------------------------------------------------------------------

    def _RTU_write(
        self, hvlreg: HVL_Register, value: int
    ) -> Tuple[bool, Union[int, None]]:
        """Send a 'write' RTU command over Modbus to the slave device.

        Args:
            hvlreg (HVL_Register):
                `HVL_Register` object containing Modbus address to write to and
                its datum type.

            value (int):
                Raw integer value to write to the Modbus address.

        Returns: (tuple)
            success (bool):
                True if successful, False otherwise.

            data_val (int | None):
                Obtained data value as raw integer. `None` if unsuccessful.
        """
        if not self.is_alive:
            pft("Device is not connected yet or already closed.", 3)
            return False, None  # --> leaving

        # Construct 'write' command
        byte_cmd = bytearray(8)
        byte_cmd[0] = self.modbus_slave_address
        byte_cmd[1] = HVL_FuncCode.WRITE
        byte_cmd[2] = (hvlreg.address & 0xFF00) >> 8  # address HI
        byte_cmd[3] = hvlreg.address & 0x00FF  # address LO

        if hvlreg.datum_type in (HVL_DType.U08, HVL_DType.U16):
            byte_cmd[4] = (value & 0xFF00) >> 8  # data HI
            byte_cmd[5] = value & 0x00FF  # data LO
        else:
            pft(
                f"Unsupported datum type. Got {hvlreg.datum_type}, "
                "but only U08 and U16 are implemented."
            )
            return False, None

        byte_cmd[6:] = crc16(byte_cmd[:6])

        # Slow down message rate according to Modbus specification
        silent_period = self._calculate_silent_period()
        time_since_last_msg = time.perf_counter() - self._tick_last_msg
        if time_since_last_msg < silent_period:
            accurate_delay_ms((silent_period - time_since_last_msg) * 1000)

        # Send command and read reply
        N_expected_reply_bytes = 8  # Successful 'write' reply is 8 bytes long

        success, reply = self.query_bytes(
            msg=byte_cmd,
            N_bytes_to_read=N_expected_reply_bytes,
        )
        self._tick_last_msg = time.perf_counter()

        # Parse the returned data value
        data_val = None
        if success and isinstance(reply, bytes):
            if len(reply) == N_expected_reply_bytes:
                # All is correct
                data_val = (reply[4] << 8) + reply[5]

                if hvlreg.datum_type == HVL_DType.S08:
                    data_val = data_val - (1 << 8)
                elif hvlreg.datum_type == HVL_DType.S16:
                    data_val = data_val - (1 << 16)

        if not success and isinstance(reply, bytes):
            # Probably received a Modbus exception.
            # TODO: Test for and parse Modbus exceptions.
            print(f"Reply received: {pretty_hex(reply)}")

        return success, data_val

    # --------------------------------------------------------------------------
    #   begin
    # --------------------------------------------------------------------------

    def begin(self) -> bool:
        """Stop the pump, initialize to safe default parameters and read the
        necessary parameters of the HVL controller and store it in the `state`,
        `error_status` and `device_status` members.

        This method should be called once and immediately after a successful
        connection to the HVL controller has been established.
        """
        success = True
        success &= self.pump_stop()

        # Enable the PID pressure controller inside of the inverter
        success &= self.pump_enable_pressure_PID()

        success &= self.read_hvl_mode()
        success &= self.read_min_frequency()
        success &= self.read_max_frequency()
        success &= self.read_nominal_motor_current()
        success &= self.use_digital_required_value_1()

        # Prevent test run scheduling of the pump
        success &= self.set_test_run(0)

        # Prevent auto-restart of the pump when pressure has dropped
        success &= self.set_start_value(100)  # 100 == Off

        # Set setpoints to lowest possible values for safety
        success &= self.set_wanted_pressure(0)
        success &= self.set_wanted_frequency(self.state.min_frequency)

        success &= self.read_device_status()
        success &= self.read_error_status()

        return success

    # --------------------------------------------------------------------------
    #   Implementations of _RTU_read & _RTU_write
    # --------------------------------------------------------------------------

    def read_hvl_mode(self) -> bool:
        """P105: Read the operation mode of the HVL controller.

        0: Controller (Default)     1 Hydrovar
        1: Cascade Relay            1 Hydrovar and Premium Card
        2: Cascade Serial           More than one pump
        3: Actuator                 1 Hydrovar
        4: Cascade Synchron         All pumps operate on the same frequency

        The Actuator mode is used if the HYDROVAR is a standard VFD with:
        • Fixed speed requirements or
        • An external speed signal is connected.

        Readings will be stored in class member `state`.
        """
        success, data_val = self._RTU_read(HVLREG_MODE)
        if data_val is not None:
            try:
                val = HVL_Mode(data_val)
            except ValueError:
                pft(
                    f"Unsupported HVL mode. Got {data_val}, "
                    "but only 0: Controller and 3: Actuator are supported."
                )
                sys.exit(0)  # Severe error, hence exit
            self.state.hvl_mode = val
            print("Read HVL mode:", val.name, end="")
            print(
                " | Regulate pressure"
                if val == HVL_Mode.CONTROLLER
                else " | Fixed frequency"
            )

        return success

    def set_hvl_mode(self, hvl_mode: HVL_Mode) -> bool:
        """P105: Set the operation mode of the HVL controller.

        0: Controller (Default)     1 Hydrovar
        1: Cascade Relay            1 Hydrovar and Premium Card
        2: Cascade Serial           More than one pump
        3: Actuator                 1 Hydrovar
        4: Cascade Synchron         All pumps operate on the same frequency

        The Actuator mode is used if the HYDROVAR is a standard VFD with:
        • Fixed speed requirements or
        • An external speed signal is connected.

        Readings will be stored in class member `state`.
        """
        try:
            val = HVL_Mode(hvl_mode)
        except ValueError:
            pft(
                f"Unsupported HVL mode. Got {hvl_mode}, "
                "but only 0: Controller and 3: Actuator are supported."
            )
            sys.exit(0)  # Severe error, hence exit
        success, data_val = self._RTU_write(HVLREG_MODE, hvl_mode)
        if data_val is not None:
            val = HVL_Mode(data_val)
            self.state.hvl_mode = val
            print("Set HVL mode:", val.name, end="")
            print(
                " | Regulate pressure"
                if val == HVL_Mode.CONTROLLER
                else " | Fixed frequency"
            )

        return success

    def pump_start(self) -> bool:
        """Readings will be stored in class member `state`."""
        success, data_val = self._RTU_write(HVLREG_STOP_START, 1)
        if data_val is not None:
            val = bool(data_val)
            self.state.pump_is_on = val
            print(f"Pump turned {'ON' if val else 'OFF'}")

        return success

    def pump_stop(self) -> bool:
        """Readings will be stored in class member `state`."""
        success, data_val = self._RTU_write(HVLREG_STOP_START, 0)
        if data_val is not None:
            val = bool(data_val)
            self.state.pump_is_on = val
            print(f"Pump turned {'ON' if val else 'OFF'}")

        return success

    def pump_enable_pressure_PID(self) -> bool:
        """P24: Manually enable the device.

        This setting only takes effects when in HVL mode `CONTROLLER`, i.e. when
        we try to regulate a wanted pressure. It seems to enable the PID
        controller running inside of the inverter. When in HVL mode `ACTUATOR`
        this parameter gets ignored.

        NOTE: Not to be confused with the inverter input terminal 18 'ON_OFF',
        which solely sets the flag `self.state.pump_is_enabled` via
        `self.read_device_status()`.
        """
        success, data_val = self._RTU_write(HVLREG_ENABLE_DEVICE, 1)
        if data_val is not None:
            val = bool(data_val)
            print(f"Pump PID is {'ENABLED' if val else 'DISABLED'}")

        return success

    def pump_disable_pressure_PID(self) -> bool:
        """P24: Manually disable the device.

        This setting only takes effects when in HVL mode `CONTROLLER`, i.e. when
        we try to regulate a wanted pressure. It seems to disable the PID
        controller running inside of the inverter. When in HVL mode `ACTUATOR`
        this parameter gets ignored.

        NOTE: Not to be confused with the inverter input terminal 18 'ON_OFF',
        which solely sets the flag `self.state.pump_is_enabled` via
        `self.read_device_status()`.
        """
        success, data_val = self._RTU_write(HVLREG_ENABLE_DEVICE, 0)
        if data_val is not None:
            val = bool(data_val)
            print(f"Pump PID is {'ENABLED' if val else 'DISABLED'}")

        return success

    def read_actual_pressure(self) -> bool:
        """Read the actual pressure in bar.
        Readings will be stored in class member `state`.
        """
        success, data_val = self._RTU_read(HVLREG_ACTUAL_VALUE)
        if data_val is not None:
            val = float(data_val) / 100
            self.state.actual_pressure = val
            # print(f"Actual pressure : {val:4.2f} bar")

        return success

    def set_wanted_pressure(self, P_bar: float) -> bool:
        """P820: Set the digital required value 1 in bar.
        Readings will be stored in class member `state`.
        """
        # Limit pressure setpoint
        P_bar = max(float(P_bar), 0)
        P_bar = min(float(P_bar), self.max_pressure_setpoint_bar)

        success, data_val = self._RTU_write(HVLREG_REQ_VAL_1, int(P_bar * 100))
        if data_val is not None:
            val = float(data_val) / 100
            self.state.wanted_pressure = val
            print(f"Set wanted pressure : {val:4.2f} bar")

        return success

    def read_wanted_pressure(self) -> bool:
        """P820: Read the digital required value 1 in bar.
        Readings will be stored in class member `state`.
        """
        success, data_val = self._RTU_read(HVLREG_REQ_VAL_1)
        if data_val is not None:
            val = float(data_val) / 100
            self.state.wanted_pressure = val
            print(f"Read wanted pressure: {val:4.2f} bar")

        return success

    def read_min_frequency(self) -> bool:
        """P250: Read the minimum frequency in Hz.
        Readings will be stored in class member `state`.
        """
        success, data_val = self._RTU_read(HVLREG_MIN_FREQ)
        if data_val is not None:
            val = float(data_val) / 10
            self.state.min_frequency = val
            print(f"Read min frequency: {val:.1f} Hz")

        return success

    def read_max_frequency(self) -> bool:
        """P245: Read the maximum frequency in Hz.
        Readings will be stored in class member `state`.
        """
        success, data_val = self._RTU_read(HVLREG_MAX_FREQ)
        if data_val is not None:
            val = float(data_val) / 10
            self.state.max_frequency = val
            print(f"Read max frequency: {val:.1f} Hz")

        return success

    def read_nominal_motor_current(self) -> bool:
        """P268: Read the nominal motor current in A.
        Readings will be stored in class member `state`.
        """
        success, data_val = self._RTU_read(HVLREG_MOTOR_NOM_CURR)
        if data_val is not None:
            val = float(data_val) / 100
            self.state.nom_motor_current = val
            print(f"Read nominal motor current: {val:.2f} A")

        return success

    def read_actual_frequency(self) -> bool:
        """Read the actual frequency of the inverter in Hz.
        Readings will be stored in class member `state`.
        """
        success, data_val = self._RTU_read(HVLREG_OUTPUT_FREQ)
        if data_val is not None:
            val = float(data_val) / 10
            self.state.actual_frequency = val
            # print(f"Actual frequency: {val:4.1f} Hz")

        return success

    def set_wanted_frequency(self, f_Hz: float) -> bool:
        """P830: Set the required frequency 1 for Actuator mode in Hz.
        Readings will be stored in class member `state`.
        """
        # Limit frequency setpoint
        f_Hz = min(f_Hz, self.state.max_frequency)
        f_Hz = max(f_Hz, self.state.min_frequency)

        # TODO: Check for Modbus 'ILLEGAL DATA VALUE' exception
        # Second reply byte reads 0x86 in that case
        success, data_val = self._RTU_write(
            HVLREG_ACTUAT_FREQ_1, int(f_Hz * 10)
        )
        if data_val is not None:
            val = float(data_val) / 10
            self.state.wanted_frequency = val
            print(f"Set wanted frequency: {val:4.1f} Hz")

        return success

    def read_wanted_frequency(self) -> bool:
        """P830: Read the required frequency 1 for Actuator mode in Hz.
        Readings will be stored in class member `state`.
        """
        success, data_val = self._RTU_read(HVLREG_ACTUAT_FREQ_1)
        if data_val is not None:
            val = float(data_val) / 10
            self.state.wanted_frequency = val
            print(f"Read wanted frequency: {val:4.1f} Hz")

        return success

    def set_start_value(self, pct: float) -> bool:
        """P04: This parameter defines, in percentage (0-100%) of the required
        value (P02 REQUIRED VAL.), the start value after pump stops. If P02
        REQUIRED VAL. is met and there is no more consumption, then the pump
        stops. The pump starts again when the pressure drops below P04 START
        VALUE. Value 100% makes this parameter not effective (100%=off)!
        """
        pct = max(pct, 0)
        pct = min(pct, 100)
        success, data_val = self._RTU_write(HVLREG_START_VALUE, int(pct))
        if data_val is not None:
            val = float(data_val)
            print(f"Set start value: {val:.0f} %")

        return success

    def set_error_reset(self, flag: Union[int, bool]) -> bool:
        """P615: Select automatic reset of errors."""
        success, data_val = self._RTU_write(HVLREG_ERROR_RESET, int(flag))
        if data_val is not None:
            val = int(data_val)
            print(f"Set error reset: {val}")

        return success

    def read_error_status(self) -> bool:
        """Readings will be stored in class member `error_status`."""
        success, data_val = self._RTU_read(HVLREG_ERRORS_H3)
        if data_val is not None:
            s = self.error_status  # Shorthand
            # fmt: off
            s.overcurrent       = bool(data_val & (1 << 0))
            s.overload          = bool(data_val & (1 << 1))
            s.overvoltage       = bool(data_val & (1 << 2))
            s.phase_loss        = bool(data_val & (1 << 3))
            s.inverter_overheat = bool(data_val & (1 << 4))
            s.motor_overheat    = bool(data_val & (1 << 5))
            s.lack_of_water     = bool(data_val & (1 << 6))
            s.minimum_threshold = bool(data_val & (1 << 7))
            s.act_val_sensor_1  = bool(data_val & (1 << 8))
            s.act_val_sensor_2  = bool(data_val & (1 << 9))
            s.setpoint_1_low_mA = bool(data_val & (1 << 10))
            s.setpoint_2_low_mA = bool(data_val & (1 << 11))
            # fmt: on
            # s.report()

        return success

    def read_device_status(self) -> bool:
        """Readings will be stored in class member `device_status`. Also, class
        members `state.pump_is_on, `state.pump_is_running` and
        `state.pump_is_enabled` will be updated.
        """
        success, data_val = self._RTU_read(HVLREG_DEV_STATUS_H4)
        if data_val is not None:
            s = self.device_status  # Shorthand
            # fmt: off
            s.device_is_preset                    = bool(data_val & (1 << 0))
            s.device_is_ready_for_regulation      = bool(data_val & (1 << 1))
            s.device_has_an_error                 = bool(data_val & (1 << 2))
            s.device_has_a_warning                = bool(data_val & (1 << 3))
            s.external_ON_OFF_terminal_enabled    = bool(data_val & (1 << 4))
            s.device_is_enabled_with_start_button = bool(data_val & (1 << 5))
            s.motor_is_running                    = bool(data_val & (1 << 6))
            s.solo_run_ON_OFF                     = bool(data_val & (1 << 14))
            s.inverter_STOP_START                 = bool(data_val & (1 << 15))
            # fmt: on
            # s.report()

            self.state.pump_is_on = s.device_is_enabled_with_start_button
            self.state.pump_is_running = s.motor_is_running
            self.state.pump_is_enabled = s.external_ON_OFF_terminal_enabled

        return success

    def read_inverter_diagnostics(self) -> bool:
        """P43, P44, P45: Read out the diagnostic values (temperature, current
        and voltage) of the inverter.
        Readings will be stored in class member `state`.
        """
        success_1, data_val = self._RTU_read(HVLREG_TEMP_INVERTER)
        if data_val is not None:
            val = float(data_val)
            self.state.inverter_temp = val
            # print(f"Read inverter temperature: {val:5.0f} 'C")

        success_2, data_val = self._RTU_read(HVLREG_VOLT_INVERTER)
        if data_val is not None:
            val = float(data_val)
            self.state.inverter_volt = val
            # print(f"Read inverter voltage    : {val:5.0f} V")

        success_3, data_val = self._RTU_read(HVLREG_CURR_INVERTER)
        if data_val is not None:
            val = float(data_val) / 100
            self.state.inverter_curr_A = val
            self.state.inverter_curr_pct = (
                val / self.state.nom_motor_current * 100
            )
            # print(f"Read inverter current    : {val:5.2f} A")
            # print(f"Read inverter current    : {self.state.inverter_curr_pct:5.1f} %")

        return success_1 and success_2 and success_3

    def use_digital_required_value_1(self) -> bool:
        """P805, P810, P815: Set up the registers to make use of a digitally
        supplied required value 1 and disable the required value 2."""

        success_1, _ = self._RTU_write(HVLREG_C_REQ_VAL_1, 1)  # 1: Dig
        success_2, _ = self._RTU_write(HVLREG_C_REQ_VAL_2, 0)  # 0: Off
        success_3, _ = self._RTU_write(HVLREG_SW_REQ_VAL, 0)  # 0: Setp. 1

        return success_1 and success_2 and success_3

    def set_test_run(self, hours) -> bool:
        """P1005: Controls the automatic test run, which starts up the pump
        after the last stop, to prevent the pump from blocking (possible setting
        are "Off" or "After 100 hrs".
        """
        # Limit hours
        hours = min(hours, 100)
        hours = max(hours, 0)
        success, _ = self._RTU_write(HVLREG_TEST_RUN, hours)

        return success


# -----------------------------------------------------------------------------
#   Main: Will show a demo when run from the terminal
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    # Path to the textfile containing the (last used) serial port
    PATH_PORT = "config/port_Hydrovar.txt"

    pump = XylemHydrovarHVL(
        connect_to_modbus_slave_address=0x01,
        max_pressure_setpoint_bar=3,
    )
    pump.serial_settings = {
        "baudrate": 115200,
        "bytesize": 8,
        "parity": "N",
        "stopbits": 1,
        "timeout": 0.2,
        "write_timeout": 0.2,
    }

    if pump.auto_connect(PATH_PORT):
        pump.begin()
    else:
        sys.exit(0)

    # Report
    pump.device_status.report()
    pump.error_status.report()
    pump.read_inverter_diagnostics()
    print(f"Read inverter temperature: {pump.state.inverter_temp:5.0f} 'C")
    print(f"Read inverter voltage    : {pump.state.inverter_volt:5.0f} V")
    print(f"Read inverter current    : {pump.state.inverter_curr_A:5.2f} A")
    print(f"Read inverter current    : {pump.state.inverter_curr_pct:5.1f} %")
    pump.read_actual_pressure()
    print(f"Actual pressure : {pump.state.actual_pressure:4.2f} bar")
    pump.read_actual_frequency()
    print(f"Actual frequency: {pump.state.actual_frequency:4.1f} Hz")

    # pump.set_error_reset(False)
    # pump.set_mode(HVL_Mode.CONTROLLER)
    # pump.set_wanted_pressure(1)
    # pump.read_wanted_pressure()

    # sys.exit(0)

    # Determine ModBus message round-trip time
    print("Determining ModBus round-trip time...")
    N = 100
    tick = time.perf_counter()
    for i in range(N):
        pump.read_actual_pressure()
    print(f"  {(time.perf_counter() - tick)*1000/N:.0f} ms")
