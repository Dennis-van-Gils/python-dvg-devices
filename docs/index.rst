DvG_Devices
=============
*Collection of I/O interfaces to communicate with microcontroller boards and
laboratory devices, with optional PyQt/PySide multithread support and graphical
user-interfaces.*

- Documentation: https://python-dvg-devices.readthedocs.io
- Github: https://github.com/Dennis-van-Gils/python-dvg-devices
- PyPI: https://pypi.org/project/dvg-devices

Supports PyQt5, PyQt6, PySide2 and PySide6.

Installation::

    pip install dvg-devices

Installation with an optional Qt-library::

    pip install dvg-devices[pyqt5/pyqt6/pyside2/pyside6]

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
  `DvG_StreamCommand <https://github.com/Dennis-van-Gils/DvG_StreamCommand>`_ it
  allows for automatically connecting to your Arduino(-like) device and for easy
  serial I/O communication.

* Separate PyQt/PySide interfaces are provided for each of these devices,
  offering out-of-the-box multithreaded data acquisition and communication. It
  relies on `DvG_QDeviceIO <https://python-dvg-qdeviceio.readthedocs.io>`_.

* Ready-to-run PyQt/PySide demos to directly control many of the supported
  devices with a graphical user-interface.


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
