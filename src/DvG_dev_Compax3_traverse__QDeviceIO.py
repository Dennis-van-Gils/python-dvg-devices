#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt5 module to provide multithreaded communication and periodical data
acquisition for a Compax3 traverse controller.
"""
__author__      = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__         = ""
__date__        = "14-09-2018"
__version__     = "1.0.0"

from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets as QtWid

from DvG_pyqt_controls import (SS_GROUP,
                               SS_TEXTBOX_ERRORS,
                               create_error_LED,
                               create_tiny_LED)

import DvG_dev_Compax3_traverse__fun_RS232 as compax3_functions
import DvG_dev_Base__pyqt_lib as Dev_Base_pyqt_lib

# Show debug info in terminal? Warning: Slow! Do not leave on unintentionally.
DEBUG_worker_DAQ  = False
DEBUG_worker_send = False

# ------------------------------------------------------------------------------
#   Compax3_traverse_pyqt
# ------------------------------------------------------------------------------

class Compax3_traverse_pyqt(Dev_Base_pyqt_lib.Dev_Base_pyqt, QtCore.QObject):
    """Manages multithreaded communication and periodical data acquisition for
    a Compax3 traverse controller, referred to as the 'device'.

    In addition, it also provides PyQt5 GUI objects for control of the device.
    These can be incorporated into your application.

    All device I/O operations will be offloaded to 'workers', each running in
    a newly created thread instead of in the main/GUI thread.

        - Worker_DAQ:
            Periodically acquires data from the device.

        - Worker_send:
            Maintains a thread-safe queue where desired device I/O operations
            can be put onto, and sends the queued operations first in first out
            (FIFO) to the device.

    (*): See 'DvG_dev_Base__pyqt_lib.py' for details.

    Args:
        dev:
            Reference to a 'DvG_dev_Compax3_traverse__fun_RS232.Compax3_traverse'
            instance.

        (*) DAQ_update_interval_ms
        (*) DAQ_critical_not_alive_count
        (*) DAQ_timer_type

    Main methods:
        (*) start_thread_worker_DAQ(...)
        (*) start_thread_worker_send(...)
        (*) close_all_threads()

    Inner-class instances:
        (*) worker_DAQ
        (*) worker_send

    Main data attributes:
        (*) DAQ_update_counter
        (*) obtained_DAQ_update_interval_ms
        (*) obtained_DAQ_rate_Hz

    Main GUI objects:
        qgrp (PyQt5.QtWidgets.QGroupBox)

    Signals:
        (*) signal_DAQ_updated()
        (*) signal_connection_lost()
    """
    def __init__(self,
                 dev: compax3_functions.Compax3_traverse,
                 DAQ_update_interval_ms=250,
                 DAQ_critical_not_alive_count=1,
                 DAQ_timer_type=QtCore.Qt.CoarseTimer,
                 parent=None):
        super(Compax3_traverse_pyqt, self).__init__(parent=parent)

        self.attach_device(dev)

        self.create_worker_DAQ(DAQ_update_interval_ms,
                               self.DAQ_update,
                               DAQ_critical_not_alive_count,
                               DAQ_timer_type,
                               DEBUG=DEBUG_worker_DAQ)

        self.create_worker_send(DEBUG=DEBUG_worker_send)

        self.create_GUI()
        self.signal_DAQ_updated.connect(self.update_GUI)
        self.connect_signals_to_slots()
        if not self.dev.is_alive:
            self.update_GUI()  # Correctly reflect an offline device

        # Flags for Jog+/Jog- pushbutton control
        self.jog_plus_is_active = False
        self.jog_minus_is_active = False

    # --------------------------------------------------------------------------
    #   DAQ_update
    # --------------------------------------------------------------------------

    def DAQ_update(self):
        success = self.dev.query_position()
        success &= self.dev.query_status_word_1()

        if not(self.dev.status_word_1.no_error):
            self.dev.query_error()

        return success

    # --------------------------------------------------------------------------
    #   create_GUI
    # --------------------------------------------------------------------------

    def create_GUI(self):
        default_font_height = 17
        default_font_width = 8

        # Sub-groupbox: Status word 1 bits
        self.sw1_powerless          = create_tiny_LED()
        self.sw1_powered_stationary = create_tiny_LED()
        self.sw1_zero_pos_known     = create_tiny_LED()
        self.sw1_pos_reached        = create_tiny_LED()

        i = 0;
        p = {'alignment': QtCore.Qt.AlignRight}
        grid = QtWid.QGridLayout()
        grid.setVerticalSpacing(4)
        grid.addWidget(QtWid.QLabel("powerless", **p)         , i, 0)
        grid.addWidget(self.sw1_powerless                     , i, 1); i+=1
        grid.addWidget(QtWid.QLabel("powered stationary", **p), i, 0)
        grid.addWidget(self.sw1_powered_stationary            , i, 1); i+=1
        grid.addWidget(QtWid.QLabel("zero pos. known", **p)   , i, 0)
        grid.addWidget(self.sw1_zero_pos_known                , i, 1); i+=1
        grid.addWidget(QtWid.QLabel("position reached", **p)  , i, 0)
        grid.addWidget(self.sw1_pos_reached                   , i, 1); i+=1
        #grid.setColumnStretch(0, 0)
        #grid.setColumnStretch(1, 0)

        self.qgrp_sw1 = QtWid.QGroupBox("Status word 1")
        self.qgrp_sw1.setLayout(grid)

        # Main groupbox
        font_lbl_status = QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Bold)
        self.lbl_status = QtWid.QLabel("OFFLINE", font=font_lbl_status,
                                       alignment=QtCore.Qt.AlignCenter)
        self.lbl_status.setFixedHeight(
                3 * QtGui.QFontMetrics(font_lbl_status).height())

        self.sw1_error_tripped = create_error_LED(text="No error")
        self.error_msg = QtWid.QPlainTextEdit('', lineWrapMode=True)
        self.error_msg.setStyleSheet(SS_TEXTBOX_ERRORS)
        self.error_msg.setMinimumWidth(22 * default_font_width)
        self.error_msg.setFixedHeight(4 * default_font_height)
        self.pbtn_ackn_error = QtWid.QPushButton("Acknowledge error")
        self.qled_cur_pos = QtWid.QLineEdit("nan", readOnly = True,
                                            alignment=QtCore.Qt.AlignRight)
        self.qled_new_pos = QtWid.QLineEdit("nan", readOnly = False,
                                            alignment=QtCore.Qt.AlignRight)
        self.pbtn_move_to_new_pos = QtWid.QPushButton("Move to new position")
        self.pbtn_move_to_new_pos.setFixedHeight(3 * default_font_height)
        self.pbtn_jog_plus  = QtWid.QPushButton("Jog +")
        self.pbtn_jog_minus = QtWid.QPushButton("Jog -")
        self.pbtn_stop = QtWid.QPushButton("\nSTOP &&\nREMOVE POWER\n")
        self.lbl_update_counter = QtWid.QLabel("0")

        i = 0;
        p = {'alignment': QtCore.Qt.AlignRight}
        grid = QtWid.QGridLayout()
        grid.setVerticalSpacing(4)
        grid.addWidget(self.lbl_status             , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 12)      , i, 0)      ; i+=1
        grid.addWidget(self.sw1_error_tripped      , i, 0, 1, 3); i+=1
        grid.addWidget(self.error_msg              , i, 0, 1, 3); i+=1
        grid.addWidget(self.pbtn_ackn_error        , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 12)      , i, 0)      ; i+=1
        grid.addWidget(self.qgrp_sw1               , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 12)      , i, 0)      ; i+=1

        grid.addWidget(QtWid.QLabel("Position:")   , i, 0, 1, 3); i+=1
        grid.addWidget(QtWid.QLabel("Current")     , i, 0)
        grid.addWidget(self.qled_cur_pos           , i, 1)
        grid.addWidget(QtWid.QLabel("mm")          , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("New")         , i, 0)
        grid.addWidget(self.qled_new_pos           , i, 1)
        grid.addWidget(QtWid.QLabel("mm")          , i, 2)      ; i+=1

        grid.addItem(QtWid.QSpacerItem(1, 12)      , i, 0)      ; i+=1
        grid.addWidget(self.pbtn_move_to_new_pos   , i, 0, 1, 3); i+=1
        grid.addWidget(self.pbtn_jog_plus          , i, 0, 1, 3); i+=1
        grid.addWidget(self.pbtn_jog_minus         , i, 0, 1, 3); i+=1
        grid.addWidget(self.pbtn_stop              , i, 0, 1, 3); i+=1
        grid.addWidget(self.lbl_update_counter     , i, 0, 1, 3); i+=1
        #grid.setColumnStretch(0, 0)
        #grid.setColumnStretch(1, 0)
        #grid.setColumnStretch(2, 0)

        self.qgrp = QtWid.QGroupBox("%s" % self.dev.name)
        self.qgrp.setStyleSheet(SS_GROUP)
        self.qgrp.setLayout(grid)
        self.qgrp.setMaximumWidth(200)   # Work=around, hard limit width

    # --------------------------------------------------------------------------
    #   update_GUI
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def update_GUI(self):
        """NOTE: 'self.dev.mutex' is not being locked, because we are only
        reading 'state' for displaying purposes. We can do this because 'state'
        members are written and read atomicly.
        Not locking the mutex might speed up the program.
        """
        if self.dev.is_alive:
            # At startup
            if self.DAQ_update_counter == 1:
                self.qled_new_pos.setText("%.2f" % self.dev.state.cur_pos)

            if self.dev.status_word_1.powerless:
                self.lbl_status.setText("powerless")
            else:
                if self.dev.status_word_1.powered_stationary:
                    self.lbl_status.setText("POWERED\nstationary")
                else:
                    self.lbl_status.setText("POWERED")

            self.sw1_error_tripped.setChecked(
                    not(self.dev.status_word_1.no_error))
            if self.dev.status_word_1.no_error:
                self.sw1_error_tripped.setText("No error")
                self.error_msg.setPlainText("")
                self.error_msg.setReadOnly(False)
                self.error_msg.setStyleSheet(SS_TEXTBOX_ERRORS)
            else:
                self.sw1_error_tripped.setText("ERROR TRIPPED")
                self.error_msg.setPlainText(self.dev.state.error_msg)
                self.error_msg.setReadOnly(True)
                self.error_msg.setStyleSheet(SS_TEXTBOX_ERRORS)
            self.sw1_powerless.setChecked(self.dev.status_word_1.powerless)
            self.sw1_powered_stationary.setChecked(
                    self.dev.status_word_1.powered_stationary)
            self.sw1_zero_pos_known.setChecked(
                    self.dev.status_word_1.zero_pos_known)
            self.sw1_pos_reached.setChecked(self.dev.status_word_1.pos_reached)
            self.qled_cur_pos.setText("%.2f" % self.dev.state.cur_pos)

            self.lbl_update_counter.setText("%s" % self.DAQ_update_counter)
        else:
            self.qgrp.setEnabled(False)

    # --------------------------------------------------------------------------
    #   GUI functions
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def process_pbtn_ackn_error(self):
        self.worker_send.queued_instruction(self.dev.acknowledge_error)

    @QtCore.pyqtSlot()
    def process_editingFinished_qled_new_pos(self):
        try:
            new_pos = float(self.qled_new_pos.text())
        except (TypeError, ValueError):
            new_pos = 0.0
        except:
            raise()
        self.qled_new_pos.setText("%.2f" % new_pos)

    @QtCore.pyqtSlot()
    def process_pbtn_move_to_new_pos(self):
        # Double check if the value in the QLineEdit is actually numeric
        try:
            new_pos = float(self.qled_new_pos.text())
        except:
            raise()
        self.worker_send.queued_instruction(self.dev.move_to_target_position,
                                            (new_pos, 2))

    @QtCore.pyqtSlot()
    def process_pbtn_jog_plus_pressed(self):
        if not(self.jog_plus_is_active):
            self.jog_plus_is_active = True
            self.worker_send.queued_instruction(self.dev.jog_plus)

    @QtCore.pyqtSlot()
    def process_pbtn_jog_plus_released(self):
        self.jog_plus_is_active = False
        self.worker_send.queued_instruction(self.dev.stop_motion_but_keep_power)

    @QtCore.pyqtSlot()
    def process_pbtn_jog_minus_pressed(self):
        if not(self.jog_minus_is_active):
            self.jog_minus_is_active = True
            self.worker_send.queued_instruction(self.dev.jog_minus)

    @QtCore.pyqtSlot()
    def process_pbtn_jog_minus_released(self):
        self.jog_minus_is_active = False
        self.worker_send.queued_instruction(self.dev.stop_motion_but_keep_power)

    @QtCore.pyqtSlot()
    def process_pbtn_stop(self):
        self.worker_send.queued_instruction(self.dev.stop_motion_and_remove_power)

    # --------------------------------------------------------------------------
    #   connect_signals_to_slots
    # --------------------------------------------------------------------------

    def connect_signals_to_slots(self):
        #self.send_setpoint.editingFinished.connect(
        #        self.send_setpoint_from_textbox)

        self.pbtn_ackn_error.clicked.connect(self.process_pbtn_ackn_error)
        self.qled_new_pos.editingFinished.connect(
                self.process_editingFinished_qled_new_pos)
        self.pbtn_move_to_new_pos.clicked.connect(
                self.process_pbtn_move_to_new_pos)
        #self.pbtn_debug.clicked.connect(self.process_pbtn_debug)
        self.pbtn_jog_plus.pressed.connect(self.process_pbtn_jog_plus_pressed)
        self.pbtn_jog_plus.released.connect(self.process_pbtn_jog_plus_released)
        self.pbtn_jog_minus.pressed.connect(self.process_pbtn_jog_minus_pressed)
        self.pbtn_jog_minus.released.connect(self.process_pbtn_jog_minus_released)
        self.pbtn_stop.clicked.connect(self.process_pbtn_stop)