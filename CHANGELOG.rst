Changelog
=========

1.5.1 (2025-01-21)
------------------
* Device Keysight_3497xA: Made hard-coded `VISA_TIMEOUT` an input argument
  instead

1.5.0 (2024-06-27)
------------------
* Support for Numpy 2.0
* Restore support for Python 3.6. Was removed by mistake. Version 1.4.0 and this
  version do support Python 3.6 actually, but only in combination with PyQt5.
  PySide2 will not work because the wrapper library `qtpy` still expects
  `app.exec_()` instead of `app.exec()`. That got fixed in the `qtpy` version
  for Python >= 3.7.

1.4.0 (2024-05-23)
------------------
Major clean-up and streamlining:

* Using `qtpy` library instead of my own Qt5/6 mechanism
* Changed all string formatting to f-strings
* Extended type hinting and checking
* Made demos uniform and passing `qdev` arguments to `MainWindow` now
* Individual source files now follow the PyPi package version
* Resolved nearly all Pylint / Pylance warnings
* Removed Python 3.6 support

New devices added:

* Xylem Hydrovar HVL - Variable speed pump controller
* Novanta IMS MDrive - Stepper motor controller

1.3.0 (2023-02-23)
------------------
* Added method ``BaseDevice.SerialDevice.query_bytes()``
* Fixed type hints in ``BaseDevice.SerialDevice``

1.2.0 (2022-09-14)
------------------
* Added support for PyQt5, PyQt6, PySide2 and PySide6

1.1.0 (2022-02-01)
------------------
* Added method ``BaseDevice.SerialDevice.readline()``

1.0.0 (2021-07-02)
------------------
* Stable release, identical to v0.2.6

0.2.6 (2021-03-02)
------------------
* Minor: Adjusted width of GUI control in ``Julabo_circulator_qdev.py``

0.2.5 (2021-03-02)
------------------
* Loosened dependence to ``pyserial~= 3.4``

0.2.4 (2021-03-02)
------------------
* Added device: Julabo circulator

0.2.3 (2020-08-27)
------------------
* Workaround for bug with unknown cause in ``Aim_TTi_PSU_protocol_RS232`` where
  the power supply occasionally will skew the serial input and output stream,
  such that the reply matches the second-previous query statement. Fixed by
  forcefully flushing the serial input and output buffers whenever a wrong reply
  is received. Hopefully, this will fix the skew when the next ``query()``
  operation gets executed.

0.2.2 (2020-08-27)
------------------
* Fixed bug in ``BaseDevice.query_ascii()``. The use of ``ast.literal_eval`` got
  removed because it chokes on ``nan``. Everything is now interpreted as a
  ``float`` instead.

0.2.1 (2020-08-12)
------------------
* Fix wrong import statement ``dvg-pyqt-controls``
* Fix wrong import statement ``dvg-pyqt-filelogger``

0.2.0 (2020-08-11)
------------------
* Added dependence ``dvg-pyqt-controls~=1.0``
* Added dependence ``dvg-pyqt-filelogger~=1.0``
* Added dependence ``dvg-pyqtgraph-threadsafe~=3.0``

0.1.0 (2020-07-23)
------------------
* Fixed bug in ``BaseDevice.py`` where ``inspect.getouterframes()`` would
  momentarily suspend the thread. Solved by ditching inspect. The new
  ``ID_validation_query`` mechanism now relies on a simple boolean flag that
  gets set to force ``query()`` to raise on timeout.
* Update dependence ``dvg-qdeviceio==0.3.0``

0.0.7 (2020-07-17)
------------------
* Update dependence ``dvg-qdeviceio==0.2.2``

0.0.6 (2020-07-16)
------------------
* Finished implementing ``BaseDevice.SerialDevice()``
* Update dependence ``dvg-qdeviceio==0.2.1``

0.0.5 (2020-07-07)
------------------
* Update dependence ``dvg-qdeviceio==0.2.0``
  Enum ``DAQ_trigger`` is now called ``DAQ_TRIGGER``
* Code style: Black

0.0.4 (2020-07-04)
------------------
* Update dependence ``dvg-qdeviceio==0.1.2``

0.0.3 (2020-07-02)
------------------
* Fixed broken packaging

0.0.2 (2020-07-02)
------------------
* Major restructuring PyPI package
* Implemented ``DvG_QDeviceIO``

0.0.1 (2020-07-01)
------------------
* First release on PyPI
