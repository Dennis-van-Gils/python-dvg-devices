# Contents
Python library to interface with an Arduino(-like) device over a serial connection with the possibility of multithreaded communication using PyQt5.

**A multithreaded demo showing off the features of this library can be found here:** [DvG_Arduino_PyQt_multithread_demo](https://github.com/Dennis-van-Gils/DvG_Arduino_PyQt_multithread_demo). Give it a try. It has a [PyQt5](https://pypi.org/project/PyQt5/) graphical user-interface, with a [PyQtGraph](http://pyqtgraph.org/) plot for fast real-time plotting of data, which are obtained from a waveform generating Arduino (source files included) at a data rate of 100 Hz, and it provides logging this data to a file.

#### DvG_dev_Arduino__fun_serial.py

Provides class `Arduino`. It can automatically connect to an Arduino(-like) device by scanning over all serial ports and provides message based communication like `ard.write('toggle LED')`, `[success, ans_str] = ard.query('value?')` and `[success, ans_list_of_floats] = ard.query_ascii_values('values?')`.

Requirements:
* [pySerial](https://pypi.org/project/pyserial/)
* [DvG_debug_functions](https://github.com/Dennis-van-Gils/DvG_debug_functions/)

#### On the Arduino side
I also provide a C++ library for the Arduino(-like) device that provides listening to a serial port for commands and act upon them. That library can be used in conjunction (but not required) with this Python library. See [DvG_SerialCommand](https://github.com/Dennis-van-Gils/DvG_SerialCommand).

#### DvG_dev_Arduino__pyqt_lib.py

Provides class `Arduino_pyqt` with higher-level PyQt5 functions. It provides multithreaded communication with an Arduino(-like) device where one thread reads data from the device at a fixed rate and another thread maintains a thread-safe queue to send out messages to the device.

Requirements:
* [NumPy](https://www.numpy.org/)
* [PyQt5](https://pypi.org/project/PyQt5/)
* [DvG_dev_Arduino__fun_serial.py](DvG_dev_Arduino__fun_serial.py)
* [DvG_dev_Base__pyqt_lib.py](DvG_dev_Base__pyqt_lib.py)



# DvG_dev_Arduino__fun_serial.py
Module to communicate with an Arduino(-like) device over a serial connection.
* Provides automatic scanning over all serial ports for the Arduino.
* Mimicks the [PyVISA](https://pypi.org/project/PyVISA/) library  by providing ``query`` and ``query_ascii_values`` methods, which write a message to the Arduino and return back its reply.

The Arduino should be programmed to respond to a so-called 'identity' query over the serial connection. It must reply to ``query('id?')`` with an ASCII string response. Choosing a unique identity response per each Arduino in your project allows for auto-connecting to these Arduinos without specifying the serial port.

Only ASCII based communication is supported so-far. Binary encoded communication will be possible as well after a few modifications to this library have been made (work in progress).

#### class Arduino(...):
```
    Manages serial communication with an Arduino(-like) device.

    Methods:
        close():
            Close the serial connection.

        connect_at_port(...)
            Try to establish a connection on this serial port.

        scan_ports(...)
            Scan over all serial ports and try to establish a connection.

        auto_connect(...)
            Try the last used serial port, or scan over all when it fails.

        write(...)
            Write a string to the serial port.

        query(...)
            Write a string to the serial port and return the reply.

        query_ascii_values(...)
            Write a string to the serial port and return the reply, parsed
            into a list of floats.

    Important member:
        ser: 'serial.Serial' instance belonging to the Arduino.
```
