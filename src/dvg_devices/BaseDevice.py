#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Provides base class SerialDevice(), offering higher-level general I/O methods
for a serial device, like autoconnect. Instances of this class will tie in
nicely with :class:`dvg_qdeviceio.QDeviceIO`.

These base classes are meant to be inherited into your own specific *Device*
class.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "13-07-2020"
__version__ = "0.0.5"
# pylint: disable=bare-except, broad-except, try-except-raise

import sys
from typing import Callable
from pathlib import Path

import serial
import serial.tools.list_ports

from dvg_debug_functions import print_fancy_traceback as pft


class SerialDevice:
    """This class provides higher-level general I/O methods for a serial device,
    by wrapping the excellent `pySerial
    <https://pyserial.readthedocs.io/en/latest/pyserial.html>`_ library.

    The following functionality is offered:

    * TODO: mention write, query and close.

    * Scanning over all serial ports to autoconnect to the desired serial
      device, based on the device's reply to a validation query.

    * Autoconnecting to the device, based on the last known successful port that
      gets written to a configuration textfile.

    Instances of this class will tie in nicely with
    :class:`dvg_qdeviceio.QDeviceIO`.

    Args:
        long_name (:obj:`str`, optional):
            Long display name of the device in a general sense. E.g.,
            `"Keysight N8700 PSU"` or `"Arduino M0 Pro"`.

            Default: `"Serial Device"`

        name (:obj:`str`, optional):
            Short display name for the device. E.g., `"PSU_1"` or `"blinker"`.

            Default: `"Dev_1"`

    Attributes:
        long_name (:obj:`str`):
            Long display name of the device in a general sense. E.g,
            `"Keysight N8700 PSU"` or `"Arduino M0 Pro"`.

        name (:obj:`str`):
            Short display name for the device. E.g., `"PSU_1"` or `"blinker"`.

        serial_init_kwargs (:obj:`dict`):
            Dictionary of keyword arguments to be passed directly to
            :class:`serial.Serial` at initialization of the serial port when
            trying to connect. Do not specify `port` in this dictionary as it
            will be supplied by this class's machinery.

            Default: `{"baudrate": 9600, "timeout": 2, "write_timeout": 2}`

        ser (:class:`serial.Serial` | :obj:`None`):
            Will be set to a :class:`serial.Serial` device instance when a
            connection has been established. Otherwise: :obj:`None`.

        is_alive (:obj:`bool`):
            Is the connection alive? I.e., Can we communicate?
    """

    def __init__(
        self, name="Dev_1", long_name="Serial Device",
    ):

        self.name = name
        self.long_name = long_name

        # Default serial settings
        self.serial_init_kwargs = {
            "baudrate": 9600,
            "timeout": 2,
            "write_timeout": 2,
        }
        self.read_term_char = "\n"
        self.write_term_char = "\n"

        self._ID_validation_query = None
        self._valid_ID_broad = None
        self._valid_ID_specific = None

        self.ser = None
        self.is_alive = False

    # --------------------------------------------------------------------------
    #   def set_ID_validation_query
    # --------------------------------------------------------------------------

    def set_ID_validation_query(
        self,
        ID_validation_query: Callable[[], tuple],
        valid_ID_broad: object,
        valid_ID_specific: object = None,
    ):
        """When this method **is not** called, then the following default scheme
        applies:

            During :meth:`connect_at_port`, :meth:`scan_ports` or
            :meth:`auto_connect` a succesful connection to *any* serial device
            will be accepted and be stored in class member :attr:`ser`.

        When this method **is** called, then the following scheme applies:

            During :meth:`connect_at_port`, :meth:`scan_ports` or
            :meth:`auto_connect` a connection to a *desired* device will be
            attempted by performing a query for a device ID over the serial
            connection. The serial connection will be accepted and be stored in
            class member :attr:`ser` whenever the following scheme returns
            succesful:

        Args:
            ID_validation_query (:obj:`~typing.Callable` [[], :obj:`tuple`]):
                Reference to a function to perform an ID validation query
                on the device when connecting. The function should take zero
                arguments and return a tuple consisting of two objects, as will
                be explained further down. Only when the outcome of the
                validation is successful, will the connection be accepted and
                remain open. Otherwise, the connection will be automatically
                closed again.

                The device's reply on the validation query will be tested
                against the two other arguments: ``valid_ID_broad`` (required)
                and ``valid_ID_specific`` (optional).

                The *broad* reply can be used to allow connections to a device
                of a certain manufacturer and model. E.g., in a response to an
                ``*idn?`` validation query, one can test a part of the full
                reply -- say, `"THURLBY THANDAR, QL355TP, 279730, 1.00 – 1.00"`
                -- against `"THURLBY THANDAR, QL"` to allow connections to *any*
                Thurlby Thandar QL-series power supply.

                The *specific* reply can be used to narrow down to a specific
                device, once it has passed the *broad* validation test. In the
                example above, one could test against the series number
                `"279730"`, for instance. When argument ``valid_ID_specific``
                is not supplied, any *broad* match will be accepted as
                connection.

                The function to be passed, being defined as a class method
                inside of a derived :class:`SerialDevice` class, should have a
                general form like:

                .. code-block:: python

                    def my_ID_validation_query(self) -> (object, object):
                        self.ser.write("*idn?\\n".encode())
                        ans = self.ser.readline().decode().strip()
                        # ans = "THURLBY THANDAR, QL355TP, 279730, 1.00 – 1.00"

                        ID_reply_broad = ans[:19]               # "THURLBY THANDAR, QL"
                        ID_reply_specific = ans.split(",")[2]   # "279730"

                        return (ID_reply_broad, ID_reply_specific)

                When set to :obj:`None`, no validation will take place and *any*
                successful connection will be accepted and remain open.

            valid_ID_broad (:obj:`object`):
                Reply to be broadly matched when a function reference is being
                passed onto ``ID_validation_query``.

            valid_ID_specific (:obj:`object`, optional):
                Reply to be specifically matched when a function reference is
                being passed onto ``ID_validation_query``. Note: When set
                to :obj:`None`, any connection that is *broadly* matched will be
                accepted and remain open.

                Default: :obj:`None`
        """
        self._ID_validation_query = ID_validation_query
        self._valid_ID_broad = valid_ID_broad
        self._valid_ID_specific = valid_ID_specific

    # --------------------------------------------------------------------------
    #   write
    # --------------------------------------------------------------------------

    def write(self, msg_str, timeout_warning_style=1) -> bool:
        """Send a message to the serial device.

        Args:
            msg_str (:obj:`str`):
                ASCII string to be sent to the serial device.

            timeout_warning_style (:obj:`int`, optional):
                - :const:`1`: Will print a traceback error message on screen and
                  continue.
                - :const:`2`: Will raise the exception again.

                Default: :const:`1`

        Returns:
            True if successful, False otherwise.
        """
        success = False

        if not self.is_alive:
            pft("Device is not connected yet or already closed.", 3)
        else:
            try:
                self.ser.write((msg_str + self.write_term_char).encode())
            except (
                serial.SerialTimeoutException,
                serial.SerialException,
            ) as err:
                if timeout_warning_style == 1:
                    pft(err, 3)
                elif timeout_warning_style == 2:
                    raise (err)
            except Exception as err:
                pft(err, 3)
                sys.exit(0)
            else:
                success = True

        return success

    # --------------------------------------------------------------------------
    #   query
    # --------------------------------------------------------------------------

    def query(self, msg_str, timeout_warning_style=1) -> tuple:
        """Send a message to the serial device and subsequently read the reply.

        Args:
            msg_str (:obj:`str`):
                ASCII string to be sent to the serial device.

            timeout_warning_style (:obj:`int`, optional):
                - :const:`1`: Will print a traceback error message on screen and
                  continue.

                - :const:`2`: Will raise the exception again.

                Default: :const:`1`

        Returns:
            :obj:`tuple`:

                - success (:obj:`bool`):
                    True if successful, False otherwise.

                - ans_str (:obj:`str` | :obj:`None`):
                    ASCII string received from the device. :obj:`None` if
                    unsuccessful.
        """
        success = False
        ans_str = None

        if self.write(msg_str, timeout_warning_style):
            try:
                ans_bytes = self.ser.read_until(self.read_term_char.encode())
            except (
                serial.SerialTimeoutException,
                serial.SerialException,
            ) as err:
                # Note: The Serial library does not throw an exception when it
                # times out in `read`, only when it times out in`write`! We
                # will check for zero received bytes as indication for a read
                # timeout, later.
                # See https://stackoverflow.com/questions/10978224/serialtimeoutexception-in-python-not-working-as-expected
                pft(err, 3)
            except Exception as err:
                pft(err, 3)
                sys.exit(0)
            else:
                if len(ans_bytes) == 0:
                    # Received 0 bytes, probably due to a timeout.
                    if timeout_warning_style == 1:
                        pft("Received 0 bytes. Read probably timed out.", 3)
                    elif timeout_warning_style == 2:
                        raise serial.SerialTimeoutException
                else:
                    try:
                        ans_str = ans_bytes.decode("utf8").strip()
                    except UnicodeDecodeError as err:
                        # Print error and struggle on
                        pft(err, 3)
                    except Exception as err:
                        pft(err, 3)
                        sys.exit(0)
                    else:
                        success = True

        return (success, ans_str)

    # --------------------------------------------------------------------------
    #   close
    # --------------------------------------------------------------------------

    def close(self, ignore_exceptions=False):
        """Cancel all pending serial operations and close the serial port.
        """
        if self.ser is not None:
            try:
                self.ser.cancel_read()
            except:
                pass
            try:
                self.ser.cancel_write()
            except:
                pass

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
    #   connect_at_port
    # --------------------------------------------------------------------------

    def connect_at_port(self, port: str, verbose=True) -> bool:
        """Open the serial port at address ``port`` and try to establish a
        connection.

        If the connection is successful and :meth:`set_ID_validation_query`
        was not set, then this function will return :const:`True`.

        If :meth:`set_ID_validation_query` was set, then this function will
        return :const:`True` or :const:`False` depending on the validation
        scheme as explained in :meth:`set_ID_validation_query`.

        Args:
            port (:obj:`str`):
                Serial port address to open.

            verbose (:obj:`bool`, optional):
                Print a `"Connecting to: "`-message to the terminal?

                Default: :const:`True`

        Returns:
            :const:`True` when successful, :const:`False` otherwise.
        """

        if verbose:
            if (
                self._ID_validation_query is None
                or self._valid_ID_specific is None
            ):
                print("Connecting to: %s" % self.long_name)
            else:
                print(
                    "Connecting to: %s | `%s`"
                    % (self.long_name, self._valid_ID_specific)
                )

        print("  @ %-5s: " % port, end="")
        try:
            # Open the serial port
            self.ser = serial.Serial(port=port, **self.serial_init_kwargs)
        except serial.SerialException:
            print("Could not open port.")
            return False
        except Exception as err:
            pft(err, 3)
            sys.exit(0)

        if self._ID_validation_query is None:
            # Found any device
            print("Any Success!")
            print("  `%s`\n" % self.name)
            self.is_alive = True
            return True

        # Optional validation query
        try:
            self.is_alive = True  # We must assume communication is possible
            (
                broad_query_reply,
                specific_query_reply,
            ) = self._ID_validation_query()

        except:
            print("I/O error in ID_validation_query().")
            self.close(ignore_exceptions=True)
            return False

        if broad_query_reply == self._valid_ID_broad:
            if specific_query_reply is not None:
                print("Found `%s`: " % specific_query_reply, end="")

            if self._valid_ID_specific is None:
                # Found a matching device in a broad sense
                print("Broad Success!")
                print("  `%s`\n" % self.name)
                self.is_alive = True
                return True

            elif specific_query_reply == self._valid_ID_specific:
                # Found a matching device in a specific sense
                print("Specific Success!")
                print("  `%s`\n" % self.name)
                self.is_alive = True
                return True

        print("Wrong or no device.")
        self.close(ignore_exceptions=True)
        return False

    # --------------------------------------------------------------------------
    #   scan_ports
    # --------------------------------------------------------------------------

    def scan_ports(self) -> bool:
        """Scan over all serial ports and try to establish a connection. See
        further the description at :meth:`connect_at_port`.

        Returns:
            :const:`True` when successful, :const:`False` otherwise.
        """
        if self._ID_validation_query is None or self._valid_ID_specific is None:
            print("Scanning ports for: %s" % self.long_name)
        else:
            print(
                "Scanning ports for: %s | `%s`"
                % (self.long_name, self._valid_ID_specific)
            )

        # Ports is a list of tuples
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            port = p[0]
            if self.connect_at_port(port, verbose=False):
                return True
            else:
                continue

        # Scanned over all the ports without finding a match
        print("\n  ERROR: Device not found")
        return False

    # --------------------------------------------------------------------------
    #   auto_connect
    # --------------------------------------------------------------------------

    def auto_connect(
        self, filepath_last_known_port: str = "config/port.txt"
    ) -> bool:
        """Try to connect to the device using the last-known successful port
        as got written to the textfile ``filepath_last_known_port`` by the
        previous call to :meth:`auto_connect`.

        When the file does not exist, can not be read or if the desired device
        can not be found at that specific port, then a scan over all ports will
        be performed by automatically invoking :meth:`scan_ports`.

        Args:
            filepath_last_known_port (:obj:`str`):
                Default: `"config/port.txt"`

        Returns:
            :const:`True` when successful, :const:`False` otherwise.
        """
        path = Path(filepath_last_known_port)
        port = self._get_last_known_port(path)

        if port is not None:
            success = self.connect_at_port(port)
        else:
            success = False

        if not success:
            success = self.scan_ports()
            if success:
                self._store_last_known_port(path, self.ser.portstr)

        return success

    # -----------------------------------------------------------------------------
    #   _get_last_known_port
    # -----------------------------------------------------------------------------

    def _get_last_known_port(self, path: Path):
        """Try to open the textfile pointed to by ``path``, containing the port
        to open. Do not panic if the file does not exist or cannot be read.

        Args:
            path (:class:`pathlib.Path`):
                Path to the textfile, e.g., ``Path("config/port.txt")``.

        Returns:
            The port name :obj:`str` when the textfile is read out successfully,
            :obj:`None` otherwise.
        """
        if isinstance(path, Path):
            if path.is_file():
                try:
                    with path.open() as f:
                        port = f.readline().strip()
                    return port
                except:
                    pass  # Do not panic and remain silent

        return None

    # -----------------------------------------------------------------------------
    #   _store_last_known_port
    # -----------------------------------------------------------------------------

    def _store_last_known_port(self, path: Path, port_str):
        """Try to write the port name string ``port_str`` to the textfile
        pointed to by ``path``. Do not panic if the file can not be created or
        written to.

        Args:
            path (:class:`pathlib.Path`):
                Path to the textfile, e.g., ``Path("config/port.txt")``.

            port_str (:obj:`str`):
                The port name string to write to file.

        Returns:
            :const:`True` when successful, :const:`False` otherwise.
        """
        if isinstance(path, Path):
            if not path.parent.is_dir():
                # Subfolder does not exists yet. Create.
                try:
                    path.parent.mkdir()
                except:
                    pass  # Do not panic and remain silent

            try:
                # Write the config file
                path.write_text(port_str)
            except:
                pass  # Do not panic and remain silent
            else:
                return True

        return False
