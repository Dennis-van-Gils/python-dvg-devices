#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qt tests
"""
# pylint: disable=missing-function-docstring, unused-import, wrong-import-position

import sys

"""
from PyQt5 import QtCore, QtGui, QtWidgets as QtWid
from PyQt5.QtCore import pyqtSlot as Slot
from PyQt5.QtCore import pyqtSignal as Signal

QT_LIB = "PYQT5"
"""

"""
from PyQt6 import QtCore, QtGui, QtWidgets as QtWid
from PyQt6.QtCore import pyqtSlot as Slot
from PyQt6.QtCore import pyqtSignal as Signal

QT_LIB = "PYQT6"
"""

"""
from PySide2 import QtCore, QtGui, QtWidgets as QtWid
from PySide2.QtCore import Slot
from PySide2.QtCore import Signal

QT_LIB = "PYSIDE2"
"""

# """
from PySide6 import QtCore, QtGui, QtWidgets as QtWid
from PySide6.QtCore import Slot
from PySide6.QtCore import Signal

QT_LIB = "PYSIDE6"
# """

# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.setWindowTitle("Qt tests")

        self.pbtn_test_msgbox = QtWid.QPushButton("QMessageBox test")
        self.pbtn_test_msgbox.clicked.connect(self.test_msgbox)

        self.pbtn_test_msgbox2 = QtWid.QPushButton("QMessageBox2 test")
        self.pbtn_test_msgbox2.clicked.connect(self.test_msgbox2)

        hbox = QtWid.QHBoxLayout(self)
        hbox.addWidget(self.pbtn_test_msgbox)
        hbox.addWidget(self.pbtn_test_msgbox2)

    @Slot()
    def test_msgbox(self):
        """Validated: Runs in both PyQt5 and PySide6.
        Safe to ignore pylint warnings.
        """
        msgbox = QtWid.QMessageBox()
        msgbox.setIcon(QtWid.QMessageBox.Icon.Information)
        msgbox.setWindowTitle("My title")
        msgbox.setText("My text")
        msgbox.setStandardButtons(
            QtWid.QMessageBox.StandardButton.Cancel
            | QtWid.QMessageBox.StandardButton.Ok
        )
        msgbox.setDefaultButton(QtWid.QMessageBox.StandardButton.Cancel)
        reply = msgbox.exec()

        """
        # Equivalent to above, but with more linting warnings:
        reply = QtWid.QMessageBox.information(
            None,
            "My title",
            "My text",
            QtWid.QMessageBox.StandardButton.Cancel
            | QtWid.QMessageBox.StandardButton.Ok,
            QtWid.QMessageBox.StandardButton.Cancel,
        )
        """

        if reply == QtWid.QMessageBox.StandardButton.Ok:
            print("Ok")
        else:
            print("Cancel")

    @Slot()
    def test_msgbox2(self):
        """Validated: Runs in both PyQt5 and PySide6.
        Safe to ignore pylint warnings.
        """
        msgbox = QtWid.QMessageBox()
        msgbox.setIcon(QtWid.QMessageBox.Icon.Information)
        msgbox.setWindowTitle("My title")
        msgbox.setText("My text")
        msgbox.exec()


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------


if __name__ == "__main__":
    app = QtWid.QApplication(sys.argv)

    window = MainWindow()
    window.show()

    if QT_LIB in ("PYQT5", "PYSIDE2"):
        sys.exit(app.exec_())
    else:
        sys.exit(app.exec())
