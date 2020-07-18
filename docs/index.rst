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
    Parker Compax3             servo controller
    Keysight 3497xA            digital multimeter
    Keysight N8700             power supply
    Picotech PT104             temperature logger
    PolyScience PD             recirculating bath
    ThermoFisher ThermoFlex    chiller
    =======================    =======================

Highlights
----------
* Class SerialDevice() offering higher-level general I/O methods for
  a serial device, such as auto_connect(), write() and query().

* Class Arduino() which wraps around SerialDevice(). In combination with
  https://github.com/Dennis-van-Gils/DvG_SerialCommand it allows for
  automatically connecting to your Arduino(-like) device and for easy serial
  I/O communication.

* Separate PyQt5 interfaces are provided for each of these devices
  offering out-of-the-box multithreaded data acquisition and communication. It
  relies on https://python-dvg-qdeviceio.readthedocs.io/en/latest.

* Ready-to-run PyQt5 demos to directly control many of the supported
  devices.


.. toctree::
   :caption: API

   api-serialdevice
   api-arduinoprotocolserial



.. toctree::
   :maxdepth: 1
   :caption: Other

   authors
   changelog
   contributing
   genindex
