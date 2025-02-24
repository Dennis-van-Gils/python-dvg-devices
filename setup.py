#!/usr/bin/env python
# -*- encoding: utf-8 -*-
from __future__ import absolute_import
from __future__ import print_function

import io
import re
from glob import glob
from os.path import basename
from os.path import dirname
from os.path import join
from os.path import splitext

from setuptools import find_namespace_packages
from setuptools import setup


def read(*names, **kwargs):
    with io.open(
        join(dirname(__file__), *names), encoding=kwargs.get("encoding", "utf8")
    ) as fh:
        return fh.read()


setup(
    name="dvg-devices",
    version="1.5.1",
    license="MIT",
    description="Collection of I/O interfaces to communicate with microcontroller boards and laboratory devices, with optional PyQt/PySide multithread support and graphical user-interfaces.",
    long_description="%s\n%s"
    % (
        re.compile("^.. start-badges.*^.. end-badges", re.M | re.S).sub(
            "", read("README.rst")
        ),
        re.sub(":[a-z]+:`~?(.*?)`", r"``\1``", read("CHANGELOG.rst")),
    ),
    long_description_content_type="text/x-rst",
    author="Dennis van Gils",
    author_email="vangils.dennis@gmail.com",
    url="https://python-dvg-devices.readthedocs.io",
    packages=find_namespace_packages("src"),
    package_dir={"": "src"},
    py_modules=[splitext(basename(path))[0] for path in glob("src/*.py")],
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        # complete classifier list: http://pypi.python.org/pypi?%3Aaction=list_classifiers
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: MIT License",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Topic :: Scientific/Engineering ",
        "Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)",
        "Topic :: Scientific/Engineering :: Physics",
    ],
    project_urls={
        "Issue Tracker": "https://github.com/Dennis-van-Gils/python-dvg-devices/issues",
    },
    keywords=[
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "device I/O",
        "automation",
        "laboratory",
        "science",
        "control",
        "experiment",
        "multithread",
        "Arduino",
        "serial",
        "VISA",
    ],
    python_requires=">=3.6",
    install_requires=[
        "dvg-debug-functions~=2.5",
        "dvg-pid-controller~=2.2",
        "dvg-pyqt-controls~=1.5",
        "dvg-pyqt-filelogger~=1.4",
        "dvg-pyqtgraph-threadsafe~=3.4",
        "dvg-qdeviceio~=1.6",
        "matplotlib~=3.1",
        "numpy>=1.15,<3.0",
        "pyserial~=3.4",
        "pyvisa~=1.11",
        "qtpy",
    ],
    extras_require={
        "pyqt5": ["pyqt5~=5.12"],
        "pyqt6": ["pyqt6"],
        "pyside2": ["pyside2"],
        "pyside6": ["pyside6"],
    },
)
