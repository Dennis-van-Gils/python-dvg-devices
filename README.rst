.. image:: https://img.shields.io/pypi/v/dvg-devices
    :target: https://pypi.org/project/dvg-devices
.. image:: https://img.shields.io/pypi/pyversions/dvg-devices
    :target: https://pypi.org/project/dvg-devices
.. image:: https://requires.io/github/Dennis-van-Gils/python-dvg-devices/requirements.svg?branch=master
    :target: https://requires.io/github/Dennis-van-Gils/python-dvg-devices/requirements/?branch=master
    :alt: Requirements Status
.. image:: https://readthedocs.org/projects/python-dvg-devices/badge/?version=latest
    :target: https://python-dvg-devices.readthedocs.io/en/latest/?badge=latest
.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/psf/black
.. image:: https://img.shields.io/badge/License-MIT-purple.svg
    :target: https://github.com/Dennis-van-Gils/python-dvg-devices/blob/master/LICENSE.txt

DvG_Devices
=============
*Collection of I/O interfaces to communicate with microcontroller boards and
laboratory devices, with optional PyQt5 multithread support and graphical
user-interfaces.*

- Documentation: https://python-dvg-devices.readthedocs.io
- Github: https://github.com/Dennis-van-Gils/python-dvg-devices
- PyPI: https://pypi.org/project/dvg-devices

Installation::

    pip install dvg-devices

Supported devices
-----------------

    =======================    =======================
    Arduino, or similar        microcontroller board
    Aim TTi QL series II       power supply
    Bronkhorst EL-FLOW         mass flow controller
    Julabo circulator          recirculating bath
    Keysight 3497xA            digital multimeter
    Keysight N8700             power supply
    Parker Compax3             servo controller
    Picotech PT104             temperature logger
    PolyScience PD             recirculating bath
    ThermoFisher ThermoFlex    chiller
    =======================    =======================

Highlights
----------
* Class ``SerialDevice()`` offering higher-level general I/O methods for
  a serial device, such as ``auto_connect()``, ``write()`` and ``query()``.

* Class ``Arduino()`` which wraps around ``SerialDevice()``. In combination with
  `DvG_SerialCommand <https://github.com/Dennis-van-Gils/DvG_SerialCommand>`_ it
  allows for automatically connecting to your Arduino(-like) device and for easy
  serial I/O communication.

* Separate PyQt5 interfaces are provided for each of these devices, offering
  out-of-the-box multithreaded data acquisition and communication. It relies on
  `DvG_QDeviceIO <https://python-dvg-qdeviceio.readthedocs.io>`_.

* Ready-to-run PyQt5 demos to directly control many of the supported
  devices with a graphical user-interface.
