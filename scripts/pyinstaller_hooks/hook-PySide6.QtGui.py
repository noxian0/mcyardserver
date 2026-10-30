"""Collect Widgets image/platform support without unused PDF/QML add-ons."""
from pathlib import Path
from PyInstaller.utils.hooks.qt import pyside6_library_info

hiddenimports,binaries,datas=pyside6_library_info.collect_module('PySide6.QtGui')
# Remove these plugins before PyInstaller scans native dependencies. The PDF
# image handler would pull QtPdf in; the virtual keyboard would pull QtQuick,
# QtQml and QtVirtualKeyboard in. MCyard has no PDF, QML or virtual-keyboard UI.
excluded={'qpdf.dll','qtvirtualkeyboardplugin.dll'}
binaries=[entry for entry in binaries if Path(entry[0]).name.lower() not in excluded]
