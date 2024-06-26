|pypi| |python| |readthedocs| |black| |license|

.. |pypi| image:: https://img.shields.io/pypi/v/dvg-devices
    :target: https://pypi.org/project/dvg-devices
.. |python| image:: https://img.shields.io/pypi/pyversions/dvg-devices
    :target: https://pypi.org/project/dvg-devices
.. |readthedocs| image:: https://readthedocs.org/projects/python-dvg-devices/badge/?version=latest
    :target: https://python-dvg-devices.readthedocs.io/en/latest/?badge=latest
.. |black| image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/psf/black
.. |license| image:: https://img.shields.io/badge/License-MIT-purple.svg
    :target: https://github.com/Dennis-van-Gils/python-dvg-devices/blob/master/LICENSE.txt

DvG_Devices
=============
*Collection of I/O interfaces to communicate with microcontroller boards and
laboratory devices, with optional PyQt/PySide multithread support and graphical
user-interfaces.*

Supports PyQt5, PyQt6, PySide2 and PySide6.

- Documentation: https://python-dvg-devices.readthedocs.io
- Github: https://github.com/Dennis-van-Gils/python-dvg-devices
- PyPI: https://pypi.org/project/dvg-devices

Installation::

    pip install dvg-devices

To be able to run the several provided graphical user-interfaces, one has to
install an additional Qt-library. This can be either PyQt5, PyQt6, PySide2 or
PySide6. Pick one. My personal recommendation is ``PyQt5 for Python <= 3.7``,
and ``PySide6 for Python >= 3.8``::

    pip install pyqt5
    pip install pyqt6
    pip install pyside2
    pip install pyside6

If you wish to interface with an GPIB device you need to additionally install a
Visa backend. See
https://pyvisa.readthedocs.io/en/latest/introduction/getting.html

Supported devices
-----------------

    =======================    ==============================
    Arduino, or similar        Microcontroller board
    Aim TTi QL series II       Power supply
    Bronkhorst EL-FLOW         Mass flow controller
    Julabo circulator          Recirculating bath
    Keysight 3497xA            Digital multimeter
    Keysight N8700             Power supply
    Novanta IMS MDrive         Stepper motor controller
    Parker Compax3             Servo controller
    Picotech PT104             Temperature logger
    PolyScience PD             Recirculating bath
    ThermoFisher ThermoFlex    Chiller
    Xylem Hydrovar HVL         Variable speed pump controller
    =======================    ==============================

Highlights
----------
* Class ``SerialDevice()`` offering higher-level general I/O methods for
  a serial device, such as ``auto_connect()``, ``write()`` and ``query()``.

* Class ``Arduino()`` which wraps around ``SerialDevice()``. In combination with
  `DvG_StreamCommand <https://github.com/Dennis-van-Gils/DvG_StreamCommand>`_ it
  allows for automatically connecting to your Arduino(-like) device and for easy
  serial I/O communication.

* Separate PyQt/PySide interfaces are provided for each of these devices,
  offering out-of-the-box multithreaded data acquisition and communication. It
  relies on `DvG_QDeviceIO <https://python-dvg-qdeviceio.readthedocs.io>`_.

* Ready-to-run PyQt/PySide demos to directly control many of the supported
  devices with a graphical user-interface.
