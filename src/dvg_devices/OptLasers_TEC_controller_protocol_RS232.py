#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Provides higher-level general I/O methods for communicating with an
OptLasers thermoelectric cooler (TEC) controller using the RS232 protocol.
Specifically written for the OptLasers TEC-8A-24V-PID-HC-RS232 controller, see
https://optlasers.com/tec-controllers/tec-8a-24v-pid-hc-rs232-programmable-temperature-controller.

When this module is directly run from the terminal a demo will be shown.
"""

__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "13-08-2026"
__version__ = "1.7.0"
# pylint: disable=missing-function-docstring

from typing import Union, Tuple

import numpy as np

from dvg_debug_functions import print_fancy_traceback as pft, dprint
from dvg_devices.BaseDevice import SerialDevice


class OptLasersTEC(SerialDevice):
    """Provides higher-level general I/O methods for communicating with an
    OptLasers thermoelectric cooler (TEC) controller using the RS232 protocol.
    Specifically written for the OptLasers TEC-8A-24V-PID-HC-RS232 controller.
    """

    class State:
        """Container for the process and measurement variables."""

        # Process variables
        # -----------------

        T_set: float = np.nan
        """Temperature setpoint ['C]."""

        P: float = np.nan
        """PID proportional term, range [0.0 — 20.0]. At a value of 20.0, an
        error of 0.5 'C causes maximum output (100%)."""

        I: float = np.nan
        """PID integral term, range [0.0 — 20.0]. A value of < 0.05 will turn
        off the integrator and clear it. The integrator saturates at -100% and
        +100%, and does not clear itself on any timeout."""

        D: float = np.nan
        """PID derivative term, range [0.0 — 20.0]. A value of < 0.05 will turn
        off the differentiator and clear it."""

        T_min: int = 0
        """Lower temperature threshold ['C]. Will be checked by the TEC
        controller, in turn driving its open collector (OC) output."""

        T_max: int = 0
        """Upper temperature threshold ['C]. Will be checked by the TEC
        controller, in turn driving its open collector (OC) output."""

        is_supply_ON: bool = True
        """Is power being supplied to the TEC element by the TEC controller?
        Note that this parameter can not get queried from the TEC controller
        itself. It can only be blindly set using methods `turn_supply_ON()` and
        `turn_supply_OFF()`. The TEC controller always starts up fresh with the
        supply turned on."""

        # Measurement variables
        # ---------------------

        T_meas: float = np.nan
        """Measured temperature ['C]."""

        OC: int = 0
        """Open collector output state.
        0: Disconnected from GND.
        1: Connected to GND."""

        PWM: int = 0
        """Pulse-width modulation percentage [%]. Negative values indicate
        cooling, positive values indicate heating. Absolute values correspond to
        the driving intensity."""

    # --------------------------------------------------------------------------
    #   __init__
    # --------------------------------------------------------------------------

    def __init__(
        self,
        name="TEC_1",
        long_name="OptLasers TEC controller",
        debug=False,
    ):
        super().__init__(name=name, long_name=long_name)

        # Default serial settings
        self.serial_settings = {
            "baudrate": 38400,
            "timeout": 2,
            "write_timeout": 2,
        }
        self.set_read_termination("\r\n")
        self.set_write_termination(None)

        self.set_ID_validation_query(
            ID_validation_query=self.ID_validation_query,
            valid_ID_broad="<!>",
            valid_ID_specific=None,
        )

        # Container for the process and measurement variables
        self.state = self.State()

        self.debug = debug

    # --------------------------------------------------------------------------
    #   ID_validation_query
    # --------------------------------------------------------------------------

    def ID_validation_query(self) -> Tuple[str, Union[str, None]]:
        _success, reply = self.query("!")
        return reply if isinstance(reply, str) else "", None

    # --------------------------------------------------------------------------
    #   begin
    # --------------------------------------------------------------------------

    def begin(self):
        """This method should be called directly after having established a
        serial connection to the TEC controller.

        As a safety feature, this method will send a command to the TEC
        controller to immediately remove power to its TEC element. You should
        call method `turn_supply_ON()` to start driving the TEC.
        """
        self.turn_supply_OFF()
        self.query_state()
        print(" Initial TEC controller variables:")
        self.report()

    # --------------------------------------------------------------------------
    #   report
    # --------------------------------------------------------------------------

    def report(self):
        """Pretty print a report to the terminal containing all process and
        measurement variables of the TEC controller."""
        state = self.state
        print(
            "┌────────────────────────────────┐\n"
            f"│ TEC controller: {self.name:<14s} │\n"
            "├───┬──────────┬────────┬────────┤\n"
            f"│ P │ {state.P:5.2f}    │ supply │ "
            f"{'    ON' if state.is_supply_ON else '   OFF'} │\n"
            f"│ I │ {state.I:5.2f}    │ T_min  │ {state.T_min:3d} 'C │\n"
            f"│ D │ {state.D:5.2f}    │ T_max  │ {state.T_max:3d} 'C │\n"
            "├───┴─┬────────┼────────┼────────┴──┐\n"
            f"│ OC  │ {state.OC:d}      │ T_set  │ {state.T_set:6.2f} 'C │\n"
            f"│ PWM │ {state.PWM:<+4d} % │ T_meas │ {state.T_meas:6.2f} 'C │\n"
            "└─────┴────────┴────────┴───────────┘"
        )

    # --------------------------------------------------------------------------
    #   query_state
    # --------------------------------------------------------------------------

    def query_state(self) -> bool:
        """Query a single readout from the TEC controller, containing all its
        process and measurement variables like the current temperature reading,
        temperature setpoint, PID parameters, min & max temperatures, open
        collector output and PWM strength.

        The reply will get parsed into separate variables and each will be
        stored in the `state` class member.

        NOTE: The minimal readout period for continuous polling of the TEC
        controller variables is around 1.09 sec. Do not try to read faster than
        this.

        Returns ('bool'):
            True if the command was successfully send to the device and its
            reply got succesfully parsed, False otherwise.
        """
        command = "o"
        self._print_serial_debug_info("TX", command)
        self.write(command)

        _success, reply = self.readline()
        self._print_serial_debug_info("RX", reply)
        if not isinstance(reply, str) or reply != "<o>":
            pft("Received an incorrect reply from the TEC controller.")
            return False

        _success, reply = self.readline()
        self._print_serial_debug_info("RX", reply)
        if not isinstance(reply, str):
            pft("Received an incorrect reply from the TEC controller.")
            return False

        return self._parse_readout_line(reply)

    # --------------------------------------------------------------------------
    #   send_process_variables
    # --------------------------------------------------------------------------

    def send_process_variables(
        self,
        T_set: Union[float, None] = None,
        T_min: Union[int, None] = None,
        T_max: Union[int, None] = None,
        P: Union[float, None] = None,
        I: Union[float, None] = None,
        D: Union[float, None] = None,
    ) -> bool:
        """Send new process variables to the TEC controller and double check
        these newly set variables which will be stored in the `state` class
        member.

        All the passed variables are optional. When a variable is omitted or set
        to `None`, the currently known value will be left unaltered.

        Args:
            T_set (float, optional):
                Temperature setpoint ['C].

            T_min (int, optional):
                Lower temperature threshold ['C]. Will be checked by the TEC
                controller, in turn driving its open collector (OC) output.

            T_max (int, optional):
                Upper temperature threshold ['C]. Will be checked by the TEC
                controller, in turn driving its open collector (OC) output.

            P (float, optional):
                PID proportional term, range [0.0 — 20.0]. At a value of 20.0,
                an error of 0.5 'C causes maximum output (100%).

            I (float, optional):
                PID integral term, range [0.0 — 20.0]. A value of < 0.05 will
                turn off the integrator and clear it. The integrator saturates
                at -100% and +100%, and does not clear itself on any timeout.

            D (float, optional):
                PID derivative term, range [0.0 — 20.0]. A value of < 0.05 will
                turn off the differentiator and clear it.

        Returns ('bool'):
            True if the command was successfully send to the device and its
            reply got succesfully parsed, False otherwise.
        """
        if T_set is None:
            T_set = self.state.T_set
        if T_min is None:
            T_min = self.state.T_min
        if T_max is None:
            T_max = self.state.T_max
        if P is None:
            P = self.state.P
        if I is None:
            I = self.state.I
        if D is None:
            D = self.state.D

        T_set = np.clip(np.nan_to_num(T_set), -100, 100)
        T_min = np.clip(T_min, -100, 100)
        T_max = int(np.clip(T_max, -100, 100))
        T_min = np.amin(np.array([T_min, T_max - 1]))
        P = float(np.clip(np.nan_to_num(P), 0, 20))
        I = float(np.clip(np.nan_to_num(I), 0, 20))
        D = float(np.clip(np.nan_to_num(D), 0, 20))

        if I < 0.5:
            I = 0
        if D < 0.5:
            D = 0

        # Send new process variables to the TEC controller
        command = f"<{T_set:.2f} {P:.2f} {I:.2f} {D:.2f} {T_min:d} {T_max:d}>"
        self._print_serial_debug_info("TX", command)
        self.write(command)

        # The TEC controller replies with two lines, like, e.g.:
        # line 1: <<16 8 1 2 10 30>>
        # line 2: eTzc=+16.00  eKp= 8.00  eKi= 1.00  eKd= 2.00  eTmin=+10.0  eTmax=+30.0

        # We catch line 1 and ignore it.
        _success, reply = self.readline()
        self._print_serial_debug_info("RX", reply)

        # We parse line 2.
        _success, reply = self.readline()
        self._print_serial_debug_info("RX", reply)
        if not isinstance(reply, str):
            pft("Received an incorrect reply from the TEC controller.")
            return False

        return self._parse_readout_line_2(reply)

    def send_T_set(self, value: float) -> bool:
        """Send process variable `T_set` to the TEC controller and double check
        this newly set variable which will be stored in the `state` class
        member.

        `T_set`: Temperature setpoint ['C].

        Returns ('bool'):
            True if the command was successfully send to the device and its
            reply got succesfully parsed, False otherwise.
        """
        return self.send_process_variables(T_set=value)

    def send_T_min(self, value: int) -> bool:
        """Send process variable `T_min` to the TEC controller and double check
        this newly set variable which will be stored in the `state` class
        member.

        `T_min`: Lower temperature threshold ['C]. Will be checked by the TEC
        controller, in turn driving its open collector (OC) output.

        Returns ('bool'):
            True if the command was successfully send to the device and its
            reply got succesfully parsed, False otherwise.
        """
        return self.send_process_variables(T_min=value)

    def send_T_max(self, value: int) -> bool:
        """Send process variable `T_max` to the TEC controller and double check
        this newly set variable which will be stored in the `state` class
        member.

        `T_max`: Upper temperature threshold ['C]. Will be checked by the TEC
        controller, in turn driving its open collector (OC) output.

        Returns ('bool'):
            True if the command was successfully send to the device and its
            reply got succesfully parsed, False otherwise.
        """
        return self.send_process_variables(T_max=value)

    def send_P(self, value: float) -> bool:
        """Send process variable `P` to the TEC controller and double check
        this newly set variable which will be stored in the `state` class
        member.

        `P`: PID proportional term, range [0.0 — 20.0]. At a value of 20.0, an
        error of 0.5 'C causes maximum output (100%).

        Returns ('bool'):
            True if the command was successfully send to the device and its
            reply got succesfully parsed, False otherwise.
        """
        return self.send_process_variables(P=value)

    def send_I(self, value: float) -> bool:
        """Send process variable `I` to the TEC controller and double check
        this newly set variable which will be stored in the `state` class
        member.

        `I`: PID integral term, range [0.0 — 20.0]. A value of < 0.05 will turn
        off the integrator and clear it. The integrator saturates at -100% and
        +100%, and does not clear itself on any timeout.

        Returns ('bool'):
            True if the command was successfully send to the device and its
            reply got succesfully parsed, False otherwise.
        """

        return self.send_process_variables(I=value)

    def send_D(self, value: float) -> bool:
        """Send process variable `D` to the TEC controller and double check
        this newly set variable which will be stored in the `state` class
        member.

        `D`: PID derivative term, range [0.0 — 20.0]. A value of < 0.05 will
        turn off the differentiator and clear it.

        Returns ('bool'):
            True if the command was successfully send to the device and its
            reply got succesfully parsed, False otherwise.
        """
        return self.send_process_variables(D=value)

    # --------------------------------------------------------------------------
    #   turn_supply_ON
    # --------------------------------------------------------------------------

    def turn_supply_ON(self) -> bool:
        """Send command to supply power to the TEC element.

        Returns ('bool'):
            True if the command was successfully send to the device, False
            otherwise.
        """
        command = "A"
        self._print_serial_debug_info("TX", command)
        self.write(command)

        _success, reply = self.readline()
        self._print_serial_debug_info("RX", reply)
        if not isinstance(reply, str) or reply != "<A>":
            pft("Received an incorrect reply from the TEC controller.")
            return False

        self.state.is_supply_ON = True
        return True

    # --------------------------------------------------------------------------
    #   turn_supply_OFF
    # --------------------------------------------------------------------------

    def turn_supply_OFF(self) -> bool:
        """Send command to remove power to the TEC element.

        Returns ('bool'):
            True if the command was successfully send to the device, False
            otherwise.
        """
        command = "a"
        self._print_serial_debug_info("TX", command)
        self.write(command)

        _success, reply = self.readline()
        self._print_serial_debug_info("RX", reply)
        if not isinstance(reply, str) or reply != "<a>":
            pft("Received an incorrect reply from the TEC controller.")
            return False

        self.state.is_supply_ON = False
        return True

    # --------------------------------------------------------------------------
    #   _parse_readout_line
    # --------------------------------------------------------------------------

    def _parse_readout_line(self, line: str) -> bool:
        """Parses a single readout line as reported by the TEC controller into
        separate variables and each will be stored in the `state` class
        member.

        Returns ('bool'):
            True if the line could be successfully parsed into separate
            variables, False otherwise.
        """
        # Line template to parse, e.g:
        # Tz=+16.00 P= 8.00 I= 1.00 D= 2.00 T=+10...+30 Tr=+23.45 OC=0 PW=-100
        # fmt: off
        line = line.strip()
        idx_T_set  = line.find("Tz=")
        idx_P      = line.find("P=")
        idx_I      = line.find("I=")
        idx_D      = line.find("D=")
        idx_T_lims = line.find("T=")
        idx_T_meas = line.find("Tr=")
        idx_OC     = line.find("OC=")
        idx_PW     = line.find("PW=")
        # fmt: on

        if -1 in [
            idx_T_set,
            idx_P,
            idx_I,
            idx_D,
            idx_T_lims,
            idx_T_meas,
            idx_OC,
            idx_PW,
        ]:
            pft("Failed to parse the reply from the TEC controller.")
            return False

        # fmt: off
        str_T_set  = line[idx_T_set + 3  : idx_P]     .replace(" ", "")
        str_P      = line[idx_P + 2      : idx_I]     .replace(" ", "")
        str_I      = line[idx_I + 2      : idx_D]     .replace(" ", "")
        str_D      = line[idx_D + 2      : idx_T_lims].replace(" ", "")
        str_T_lims = line[idx_T_lims + 2 : idx_T_meas].replace(" ", "")
        str_T_meas = line[idx_T_meas + 3 : idx_OC]    .replace(" ", "")
        str_OC     = line[idx_OC + 3     : idx_PW]    .replace(" ", "")
        str_PW     = line[idx_PW + 3     :]           .replace(" ", "")
        str_T_min, str_T_max = str_T_lims.split("...")
        # fmt: on

        try:
            # fmt: off
            self.state.T_set  = float(str_T_set)
            self.state.P      = float(str_P)
            self.state.I      = float(str_I)
            self.state.D      = float(str_D)
            self.state.T_min  = int(str_T_min)
            self.state.T_max  = int(str_T_max)
            self.state.T_meas = float(str_T_meas)
            self.state.OC     = int(str_OC)
            self.state.PWM    = int(str_PW)
            # fmt: on
        except ValueError as err:
            pft(err)
            return False

        return True

    # --------------------------------------------------------------------------
    #   _parse_readout_line_2
    # --------------------------------------------------------------------------

    def _parse_readout_line_2(self, line: str) -> bool:
        """Parses a single readout line as reported by the TEC controller into
        separate variables and each will be stored in the `state` class
        member.

        Returns ('bool'):
            True if the line could be successfully parsed into separate
            variables, False otherwise.
        """
        # Line template to parse, e.g:
        # eTzc=+16.00  eKp= 8.00  eKi= 1.00  eKd= 2.00  eTmin=+10.0  eTmax=+30.0
        # fmt: off
        line = line.strip()
        idx_T_set = line.find("eTzc=")
        idx_P     = line.find("eKp=")
        idx_I     = line.find("eKi=")
        idx_D     = line.find("eKd=")
        idx_T_min = line.find("eTmin=")
        idx_T_max = line.find("eTmax=")
        # fmt: on

        if -1 in [idx_T_set, idx_P, idx_I, idx_D, idx_T_min, idx_T_max]:
            pft("Failed to parse the reply from the TEC controller.")
            return False

        # fmt: off
        str_T_set = line[idx_T_set + 5 : idx_P]    .replace(" ", "")
        str_P     = line[idx_P + 4     : idx_I]    .replace(" ", "")
        str_I     = line[idx_I + 4     : idx_D]    .replace(" ", "")
        str_D     = line[idx_D + 4     : idx_T_min].replace(" ", "")
        str_T_min = line[idx_T_min + 6 : idx_T_max].replace(" ", "")
        str_T_max = line[idx_T_max + 6 :]          .replace(" ", "")
        # fmt: on

        try:
            # fmt: off
            self.state.T_set = float(str_T_set)
            self.state.P     = float(str_P)
            self.state.I     = float(str_I)
            self.state.D     = float(str_D)
            self.state.T_min = int(float(str_T_min))
            self.state.T_max = int(float(str_T_max))
            # fmt: on
        except ValueError as err:
            pft(err)
            return False

        return True

    # --------------------------------------------------------------------------
    #   _debug_info
    # --------------------------------------------------------------------------

    def _print_serial_debug_info(self, TX_or_RX, msg):
        if self.debug:
            dprint(f"{TX_or_RX} {self.name}: {msg}")


# ------------------------------------------------------------------------------
#   Main: Will show a demo when run from the terminal
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import signal
    import datetime

    class GracefulKiller:
        kill_now = False

        def __init__(self):
            signal.signal(signal.SIGINT, self.exit_gracefully)
            signal.signal(signal.SIGTERM, self.exit_gracefully)

        def exit_gracefully(self, _signum, _frame):
            self.kill_now = True

    tec = OptLasersTEC(debug=False)
    tec.auto_connect()

    if not tec.is_alive:
        sys.exit(0)

    tec.begin()
    tec.send_process_variables(T_set=20, P=8, I=1, D=2, T_min=10, T_max=30)
    tec.turn_supply_ON()

    killer = GracefulKiller()
    while not killer.kill_now:
        print(datetime.datetime.now().strftime(" %H:%M:%S"))
        tec.query_state()
        tec.report()
        print("\033[12A")

    print("\n" * 11)
    tec.close()
