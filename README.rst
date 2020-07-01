.. image:: https://img.shields.io/pypi/v/dvg-devices
    :target: https://pypi.org/project/dvg-devices
.. image:: https://img.shields.io/pypi/pyversions/dvg-devices
    :target: https://pypi.org/project/dvg-devices
.. image:: https://img.shields.io/badge/License-MIT-purple.svg
    :target: https://github.com/Dennis-van-Gils/python-dvg-devices/blob/master/LICENSE.txt

DvG_Devices
=============
Collection of interfaces to communicate with laboratory devices, with support
for multithreading in PyQt5.

* Arduino -- microcontroller
* Bronkhorst -- mass flow controller
* Compax3 -- servo controller
* Keysight 3497xA -- digital multimeter
* Keysight N8700 -- power supply
* Picotech PT104 -- temperature logger
* PolyScience PD -- recirculating bath
* ThermoFlex -- chiller

IN PROGRESS:

Currently this library contains the prototypes as used in the TMHT Tunnel
facility. Everything has to be rewritten to make use of `DvG_QDeviceIO`. This
is in progress and might take a while.
