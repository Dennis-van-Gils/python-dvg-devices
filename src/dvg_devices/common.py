#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Serial device function library
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "08-07-2020"
__version__ = "0.0.5"
# pylint: disable=bare-except, broad-except, try-except-raise

import sys
from typing import Callable
from pathlib import Path

import serial
import serial.tools.list_ports

from dvg_debug_functions import print_fancy_traceback as pft


class Serial_Device:
    def __init__(self, long_name="Serial Device", name="Dev_1"):
        # serial.Serial device instance
        self.ser = None

        # Long display name of the device in a general sense.
        # Suggestion: "[Manufacturer] [Model] [Device category]",
        # e.g. "Keysight N8700 PSU"
        self.long_name = long_name

        # Short display name for a specific device, e.g. "PSU_1"
        self.name = name

        # Is the connection alive?
        self.is_alive = False

    # --------------------------------------------------------------------------
    #   close
    # --------------------------------------------------------------------------

    def close(self, ignore_exceptions=False):
        """Close the serial port
        """
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception as err:
                if ignore_exceptions:
                    pass
                else:
                    pft(err, 3)
                    sys.exit(0)

        self.is_alive = False

    # --------------------------------------------------------------------------
    #   close
    # --------------------------------------------------------------------------

    def connect_at_port(
        self,
        port: str,
        validation_query: Callable[[object], list] = None,
        valid_broad_query_reply: object = None,
        valid_specific_query_reply: object = None,
        verbose=True,
        **kwargs,  # To be passed to serial.Serial(), e.g., port, baudrate, timeout, ...
    ):
        """Open the serial port at address `port`, with additional parameters
        given by the optional keyword arguments `**kwargs` -- such as `baudrate`
        and `timeout` -- and try to establish a connection.

        When the connection is successful, an optional query -- given by
        `validation_query` -- can be send to the device. Its reply will then be
        checked against argument `valid_query_reply`.

        When the connection was successful and no `validation_query` was passed,
        then this function will return :const:`True`, otherwise :const:`False`.

        When the connection was successful and a `validation_query` was passed

        Args:
            port (:obj:`str`): Serial port address to open.

            validation_query (:obj:`Callable[[Generic], [bool, Generic]`, optional):
                Reference to a function to perform a validation query on the
                device. The function must take a single argument, which will be
                `valid_query_reply`, and must return :obj:`bool` to indicate a
                successful match between the query reply and
                `valid_query_reply`.

                When set to :obj:`None`, no validation will take place and

                Default: :obj:`None`

            valid_query_reply (:obj:`Generic`, optional):
                Reply to be matched when argument `validation_query` is being
                passed. When set to :obj:`None`, any reply will be accepted as
                a match. This is useful to connect

                Default: :obj:`None`

            verbose (:obj:`bool`, optional): Print a 'Connecting to: `-message
                to the terminal, when :const:`True`.

                Default: :const:`True`

            **kwargs:
                Will be directly passed onto :meth:`serial.Serial`, e.g.,
                `baudrate`, `timeout`, etc.

        Returns: True if successful, False otherwise.



        def validation_query(a):
            ...:     dev.ser.write("id?\n".encode())
            ...:     ans=dev.ser.readline().decode().strip()
            ...:     return (a==ans, ans)
            ...:

        """

        if verbose:
            if validation_query is None or valid_specific_query_reply is None:
                print("Connecting to: %s" % self.long_name)
            else:
                print(
                    "Connecting to: %s | `%s`"
                    % (self.long_name, valid_specific_query_reply)
                )

        print("  @ %-5s: " % port, end="")
        try:
            # Open the serial port
            self.ser = serial.Serial(port=port, **kwargs,)
        except serial.SerialException:
            print("Could not open port.")
            return False
        except Exception as err:
            pft(err, 3)
            sys.exit(0)

        if validation_query is None:
            # Found any device
            print("Any Success!\n")
            self.is_alive = True
            return True

        # Optional validation query
        try:
            (is_matching_broadly, specific_query_reply) = validation_query(
                valid_broad_query_reply
            )
        except:
            print("I/O error in validation_query().")
            if self.ser is not None:
                self.ser.close()
            return False

        if is_matching_broadly:
            if specific_query_reply is not None:
                print("Found `%s`: " % specific_query_reply, end="")

            if valid_specific_query_reply is None:
                # Found a matching device in a broad sense
                print("Broad Success!\n")
                self.is_alive = True
                return True

            elif specific_query_reply == valid_specific_query_reply:
                # Found a matching device in a specific sense
                print("Specific Success!\n")
                self.is_alive = True
                return True

        print("Wrong or no device.")
        if self.ser is not None:
            self.ser.close()
        self.is_alive = False
        return False

    # --------------------------------------------------------------------------
    #   scan_ports
    # --------------------------------------------------------------------------

    def scan_ports(
        self,
        validation_query: Callable[[object], list] = None,
        valid_broad_query_reply: object = None,
        valid_specific_query_reply: object = None,
        **kwargs,
    ):
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
        if validation_query is None or valid_specific_query_reply is None:
            print("Scanning ports for: %s" % self.long_name)
        else:
            print(
                "Scanning ports for: %s | `%s`"
                % (self.long_name, valid_specific_query_reply)
            )

        # Ports is a list of tuples
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            port = p[0]
            if self.connect_at_port(
                port,
                validation_query=validation_query,
                valid_broad_query_reply=valid_broad_query_reply,
                valid_specific_query_reply=valid_specific_query_reply,
                verbose=False,
                **kwargs,
            ):
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

