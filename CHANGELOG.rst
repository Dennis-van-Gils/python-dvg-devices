Changelog
=========

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
