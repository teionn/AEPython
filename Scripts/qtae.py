import sys
import os
import json
import textwrap

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


class FindReplaceBar(QtWidgets.QWidget):
    def __init__(self, editor_provider, parent=None):
        super().__init__(parent)
        self.__editor_provider = editor_provider

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 2, 0, 2)
        self.setLayout(layout)

        self.find_edit = QtWidgets.QLineEdit()
        self.find_edit.setPlaceholderText("Find")
        self.find_edit.returnPressed.connect(self.find_next)
        layout.addWidget(self.find_edit, 0, 0)

        self.button_prev = QtWidgets.QPushButton("Prev")
        self.button_prev.clicked.connect(self.find_previous)
        layout.addWidget(self.button_prev, 0, 1)

        self.button_next = QtWidgets.QPushButton("Next")
        self.button_next.clicked.connect(self.find_next)
        layout.addWidget(self.button_next, 0, 2)

        self.check_case = QtWidgets.QCheckBox("Aa")
        self.check_case.setToolTip("Match case")
        layout.addWidget(self.check_case, 0, 3)

        self.label_status = QtWidgets.QLabel("")
        self.label_status.setMinimumWidth(80)
        layout.addWidget(self.label_status, 0, 4)

        self.button_close = QtWidgets.QPushButton("X")
        self.button_close.setFixedWidth(24)
        self.button_close.clicked.connect(self.close_bar)
        layout.addWidget(self.button_close, 0, 5)

        self.replace_edit = QtWidgets.QLineEdit()
        self.replace_edit.setPlaceholderText("Replace with")
        self.replace_edit.returnPressed.connect(self.replace_one)
        layout.addWidget(self.replace_edit, 1, 0)

        self.button_replace = QtWidgets.QPushButton("Replace")
        self.button_replace.clicked.connect(self.replace_one)
        layout.addWidget(self.button_replace, 1, 1, 1, 2)

        self.button_replace_all = QtWidgets.QPushButton("All")
        self.button_replace_all.clicked.connect(self.replace_all)
        layout.addWidget(self.button_replace_all, 1, 3, 1, 2)

        self.__replace_widgets = [self.replace_edit, self.button_replace, self.button_replace_all]

        self.hide()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.close_bar()
            return
        super().keyPressEvent(event)

    def show_find(self, with_replace=False):
        editor = self.__editor_provider()
        if editor is not None:
            selected = editor.textCursor().selectedText()
            if selected != "" and " " not in selected:
                self.find_edit.setText(selected)

        self.show()
        for widget in self.__replace_widgets:
            widget.setVisible(with_replace)
        self.label_status.setText("")
        self.find_edit.setFocus()
        self.find_edit.selectAll()

    def close_bar(self):
        self.hide()
        editor = self.__editor_provider()
        if editor is not None:
            editor.setFocus()

    def __find_flags(self, backwards=False):
        flags = QtGui.QTextDocument.FindFlags()
        if self.check_case.isChecked():
            flags |= QtGui.QTextDocument.FindCaseSensitively
        if backwards:
            flags |= QtGui.QTextDocument.FindBackward
        return flags

    def __find(self, backwards):
        editor = self.__editor_provider()
        text = self.find_edit.text()
        if editor is None or text == "":
            return

        document = editor.document()
        found = document.find(text, editor.textCursor(), self.__find_flags(backwards))
        if found.isNull():
            # wrap around
            cursor = QtGui.QTextCursor(document)
            if backwards:
                cursor.movePosition(QtGui.QTextCursor.End)
            found = document.find(text, cursor, self.__find_flags(backwards))

        if found.isNull():
            self.label_status.setText("Not found")
        else:
            self.label_status.setText("")
            editor.setTextCursor(found)

    def find_next(self):
        self.__find(False)

    def find_previous(self):
        self.__find(True)

    def replace_one(self):
        editor = self.__editor_provider()
        text = self.find_edit.text()
        if editor is None or text == "":
            return

        cursor = editor.textCursor()
        selected = cursor.selectedText()
        if self.check_case.isChecked():
            matched = selected == text
        else:
            matched = selected.lower() == text.lower()

        if matched:
            cursor.insertText(self.replace_edit.text())
        self.find_next()

    def replace_all(self):
        editor = self.__editor_provider()
        text = self.find_edit.text()
        if editor is None or text == "":
            return

        document = editor.document()
        replacement = self.replace_edit.text()

        edit_cursor = QtGui.QTextCursor(document)
        edit_cursor.beginEditBlock()
        count = 0
        cursor = QtGui.QTextCursor(document)
        while True:
            cursor = document.find(text, cursor, self.__find_flags())
            if cursor.isNull():
                break
            cursor.insertText(replacement)
            count += 1
        edit_cursor.endEditBlock()

        self.label_status.setText(f"{count} replaced")


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

        def flush(self):
            pass

    SESSION_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "AEPython")
    SESSION_FILE = os.path.join(SESSION_DIR, "session.json")

    def __init__(self, parent=None):
        super().__init__(parent)

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

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.__close_tab)
        self.tabs.currentChanged.connect(self.__update_title)
        code_layout.addWidget(self.tabs)

        self.find_bar = FindReplaceBar(self.__current_editor)
        code_layout.addWidget(self.find_bar)

        self.button_execute = QtWidgets.QPushButton("Execute (Ctrl+Enter)")
        self.button_execute.clicked.connect(self.__execute)
        code_layout.addWidget(self.button_execute)

        splitter.addWidget(output_widget)
        splitter.addWidget(code_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([200, 400])

        self.__build_menus()

        if not self.__restore_session():
            self.__add_tab()

        self.__update_title()

        sys.stdout = self.Logger(self.textedit_output)
        sys.stderr = self.Logger(self.textedit_output, QtGui.QColor(255, 0, 0), self.show)
        print("AE Python 1.0.0")

    def __build_menus(self):
        def add_action(menu, text, slot, shortcut=None):
            action = QtWidgets.QAction(text, self)
            if shortcut is not None:
                if isinstance(shortcut, list):
                    action.setShortcuts(shortcut)
                else:
                    action.setShortcut(shortcut)
            action.triggered.connect(slot)
            menu.addAction(action)
            return action

        file_menu = self.menuBar().addMenu("File")
        add_action(file_menu, "New", self.__new_file, QtGui.QKeySequence.New)
        add_action(file_menu, "Open...", self.__open_file, QtGui.QKeySequence.Open)
        add_action(file_menu, "Save", self.__save_file, QtGui.QKeySequence.Save)
        add_action(file_menu, "Save As...", self.__save_file_as, QtGui.QKeySequence("Ctrl+Shift+S"))
        add_action(file_menu, "Close Tab", self.__close_current_tab, QtGui.QKeySequence("Ctrl+W"))
        file_menu.addSeparator()
        add_action(file_menu, "Execute Python File", self.__execute_file)

        edit_menu = self.menuBar().addMenu("Edit")
        add_action(edit_menu, "Find...", lambda: self.find_bar.show_find(False),
                   QtGui.QKeySequence.Find)
        add_action(edit_menu, "Replace...", lambda: self.find_bar.show_find(True),
                   QtGui.QKeySequence.Replace)
        add_action(edit_menu, "Find Next", self.find_bar.find_next, QtGui.QKeySequence.FindNext)
        add_action(edit_menu, "Find Previous", self.find_bar.find_previous,
                   QtGui.QKeySequence.FindPrevious)
        edit_menu.addSeparator()
        add_action(edit_menu, "Go to Line...", self.__go_to_line, QtGui.QKeySequence("Ctrl+G"))
        add_action(edit_menu, "Toggle Comment", self.__toggle_comment)

        run_menu = self.menuBar().addMenu("Run")
        add_action(run_menu, "Execute", self.__execute,
                   [QtGui.QKeySequence("Ctrl+Return"), QtGui.QKeySequence("Ctrl+Enter")])
        add_action(run_menu, "Execute Current Line", self.__execute_line,
                   [QtGui.QKeySequence("Ctrl+Shift+Return"), QtGui.QKeySequence("Ctrl+Shift+Enter")])

    # ---- tabs -------------------------------------------------------------

    def __add_tab(self, file_path=None, content=None, modified=False):
        editor = CodeEditor()
        editor.file_path = file_path

        if content is not None:
            editor.setPlainText(content)
        elif file_path is not None:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    editor.setPlainText(f.read())
            except:
                import traceback
                traceback.print_exc()

        editor.document().setModified(modified)
        editor.document().modificationChanged.connect(
            lambda _, e=editor: self.__update_tab_text(e))

        index = self.tabs.addTab(editor, self.__tab_name(editor))
        self.tabs.setTabToolTip(index, "" if file_path is None else file_path)
        self.tabs.setCurrentIndex(index)
        editor.setFocus()
        return editor

    def __tab_name(self, editor):
        name = "untitled" if editor.file_path is None else os.path.basename(editor.file_path)
        if editor.document().isModified():
            name += "*"
        return name

    def __update_tab_text(self, editor):
        index = self.tabs.indexOf(editor)
        if index >= 0:
            self.tabs.setTabText(index, self.__tab_name(editor))
            self.tabs.setTabToolTip(index, "" if editor.file_path is None else editor.file_path)
        self.__update_title()

    def __current_editor(self):
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, CodeEditor) else None

    def __close_tab(self, index):
        editor = self.tabs.widget(index)
        if not isinstance(editor, CodeEditor):
            return
        if not self.__maybe_save(editor):
            return

        self.tabs.removeTab(index)
        editor.deleteLater()

        if self.tabs.count() == 0:
            self.__add_tab()
        self.__save_session()

    def __close_current_tab(self):
        index = self.tabs.currentIndex()
        if index >= 0:
            self.__close_tab(index)

    def __update_title(self, *args):
        editor = self.__current_editor()
        if editor is None:
            self.setWindowTitle("AE Python")
            return
        name = "untitled" if editor.file_path is None else os.path.basename(editor.file_path)
        self.setWindowTitle(f"AE Python - {name}[*]")
        self.setWindowModified(editor.document().isModified())

    # ---- file operations --------------------------------------------------

    def __maybe_save(self, editor):
        if not editor.document().isModified():
            return True
        if editor.toPlainText() == "" and editor.file_path is None:
            return True

        self.tabs.setCurrentWidget(editor)
        ret = QtWidgets.QMessageBox.warning(
            self, "AE Python",
            f"'{self.__tab_name(editor).rstrip('*')}' has been modified.\n"
            "Do you want to save your changes?",
            QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel)

        if ret == QtWidgets.QMessageBox.Save:
            return self.__save_file()
        return ret == QtWidgets.QMessageBox.Discard

    def __new_file(self):
        self.__add_tab()
        self.__save_session()

    def __open_file(self):
        file_path = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Python File", self.__default_dir(), "Python (*.py)")[0]
        if file_path == '':
            return

        for index in range(self.tabs.count()):
            editor = self.tabs.widget(index)
            if isinstance(editor, CodeEditor) and editor.file_path == file_path:
                self.tabs.setCurrentIndex(index)
                return

        # reuse an empty untitled tab
        current = self.__current_editor()
        if current is not None and current.file_path is None \
                and current.toPlainText() == "" and not current.document().isModified():
            self.tabs.removeTab(self.tabs.indexOf(current))
            current.deleteLater()

        self.__add_tab(file_path=file_path)
        self.__save_session()

    def __save_file(self):
        editor = self.__current_editor()
        if editor is None:
            return False
        if editor.file_path is None:
            return self.__save_file_as()

        try:
            with open(editor.file_path, 'w', encoding='utf-8') as f:
                f.write(editor.toPlainText())
        except:
            import traceback
            traceback.print_exc()
            return False

        editor.document().setModified(False)
        self.__save_session()
        return True

    def __save_file_as(self):
        editor = self.__current_editor()
        if editor is None:
            return False

        file_path = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Python File", self.__default_dir(), "Python (*.py)")[0]
        if file_path == '':
            return False

        editor.file_path = file_path
        self.__update_tab_text(editor)
        return self.__save_file()

    def __default_dir(self):
        editor = self.__current_editor()
        if editor is None or editor.file_path is None:
            return ""
        return os.path.dirname(editor.file_path)

    # ---- session ----------------------------------------------------------

    def __save_session(self):
        try:
            tabs = []
            for index in range(self.tabs.count()):
                editor = self.tabs.widget(index)
                if not isinstance(editor, CodeEditor):
                    continue
                modified = editor.document().isModified()
                content = editor.toPlainText() if (editor.file_path is None or modified) else None
                tabs.append({
                    "file_path": editor.file_path,
                    "content": content,
                    "modified": modified,
                })

            os.makedirs(self.SESSION_DIR, exist_ok=True)
            with open(self.SESSION_FILE, 'w', encoding='utf-8') as f:
                json.dump({"tabs": tabs, "current": self.tabs.currentIndex()}, f)
        except:
            import traceback
            traceback.print_exc()

    def __restore_session(self):
        try:
            if not os.path.isfile(self.SESSION_FILE):
                return False
            with open(self.SESSION_FILE, 'r', encoding='utf-8') as f:
                session = json.load(f)

            tabs = session.get("tabs", [])
            if len(tabs) == 0:
                return False

            for tab in tabs:
                self.__add_tab(file_path=tab.get("file_path"),
                               content=tab.get("content"),
                               modified=tab.get("modified", False))

            current = session.get("current", 0)
            if 0 <= current < self.tabs.count():
                self.tabs.setCurrentIndex(current)
            return True
        except:
            import traceback
            traceback.print_exc()
            return False

    def closeEvent(self, event):
        # preserve all code (including unsaved edits) in the session
        self.__save_session()
        super().closeEvent(event)

    # ---- editing ----------------------------------------------------------

    def __go_to_line(self):
        editor = self.__current_editor()
        if editor is None:
            return

        line, ok = QtWidgets.QInputDialog.getInt(
            self, "Go to Line", "Line:",
            editor.textCursor().blockNumber() + 1, 1, editor.blockCount())
        if not ok:
            return

        cursor = QtGui.QTextCursor(editor.document().findBlockByNumber(line - 1))
        editor.setTextCursor(cursor)
        editor.centerCursor()
        editor.setFocus()

    def __toggle_comment(self):
        editor = self.__current_editor()
        if editor is not None:
            editor.toggle_comment()

    # ---- execution --------------------------------------------------------

    def __run_code(self, code):
        # auto-save on execute: code is never lost even if AE goes down
        self.__save_session()
        try:
            exec(code, globals(), _ae.locals)
        except:
            import traceback
            traceback.print_exc()

    def __execute(self):
        editor = self.__current_editor()
        if editor is None:
            return

        cursor = editor.textCursor()
        if cursor.hasSelection():
            # QTextCursor.selectedText() uses U+2029 as the line separator
            code = textwrap.dedent(cursor.selectedText().replace('\u2029', '\n'))
        else:
            code = editor.toPlainText()
        self.__run_code(code)

    def __execute_line(self):
        editor = self.__current_editor()
        if editor is None:
            return
        self.__run_code(editor.textCursor().block().text().strip())

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
