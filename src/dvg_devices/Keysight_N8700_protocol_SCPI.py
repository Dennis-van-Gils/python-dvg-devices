#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Function library for Keysight series N8700 power supplies (PSU) over SCPI.

Communication errors will be handled as non-fatal. This means it will struggle
on with the script while reporting error messages to the command line output,
as opposed to terminating the program completely.

State variables that read numpy.nan indicate that they are uninitialized or that
the previous query resulted in a communication error.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "04-04-2024"
__version__ = "1.4.0"
# pylint: disable=missing-function-docstring, multiple-statements, broad-except

import os
import time
from pathlib import Path

import pyvisa
import numpy as np

from dvg_debug_functions import print_fancy_traceback
from dvg_pid_controller import PID_Controller

# 'No error left' reply from the PSU
STR_NO_ERROR = "ERR 0"

# VISA settings
VISA_TIMEOUT = 4000  # 4000 [msec]

# Default config file path
PATH_CONFIG = Path(os.getcwd() + "/config/settings_Keysight_PSU.txt")


class Keysight_N8700:
    class State:
        """Container for the process and measurement variables.
        [numpy.nan] values indicate that the parameter is not initialized or
        that the last query was unsuccessful in communication.
        """

        # fmt: off
        V_source: float = 0     # Voltage to be sourced [V]
        I_source: float = 0     # Current to be sourced [A]
        P_source: float = 0     # Power to be sourced, when PID controller is on [W]
        ENA_PID : bool = False  # Is the PID controller on the power output enabled?

        V_meas: float = np.nan  # Measured output voltage [V]
        I_meas: float = np.nan  # Measured output current [A]
        P_meas: float = np.nan  # Derived output power    [W]

        OVP_level : float = np.nan  # Over-voltage protection level [V]
        ENA_OCP   : bool = False    # Is over-current protection enabled?
        ENA_output: bool= False     # Is power output enabled (by software)?
        # fmt: on

        # The single error string retreived from the error queue of the device.
        # None indicates no error is left in the queue.
        error: str | None = None

        # This list of strings is provided to be able to store all errors from
        # the device queue. This list is populated by calling 'query_error'
        # until no error is left in the queue. This list can then be printed to
        # screen or GUI and the user should 'acknowledge' the list, after which
        # the list can be emptied (=[]) again.
        all_errors: list[str] = []

        # Questionable condition status registers
        # fmt: off
        status_QC_OV : bool = False  # Output disabled by over-voltage protection
        status_QC_OC : bool = False  # Output disabled by over-current protection
        status_QC_PF : bool = False  # Output disabled because AC power failed
        status_QC_OT : bool = False  # Output disabled by over-temperature protection
        status_QC_INH: bool = False  # Output turned off by external J1 inhibit signal (ENABLE)
        status_QC_UNR: bool = False  # The output is unregulated

        # Operation condition status registers
        status_OC_WTG: bool = False  # Unit waiting for transient trigger
        status_OC_CV : bool = False  # Output in constant voltage
        status_OC_CC : bool = False  # Output in constant current
        # fmt: on

    class Config:
        # fmt: off
        V_source : float = 120       # Voltage to be sourced [V]
        I_source : float = 1         # Current to be sourced [A]
        P_source : float = 0         # Power   to be sourced [W]
        OVP_level: float = 126       # Over-voltage protection level [V]
        ENA_OCP  : bool  = True      # Is over-current protection enabled?
        # fmt: on

    # --------------------------------------------------------------------------
    #   __init__
    # --------------------------------------------------------------------------

    def __init__(
        self,
        visa_address: str = "",
        path_config=PATH_CONFIG,
        name="PSU",
    ):
        """
        Args:
            visa_address (`str`):
                VISA device address.

            path_config (`pathlib.Path`):
                Path to the configuration file.
        """
        self._visa_address = visa_address
        self.name = name
        self._idn: str = ""  # The identity of the device ("*IDN?")

        # Placeholder for the VISA device instance
        self.device: pyvisa.resources.MessageBasedResource | None = None

        # Is the connection to the device alive?
        self.is_alive: bool = False

        # Container for the process and measurement variables
        self.state = self.State()
        self.config = self.Config()

        # Location of the configuration file
        self.path_config: Path = path_config

        # Placeholder for a future PID controller on the power output
        self.PID_power = PID_Controller(Kp=0, Ki=0, Kd=0)

    # --------------------------------------------------------------------------
    #   close
    # --------------------------------------------------------------------------

    def close(self):
        if (not self.is_alive) or (self.device is None):
            # print("ERROR: Device is already closed.")
            pass  # Remain silent. Device is already closed.
        else:
            self.device.close()
            self.is_alive = False

    # --------------------------------------------------------------------------
    #   connect
    # --------------------------------------------------------------------------

    def connect(self, rm: pyvisa.ResourceManager) -> bool:
        """Try to connect to the PSU over VISA at the given address. When
        successful the VISA device instance will be stored in member 'device'
        and its identity is queried and stored in '_idn'.

        Args:
            rm `(pyvisa.ResourceManager)`:
                Instance of VISA ResourceManager.

        Returns: True if successful, False otherwise.
        """
        self.is_alive = False

        print("Connect to: Keysight N8700 series PSU")
        print(f"  @ {self._visa_address} : ", end="")

        try:
            device = rm.open_resource(self._visa_address, timeout=VISA_TIMEOUT)
            device.clear()
        except pyvisa.VisaIOError:
            print("Could not open resource.\n")
            return False
        except Exception as err:
            raise err

        if not isinstance(device, pyvisa.resources.MessageBasedResource):
            print("ERROR: Device is not a `MessageBasedResource`.")
            return False

        print("Success!")
        self.device = device
        self.is_alive = True

        _success, reply = self.query("*idn?")
        self.wait_for_OPC()

        if not isinstance(reply, str):
            return False

        self._idn = reply
        print(f"  {self._idn}\n")
        return True

    # --------------------------------------------------------------------------
    #   begin
    # --------------------------------------------------------------------------

    def begin(self) -> bool:
        """This function should run directly after having established a
        connection to a Keysight PSU.

        Returns: True if all messages were sent and received successfully,
            False otherwise.
        """
        # Clear errors
        self.state.error = None
        self.state.all_errors = []

        if not self.is_alive or self.device is None:
            print("ERROR: Device is not connected yet or already closed.")
            return False

        # We must clear the device to resolve intermittent I/O communication
        # problems particular to this PSU.
        self.device.clear()
        time.sleep(0.01)

        success = True
        success &= self.set_PON_off()  # Force power-on state off for safety

        self.wait_for_OPC()
        # BELOW IS COMMENTED OUT because .stb fails intermittently, perhaps due
        # to the USB isolator
        # self.prepare_wait_for_OPC_indefinitely()

        success &= self.query_OVP_level()
        success &= self.query_V_source()
        success &= self.query_I_source()
        success &= self.query_ENA_OCP()
        success &= self.query_status_QC()
        success &= self.query_status_OC()

        self.query_all_errors_in_queue()

        # BELOW IS COMMENTED OUT because .stb fails intermittently, perhaps due
        # to the USB isolator
        # self.wait_for_OPC_indefinitely()
        self.wait_for_OPC()

        return success

    # --------------------------------------------------------------------------
    #   reinitialize
    # --------------------------------------------------------------------------

    def reinitialize(self) -> bool:
        """Reinitialize the PSU, including clear and reset

        Returns: True if all messages were sent and received successfully,
            False otherwise.
        """
        # Clear errors
        self.state.error = None
        self.state.all_errors = []

        if not self.is_alive or self.device is None:
            print("ERROR: Device is not connected yet or already closed.")
            return False

        # Clear device's input and output buffers
        self.device.clear()

        success = True
        success &= self.clear_and_reset()
        success &= self.set_PON_off()
        success &= self.set_OVP_level(self.config.OVP_level)
        success &= self.set_V_source(self.config.V_source)
        success &= self.set_I_source(self.config.I_source)
        self.state.P_source = self.config.P_source
        self.state.ENA_PID = False
        success &= self.set_ENA_OCP(self.config.ENA_OCP)

        self.wait_for_OPC()
        self.prepare_wait_for_OPC_indefinitely()

        success &= self.query_OVP_level()
        success &= self.query_V_source()
        success &= self.query_I_source()
        success &= self.query_ENA_OCP()
        success &= self.query_status_QC()
        success &= self.query_status_OC()

        self.query_all_errors_in_queue()

        self.wait_for_OPC_indefinitely()

        return success

    # --------------------------------------------------------------------------
    #   write
    # --------------------------------------------------------------------------

    def write(self, msg_str) -> bool:
        """Try to write a command to the device.

        Args:
            msg_str (`str`):
                Message to be sent.

        Returns: True if the message was sent successfully, False otherwise.
            NOTE: It does not indicate whether the message made sense to the
            device.
        """

        if not self.is_alive or self.device is None:
            print("ERROR: Device is not connected yet or already closed.")
            return False

        try:
            self.device.write(msg_str)
        except pyvisa.VisaIOError as err:
            # Print error and struggle on
            print_fancy_traceback(err)
            return False
        except Exception as err:
            raise err

        return True

    # --------------------------------------------------------------------------
    #   query
    # --------------------------------------------------------------------------

    def query(self, msg_str: str) -> tuple[bool, str | None]:
        """Try to query the device.

        Args:
            msg_str (`str`):
                Message to be sent.

        Returns:
            success (`bool`):
                True if the message was sent and a reply was received
                successfully, False otherwise.

            reply (`str` | `None`):
                Reply received from the device. None if unsuccessful.
        """
        success = False
        reply = None

        if not self.is_alive or self.device is None:
            print("ERROR: Device is not connected yet or already closed.")
            return success, reply

        try:
            reply = self.device.query(msg_str)
        except pyvisa.VisaIOError as err:
            # Print error and struggle on
            print_fancy_traceback(err)
        except Exception as err:
            raise err
        else:
            reply = reply.strip()
            success = True

        return success, reply

    # --------------------------------------------------------------------------
    #   System status related
    # --------------------------------------------------------------------------

    def clear_and_reset(self) -> bool:
        """Clear device status and reset. Return when this operation has
        completed on the device. Blocking.

        Returns: True if the message was sent successfully, False otherwise.
        """

        if not self.is_alive or self.device is None:
            print("ERROR: Device is not connected yet or already closed.")
            return False

        # The reset operation can take a long time to complete. Momentarily
        # increase the timeout to 2000 msec if necessary.
        self.device.timeout = max(self.device.timeout, 2000)

        # Send clear and reset
        success = self.write("*cls;*rst")

        # Wait for the last operation to finish before timeout expires
        self.wait_for_OPC()

        # Restore timeout
        self.device.timeout = VISA_TIMEOUT

        return success

    def wait_for_OPC(self) -> bool:
        """'Operation complete' query, used for event synchronization.

        Will wait for all device operations to complete or until a timeout is
        triggered. Blocking.

        Returns True if successful, False otherwise.
        """
        # Returns an ASCII "+1" when all pending overlapped operations have been
        # completed.
        _success, reply = self.query("*opc?")
        if reply == "1":
            return True

        print(f"Warning: *opc? timed out at device {self.name}")
        return False

    def wait_for_OPC_indefinitely(self):
        """Poll OPC status bit for 'operation complete', used for event
        synchronization.

        Will wait indefinitely for all device operations to complete. Blocking.

        Make sure that the ESR is set to signal bit 0 - OPC (operation complete)
        before you call this function. This can be done by calling
        'prepare_wait_for_OPC_indefinitely()'.
        """

        if not self.is_alive or self.device is None:
            print("ERROR: Device is not connected yet or already closed.")
            return

        # Let the device set the ESR bit 0 - OPC (operation complete) to 1 after
        # all device operations have completed.
        self.write("*opc")

        # Poll the OPC status bit for 'operation complete'. This is the 5th
        # bit.
        while not (self.device.stb & 0b100000) == 0b100000:
            time.sleep(0.01)

        # Reset the ESR bit 0 - OPC back to 0.
        self.query("*esr?")

    def prepare_wait_for_OPC_indefinitely(self) -> bool:
        """Set the ESR to signal bit 0 - OPC (operation complete). Should be
        called only once after a '*rst' in case you want to make use of
        'wait_for_OPC_indefinitely()'.

        Returns: True if the message was sent successfully, False otherwise.
        """
        return self.write("*ese 1")

    def query_error(self, verbose: bool = False) -> bool:
        """Pop one error string from the error queue of the device and store it
        in the 'State'-class member. A value of None indicates no error is left.

        Returns: True if the query was received successfully, False otherwise.
        """
        success, reply = self.query("err?")
        if isinstance(reply, str):
            if reply.find(STR_NO_ERROR) == 0:
                self.state.error = None
            else:
                self.state.error = reply.strip("ERR").strip()
                if verbose:  # DEBUG INFO
                    print(f"  {self.state.error}")
        return success

    def query_all_errors_in_queue(self, verbose: bool = False):
        """Check if there are errors in the device queue and retrieve all if
        any and append these to 'state.all_errors'.
        """
        if not self.is_alive or self.device is None:
            print("ERROR: Device is not connected yet or already closed.")
            return

        # if (self.device.stb & 0b100) == 0b100:
        # There are unread errors in the queue available. Retrieve all.
        while True:
            if self.query_error():
                if self.state.error is None:
                    break

                self.state.all_errors.append(self.state.error)
            else:
                break

        if verbose:  # DEBUG INFO
            for error in self.state.all_errors:
                print(f"  {error}")

    def query_status_QC(self, verbose: bool = False) -> bool:
        """Read out the questionable condition status registers of the device
        and store them in the 'State'-class members.

        Returns: True if the query was received successfully, False otherwise.
        """
        success, reply = self.query("stat:ques:cond?")
        if isinstance(reply, str):
            # fmt: off
            status_code = int(reply)
            self.state.status_QC_OV  = bool(status_code & 1)
            self.state.status_QC_OC  = bool(status_code & 2)
            self.state.status_QC_PF  = bool(status_code & 4)
            self.state.status_QC_OT  = bool(status_code & 16)
            self.state.status_QC_INH = bool(status_code & 512)
            self.state.status_QC_UNR = bool(status_code & 1024)

            if verbose:  # DEBUG INFO
                if self.state.status_QC_OV:  print("  OV")
                if self.state.status_QC_OC:  print("  OC")
                if self.state.status_QC_PF:  print("  PF")
                if self.state.status_QC_OT:  print("  OT")
                if self.state.status_QC_INH: print("  INH")
                if self.state.status_QC_UNR: print("  UNH")
            # fmt: on

        return success

    def query_status_OC(self, verbose: bool = False) -> bool:
        """Read out the operation condition status registers of the device
        and store them in the 'State'-class members.

        Returns: True if the query was received successfully, False otherwise.
        """
        success, reply = self.query("stat:oper:cond?")
        if isinstance(reply, str):
            # fmt: off
            status_code = int(reply)
            self.state.status_OC_WTG = bool(status_code & 32)
            self.state.status_OC_CV  = bool(status_code & 256)
            self.state.status_OC_CC  = bool(status_code & 1024)

            if verbose:  # DEBUG INFO
                if self.state.status_OC_WTG: print("  WTG")
                if self.state.status_OC_CV : print("  CV")
                if self.state.status_OC_CC : print("  CC")
            # fmt: on

        return success

    # --------------------------------------------------------------------------
    #   set_PON_off
    # --------------------------------------------------------------------------

    def set_PON_off(self) -> bool:
        """Set the power-on state of the PSU to off.

        Returns: True if the message was sent successfully, False otherwise.
        """
        return self.write("outp:pon:stat rst")

    # --------------------------------------------------------------------------
    #   Protection related
    # --------------------------------------------------------------------------

    def clear_output_protection(self) -> bool:
        """Clear the latched signals that have disabled the output. The
        over-voltage and over-current conditions are always latching. The over-
        temperature condition, AC-fail condition, Enable pins, and SO pins are
        latching if OUTPut:PON:STATe is RST, and non-latching if
        OUTPut:PON:STATe is AUTO. All conditions that generate the fault must be
        removed before the latch can be cleared. The output is then restored to
        the state it was in before the fault condition occurred.

        Returns: True if the message was sent successfully, False otherwise.
        """
        return self.write("outp:prot:cle")

    """These commands enable or disable the over-current protection (OCP)
    function. The enabled state is On (1); the disabled state is Off (0). If the
    over-current protection function is enabled and the output goes into
    constant current operation, the output is disabled and OC is set in the
    Questionable Condition status register. The *RST value = Off.

    An over-current condition can be cleared with the Output Protection Clear
    command after the cause of the condition is removed
    """

    def set_ENA_OCP(self, flag: bool = True) -> bool:
        """
        Returns: True if the message was sent successfully, False otherwise.
        """
        if flag:
            success = self.write("sour:curr:prot:stat on")
            if success:
                self.state.ENA_OCP = True
        else:
            success = self.write("sour:curr:prot:stat off")
            if success:
                self.state.ENA_OCP = False
        return success

    def query_ENA_OCP(self, verbose: bool = False) -> bool:
        """
        Returns: True if the query was received successfully, False otherwise.
        """
        _success, reply = self.query("sour:curr:prot:stat?")
        if isinstance(reply, str):
            self.state.ENA_OCP = bool(int(reply))
            if verbose:  # DEBUG INFO
                print(self.state.ENA_OCP)
            return True

        return False

    """These commands set the over-voltage protection (OVP) level of the
    output. The values are programmed in volts. If the output voltage exceeds
    the OVP level, the output is disabled and OV is set in the Questionable
    Condition status register. The *RST value = Max.

    The range of values that can be programmed for this command is coupled with
    the immediate voltage level setting. The minimum value for the voltage
    protection level is either the value in the following table (see manual), or
    the immediate voltage setting multiplied by 1.05; whichever is higher. The
    maximum setting is the value in the table.

    An over-voltage condition can be cleared with the Output Protection Clear
    command after the condition that caused the OVP trip is removed.
    """

    def set_OVP_level(self, voltage_V: float) -> bool:
        """
        Returns: True if the message was sent successfully, False otherwise.
        """
        self.state.OVP_level = voltage_V
        return self.write(f"sour:volt:prot:lev {voltage_V:.5f}")

    def query_OVP_level(self, verbose: bool = False) -> bool:
        """
        Returns: True if the query was received successfully, False otherwise.
        """
        _success, reply = self.query("sour:volt:prot:lev?")
        if isinstance(reply, str):
            self.state.OVP_level = float(reply)
            if verbose:  # DEBUG INFO
                print(self.state.OVP_level)
            return True

        return False

    # --------------------------------------------------------------------------
    #   Output related
    # --------------------------------------------------------------------------

    def clear_output_protection_and_turn_on(self) -> bool:
        """Combine instructions 'clear output protection' and 'turn on output'
        into one SCPI message.

        Returns: True if the message was sent successfully, False otherwise.
        """
        success = self.write("outp:prot:cle;*opc;:outp on")
        if success:
            self.state.ENA_output = True
        return success

    def turn_on(self) -> bool:
        """
        Returns: True if the message was sent successfully, False otherwise.
        """
        return self.set_ENA_output(True)

    def turn_off(self) -> bool:
        """
        Returns: True if the message was sent successfully, False otherwise.
        """
        return self.set_ENA_output(False)

    def set_ENA_output(self, flag: bool) -> bool:
        """
        Returns: True if the message was sent successfully, False otherwise.
        """
        if flag:
            success = self.write("outp on")
            if success:
                self.state.ENA_output = True
        else:
            success = self.write("outp off")
            if success:
                self.state.ENA_output = False
        return success

    def query_ENA_output(self, verbose: bool = False) -> bool:
        """
        Returns: True if the query was received successfully, False otherwise.
        """
        _success, reply = self.query("outp?")
        if isinstance(reply, str):
            self.state.ENA_output = bool(int(reply))
            if verbose:  # DEBUG INFO
                print(self.state.ENA_output)
            return True

        return False

    def set_I_source(self, current_A: float) -> bool:
        """
        Returns: True if the message was sent successfully, False otherwise.
        """
        self.state.I_source = current_A
        return self.write(f"sour:curr {current_A:.5f}")

    def set_V_source(self, voltage_V: float) -> bool:
        """
        Returns: True if the message was sent successfully, False otherwise.
        """
        self.state.V_source = voltage_V
        return self.write(f"sour:volt {voltage_V:.5f}")

    def query_I_source(self, verbose: bool = False) -> bool:
        """
        Returns: True if the query was received successfully, False otherwise.
        """
        _success, reply = self.query("sour:curr?")
        if isinstance(reply, str):
            self.state.I_source = float(reply)
            if verbose:  # DEBUG INFO
                print(self.state.I_source)
            return True

        return False

    def query_V_source(self, verbose: bool = False) -> bool:
        """
        Returns: True if the query was received successfully, False otherwise.
        """
        _success, reply = self.query("sour:volt?")
        if isinstance(reply, str):
            self.state.V_source = float(reply)
            if verbose:  # DEBUG INFO
                print(self.state.V_source)
            return True

        return False

    def query_I_meas(self, verbose: bool = False) -> bool:
        """
        Returns: True if the query was received successfully, False otherwise.
        """
        _success, reply = self.query("meas:curr?")
        if isinstance(reply, str):
            self.state.I_meas = float(reply)
            self.state.P_meas = self.state.I_meas * self.state.V_meas
            if verbose:  # DEBUG INFO
                print(self.state.I_meas)
            return True

        return False

    def query_V_meas(self, verbose: bool = False) -> bool:
        """
        Returns: True if the query was received successfully, False otherwise.
        """
        _success, reply = self.query("meas:volt?")
        if isinstance(reply, str):
            self.state.V_meas = float(reply)
            self.state.P_meas = self.state.I_meas * self.state.V_meas
            if verbose:  # DEBUG INFO
                print(self.state.V_meas)
            return True

        return False

    # --------------------------------------------------------------------------
    #   Speed tests for debugging
    # --------------------------------------------------------------------------

    def speed_test(self):
        """Results:
        Each iteration takes 208 ms to finish.
        Total time ~ 20.8 s
        """
        self.set_ENA_output(False)  # Disable output for safety
        self.wait_for_OPC()

        tic = time.perf_counter()

        for i in range(100):
            self.set_V_source(i)
            self.wait_for_OPC()

        print(time.perf_counter() - tic)
        self.report()

    def speed_test2(self):
        """Results:
        Each iteration takes 43 ms to finish.
        Total time ~ 4.3 s
        """
        self.set_ENA_output(False)  # Disable output for safety
        self.wait_for_OPC()

        tic = time.perf_counter()

        for i in range(100):
            self.set_V_source(i)

        self.wait_for_OPC_indefinitely()

        print(time.perf_counter() - tic)
        self.report()

    # --------------------------------------------------------------------------
    #   report
    # --------------------------------------------------------------------------

    def report(self):
        """Report to terminal."""
        print("\nQuestionable condition")
        print(chr(0x2015) * 26)
        self.query_status_QC(True)

        print("\nOperation condition")
        print(chr(0x2014) * 26)
        self.query_status_OC(True)

        print("\nError")
        print(chr(0x2014) * 26)
        self.query_error(True)
        while not self.state.error is None:
            self.query_error(True)

        print("\nProtection")
        print(chr(0x2014) * 26)
        # fmt: off
        print("  ENA_output?  : ", end=''); self.query_ENA_output(True)
        print("  ENA_OCP?     : ", end=''); self.query_ENA_OCP(True)
        print("  OVP level [V]: ", end=''); self.query_OVP_level(True)
        print("  V_source  [V]: ", end=''); self.query_V_source(True)
        print("  I_source  [A]: ", end=''); self.query_I_source(True)

        print("\nMeasure")
        print(chr(0x2014)*26)
        print("  V_meas    [V]: ", end=''); self.query_V_meas(True)
        print("  I_meas    [A]: ", end=''); self.query_I_meas(True)
        # fmt: on

    # --------------------------------------------------------------------------
    #   read_config_file
    # --------------------------------------------------------------------------

    def read_config_file(self) -> bool:
        """Try to open the config textfile containing:
             V_source       # Voltage to be sourced [V]
             I_source       # Current to be sourced [A]
             P_source       # Power   to be sourced [W]
             OVP_level      # Over-voltage protection level [V]
             ENA_OCP        # Is over-current protection enabled?

        Do not panic if the file does not exist or cannot be read.

        Returns: True if successful, False otherwise.
        """
        if isinstance(self.path_config, Path):
            if self.path_config.is_file():
                try:
                    with self.path_config.open(encoding="utf-8") as f:
                        self.config.V_source = float(f.readline().strip())
                        self.config.I_source = float(f.readline().strip())
                        self.config.P_source = float(f.readline().strip())
                        self.config.OVP_level = float(f.readline().strip())
                        self.config.ENA_OCP = (
                            f.readline().strip().lower() == "true"
                        )

                    return True
                except Exception:
                    pass  # Do not panic and remain silent

        return False

    # --------------------------------------------------------------------------
    #   write_config_file
    # --------------------------------------------------------------------------

    def write_config_file(self) -> bool:
        """Try to write the config textfile containing:
             V_source       # Voltage to be sourced [V]
             I_source       # Current to be sourced [A]
             P_source       # Power   to be sourced [W]
             OVP_level      # Over-voltage protection level [V]
             ENA_OCP        # Is over-current protection enabled?

        Do not panic if the file does not exist or cannot be read.

        Returns: True if successful, False otherwise.
        """
        if isinstance(self.path_config, Path):
            if not self.path_config.parent.is_dir():
                # Subfolder does not exists yet. Create.
                try:
                    self.path_config.parent.mkdir()
                except Exception:
                    pass  # Do not panic and remain silent

            try:
                # Write the config file
                self.path_config.write_text(
                    f"{self.state.V_source:.2f}\n"
                    f"{self.state.I_source:.3f}\n"
                    f"{self.state.P_source:.2f}\n"
                    f"{self.state.OVP_level:.2f}\n"
                    f"{self.state.ENA_OCP}",
                    encoding="utf-8",
                )
            except Exception:
                pass  # Do not panic and remain silent
            else:
                return True

        return False
