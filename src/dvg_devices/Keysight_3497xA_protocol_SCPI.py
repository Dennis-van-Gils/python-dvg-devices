#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Function library for an HP/Agilent/Keysight 34970A/34972A data acquisition/
switch unit over SCPI.

Communication errors will be handled as non-fatal. This means it will struggle
on with the script while reporting error messages to the command line output,
as opposed to terminating the program completely.

Queries resulting in numpy.nan indicate that they are uninitialized or that
the query resulted in a communication error.

State variables that are an empty list [] indicate that they are uninitialized
or that the previous query resulted in a communication error.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "15-07-2020"
__version__ = "0.1.0"
# pylint: disable=try-except-raise

import time
import visa
import numpy as np

from dvg_debug_functions import print_fancy_traceback

WRITE_TERMINATION = "\n"
READ_TERMINATION = "\n"

# 'No error left' reply
STR_NO_ERROR = "+0,"

# VISA settings
VISA_TIMEOUT = 2000  # 4000 [msec]


class Keysight_3497xA:
    """List of SCPI commands to be send to the 3497xA to set up the scan cycle.
    Will be assigned by calling 'Keysight_3497xA.begin(SCPI_setup_commands=...)'
    in e.g. the 'main' routine.

    Example:
        from dvg_devices.Keysight_3497xA_protocol_SCPI import Keysight_3497xA

        mux = Keysight_3497xA("GPIB::09")
        scan_list = "(@101:106)"
        SCPI_setup_commands = [
                "rout:open %s" % scan_list,
                "conf:temp TC,J,%s" % scan_list,
                "unit:temp C,%s" % scan_list,
                "sens:temp:tran:tc:rjun:type INT,%s" % scan_list,
                "sens:temp:tran:tc:check ON,%s" % scan_list,
                "sens:temp:nplc 1,%s" % scan_list,
                "rout:scan %s" % scan_list]
        mux.begin(SCPI_setup_commands)
    """

    SCPI_setup_commands = []  # Init as empty list, no commands

    # Flag to determine if the status byte register of the device (device.stb)
    # can be used to poll for any errors in the device queue. The 2nd bit of the
    # status byte would then indicate any errors in the queue. Polling stb is
    # way faster then sending a full 'query_error'.
    # Q: How do we determine?
    # A: Based on the manufacturer reported by the *idn? query. Note that this
    # information can differ from the name printed on the front panel! This
    # library will switch error checking functionality and GUI based on the
    # manufacturer.
    can_check_error_queue_by_polling_stb = False

    class State:
        """Container for the process and measurement variables.
        An empty list [] indicates that the parameter is not initialized or
        that the last query was unsuccessful in communication.
        """

        # All the channels in the scan list retreived from the 3497xA [list of
        # strings]. This can be used to e.g. populate a table view with correct
        # labels.
        all_scan_list_channels = []

        # List of readings returned by the device after a full scan cycle
        readings = []

        # The single error string retreived from the error queue of the device.
        # None indicates no error is left in the queue.
        error = None

        # This list of strings is provided to be able to store all errors from
        # the device queue. This list is populated by calling 'query_error'
        # until no error is left in the queue. This list can then be printed to
        # screen or GUI and the user should 'acknowledge' the list, after which
        # the list can be emptied (=[]) again.
        all_errors = []

    class Diag:
        """Container for the diagnostic information.
        [numpy.nan] values indicate that the parameter is not initialized or
        that the last query was unsuccessful in communication.
        """

        # Cycle count of the three backplane relays on the internal DMM.
        # diag:dmm:cycl?
        slot_1_DMM_cycles = np.nan
        slot_2_DMM_cycles = np.nan
        slot_3_DMM_cycles = np.nan

        # Identity of the three plug-in modules in the specified slot.
        # syst:ctyp?
        slot_1_ctype = "none"
        slot_2_ctype = "none"
        slot_3_ctype = "none"

        # Custom label of up to 10 characters stored in non-volatile memory
        # of the module in the specified slot. We have used it to store the
        # serial number of the module as printed on its back.
        # diag:peek:slot:data?
        slot_1_label = np.nan
        slot_2_label = np.nan
        slot_3_label = np.nan

        # Cycle count on all available channels of the specified slot.
        # diag:rel:cycl?
        slot_1_relay_cycles = []
        slot_2_relay_cycles = []
        slot_3_relay_cycles = []

    # --------------------------------------------------------------------------
    #   __init__
    # --------------------------------------------------------------------------

    def __init__(self, visa_address=None, name="MUX"):
        """
        Args:
            visa_address (str): VISA device address
        """
        self._visa_address = visa_address
        self.name = name
        self._idn = None  # The identity of the device ("*IDN?")

        # Placeholder for the VISA device instance
        self.device = None

        # Is the connection to the device alive?
        self.is_alive = False

        # Container for the process and measurement variables
        self.state = self.State()

        # Container for the diagnostic relay cycle counts.
        self.diag = self.Diag()

    # --------------------------------------------------------------------------
    #   close
    # --------------------------------------------------------------------------

    def close(self):
        if not self.is_alive:
            # print("ERROR: Device is already closed.")
            pass  # Remain silent. Device is already closed.
        else:
            self.device.close()
            self.is_alive = False

    # --------------------------------------------------------------------------
    #   connect
    # --------------------------------------------------------------------------

    def connect(self, rm):
        """Try to connect to the device over VISA at the given address. When
        succesful the VISA device instance will be stored in member 'device'
        and its identity is queried and stored in '_idn'.

        Args:
            rm: Instance of visa.ResourceManager

        Returns: True if successful, False otherwise.
        """
        self.is_alive = False

        print("Connect to: Keysight 3497xA")
        print("  @ %s : " % self._visa_address, end="")
        try:
            self.device = rm.open_resource(
                self._visa_address, timeout=VISA_TIMEOUT
            )
            self.device.clear()
        except visa.VisaIOError:
            print("Could not open resource.\n")
            return False
        except:
            raise
        print("Success!")
        self.is_alive = True
        self.device.write_termination = WRITE_TERMINATION
        self.device.read_termination = READ_TERMINATION

        success, self._idn = self.query("*idn?")
        self.wait_for_OPC()

        if success:
            print("  %s\n" % self._idn)
            return True

        return False

    # --------------------------------------------------------------------------
    #   begin
    # --------------------------------------------------------------------------

    def begin(self, SCPI_setup_commands=None):
        """This function should run directly after having established a
        connection to a 3497xA.

        Args:
            SCPI_setup_commands (list of strings): List of SCPI commands to be
            send to the 3497xA to set up the scan cycle. [None]: The previously
            passed set of commands remain valid. []: All commands will be
            cleared.

        Returns: True if all messages were sent and received successfully,
            False otherwise.
        """
        # Clear errors
        self.state.error = None
        self.state.all_errors = []

        # Store SCPI setup commands
        if SCPI_setup_commands is not None:
            self.SCPI_setup_commands = SCPI_setup_commands

        if not self.is_alive:
            print("ERROR: Device is not connected yet or already closed.")
            return False

        # Flag to determine if the status byte register of the device
        # (device.stb) can be used to poll for any errors in the device queue.
        if self._idn.lower().find("hewlett") >= 0:
            # E.g. 'HEWLETT-PACKARD,34970A,0,13-2-2'
            self.can_check_error_queue_by_polling_stb = False
        elif self._idn.lower().find("agilent") >= 0:
            # E.g. 'Agilent Technologies,34972A,MY49018071,1.16-1.12-02-02'
            self.can_check_error_queue_by_polling_stb = False  # Is actually True, but .stb malfunctions and causes locked up device
        else:
            self.can_check_error_queue_by_polling_stb = False

        # fmt: off
        success = self.abort_reset_clear()
        success &= self.query_diagnostics()             ; self.wait_for_OPC()
        success &= self.perform_SCPI_setup_commands()   ; self.wait_for_OPC()
        success &= self.query_all_scan_list_channels()  ; self.wait_for_OPC()
        self.query_all_errors_in_queue()                ; self.wait_for_OPC()
        self.report_diagnostics()
        # fmt: on

        return success

    # --------------------------------------------------------------------------
    #   write
    # --------------------------------------------------------------------------

    def write(self, msg_str):
        """Try to write a command to the device.

        Args:
            msg_str (string): Message to be sent.

        Returns: True if the message was sent successfully, False otherwise.
            NOTE: It does not indicate whether the message made sense to the
            device.
        """

        if not self.is_alive:
            print("ERROR: Device is not connected yet or already closed.")
            return False

        try:
            self.device.write(msg_str)
        except visa.VisaIOError as err:
            # Print error and struggle on
            print_fancy_traceback(err, 3)
            return False
        except:
            raise

        return True

    # --------------------------------------------------------------------------
    #   query
    # --------------------------------------------------------------------------

    def query(self, msg_str):
        """Try to query the device.

        Args:
            msg_str (string): Message to be sent.

        Returns:
            success (bool): True if the message was sent and a reply was
                received successfully, False otherwise.
            ans_str (string): Reply received from the device. [numpy.nan] if
                unsuccessful.
        """
        success = False
        ans_str = np.nan

        if not self.is_alive:
            print("ERROR: Device is not connected yet or already closed.")
        else:
            try:
                ans_str = self.device.query(msg_str)
            except visa.VisaIOError as err:
                # Print error and struggle on
                print_fancy_traceback(err, 3)
            except:
                raise
            else:
                ans_str = ans_str.strip()
                success = True

        return (success, ans_str)

    # --------------------------------------------------------------------------
    #   query_ascii_values
    # --------------------------------------------------------------------------

    def query_ascii_values(self, msg_str):
        """Try to query the device.

        Args:
            msg_str (string): Message to be sent.

        Returns:
            success (bool): True if the message was sent and a reply was
                received successfully, False otherwise.
            ans_list (list): Reply received from the device. Empty list [] if
                unsuccessful.
        """
        success = False
        ans_list = []

        if not self.is_alive:
            print("ERROR: Device is not connected yet or already closed.")
        else:
            try:
                ans_list = self.device.query_ascii_values(msg_str)
            except visa.VisaIOError as err:
                # Print error and struggle on
                print_fancy_traceback(err, 3)
            except:
                raise
            else:
                success = True

        return (success, ans_list)

    # --------------------------------------------------------------------------
    #   query_diagnostics
    # --------------------------------------------------------------------------

    def query_diagnostics(self, verbose=False):
        """
        Returns: True if all messages were sent and received successfully,
            False otherwise.
        """
        all_success = True

        # Retrieve relay cycle counts of internal DMM
        success, DMM_cycles = self.query_ascii_values("diag:dmm:cycl?")
        all_success &= success

        if success:
            [
                self.diag.slot_1_DMM_cycles,
                self.diag.slot_2_DMM_cycles,
                self.diag.slot_3_DMM_cycles,
            ] = DMM_cycles
        else:
            [
                self.diag.slot_1_DMM_cycles,
                self.diag.slot_2_DMM_cycles,
                self.diag.slot_3_DMM_cycles,
            ] = [np.nan] * 3

        # Check all 3 slots for installed modules. Create a list of all
        # available channels if a multiplexer module is installed. This list
        # will be used to retreive the relay cycle count of each channel.
        ch_list_SCPI = ""

        for i in range(3):
            bank = 100 * (i + 1)
            success, slot_ctype = self.query("syst:ctyp? %i" % bank)
            all_success &= success

            if success:
                if slot_ctype.find(",0,0,0") > -1:
                    N_chans = 0
                    slot_ctype = "none"
                elif slot_ctype.find("34901A") > -1:
                    N_chans = 20
                elif slot_ctype.find("34902A") > -1:
                    N_chans = 16
                else:
                    N_chans = 0
            else:
                slot_ctype = "none"
                N_chans = 0

            if slot_ctype == "none":
                slot_label = np.nan
            else:
                success, slot_label = self.query(
                    "diag:peek:slot:data? %i" % bank
                )
                all_success &= success

                if success:
                    slot_label = slot_label.strip('"')

            if N_chans > 0:
                ch_list_SCPI = "%i:%i" % (bank + 1, bank + N_chans)
                success, relay_cycles = self.query_ascii_values(
                    "diag:rel:cycl? (@%s)" % ch_list_SCPI
                )
                all_success &= success

                if not success:
                    relay_cycles = []
            else:
                relay_cycles = []

            if i == 0:
                self.diag.slot_1_ctype = slot_ctype
                self.diag.slot_1_label = slot_label
                self.diag.slot_1_relay_cycles = relay_cycles
            if i == 1:
                self.diag.slot_2_ctype = slot_ctype
                self.diag.slot_2_label = slot_label
                self.diag.slot_2_relay_cycles = relay_cycles
            if i == 2:
                self.diag.slot_3_ctype = slot_ctype
                self.diag.slot_3_label = slot_label
                self.diag.slot_3_relay_cycles = relay_cycles

        if verbose:
            self.report_diagnostics()

        return all_success

    # --------------------------------------------------------------------------
    #   report_diagnostics
    # --------------------------------------------------------------------------

    def report_diagnostics(self):
        print("  Relay cycle count internal DMM:")
        print("    slot 1: %.1e" % self.diag.slot_1_DMM_cycles)
        print("    slot 2: %.1e" % self.diag.slot_2_DMM_cycles)
        print("    slot 3: %.1e" % self.diag.slot_3_DMM_cycles)
        print("")

        for i in range(3):
            if i == 0:
                slot_ctype = self.diag.slot_1_ctype
                slot_label = self.diag.slot_1_label
                relay_cycles = self.diag.slot_1_relay_cycles
            if i == 1:
                slot_ctype = self.diag.slot_2_ctype
                slot_label = self.diag.slot_2_label
                relay_cycles = self.diag.slot_2_relay_cycles
            if i == 2:
                slot_ctype = self.diag.slot_3_ctype
                slot_label = self.diag.slot_3_label
                relay_cycles = self.diag.slot_3_relay_cycles

            print("  Slot %i:" % (i + 1))
            print("    %s" % slot_ctype)
            if slot_ctype != "none":
                print("    Serial: %s" % slot_label)
            if not (relay_cycles == []):
                print("    Relay cycle count")
                for j in range(len(relay_cycles)):
                    print("      ch %2i: %8i" % (j + 1, relay_cycles[j]))
            print("")

    # --------------------------------------------------------------------------
    #   System status related
    # --------------------------------------------------------------------------

    def abort_reset_clear(self):
        """Abort measurement, reset device and clear status. Return when this
        operation has completed on the device. Blocking.

        Returns: True if the message was sent successfully, False otherwise.
        """

        if not self.is_alive:
            print("ERROR: Device is not connected yet or already closed.")
            return False

        # The reset operation can take a long time to complete. Momentarily
        # increase the timeout to 2000 msec if necessary.
        if self.device.timeout < 2000:
            self.device.timeout = 2000

        # Send clear and reset
        success = self.write("abor;*rst;*cls")

        # Wait for the last operation to finish before timeout expires
        self.wait_for_OPC()

        # Restore timeout
        self.device.timeout = VISA_TIMEOUT

        return success

    def wait_for_OPC(self):
        """'Operation complete' query, used for event synchronization.

        Will wait for all device operations to complete or until a timeout is
        triggered. Blocking.
        """
        # Returns an ASCII "+1" when all pending overlapped operations have been
        # completed.
        self.query("*opc?")

    def wait_for_OPC_indefinitely(self):
        """Poll OPC status bit for 'operation complete', used for event
        synchronization.

        Will wait indefinitely for all device operations to complete. Blocking.

        Make sure that the ESR is set to signal bit 0 - OPC (operation complete)
        before you call this function. This can be done by calling
        'prepare_wait_for_OPC_indefinitely()'.
        """

        # Let the device set the ESR bit 0 - OPC (operation complete) to 1 after
        # all device operations have completed.
        self.write("*opc")

        # Poll the OPC status bit for 'operation complete'. This is the 5th
        # bit.
        while not (self.device.stb & 0b100000) == 0b100000:
            time.sleep(0.01)

        # Reset the ESR bit 0 - OPC back to 0.
        self.query("*esr?")

    def prepare_wait_for_OPC_indefinitely(self):
        """Set the ESR to signal bit 0 - OPC (operation complete). Should be
        called only once after a '*rst' in case you want to make use of
        'wait_for_OPC_indefinitely()'.

        Returns: True if the message was sent successfully, False otherwise.
        """
        return self.write("*ese 1")

    def query_error(self, verbose=False):
        """Pop one error string from the error queue of the device and store it
        in the 'State'-class member. A value of None indicates no error is left.

        Returns: True if the query was received successfully, False otherwise.
        """
        success, self.state.error = self.query("syst:err?")
        if success:
            if self.state.error.find(STR_NO_ERROR) == 0:
                self.state.error = None
            else:
                if verbose:  # DEBUG INFO
                    print("  %s" % self.state.error)
        return success

    def query_all_errors_in_queue(self, verbose=False):
        """Check if there are errors in the device queue and retrieve all if
        any and append these to 'state.all_errors'.
        """
        if not self.is_alive:
            print("ERROR: Device is not connected yet or already closed.")
            return

        if self.can_check_error_queue_by_polling_stb:
            # Fast polling method
            if (self.device.stb & 0b100) == 0b100:
                # There are unread errors in the queue available. Retrieve all.
                while True:
                    if self.query_error():
                        if self.state.error is None:
                            break
                        else:
                            self.state.all_errors.append(self.state.error)
                    else:
                        break
        else:
            # Slow full query method
            while True:
                if self.query_error():
                    if self.state.error is None:
                        break
                    else:
                        self.state.all_errors.append(self.state.error)
                else:
                    break

        if verbose:  # DEBUG INFO
            for error in self.state.all_errors:
                print("  %s" % error)

    def set_display_text(self, str_text):
        """
        Returns: True if the message was sent successfully, False otherwise.
        """
        return self.write("disp:text '%s'" % str_text)

    # --------------------------------------------------------------------------
    #   Acquisition related
    # --------------------------------------------------------------------------

    def perform_SCPI_setup_commands(self):
        """
        Returns: True if all messages were sent successfully, False otherwise.
        """
        success = True
        for command in self.SCPI_setup_commands:
            success &= self.write(command)
        self.wait_for_OPC()

        return success

    def init_scan(self):
        """Initialize the scan, i.e. start with the acquisition of data over
        all channels as programmed. Non-blocking.

        You can check for the scan to have completed by calling
        'wait_for_OPC()' and subsequently retrieve the scanned data from the
        device buffer, like this:
            k3497xA.init_scan()
            k3497xA.wait_for_OPC()
            k3497xA.fetch_scan()

        For scan operations that take longer than the time-out period, you
        should use 'wait_for_OPC_indefinitely()' like this:
            k3497xA.prepare_wait_for_OPC_indefinitely()
            k3497xA.init_scan()
            k3497xA.wait_for_OPC_indefinitely()
            k3497xA.fetch_scan()

        Returns: True if the message was sent successfully, False otherwise.
        """
        return self.write("init")

    def fetch_scan(self):
        """Retreive the last scanned data from the device buffer. The data
        will be stored in state variable 'state.readings'.

        Returns: True if the query was received successfully, False otherwise.
        """
        success, self.state.readings = self.query_ascii_values("fetc?")

        return success

    def init_scan_and_wait_for_OPC_indefinitely_and_fetch(self):
        """Blocking and mainly for testing purposes as there will be limited
        use for this series of instructions that could be blocking indefinitely.
        The scanned data will be stored in state variable 'state.readings'.

        Returns: True if the query was received successfully, False otherwise.
        """
        self.prepare_wait_for_OPC_indefinitely()
        success = self.init_scan()
        self.wait_for_OPC_indefinitely()
        success &= self.fetch_scan()
        # print(self.state.readings[1])

        return success

    def query_all_scan_list_channels(self):
        """Query the channels in the currently programmed scan list of the
        3497xA. This can be used to e.g. populate a table view with correct
        labels. The scan list channel names will be stored in state variable
        'state.all_scan_list_channels'.

        Returns: True if the query was received successfully, False otherwise.
        """

        success, str_ans = self.query("rout:scan?")
        if success:
            tmp = str_ans[str_ans.find("@") + 1 :].strip(")")
            if tmp != "":
                self.state.all_scan_list_channels = tmp.split(",")
        self.wait_for_OPC()

        return success
