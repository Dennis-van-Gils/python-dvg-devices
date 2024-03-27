#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt/PySide module to provide multithreaded communication and periodical data
acquisition for MDrive stepper motors by Novanta IMS (former Schneider Electric)
set up in party mode.

TODO: WORK IN PROGRESS
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "27-03-2024"
__version__ = "1.0.0"
# pylint: disable=broad-except, try-except-raise, missing-function-docstring, multiple-statements

import os
import sys

# TODO: Force use of PySide6 during developing. Delete when releasing code.
from PySide6 import QtCore, QtGui, QtWidgets as QtWid
from PySide6.QtCore import Slot
from PySide6.QtCore import Signal

# Mechanism to support both PyQt and PySide
# -----------------------------------------

PYQT5 = "PyQt5"
PYQT6 = "PyQt6"
PYSIDE2 = "PySide2"
PYSIDE6 = "PySide6"
QT_LIB_ORDER = [PYQT5, PYSIDE2, PYSIDE6, PYQT6]
QT_LIB = None

if QT_LIB is None:
    for lib in QT_LIB_ORDER:
        if lib in sys.modules:
            QT_LIB = lib
            break

if QT_LIB is None:
    for lib in QT_LIB_ORDER:
        try:
            __import__(lib)
            QT_LIB = lib
            break
        except ImportError:
            pass

if QT_LIB is None:
    this_file = __file__.rsplit(os.sep, maxsplit=1)[-1]
    raise ImportError(
        f"{this_file} requires PyQt5, PyQt6, PySide2 or PySide6; "
        "none of these packages could be imported."
    )

"""
# fmt: off
# pylint: disable=import-error, no-name-in-module
if QT_LIB == PYQT5:
    from PyQt5 import QtCore, QtWidgets as QtWid           # type: ignore
    from PyQt5.QtCore import pyqtSlot as Slot              # type: ignore
    from PyQt5.QtCore import pyqtSignal as Signal          # type: ignore
elif QT_LIB == PYQT6:
    from PyQt6 import QtCore, QtWidgets as QtWid           # type: ignore
    from PyQt6.QtCore import pyqtSlot as Slot              # type: ignore
    from PyQt6.QtCore import pyqtSignal as Signal          # type: ignore
elif QT_LIB == PYSIDE2:
    from PySide2 import QtCore, QtWidgets as QtWid         # type: ignore
    from PySide2.QtCore import Slot                        # type: ignore
    from PySide2.QtCore import Signal                      # type: ignore
elif QT_LIB == PYSIDE6:
    from PySide6 import QtCore, QtWidgets as QtWid         # type: ignore
    from PySide6.QtCore import Slot                        # type: ignore
    from PySide6.QtCore import Signal                      # type: ignore
# pylint: enable=import-error, no-name-in-module
# fmt: on
"""

# \end[Mechanism to support both PyQt and PySide]
# -----------------------------------------------

import dvg_pyqt_controls as controls

# from dvg_debug_functions import print_fancy_traceback as pft

# from dvg_qdeviceio import QDeviceIO, DAQ_TRIGGER
# from dvg_devices.Julabo_circulator_protocol_RS232 import Julabo_circulator


class MDrive_Controller_qdev:
    def __init__(self, **kwargs):
        super().__init__(**kwargs)  # Pass kwargs onto QtCore.QObject()

        self.create_GUI()

    # --------------------------------------------------------------------------
    #   create GUI
    # --------------------------------------------------------------------------

    def create_GUI(self):

        SS_TABS = (
            "QTabWidget::pane {"
            "   border: 0px solid gray;}"
            "QTabBar::tab:selected {"
            "   background: " + controls.COLOR_TAB_ACTIVE + "; "
            "   border-bottom-color: " + controls.COLOR_TAB_ACTIVE + ";}"
            "QTabWidget>QWidget>QWidget {"
            "   border: 2px solid gray;"
            "   background: " + controls.COLOR_TAB_ACTIVE + ";} "
            "QTabBar::tab {"
            "   background: " + controls.COLOR_TAB + ";"
            "   border: 2px solid gray;"
            "   border-bottom-color: " + controls.COLOR_TAB + ";"
            "   border-top-left-radius: 4px;"
            "   border-top-right-radius: 4px;"
            # "   min-width: 119px;"
            "   padding: 6px;} "
            "QTabBar::tab:hover {"
            "   background: " + controls.COLOR_HOVER + ";"
            "   border: 2px solid " + controls.COLOR_HOVER_BORDER + ";"
            "   border-bottom-color: " + controls.COLOR_HOVER + ";"
            "   border-top-left-radius: 4px;"
            "   border-top-right-radius: 4px;"
            "   padding: 6px;} "
            "QTabWidget::tab-bar {"
            "   left: 0px;}"
        )

        self.qtab = QtWid.QTabWidget()
        self.qtab.setStyleSheet(SS_TABS)

        # ---------------------
        #   Tab page: Control
        # ---------------------

        self.led_is_home_known = controls.create_tiny_LED(checked=True)
        self.led_is_moving = controls.create_tiny_LED(checked=True)
        self.led_is_velocity_changing = controls.create_tiny_LED(checked=True)

        p1 = {"alignment": QtCore.Qt.AlignmentFlag.AlignRight}
        p2 = {"alignment": QtCore.Qt.AlignmentFlag.AlignRight, "readOnly": True}
        self.error_status = QtWid.QLineEdit("0", **p2)
        self.current_position = QtWid.QLineEdit("nan", **p2)
        self.current_velocity = QtWid.QLineEdit("nan", **p2)
        self.software_max_position = QtWid.QLineEdit("320", **p1)
        self.software_min_position = QtWid.QLineEdit("0", **p1)
        self.wanted_position = QtWid.QLineEdit("0", **p1)
        self.wanted_velocity = QtWid.QLineEdit("0", **p1)
        self.step_size_1 = QtWid.QLineEdit("1", **p1)
        self.step_size_2 = QtWid.QLineEdit("10", **p1)

        self.pbtn_init_interface = QtWid.QPushButton("Init interface")
        self.pbtn_home = QtWid.QPushButton("Home")
        self.pbtn_move_to_position = QtWid.QPushButton("Move to position")
        self.pbtn_move_with_velocity = QtWid.QPushButton("Move with velocity")
        self.pbtn_controlled_stop = QtWid.QPushButton("Controlled stop")
        self.pbtn_step_1_plus = QtWid.QPushButton("Step+")
        self.pbtn_step_2_plus = QtWid.QPushButton("Step++")
        self.pbtn_step_1_minus = QtWid.QPushButton("Step-")
        self.pbtn_step_2_minus = QtWid.QPushButton("Step--")
        self.pbtn_STOP = QtWid.QPushButton("\nEMERGENCY STOP\n")

        i = 0
        # fmt: off
        grid = QtWid.QGridLayout()
        grid.setVerticalSpacing(2)

        grid.addWidget(QtWid.QLabel("<b>Readings</b>")       , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)                 , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Is home known?")        , i, 0)
        grid.addWidget(self.led_is_home_known                , i, 1)      ; i+=1
        grid.addWidget(QtWid.QLabel("Is moving?")            , i, 0)
        grid.addWidget(self.led_is_moving                    , i, 1)      ; i+=1
        grid.addWidget(QtWid.QLabel("Is velocity changing?") , i, 0)
        grid.addWidget(self.led_is_velocity_changing         , i, 1)      ; i+=1
        grid.addWidget(QtWid.QLabel("Error status")          , i, 0)
        grid.addWidget(self.error_status                     , i, 1)      ; i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)                 , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Current position")      , i, 0)
        grid.addWidget(self.current_position                 , i, 1)
        grid.addWidget(QtWid.QLabel("mm")                    , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("Current velocity")      , i, 0)
        grid.addWidget(self.current_velocity                 , i, 1)
        grid.addWidget(QtWid.QLabel("mm/s")                  , i, 2)      ; i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)                 , i, 0)      ; i+=1

        grid.addWidget(QtWid.QLabel("<b>Software limits</b>"), i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)                 , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Max position")          , i, 0)
        grid.addWidget(self.software_max_position            , i, 1)      ; i+=1
        grid.addWidget(QtWid.QLabel("Min position")          , i, 0)
        grid.addWidget(self.software_min_position            , i, 1)      ; i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)                 , i, 0)      ; i+=1

        grid.addWidget(QtWid.QLabel("<b>Actuate</b>")        , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)                 , i, 0)      ; i+=1
        grid.addWidget(self.pbtn_init_interface              , i, 0)      ; i+=1
        grid.addWidget(self.pbtn_home                        , i, 0)      ; i+=1
        grid.addWidget(self.pbtn_move_to_position            , i, 0)
        grid.addWidget(self.wanted_position                  , i, 1)
        grid.addWidget(QtWid.QLabel("mm")                    , i, 2)      ; i+=1
        grid.addWidget(self.wanted_velocity                  , i, 1)
        grid.addWidget(self.pbtn_move_with_velocity          , i, 0)
        grid.addWidget(QtWid.QLabel("mm/s")                  , i, 2)      ; i+=1
        grid.addWidget(self.pbtn_controlled_stop             , i, 0)      ; i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)                 , i, 0)      ; i+=1

        grid.addWidget(QtWid.QLabel("<b>Step control</b>")   , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)                 , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Step size ++/--")       , i, 0)
        grid.addWidget(self.step_size_2                      , i, 1)
        grid.addWidget(QtWid.QLabel("mm")                    , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("Step size +/-")         , i, 0)
        grid.addWidget(self.step_size_1                      , i, 1)
        grid.addWidget(QtWid.QLabel("mm")                    , i, 2)      ; i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)                 , i, 0)      ; i+=1

        subgrid = QtWid.QGridLayout()
        subgrid.setVerticalSpacing(2)
        subgrid.addWidget(self.pbtn_step_2_minus             , 0, 0)
        subgrid.addWidget(self.pbtn_step_2_plus              , 0, 1)
        subgrid.addWidget(self.pbtn_step_1_minus             , 1, 0)
        subgrid.addWidget(self.pbtn_step_1_plus              , 1, 1)

        grid.addLayout(subgrid                               , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 12)                , i, 0)      ; i+=1
        grid.addWidget(self.pbtn_STOP                        , i, 0, 1, 3); i+=1
        # fmt: on

        grid_widget = QtWid.QWidget()
        grid_widget.setLayout(grid)
        self.page_1 = self.qtab.addTab(grid_widget, "Control")

        # ---------------------
        #   Tab page: Motion
        # ---------------------

        empty_widget_1 = QtWid.QWidget()
        self.page_2 = self.qtab.addTab(empty_widget_1, "Motion params")

        # ---------------------
        #   Tab page: Device
        # ---------------------

        empty_widget_2 = QtWid.QWidget()
        self.page_3 = self.qtab.addTab(empty_widget_2, "Device")

        self.hbox = QtWid.QHBoxLayout()
        self.hbox.addWidget(self.qtab)


# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(
        self, mdrive_qdev: MDrive_Controller_qdev, parent=None, **kwargs
    ):
        super().__init__(parent, **kwargs)

        self.setWindowTitle("MDrive control")
        self.setGeometry(600, 120, 0, 0)
        self.setStyleSheet(
            controls.SS_TEXTBOX_READ_ONLY
            + controls.SS_GROUP
            + controls.SS_HOVER
        )

        self.pbtn_exit = QtWid.QPushButton("Exit")
        self.pbtn_exit.clicked.connect(self.close)
        self.pbtn_exit.setMinimumHeight(30)

        hbox = QtWid.QHBoxLayout()
        hbox.addLayout(mdrive_qdev.hbox, stretch=1)
        hbox.addWidget(
            self.pbtn_exit, alignment=QtCore.Qt.AlignmentFlag.AlignTop
        )
        hbox.addStretch(1)

        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(hbox)
        vbox.addStretch(1)


# ------------------------------------------------------------------------------
#   about_to_quit
# ------------------------------------------------------------------------------


@Slot()
def about_to_quit():
    print("About to quit")
    app.processEvents()
    # julabo_qdev.quit()
    # julabo.close()


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":

    # --------------------------------------------------------------------------
    #   Create application
    # --------------------------------------------------------------------------
    QtCore.QThread.currentThread().setObjectName("MAIN")  # For DEBUG info
    app = QtWid.QApplication(sys.argv)
    app.aboutToQuit.connect(about_to_quit)

    mdrive_qdev = MDrive_Controller_qdev()
    window = MainWindow(mdrive_qdev=mdrive_qdev)

    # Start the main GUI event loop
    window.show()
    sys.exit(app.exec())
