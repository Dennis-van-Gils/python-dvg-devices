#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PyQt/PySide module to provide multithreaded communication and periodical data
acquisition for MDrive stepper motors by Novanta IMS (former Schneider Electric)
set up in party mode.
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/python-dvg-devices"
__date__ = "23-05-2024"
__version__ = "1.4.0"
# pylint: disable=broad-except, missing-function-docstring
# pylint: disable=multiple-statements, unnecessary-lambda, too-many-lines

from enum import Enum
from functools import partial

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets as QtWid
from qtpy.QtCore import Signal, Slot  # type: ignore

import dvg_pyqt_controls as controls
from dvg_debug_functions import print_fancy_traceback as pft
from dvg_qdeviceio import QDeviceIO, DAQ_TRIGGER
from dvg_devices.MDrive_stepper_protocol_RS422 import (
    MDrive_Controller,
    MDrive_Motor,
    Movement_type,
)

FONT_MONOSPACE = QtGui.QFont("Consolas", 12, weight=QtGui.QFont.Weight.Bold)
FONT_MONOSPACE.setStyleHint(QtGui.QFont.StyleHint.TypeWriter)

# fmt: off
SS_PUSHBUTTON_PADDING = (
    "QPushButton {"
        "padding: 8px;}"
)

SS_LED = (
    "QPushButton {"
        "margin: 0;"
        "padding: 0;"
        "border: 1px solid gray;"
        "border-radius: 5px;"
        "max-height: 20px;"
        "max-width: 20px;"
        "height: 20px;"
        "width: 20px;}"
)

SS_LED_RED2GREEN = (
    "QPushButton {"
        "background-color: " + controls.COLOR_ERROR_RED + ";}"
    "QPushButton:checked {"
        "background-color: " + controls.COLOR_LED_GREEN + ";}"
)

SS_LED_NONE2GREEN = (
    "QPushButton {"
        "background-color: transparent;}"
    "QPushButton:checked {"
        "background-color: " + controls.COLOR_LED_GREEN + ";}"
)

SS_ERROR_BOX = (
    "QLineEdit {"
        "background-color: " + controls.COLOR_ERROR_RED + ";}"
    "QLineEdit:read-only {"
        "background-color: transparent;}"
)

SS_GROUPBOX = (
    "QGroupBox {"
        "padding: 0;"
        "margin-left: 0;"
        "margin-top: 3ex;}"
    "QGroupBox::title {"
        "subcontrol-origin: margin;"
        "subcontrol-position: top left;"
        "padding: 0;"
        "margin: 0;"
        "top: 0;"
        "left: 0;}"
    "QGroupBox:flat {"
        "border: 0px;"
        "border-radius: 0 0px;"
        "padding: 0;"
        "margin-left: 0;"
        "margin-top: 3ex;}"
)
# fmt: on


# Enumeration
class GUI_elements(Enum):
    [ALL, TAB_CONTROL, TAB_MOTION, TAB_DEVICE] = range(4)


# ------------------------------------------------------------------------------
#   GUI_MDrive_motor_panel
# ------------------------------------------------------------------------------


class GUI_MDrive_motor_panel(QtCore.QObject):
    """GUI elements for a single MDrive motor, bundled into a single
    `QtWidgets.QGroupBox` stored in member `main_group_box`."""

    def __init__(
        self,
        controller_qdev: QDeviceIO,  # == `MDrive_Controller_qdev`
        motor: MDrive_Motor,
        **kwargs,
    ):
        super().__init__(**kwargs)  # Pass kwargs onto QtCore.QObject()

        self.controller_qdev: MDrive_Controller_qdev = controller_qdev
        self.motor = motor
        self._create_panel()

    def _create_panel(self):
        """Create a GUI panel for a single MDrive motor."""

        # Lists of labels denoting physical units
        self.unit_labels_0: list[QtWid.QLabel] = []  # [mm]     or [rev]
        self.unit_labels_1: list[QtWid.QLabel] = []  # [mm/s]   or [rev/s]
        self.unit_labels_2: list[QtWid.QLabel] = []  # [mm/s^2] or [rev/s^2]

        # Main tab widget of the panel
        self.qtab = QtWid.QTabWidget()

        # ---------------------
        #   Tab page: Control
        # ---------------------

        p1 = {"parent": None, "checkable": True, "enabled": False}
        # fmt: off
        self.led_is_home_known        = QtWid.QPushButton(**p1)
        self.led_is_moving            = QtWid.QPushButton(**p1)
        self.led_is_velocity_changing = QtWid.QPushButton(**p1)
        # fmt: on

        self.led_is_home_known.setStyleSheet(SS_LED + SS_LED_RED2GREEN)
        self.led_is_moving.setStyleSheet(SS_LED + SS_LED_NONE2GREEN)
        self.led_is_velocity_changing.setStyleSheet(SS_LED + SS_LED_NONE2GREEN)

        self.error_status = QtWid.QLineEdit("0")
        self.error_status.setFixedWidth(controls.e8(4))
        self.error_status.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.error_status.setReadOnly(True)
        self.error_status.setStyleSheet(SS_ERROR_BOX)

        p_mono = {
            "parent": None,
            "font": FONT_MONOSPACE,
            "alignment": QtCore.Qt.AlignmentFlag.AlignTop,
        }
        p1 = {
            **p_mono,
            "alignment": (
                QtCore.Qt.AlignmentFlag.AlignTop
                | QtCore.Qt.AlignmentFlag.AlignRight
            ),
            "minimumWidth": controls.e8(12, FONT_MONOSPACE),
            "textInteractionFlags": (
                QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            ),
        }
        position_label = QtWid.QLabel(" Position", **p_mono)
        velocity_label = QtWid.QLabel(" Velocity", **p_mono)
        self.position = QtWid.QLabel("nan", **p1)
        self.velocity = QtWid.QLabel("nan", **p1)
        position_unit = QtWid.QLabel(**p_mono)
        velocity_unit = QtWid.QLabel(**p_mono)

        p1 = {
            "parent": None,
            "alignment": QtCore.Qt.AlignmentFlag.AlignRight,
        }
        p2 = {**p1, "maximumWidth": controls.e8(14)}
        # fmt: off
        self.wanted_position         = QtWid.QLineEdit("0.0" , **p1)
        self.wanted_velocity         = QtWid.QLineEdit("0.0" , **p1)
        self.software_min_position   = QtWid.QLineEdit("0.0" , **p2)
        self.software_max_position   = QtWid.QLineEdit("0.0" , **p2)
        self.step_size_1             = QtWid.QLineEdit("1.0" , **p2)
        self.step_size_2             = QtWid.QLineEdit("10.0", **p2)

        wanted_position_unit         = QtWid.QLabel()
        wanted_velocity_unit         = QtWid.QLabel()
        software_max_position_unit   = QtWid.QLabel()
        software_min_position_unit   = QtWid.QLabel()
        step_size_1_unit             = QtWid.QLabel()
        step_size_2_unit             = QtWid.QLabel()

        self.pbtn_init               = QtWid.QPushButton("Init interface")
        self.pbtn_home               = QtWid.QPushButton("Home")
        self.pbtn_move_to_position   = QtWid.QPushButton("Move to position")
        self.pbtn_move_with_velocity = QtWid.QPushButton("Move with velocity")
        self.pbtn_controlled_stop    = QtWid.QPushButton("Controlled stop")
        self.pbtn_step_1_plus        = QtWid.QPushButton("Step +")
        self.pbtn_step_2_plus        = QtWid.QPushButton("Step ++")
        self.pbtn_step_1_minus       = QtWid.QPushButton("Step -")
        self.pbtn_step_2_minus       = QtWid.QPushButton("Step --")
        self.pbtn_STOP               = QtWid.QPushButton("\nEMERGENCY STOP\n")
        # fmt: on

        # Connect GUI signals to slots
        self.pbtn_STOP.clicked.connect(self.process_pbtn_STOP)
        self.pbtn_init.clicked.connect(
            lambda: self.controller_qdev.send(self.motor.init_interface)
        )
        self.pbtn_home.clicked.connect(
            lambda: self.controller_qdev.send(self.motor.home)
        )
        self.pbtn_controlled_stop.clicked.connect(
            lambda: self.controller_qdev.send(self.motor.controlled_stop)
        )
        self.wanted_position.editingFinished.connect(
            lambda: self.validate_qlineedit_float(self.wanted_position)
        )
        self.wanted_velocity.editingFinished.connect(
            lambda: self.validate_qlineedit_float(self.wanted_velocity)
        )
        self.step_size_1.editingFinished.connect(
            lambda: self.validate_qlineedit_float(self.step_size_1)
        )
        self.step_size_2.editingFinished.connect(
            lambda: self.validate_qlineedit_float(self.step_size_2)
        )
        self.pbtn_move_to_position.clicked.connect(
            self.process_pbtn_move_to_position
        )
        self.pbtn_move_with_velocity.clicked.connect(
            self.process_pbtn_move_with_velocity
        )
        self.pbtn_step_1_plus.clicked.connect(
            lambda: self.process_pbtn_step(self.step_size_1, sign_=1)
        )
        self.pbtn_step_2_plus.clicked.connect(
            lambda: self.process_pbtn_step(self.step_size_2, sign_=1)
        )
        self.pbtn_step_1_minus.clicked.connect(
            lambda: self.process_pbtn_step(self.step_size_1, sign_=-1)
        )
        self.pbtn_step_2_minus.clicked.connect(
            lambda: self.process_pbtn_step(self.step_size_2, sign_=-1)
        )

        # Unit labels
        self.unit_labels_0.extend(
            [
                position_unit,
                software_min_position_unit,
                software_max_position_unit,
                wanted_position_unit,
                step_size_1_unit,
                step_size_2_unit,
            ]
        )
        self.unit_labels_1.extend(
            [
                velocity_unit,
                wanted_velocity_unit,
            ]
        )

        pbtns = [
            self.pbtn_init,
            self.pbtn_home,
            self.pbtn_move_to_position,
            self.pbtn_move_with_velocity,
            self.pbtn_controlled_stop,
            self.pbtn_step_1_plus,
            self.pbtn_step_2_plus,
            self.pbtn_step_1_minus,
            self.pbtn_step_2_minus,
        ]
        for pbtn in pbtns:
            pbtn.setStyleSheet(SS_PUSHBUTTON_PADDING)

        # fmt: off
        i = 0
        grid = QtWid.QGridLayout()
        grid.setVerticalSpacing(2)
        grid.setColumnStretch(2, 1)
        grid.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        subgrid = QtWid.QGridLayout()
        subgrid.setVerticalSpacing(2)
        subgrid.setColumnStretch(5, 1)
        subgrid.setColumnMinimumWidth(0, controls.e8(16))
        subgrid.setColumnMinimumWidth(3, controls.e8(13))
        subgrid.addWidget(QtWid.QLabel("Moving?")           , 0, 0)
        subgrid.addWidget(self.led_is_moving                , 0, 1)
        subgrid.addItem(QtWid.QSpacerItem(20, 1)            , 0, 2)
        subgrid.addWidget(QtWid.QLabel("Home known?")       , 0, 3)
        subgrid.addWidget(self.led_is_home_known            , 0, 4)
        subgrid.addWidget(QtWid.QLabel("Changing velocity?"), 1, 0)
        subgrid.addWidget(self.led_is_velocity_changing     , 1, 1)
        subgrid.addWidget(QtWid.QLabel("Error status")      , 1, 3)
        subgrid.addWidget(self.error_status                 , 1, 4)

        grid.addItem(subgrid                                , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)                , i, 0)      ; i+=1
        grid.addWidget(position_label                       , i, 0)
        grid.addWidget(self.position                        , i, 1)
        grid.addWidget(position_unit                        , i, 2)      ; i+=1
        grid.addWidget(velocity_label                       , i, 0)
        grid.addWidget(self.velocity                        , i, 1)
        grid.addWidget(velocity_unit                        , i, 2)      ; i+=1
        grid.addItem(QtWid.QSpacerItem(1, 12)               , i, 0)      ; i+=1

        subgrid = QtWid.QGridLayout()
        subgrid.setVerticalSpacing(2)
        subgrid.addWidget(self.pbtn_init                    , 0, 0)
        subgrid.addWidget(QtWid.QLabel("= Subroutine F1")   , 0, 1, 1, 2)
        subgrid.addWidget(self.pbtn_home                    , 1, 0)
        subgrid.addWidget(QtWid.QLabel("= Subroutine F2")   , 1, 1, 1, 2)
        subgrid.addWidget(self.pbtn_move_to_position        , 2, 0)
        subgrid.addWidget(self.wanted_position              , 2, 1)
        subgrid.addWidget(wanted_position_unit              , 2, 2)
        subgrid.addWidget(self.pbtn_move_with_velocity      , 3, 0)
        subgrid.addWidget(self.wanted_velocity              , 3, 1)
        subgrid.addWidget(wanted_velocity_unit              , 3, 2)
        subgrid.addItem(QtWid.QSpacerItem(1, 12)            , 4, 0)
        subgrid.addWidget(self.pbtn_controlled_stop         , 4, 0, 1, 3)

        actuate_group = QtWid.QGroupBox("Actuate")
        actuate_group.setLayout(subgrid)
        actuate_group.setStyleSheet(SS_GROUPBOX)
        actuate_group.setCheckable(True)
        actuate_group.setChecked(False)
        actuate_group.setFlat(True)

        subgrid = QtWid.QGridLayout()
        subgrid.setVerticalSpacing(2)
        subgrid.setColumnStretch(2, 1)
        subgrid.setColumnMinimumWidth(0, controls.e8(13))
        subgrid.addWidget(QtWid.QLabel("Min position")      , 0, 0)
        subgrid.addWidget(self.software_min_position        , 0, 1)
        subgrid.addWidget(software_min_position_unit        , 0, 2)
        subgrid.addWidget(QtWid.QLabel("Max position")      , 1, 0)
        subgrid.addWidget(self.software_max_position        , 1, 1)
        subgrid.addWidget(software_max_position_unit        , 1, 2)

        limits_group = QtWid.QGroupBox("Software limits")
        limits_group.setLayout(subgrid)
        limits_group.setStyleSheet(SS_GROUPBOX)
        limits_group.setCheckable(True)
        limits_group.setChecked(False)
        limits_group.setFlat(True)

        subsubgrid = QtWid.QGridLayout()
        subsubgrid.setSpacing(0)
        subsubgrid.addWidget(self.pbtn_step_1_minus         , 0, 0)
        subsubgrid.addWidget(self.pbtn_step_1_plus          , 0, 1)
        subsubgrid.addWidget(self.pbtn_step_2_minus         , 1, 0)
        subsubgrid.addWidget(self.pbtn_step_2_plus          , 1, 1)

        subgrid = QtWid.QGridLayout()
        subgrid.setVerticalSpacing(2)
        subgrid.setColumnStretch(2, 1)
        subgrid.setColumnMinimumWidth(0, controls.e8(13))
        subgrid.addWidget(QtWid.QLabel("Step size +/-")     , 0, 0)
        subgrid.addWidget(self.step_size_1                  , 0, 1)
        subgrid.addWidget(step_size_1_unit                  , 0, 2)
        subgrid.addWidget(QtWid.QLabel("Step size ++/--")   , 1, 0)
        subgrid.addWidget(self.step_size_2                  , 1, 1)
        subgrid.addWidget(step_size_2_unit                  , 1, 2)
        subgrid.addItem(QtWid.QSpacerItem(1, 6)             , 2, 0)
        subgrid.addLayout(subsubgrid                        , 3, 0, 1, 3)

        step_group = QtWid.QGroupBox("Step control")
        step_group.setLayout(subgrid)
        step_group.setStyleSheet(SS_GROUPBOX)
        step_group.setCheckable(True)
        step_group.setChecked(False)
        step_group.setFlat(True)

        grid.addWidget(actuate_group                        , i, 0, 1, 3); i+=1
        grid.addWidget(limits_group                         , i, 0, 1, 3); i+=1
        grid.addWidget(step_group                           , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 12)               , i, 0)      ; i+=1
        grid.addWidget(self.pbtn_STOP                       , i, 0, 1, 3); i+=1
        # fmt: on

        # Disable `limits_group` because functionality is not implemented yet.
        # TODO: Implement. Might need to add members `soft_min_position` and
        # `soft_max_position` to `MDrive_Motor.config`.
        limits_group.setVisible(False)

        grid_widget = QtWid.QWidget()
        grid_widget.setLayout(grid)
        self.page_control = self.qtab.addTab(grid_widget, "Control")

        # ---------------------
        #   Tab page: Motion
        # ---------------------

        def add_motion_row(
            grid: QtWid.QGridLayout,
            row_idx: list[int],  # Single int put in a list to allow pass by ref
            descr: str = "",
            abbrev: str = "",
            unit: str = "",
        ):

            unit_label = QtWid.QLabel(unit)
            line_edit = QtWid.QLineEdit()
            line_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
            line_edit.setFixedWidth(controls.e8(10))
            grid.addWidget(QtWid.QLabel(descr), row_idx[0], 0)
            grid.addWidget(QtWid.QLabel(abbrev), row_idx[0], 1)
            grid.addWidget(line_edit, row_idx[0], 2)
            grid.addWidget(unit_label, row_idx[0], 3)
            row_idx[0] += 1

            return line_edit, unit_label

        def add_spacer_row(grid: QtWid.QGridLayout, row_idx: list[int]):
            grid.addItem(QtWid.QSpacerItem(1, 10), row_idx[0], 0)
            row_idx[0] += 1

        self.cmbx_movement_type = QtWid.QComboBox()
        self.cmbx_movement_type.addItems([type.name for type in Movement_type])

        # fmt: off
        row_idx = [0]
        grid = QtWid.QGridLayout()
        grid.setVerticalSpacing(2)
        grid.setColumnStretch(3, 1)
        grid.setColumnMinimumWidth(3, controls.e8(10))
        grid.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        grid.addWidget(QtWid.QLabel("Movement type"), row_idx[0], 0)
        grid.addWidget(QtWid.QLabel("CT")           , row_idx[0], 1)
        grid.addWidget(self.cmbx_movement_type      , row_idx[0], 2, 1, 2)
        row_idx[0] += 1
        # fmt: on

        (
            self.calibration,
            self.calibration_unit,
        ) = add_motion_row(grid, row_idx, "Calibration", "C0", "")
        add_spacer_row(grid, row_idx)
        (
            self.acceleration_steps,
            _,
        ) = add_motion_row(grid, row_idx, "Acceleration", "A", "steps/sec^2")
        (
            self.deceleration_steps,
            _,
        ) = add_motion_row(grid, row_idx, "Deceleration", "D", "steps/sec^2")
        (
            self.initial_velocity_steps,
            _,
        ) = add_motion_row(grid, row_idx, "Initial velocity", "VI", "steps/sec")
        (
            self.maximum_velocity_steps,
            _,
        ) = add_motion_row(grid, row_idx, "Maximum velocity", "VM", "steps/sec")
        add_spacer_row(grid, row_idx)
        (
            self.acceleration,
            acceleration_unit,
        ) = add_motion_row(grid, row_idx, "Acceleration")
        (
            self.deceleration,
            deceleration_unit,
        ) = add_motion_row(grid, row_idx, "Deceleration")
        (
            self.initial_velocity,
            initial_velocity_unit,
        ) = add_motion_row(grid, row_idx, "Initial velocity")
        (
            self.maximum_velocity,
            maximum_velocity_unit,
        ) = add_motion_row(grid, row_idx, "Maximum velocity")
        add_spacer_row(grid, row_idx)
        (
            self.microsteps,
            _,
        ) = add_motion_row(grid, row_idx, "Microsteps", "MS", "microsteps")
        (
            self.limit_stop,
            _,
        ) = add_motion_row(grid, row_idx, "Limit stop", "LM", "mode 1-6")
        (
            self.run_current,
            _,
        ) = add_motion_row(grid, row_idx, "Run current", "RC", "%")
        (
            self.hold_current,
            _,
        ) = add_motion_row(grid, row_idx, "Hold current", "HC", "%")
        (
            self.hold_delay,
            _,
        ) = add_motion_row(grid, row_idx, "Hold delay", "HT", "msec")
        (
            self.settling_delay,
            _,
        ) = add_motion_row(grid, row_idx, "Settling delay", "MT", "msec")
        add_spacer_row(grid, row_idx)
        (
            self.IO_S1,
            _,
        ) = add_motion_row(grid, row_idx, "I/O point S1", "S1", "#, #, #")
        (
            self.IO_S2,
            _,
        ) = add_motion_row(grid, row_idx, "I/O point S2", "S2", "#, #, #")
        (
            self.IO_S3,
            _,
        ) = add_motion_row(grid, row_idx, "I/O point S3", "S3", "#, #, #")
        (
            self.IO_S4,
            _,
        ) = add_motion_row(grid, row_idx, "I/O point S4", "S4", "#, #, #")
        add_spacer_row(grid, row_idx)

        self.pbtn_save_to_NVM = QtWid.QPushButton(
            "Save to MDrive non-volatile memory"
        )
        self.pbtn_save_to_NVM.setStyleSheet(SS_PUSHBUTTON_PADDING)
        self.pbtn_save_to_NVM.clicked.connect(
            lambda: self.controller_qdev.send(self.motor.save_to_NVM)
        )

        # fmt: off
        row_idx[0] += 1
        grid.addWidget(
            QtWid.QLabel(
                "NOTE: Changes to above parameters are in effect\n"
                "immediately, but don't persist a power-down/up\n"
                "cycle unless saved to MDrive non-volatile memory."
            )                                           , row_idx[0], 0, 1, 4)
        row_idx[0] += 1
        grid.addItem(QtWid.QSpacerItem(1, 6)            , row_idx[0], 0)
        row_idx[0] += 1
        grid.addWidget(self.pbtn_save_to_NVM            , row_idx[0], 0, 1, 4)
        # fmt: on

        # Connect GUI signals to slots
        self.cmbx_movement_type.currentIndexChanged.connect(
            lambda x: self.process_cmbx_movement_type(x)
        )
        self.calibration.editingFinished.connect(self.process_calibration)
        self.acceleration_steps.editingFinished.connect(
            lambda: self.process_motion_param("A", self.acceleration_steps)
        )
        self.deceleration_steps.editingFinished.connect(
            lambda: self.process_motion_param("D", self.deceleration_steps)
        )
        self.initial_velocity_steps.editingFinished.connect(
            lambda: self.process_motion_param("VI", self.initial_velocity_steps)
        )
        self.maximum_velocity_steps.editingFinished.connect(
            lambda: self.process_motion_param("VM", self.maximum_velocity_steps)
        )
        self.acceleration.editingFinished.connect(
            lambda: self.process_motion_param_calibrated("A", self.acceleration)
        )
        self.deceleration.editingFinished.connect(
            lambda: self.process_motion_param_calibrated("D", self.deceleration)
        )
        self.initial_velocity.editingFinished.connect(
            lambda: self.process_motion_param_calibrated(
                "VI", self.initial_velocity
            )
        )
        self.maximum_velocity.editingFinished.connect(
            lambda: self.process_motion_param_calibrated(
                "VM", self.maximum_velocity
            )
        )
        self.microsteps.editingFinished.connect(
            lambda: self.process_motion_param("MS", self.microsteps)
        )
        self.limit_stop.editingFinished.connect(
            lambda: self.process_motion_param("LM", self.limit_stop)
        )
        self.run_current.editingFinished.connect(
            lambda: self.process_motion_param("RC", self.run_current)
        )
        self.hold_current.editingFinished.connect(
            lambda: self.process_motion_param("HC", self.hold_current)
        )
        self.hold_delay.editingFinished.connect(
            lambda: self.process_motion_param("HT", self.hold_delay)
        )
        self.settling_delay.editingFinished.connect(
            lambda: self.process_motion_param("MT", self.settling_delay)
        )
        self.IO_S1.editingFinished.connect(
            lambda: self.process_IO_S("S1", self.IO_S1)
        )
        self.IO_S2.editingFinished.connect(
            lambda: self.process_IO_S("S2", self.IO_S2)
        )
        self.IO_S3.editingFinished.connect(
            lambda: self.process_IO_S("S3", self.IO_S3)
        )
        self.IO_S4.editingFinished.connect(
            lambda: self.process_IO_S("S4", self.IO_S4)
        )

        # Unit labels
        self.unit_labels_1.extend(
            [
                initial_velocity_unit,
                maximum_velocity_unit,
            ]
        )

        self.unit_labels_2.extend(
            [
                acceleration_unit,
                deceleration_unit,
            ]
        )

        grid_widget = QtWid.QWidget()
        grid_widget.setLayout(grid)
        self.page_motion = self.qtab.addTab(grid_widget, "Motion params")

        # ---------------------
        #   Tab page: Device
        # ---------------------

        p1 = {
            "minimumWidth": controls.e8(12),
            "readOnly": True,
        }
        p2 = {
            **p1,
            "alignment": QtCore.Qt.AlignmentFlag.AlignLeft,
        }

        self.device_name = QtWid.QLineEdit(**p2)
        self.device_name.setFixedWidth(controls.e8(2))
        self.part_number = QtWid.QLineEdit(**p2)
        self.serial_number = QtWid.QLineEdit(**p2)
        self.firmware_version = QtWid.QLineEdit(**p2)
        self.user_subroutines = QtWid.QTextEdit(**p1)
        self.user_subroutines.setFont(FONT_MONOSPACE)
        self.user_subroutines.setFontPointSize(10)
        self.user_variables = QtWid.QTextEdit(**p1)
        self.user_variables.setFont(FONT_MONOSPACE)
        self.user_variables.setFontPointSize(10)

        i = 0
        grid = QtWid.QGridLayout()
        grid.setVerticalSpacing(2)
        grid.setColumnStretch(2, 1)
        grid.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # fmt: off
        grid.addWidget(QtWid.QLabel("<b>Device</b>")   , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)           , i, 0)      ; i+=1
        grid.addWidget(QtWid.QLabel("Device name")     , i, 0)
        grid.addWidget(QtWid.QLabel("DN")              , i, 1)
        grid.addWidget(self.device_name                , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("Part number")     , i, 0)
        grid.addWidget(QtWid.QLabel("PN")              , i, 1)
        grid.addWidget(self.part_number                , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("Serial number")   , i, 0)
        grid.addWidget(QtWid.QLabel("SN")              , i, 1)
        grid.addWidget(self.serial_number              , i, 2)      ; i+=1
        grid.addWidget(QtWid.QLabel("Firmware version"), i, 0)
        grid.addWidget(QtWid.QLabel("VR")              , i, 1)
        grid.addWidget(self.firmware_version           , i, 2)      ; i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)           , i, 0)      ; i+=1

        grid.addWidget(QtWid.QLabel("<b>User subroutines</b>")
                                                       , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)           , i, 0)      ; i+=1
        grid.addWidget(self.user_subroutines           , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)           , i, 0)      ; i+=1

        grid.addWidget(QtWid.QLabel("<b>User variables</b>")
                                                       , i, 0, 1, 3); i+=1
        grid.addItem(QtWid.QSpacerItem(1, 6)           , i, 0)      ; i+=1
        grid.addWidget(self.user_variables             , i, 0, 1, 3); i+=1
        # fmt: on

        grid_widget = QtWid.QWidget()
        grid_widget.setLayout(grid)
        self.page_device = self.qtab.addTab(grid_widget, "Device")

        # ---------------
        #   Rounding up
        # ---------------

        hbox = QtWid.QHBoxLayout()
        hbox.addWidget(self.qtab)

        self.main_group_box = QtWid.QGroupBox(f"Motor {self.motor.device_name}")
        self.main_group_box.setLayout(hbox)

    # --------------------------------------------------------------------------
    #   update_GUI
    # --------------------------------------------------------------------------

    @Slot()
    @Slot(GUI_elements)
    def update_GUI(self, gui_elements: GUI_elements = GUI_elements.ALL):

        if not self.motor.controller.is_alive:
            # TODO: Signal a 'lost connection to motor' to the user
            return

        # Shorthands
        state = self.motor.state
        config = self.motor.config
        C0 = config.calibration_constant

        if gui_elements in [GUI_elements.ALL, GUI_elements.TAB_CONTROL]:
            # fmt: off
            self.led_is_home_known       .setChecked(state.is_home_known)
            self.led_is_moving           .setChecked(state.is_moving)
            self.led_is_velocity_changing.setChecked(state.is_velocity_changing)
            self.error_status            .setText(f"{state.error}")
            self.error_status            .setReadOnly(not state.has_error)

            self.position.setText(f"{state.position / C0:.3f}")
            self.velocity.setText(f"{state.velocity / C0:.3f}")
            # fmt: on

        if gui_elements in [GUI_elements.ALL, GUI_elements.TAB_MOTION]:
            self.update_unit_labels(self.motor.get_base_unit())
            self.cmbx_movement_type.setCurrentIndex(config.movement_type.value)
            # fmt: off
            self.calibration           .setText(f"{C0}")
            self.acceleration_steps    .setText(f"{config.motion_A      :.0f}")
            self.deceleration_steps    .setText(f"{config.motion_D      :.0f}")
            self.initial_velocity_steps.setText(f"{config.motion_VI     :.0f}")
            self.maximum_velocity_steps.setText(f"{config.motion_VM     :.0f}")
            self.acceleration          .setText(f"{config.motion_A  / C0:.4f}")
            self.deceleration          .setText(f"{config.motion_D  / C0:.4f}")
            self.initial_velocity      .setText(f"{config.motion_VI / C0:.4f}")
            self.maximum_velocity      .setText(f"{config.motion_VM / C0:.4f}")
            self.microsteps            .setText(f"{config.motion_MS}")
            self.limit_stop            .setText(f"{config.motion_LM}")
            self.run_current           .setText(f"{config.motion_RC}")
            self.hold_current          .setText(f"{config.motion_HC}")
            self.hold_delay            .setText(f"{config.motion_HT}")
            self.settling_delay        .setText(f"{config.motion_MT}")
            self.IO_S1                 .setText(f"{config.IO_S1}")
            self.IO_S2                 .setText(f"{config.IO_S2}")
            self.IO_S3                 .setText(f"{config.IO_S3}")
            self.IO_S4                 .setText(f"{config.IO_S4}")
            # fmt: on

            lines: list[str] = []
            for _idx, (key, val) in enumerate(config.user_subroutines.items()):
                lines.append(f"{key} @ {val}")
            str_text = "\n".join(lines)
            self.user_subroutines.setText(str_text)

            lines = []
            for _idx, (key, val) in enumerate(config.user_variables.items()):
                lines.append(f"{key} = {val}")
            str_text = "\n".join(lines)
            self.user_variables.setText(str_text)

        if gui_elements in [GUI_elements.ALL, GUI_elements.TAB_DEVICE]:
            # fmt: off
            self.part_number     .setText(f"{config.part_number}")
            self.serial_number   .setText(f"{config.serial_number}")
            self.firmware_version.setText(f"{config.firmware_version}")
            self.device_name     .setText(f"{self.motor.device_name}")
            # fmt: on

        # locker.unlock()

    # --------------------------------------------------------------------------
    #   Handle controls
    # --------------------------------------------------------------------------

    def update_unit_labels(self, base_unit: str = "mm"):
        self.calibration_unit.setText(f"steps/{base_unit}")

        for unit_label in self.unit_labels_0:
            unit_label.setText(base_unit)

        for unit_label in self.unit_labels_1:
            unit_label.setText(f"{base_unit}/sec")

        for unit_label in self.unit_labels_2:
            unit_label.setText(f"{base_unit}/sec^2")

    def validate_qlineedit_float(
        self, qlin: QtWid.QLineEdit, default_val: float = 0.0
    ):
        try:
            val = float(qlin.text())
        except ValueError:
            val = default_val
        except Exception as e:
            raise e

        qlin.setText(f"{val}")

    @Slot()
    def process_pbtn_STOP(self):
        self.controller_qdev.add_to_jobs_queue(self.motor.controller.STOP)
        self.controller_qdev.add_to_jobs_queue(self.motor.controller.RESET)
        self.controller_qdev.process_jobs_queue()

    @Slot()
    def process_pbtn_move_to_position(self):
        try:
            val = float(self.wanted_position.text())
        except ValueError:
            val = 0.0
        except Exception as e:
            raise e

        if self.motor.config.movement_type == Movement_type.LINEAR:
            fun = self.motor.move_absolute_mm
        else:
            fun = self.motor.move_absolute_rev

        self.controller_qdev.send(fun, val)

    @Slot()
    def process_pbtn_move_with_velocity(self):
        try:
            val = float(self.wanted_velocity.text())
        except ValueError:
            val = 0.0
        except Exception as e:
            raise e

        if self.motor.config.movement_type == Movement_type.LINEAR:
            fun = self.motor.slew_mm_per_sec
        else:
            fun = self.motor.slew_rev_per_sec

        self.controller_qdev.send(fun, val)

    def process_pbtn_step(self, qlin: QtWid.QLineEdit, sign_: int = 1):
        try:
            val = float(qlin.text())
        except ValueError:
            val = 0.0
        except Exception as e:
            raise e

        if self.motor.config.movement_type == Movement_type.LINEAR:
            fun = self.motor.move_relative_mm
        else:
            fun = self.motor.move_relative_rev

        self.controller_qdev.send(fun, val if sign_ == 1 else -val)

    @Slot(int)
    def process_cmbx_movement_type(self, cmbx_index: int):
        try:
            CT = Movement_type(cmbx_index)
        except ValueError:
            CT = Movement_type.LINEAR
        except Exception as e:
            raise e

        if self.motor.config.movement_type == CT:
            # Prevent race condition
            return

        cmd = f"CT {CT.value:d}"
        self.controller_qdev.add_to_jobs_queue(self.motor.query, cmd)
        self.controller_qdev.add_to_jobs_queue(self.motor.query_config)
        self.controller_qdev.add_to_jobs_queue(
            "signal_GUI_update", (self, GUI_elements.TAB_MOTION)
        )
        self.controller_qdev.process_jobs_queue()

    @Slot()
    def process_calibration(self):
        try:
            C0 = int(self.calibration.text())
            C0 = max(1, C0)
        except ValueError:
            C0 = self.motor.config.calibration_constant
        except Exception as e:
            raise e

        cmd = f"C0 {C0:d}"
        self.controller_qdev.add_to_jobs_queue(self.motor.query, cmd)
        self.controller_qdev.add_to_jobs_queue(self.motor.query_config)
        self.controller_qdev.add_to_jobs_queue(
            "signal_GUI_update", (self, GUI_elements.TAB_MOTION)
        )
        self.controller_qdev.process_jobs_queue()

    def process_motion_param(
        self,
        motion_param: str,
        qlin: QtWid.QLineEdit,
    ):
        """Cast the text string of the passed QLineEdit `qlin` into an integer
        and send this value to the MDrive as a new `motion_param`. Afterwards,
        it will trigger a GUI update of the "Motion" tab."""
        try:
            val = int(qlin.text())
        except ValueError:
            val = 0
        except Exception as e:
            raise e

        cmd = f"{motion_param} {val:d}"
        self.controller_qdev.add_to_jobs_queue(self.motor.query, cmd)
        self.controller_qdev.add_to_jobs_queue(self.motor.query_config)
        self.controller_qdev.add_to_jobs_queue(
            "signal_GUI_update", (self, GUI_elements.TAB_MOTION)
        )
        self.controller_qdev.process_jobs_queue()

    def process_motion_param_calibrated(
        self,
        motion_param: str,
        qlin: QtWid.QLineEdit,
    ):
        """Cast the text string of the passed QLineEdit `qlin` into a float,
        multiply it with the calibration constant C0 and send this rounded value
        to the MDrive as a new `motion_param`. Afterwards, it will trigger a GUI
        update of the "Motion" tab."""
        try:
            val = float(qlin.text())
        except ValueError:
            val = 0
        except Exception as e:
            raise e

        C0 = self.motor.config.calibration_constant
        val = int(round(val * (C0 if not np.isnan(C0) else 1)))

        cmd = f"{motion_param} {val:d}"
        self.controller_qdev.add_to_jobs_queue(self.motor.query, cmd)
        self.controller_qdev.add_to_jobs_queue(self.motor.query_config)
        self.controller_qdev.add_to_jobs_queue(
            "signal_GUI_update", (self, GUI_elements.TAB_MOTION)
        )
        self.controller_qdev.process_jobs_queue()

    def process_IO_S(
        self,
        motion_param: str,
        qlin: QtWid.QLineEdit,
    ):
        """Concerns motion parameters "S1" to "S4" and "S9" to "S12". Validate
        the text string of the passed QLineEdit `qlin`. Expecting the following
        format: "[0-23], [0/1], [0/1]", e.g. "3, 0, 1". The validated string
        will be send to the MDrive as a new `motion_param`. Afterwards, it will
        trigger a GUI update of the "Motion" tab."""
        values: list[int] = [0, 0, 0]

        # Expecting the following format: [0-23], [0/1], [0/1]
        text_parts = qlin.text().split(",")
        for idx, text_part in enumerate(text_parts):
            if idx > 2:
                break

            try:
                val = int(text_part.strip())
            except ValueError:
                val = 0
            except Exception as e:
                raise e

            """ We'll leave number range validation to the MDrive motor
            if idx == 0:
                val = max(val, 0)
                val = min(val, 23)
            """

            if idx in (1, 2):
                val = max(val, 0)
                val = min(val, 1)

            values[idx] = val

        validated_text = f"{values[0]}, {values[1]}, {values[2]}"
        qlin.setText(validated_text)

        if validated_text == self.motor.config.IO_S1:
            return

        cmd = f"{motion_param} {validated_text}"
        self.controller_qdev.add_to_jobs_queue(self.motor.query, cmd)
        self.controller_qdev.add_to_jobs_queue(self.motor.query_config)
        self.controller_qdev.add_to_jobs_queue(
            "signal_GUI_update", (self, GUI_elements.TAB_MOTION)
        )
        self.controller_qdev.process_jobs_queue()


# ------------------------------------------------------------------------------
#   MDrive_Controller_qdev
# ------------------------------------------------------------------------------


class MDrive_Controller_qdev(QDeviceIO):
    """TODO: docstr"""

    signal_GUI_update = Signal(GUI_MDrive_motor_panel, GUI_elements)
    """Triggers updating GUI elements."""

    def __init__(
        self,
        dev: MDrive_Controller,
        DAQ_trigger=DAQ_TRIGGER.INTERNAL_TIMER,
        DAQ_interval_ms=200,
        DAQ_timer_type=QtCore.Qt.TimerType.CoarseTimer,
        critical_not_alive_count=3,
        debug=False,
        **kwargs,
    ):
        super().__init__(dev, **kwargs)  # Pass kwargs onto QtCore.QObject()
        self.dev: MDrive_Controller  # Enforce type: removes `_NoDevice()`

        self.create_worker_DAQ(
            DAQ_trigger=DAQ_trigger,
            DAQ_function=self.DAQ_function,
            DAQ_interval_ms=DAQ_interval_ms,
            DAQ_timer_type=DAQ_timer_type,
            critical_not_alive_count=critical_not_alive_count,
            debug=debug,
        )

        self.create_worker_jobs(jobs_function=self.jobs_function, debug=debug)

        self.motor_panels: list[GUI_MDrive_motor_panel] = []
        """List of MDrive motor panels, one panel for each motor."""

        self.hbox = QtWid.QHBoxLayout()
        """Main `QtWidgets.QHBoxLayout` containing all MDrive motor panels."""

        # Create panels for all MDrive motors
        for motor in self.dev.motors:
            motor_panel = GUI_MDrive_motor_panel(
                controller_qdev=self, motor=motor
            )
            self.motor_panels.append(motor_panel)

            # Each motor panel has its GUI controls grouped together in a single
            # QGroupBox, located in member `main_group_box`.
            self.hbox.addWidget(motor_panel.main_group_box)

            # Trigger an update of the 'control' tab GUI elements whenever the
            # DAQ updated, i.e. new readings are available which should get
            # displayed.
            self.signal_DAQ_updated.connect(
                partial(motor_panel.update_GUI, GUI_elements.TAB_CONTROL)
            )

        # Listen to requests to update GUI elements
        self.signal_GUI_update.connect(
            lambda motor_panel, elements: motor_panel.update_GUI(elements)
        )

        for motor_panel in self.motor_panels:
            motor_panel.update_GUI()

    # --------------------------------------------------------------------------
    #   DAQ_function
    # --------------------------------------------------------------------------

    def DAQ_function(self) -> bool:
        success = True
        for motor in self.dev.motors:
            success &= motor.query_state()
            success &= motor.query_errors()

        return success

    # --------------------------------------------------------------------------
    #   jobs_function
    # --------------------------------------------------------------------------

    def jobs_function(self, func, args):
        if func == "signal_GUI_update":
            # Special instruction
            self.signal_GUI_update.emit(*args)
        else:
            # Default job processing:
            # Send I/O operation to the device
            try:
                func(*args)
            except Exception as err:
                pft(err)
