import sys
import os

from PySide2 import QtCore, QtGui, QtWidgets

import _AEPython as _ae
import AEPython as ae
from qtcodeeditor import CodeEditor

__MainWindow = None
__PythonWindow = None


def __init_qt():
    app = QtWidgets.QApplication.instance()
    if app is not None:
        return

    app = QtWidgets.QApplication(sys.argv)

    style = '''
QMainWindow, QDialog, QAbstractButton, QLabel{
    background-color: #444444;
    color: #ffffff;
}
'''

    app.setStyleSheet(style)


class PythonWindow(QtWidgets.QMainWindow):
    class Logger:
        def __init__(self, editor: QtWidgets.QTextEdit, color=None, show=None):
            self.editor = editor
            self.color = editor.textColor() if color is None else color
            self.show = show

        def write(self, message: str):
            self.editor.moveCursor(QtGui.QTextCursor.End)
            self.editor.setTextColor(self.color)
            self.editor.insertPlainText(message)

            if self.show is not None:
                self.show()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.__file_path = None

        self.centralWidget = QtWidgets.QWidget()
        self.setCentralWidget(self.centralWidget)

        layout = QtWidgets.QVBoxLayout()
        self.centralWidget.setLayout(layout)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        layout.addWidget(splitter)

        output_widget = QtWidgets.QWidget()
        output_layout = QtWidgets.QVBoxLayout()
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_widget.setLayout(output_layout)

        label_output = QtWidgets.QLabel("Output:")
        output_layout.addWidget(label_output)

        self.textedit_output = QtWidgets.QTextEdit("")
        self.textedit_output.setStyleSheet("background-color: #e0e0e0;")
        self.textedit_output.setReadOnly(True)
        output_layout.addWidget(self.textedit_output)

        code_widget = QtWidgets.QWidget()
        code_layout = QtWidgets.QVBoxLayout()
        code_layout.setContentsMargins(0, 0, 0, 0)
        code_widget.setLayout(code_layout)

        label_code = QtWidgets.QLabel("Code:")
        code_layout.addWidget(label_code)

        self.editor_code = CodeEditor()
        self.editor_code.document().modificationChanged.connect(self.setWindowModified)
        code_layout.addWidget(self.editor_code)

        self.button_execute = QtWidgets.QPushButton("Execute (Ctrl+Enter)")
        self.button_execute.clicked.connect(self.__execute)
        code_layout.addWidget(self.button_execute)

        splitter.addWidget(output_widget)
        splitter.addWidget(code_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        file_menu = self.menuBar().addMenu("File")

        new_action = QtWidgets.QAction("New", self)
        new_action.setShortcut(QtGui.QKeySequence.New)
        new_action.triggered.connect(self.__new_file)
        file_menu.addAction(new_action)

        open_action = QtWidgets.QAction("Open...", self)
        open_action.setShortcut(QtGui.QKeySequence.Open)
        open_action.triggered.connect(self.__open_file)
        file_menu.addAction(open_action)

        save_action = QtWidgets.QAction("Save", self)
        save_action.setShortcut(QtGui.QKeySequence.Save)
        save_action.triggered.connect(self.__save_file)
        file_menu.addAction(save_action)

        save_as_action = QtWidgets.QAction("Save As...", self)
        save_as_action.setShortcut(QtGui.QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(self.__save_file_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        exec_action = QtWidgets.QAction("Execute Python File", self)
        exec_action.triggered.connect(self.__execute_file)
        file_menu.addAction(exec_action)

        run_menu = self.menuBar().addMenu("Run")

        run_action = QtWidgets.QAction("Execute", self)
        run_action.setShortcuts([QtGui.QKeySequence("Ctrl+Return"),
                                 QtGui.QKeySequence("Ctrl+Enter")])
        run_action.triggered.connect(self.__execute)
        run_menu.addAction(run_action)

        self.__update_title()

        sys.stdout = self.Logger(self.textedit_output)
        sys.stderr = self.Logger(self.textedit_output, QtGui.QColor(255, 0, 0), self.show)
        print("AE Python 1.0.0")

    def __update_title(self):
        name = "untitled" if self.__file_path is None else os.path.basename(self.__file_path)
        self.setWindowTitle(f"AE Python - {name}[*]")

    def __maybe_save(self):
        if not self.editor_code.document().isModified():
            return True

        ret = QtWidgets.QMessageBox.warning(
            self, "AE Python",
            "The code has been modified.\nDo you want to save your changes?",
            QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel)

        if ret == QtWidgets.QMessageBox.Save:
            return self.__save_file()
        return ret == QtWidgets.QMessageBox.Discard

    def __new_file(self):
        if not self.__maybe_save():
            return

        self.editor_code.clear()
        self.editor_code.document().setModified(False)
        self.__file_path = None
        self.__update_title()

    def __open_file(self):
        if not self.__maybe_save():
            return

        file_path = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Python File", self.__default_dir(), "Python (*.py)")[0]
        if file_path == '':
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.editor_code.setPlainText(f.read())
        except:
            import traceback
            traceback.print_exc()
            return

        self.editor_code.document().setModified(False)
        self.__file_path = file_path
        self.__update_title()

    def __save_file(self):
        if self.__file_path is None:
            return self.__save_file_as()

        try:
            with open(self.__file_path, 'w', encoding='utf-8') as f:
                f.write(self.editor_code.toPlainText())
        except:
            import traceback
            traceback.print_exc()
            return False

        self.editor_code.document().setModified(False)
        return True

    def __save_file_as(self):
        file_path = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Python File", self.__default_dir(), "Python (*.py)")[0]
        if file_path == '':
            return False

        self.__file_path = file_path
        self.__update_title()
        return self.__save_file()

    def __default_dir(self):
        return "" if self.__file_path is None else os.path.dirname(self.__file_path)

    def __execute(self):
        code = self.editor_code.toPlainText()
        try:
            exec(code, globals(), _ae.locals)
        except:
            import traceback
            traceback.print_exc()

    def __execute_file(self):
        file_path = QtWidgets.QFileDialog.getOpenFileName(self, "Execute Python File", "", "Python (*.py)")[0]
        if file_path == '':
            return

        dont_write_bytecode = sys.dont_write_bytecode
        module_dir = os.path.dirname(file_path)
        sys.path.insert(0, module_dir)
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(file_path, file_path)
            module = importlib.util.module_from_spec(spec)
            sys.dont_write_bytecode = True
            spec.loader.exec_module(module)
        except:
            import traceback
            traceback.print_exc()
        finally:
            sys.dont_write_bytecode = dont_write_bytecode
            if module_dir in sys.path:
                sys.path.remove(module_dir)


def GetQtAEMainWindow():
    global __MainWindow
    if __MainWindow is None:
        import win32gui
        __MainWindow = QtWidgets.QWidget()
        win32gui.SetParent(__MainWindow.winId(), _ae.getMainHWND())
    return __MainWindow


def ShowPythonWindow():
    __PythonWindow.show()


__init_qt()
__PythonWindow = PythonWindow(GetQtAEMainWindow())
