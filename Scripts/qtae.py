import sys
import os
import re
import ast
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


class EditorPane(QtWidgets.QWidget):
    """One document tab: a code editor with an optional split view sharing the document."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)

        self.file_path = None
        self.__settings = settings

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        layout.addWidget(self.splitter)

        self.editor = CodeEditor(settings=settings)
        self.editor.gotFocus.connect(lambda: self.__set_active(self.editor))
        self.splitter.addWidget(self.editor)

        self.second_editor = None
        self.__active = self.editor

    def __set_active(self, editor):
        self.__active = editor

    def active_editor(self):
        if self.__active is None:
            return self.editor
        return self.__active

    def editors(self):
        return [self.editor] if self.second_editor is None else [self.editor, self.second_editor]

    def is_split(self):
        return self.second_editor is not None

    def set_split(self, split):
        if split == self.is_split():
            return None

        if split:
            self.second_editor = CodeEditor(
                settings=self.__settings, document=self.editor.document(), lint=False)
            self.second_editor.gotFocus.connect(lambda: self.__set_active(self.second_editor))
            self.splitter.addWidget(self.second_editor)
            size = max(self.splitter.height(), self.splitter.width(), 2)
            self.splitter.setSizes([size // 2, size // 2])
            return self.second_editor
        else:
            self.second_editor.setParent(None)
            self.second_editor.deleteLater()
            self.second_editor = None
            self.__active = self.editor
            self.editor.setFocus()
            return None

    def set_split_orientation(self, horizontal):
        self.splitter.setOrientation(
            QtCore.Qt.Horizontal if horizontal else QtCore.Qt.Vertical)

    def is_split_horizontal(self):
        return self.splitter.orientation() == QtCore.Qt.Horizontal


class WorkspaceView(QtWidgets.QWidget):
    """Tree view of workspace folders. Double-click a file to open it."""

    fileActivated = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        buttons = QtWidgets.QHBoxLayout()
        layout.addLayout(buttons)

        button_add = QtWidgets.QPushButton("Add Folder...")
        button_add.clicked.connect(self.__add_folder_dialog)
        buttons.addWidget(button_add)

        button_remove = QtWidgets.QPushButton("Remove")
        button_remove.setToolTip("Remove the selected top-level folder from the workspace")
        button_remove.clicked.connect(self.__remove_selected_folder)
        buttons.addWidget(button_remove)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemExpanded.connect(self.__populate_item)
        self.tree.itemActivated.connect(self.__on_item_activated)
        self.tree.itemDoubleClicked.connect(self.__on_item_activated)
        layout.addWidget(self.tree)

    def folders(self):
        return [self.tree.topLevelItem(i).data(0, QtCore.Qt.UserRole)
                for i in range(self.tree.topLevelItemCount())]

    def set_folders(self, folders):
        self.tree.clear()
        for folder in folders:
            self.add_folder(folder)

    def add_folder(self, folder):
        if not os.path.isdir(folder) or folder in self.folders():
            return
        item = QtWidgets.QTreeWidgetItem([os.path.basename(folder.rstrip("/\\")) or folder])
        item.setData(0, QtCore.Qt.UserRole, folder)
        item.setData(0, QtCore.Qt.UserRole + 1, "dir")
        item.setToolTip(0, folder)
        item.setChildIndicatorPolicy(QtWidgets.QTreeWidgetItem.ShowIndicator)
        self.tree.addTopLevelItem(item)

    def __add_folder_dialog(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Add Folder to Workspace")
        if folder != '':
            self.add_folder(folder)

    def __remove_selected_folder(self):
        item = self.tree.currentItem()
        while item is not None and item.parent() is not None:
            item = item.parent()
        if item is not None:
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))

    def __populate_item(self, item):
        if item.data(0, QtCore.Qt.UserRole + 1) != "dir":
            return

        item.takeChildren()
        path = item.data(0, QtCore.Qt.UserRole)
        try:
            entries = sorted(os.listdir(path), key=str.lower)
        except OSError:
            return

        directories = []
        files = []
        for name in entries:
            if name.startswith(".") or name == "__pycache__":
                continue
            full = os.path.join(path, name)
            if os.path.isdir(full):
                directories.append((name, full))
            elif name.endswith(".py"):
                files.append((name, full))

        for name, full in directories:
            child = QtWidgets.QTreeWidgetItem([name])
            child.setData(0, QtCore.Qt.UserRole, full)
            child.setData(0, QtCore.Qt.UserRole + 1, "dir")
            child.setChildIndicatorPolicy(QtWidgets.QTreeWidgetItem.ShowIndicator)
            item.addChild(child)
        for name, full in files:
            child = QtWidgets.QTreeWidgetItem([name])
            child.setData(0, QtCore.Qt.UserRole, full)
            child.setData(0, QtCore.Qt.UserRole + 1, "file")
            item.addChild(child)

    def __on_item_activated(self, item, column=0):
        if item.data(0, QtCore.Qt.UserRole + 1) == "file":
            self.fileActivated.emit(item.data(0, QtCore.Qt.UserRole))


class GoToSymbolDialog(QtWidgets.QDialog):
    """Filterable list of class / def symbols. Returns the chosen line."""

    def __init__(self, symbols, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Go to Symbol")
        self.resize(400, 300)

        self.selected_line = None
        self.__symbols = symbols

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        self.filter_edit = QtWidgets.QLineEdit()
        self.filter_edit.setPlaceholderText("Type to filter symbols")
        self.filter_edit.textChanged.connect(self.__refresh)
        self.filter_edit.returnPressed.connect(self.__accept_current)
        layout.addWidget(self.filter_edit)

        self.list = QtWidgets.QListWidget()
        self.list.itemActivated.connect(self.__accept_item)
        layout.addWidget(self.list)

        self.__refresh()
        self.filter_edit.setFocus()

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Down, QtCore.Qt.Key_Up) \
                and self.filter_edit.hasFocus():
            self.list.setFocus()
            self.list.keyPressEvent(event)
            return
        super().keyPressEvent(event)

    def __refresh(self):
        pattern = self.filter_edit.text().lower()
        self.list.clear()
        for label, line in self.__symbols:
            if pattern in label.lower():
                item = QtWidgets.QListWidgetItem(label)
                item.setData(QtCore.Qt.UserRole, line)
                self.list.addItem(item)
        if self.list.count() > 0:
            self.list.setCurrentRow(0)

    def __accept_current(self):
        item = self.list.currentItem()
        if item is not None:
            self.__accept_item(item)

    def __accept_item(self, item):
        self.selected_line = item.data(QtCore.Qt.UserRole)
        self.accept()


class FindReplaceBar(QtWidgets.QWidget):
    def __init__(self, editor_provider, tabs_provider, files_search_callback,
                 activate_callback, parent=None):
        super().__init__(parent)
        self.__editor_provider = editor_provider
        self.__tabs_provider = tabs_provider
        self.__files_search_callback = files_search_callback
        self.__activate_callback = activate_callback

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

        self.button_all_tabs = QtWidgets.QPushButton("All Tabs")
        self.button_all_tabs.setToolTip("Search in all open tabs")
        self.button_all_tabs.clicked.connect(self.search_all_tabs)
        layout.addWidget(self.button_all_tabs, 0, 3)

        self.button_in_files = QtWidgets.QPushButton("In Files")
        self.button_in_files.setToolTip("Search in the Workspace folders")
        self.button_in_files.clicked.connect(self.search_in_files)
        layout.addWidget(self.button_in_files, 0, 4)

        self.check_case = QtWidgets.QCheckBox("Aa")
        self.check_case.setToolTip("Match case")
        layout.addWidget(self.check_case, 0, 5)

        self.label_status = QtWidgets.QLabel("")
        self.label_status.setMinimumWidth(80)
        layout.addWidget(self.label_status, 0, 6)

        self.button_close = QtWidgets.QPushButton("X")
        self.button_close.setFixedWidth(24)
        self.button_close.clicked.connect(self.close_bar)
        layout.addWidget(self.button_close, 0, 7)

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

        self.results_list = QtWidgets.QListWidget()
        self.results_list.setMaximumHeight(120)
        self.results_list.itemActivated.connect(self.__activate_result)
        self.results_list.itemClicked.connect(self.__activate_result)
        self.results_list.hide()
        layout.addWidget(self.results_list, 2, 0, 1, 8)

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
            if selected != "" and " " not in selected:
                self.find_edit.setText(selected)

        self.show()
        for widget in self.__replace_widgets:
            widget.setVisible(with_replace)
        self.label_status.setText("")
        self.find_edit.setFocus()
        self.find_edit.selectAll()

    def close_bar(self):
        self.hide()
        self.results_list.hide()
        self.results_list.clear()
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

    def __show_results(self, results):
        self.results_list.clear()
        for result in results:
            item = QtWidgets.QListWidgetItem(result["label"])
            item.setData(QtCore.Qt.UserRole, result)
            self.results_list.addItem(item)
        self.label_status.setText(f"{len(results)} matches")
        self.results_list.setVisible(len(results) > 0)

    def search_all_tabs(self):
        MAX_RESULTS = 500

        text = self.find_edit.text()
        if text == "":
            return

        needle = text if self.check_case.isChecked() else text.lower()
        results = []

        for name, editor, tab_index in self.__tabs_provider():
            document = editor.document()
            haystack = editor.toPlainText()
            if not self.check_case.isChecked():
                haystack = haystack.lower()

            pos = haystack.find(needle)
            while pos >= 0 and len(results) < MAX_RESULTS:
                block = document.findBlock(pos)
                results.append({
                    "kind": "tab",
                    "label": f"{name}  {block.blockNumber() + 1}: {block.text().strip()}",
                    "tab": tab_index,
                    "start": pos,
                    "end": pos + len(text),
                })
                pos = haystack.find(needle, pos + 1)

            if len(results) >= MAX_RESULTS:
                break

        self.__show_results(results)

    def search_in_files(self):
        text = self.find_edit.text()
        if text == "":
            return
        results = self.__files_search_callback(text, self.check_case.isChecked())
        self.__show_results(results)

    def __activate_result(self, item):
        self.__activate_callback(item.data(QtCore.Qt.UserRole))


class PythonWindow(QtWidgets.QMainWindow):
    class Logger:
        def __init__(self, editor: QtWidgets.QTextEdit, color=None, show=None,
                     rules=None, log_writer=None):
            self.editor = editor
            self.color = editor.textColor() if color is None else color
            self.show = show
            self.rules = rules or []
            self.log_writer = log_writer

        def write(self, message: str):
            color = self.color
            for pattern, rule_color in self.rules:
                if pattern.search(message):
                    color = rule_color
                    break

            self.editor.moveCursor(QtGui.QTextCursor.End)
            self.editor.setTextColor(color)
            self.editor.insertPlainText(message)

            if self.log_writer is not None:
                self.log_writer(message)

            if self.show is not None:
                self.show()

        def flush(self):
            pass

    CONFIG_DIR = os.path.join(os.getenv("APPDATA", os.path.expanduser("~")), "AEPython")
    SESSION_FILE = os.path.join(CONFIG_DIR, "session.json")
    SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
    OUTPUT_LOG_FILE = os.path.join(CONFIG_DIR, "output.log")

    MAX_RECENT_FILES = 10

    DEFAULT_SETTINGS = {
        "font_family": "Consolas",
        "font_size": 10,
        "indent_width": 4,
        "colors": {},
        "shortcuts": {},
        "output_highlight": [],
    }

    def __init__(self, parent=None):
        super().__init__(parent)

        self.settings = self.__load_settings()
        self.__show_whitespace = False
        self.__word_wrap = False
        self.__font_delta = 0
        self.__actions = {}
        self.__recent_files = []
        self.__log_file = None

        self.centralWidget = QtWidgets.QWidget()
        self.setCentralWidget(self.centralWidget)

        layout = QtWidgets.QVBoxLayout()
        self.centralWidget.setLayout(layout)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        layout.addWidget(splitter)

        self.output_widget = QtWidgets.QWidget()
        output_layout = QtWidgets.QVBoxLayout()
        output_layout.setContentsMargins(0, 0, 0, 0)
        self.output_widget.setLayout(output_layout)

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
        self.tabs.currentChanged.connect(self.__on_current_tab_changed)
        code_layout.addWidget(self.tabs)

        self.problems_list = QtWidgets.QListWidget()
        self.problems_list.setMaximumHeight(90)
        self.problems_list.itemActivated.connect(self.__activate_problem)
        self.problems_list.itemClicked.connect(self.__activate_problem)
        self.problems_list.hide()
        code_layout.addWidget(self.problems_list)

        self.find_bar = FindReplaceBar(self.__current_editor, self.__all_tabs,
                                       self.__search_workspace_files,
                                       self.__activate_search_result)
        code_layout.addWidget(self.find_bar)

        self.button_execute = QtWidgets.QPushButton("Execute (Ctrl+Enter)")
        self.button_execute.clicked.connect(self.__execute)
        code_layout.addWidget(self.button_execute)

        splitter.addWidget(self.output_widget)
        splitter.addWidget(code_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([200, 400])

        self.__build_workspace_dock()
        self.__build_outline_dock()
        self.__build_status_bar()
        self.__build_menus()
        self.__apply_shortcut_settings()

        if not self.__restore_session():
            self.__add_tab()

        self.__update_title()

        rules = self.__output_highlight_rules()
        sys.stdout = self.Logger(self.textedit_output,
                                 rules=rules, log_writer=self.__write_output_log)
        sys.stderr = self.Logger(self.textedit_output, QtGui.QColor(255, 0, 0), self.show,
                                 rules=rules, log_writer=self.__write_output_log)
        print("AE Python 1.0.0")

    # ---- settings ---------------------------------------------------------

    def __load_settings(self):
        settings = dict(self.DEFAULT_SETTINGS)
        try:
            if os.path.isfile(self.SETTINGS_FILE):
                with open(self.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings.update(json.load(f))
            else:
                # write a template so the settings are discoverable
                os.makedirs(self.CONFIG_DIR, exist_ok=True)
                with open(self.SETTINGS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.DEFAULT_SETTINGS, f, indent=4)
        except:
            import traceback
            traceback.print_exc()
        return settings

    def __apply_shortcut_settings(self):
        for name, sequence in self.settings.get("shortcuts", {}).items():
            action = self.__actions.get(name)
            if action is not None:
                action.setShortcut(QtGui.QKeySequence(sequence))

    def __output_highlight_rules(self):
        rules = []
        for rule in self.settings.get("output_highlight", []):
            try:
                rules.append((re.compile(rule["pattern"]), QtGui.QColor(rule["color"])))
            except (re.error, KeyError, TypeError):
                pass
        return rules

    # ---- menus ------------------------------------------------------------

    def __build_menus(self):
        def add_action(menu, name, text, slot, shortcut=None, checkable=False):
            action = QtWidgets.QAction(text, self)
            if shortcut is not None:
                if isinstance(shortcut, list):
                    action.setShortcuts(shortcut)
                else:
                    action.setShortcut(shortcut)
            if checkable:
                action.setCheckable(True)
                action.toggled.connect(slot)
            else:
                action.triggered.connect(slot)
            menu.addAction(action)
            self.__actions[name] = action
            return action

        file_menu = self.menuBar().addMenu("File")
        add_action(file_menu, "new", "New", self.__new_file, QtGui.QKeySequence.New)
        add_action(file_menu, "open", "Open...", self.__open_file, QtGui.QKeySequence.Open)
        self.recent_menu = file_menu.addMenu("Open Recent")
        self.recent_menu.aboutToShow.connect(self.__rebuild_recent_menu)
        add_action(file_menu, "save", "Save", self.__save_file, QtGui.QKeySequence.Save)
        add_action(file_menu, "save_as", "Save As...", self.__save_file_as,
                   QtGui.QKeySequence("Ctrl+Shift+S"))
        add_action(file_menu, "save_all", "Save All", self.__save_all)
        add_action(file_menu, "rename", "Rename...", self.__rename_file)
        add_action(file_menu, "revert", "Revert File", self.__revert_file)
        file_menu.addSeparator()
        add_action(file_menu, "close_tab", "Close Tab", self.__close_current_tab,
                   QtGui.QKeySequence("Ctrl+W"))
        add_action(file_menu, "close_all", "Close All Tabs", self.__close_all_tabs)
        file_menu.addSeparator()
        add_action(file_menu, "execute_python_file", "Execute Python File", self.__execute_file)

        edit_menu = self.menuBar().addMenu("Edit")
        add_action(edit_menu, "undo", "Undo", self.__undo, QtGui.QKeySequence.Undo)
        add_action(edit_menu, "redo", "Redo", self.__redo, QtGui.QKeySequence.Redo)
        edit_menu.addSeparator()
        add_action(edit_menu, "cut", "Cut", lambda: self.__editor_call("cut"),
                   QtGui.QKeySequence.Cut)
        add_action(edit_menu, "copy", "Copy", lambda: self.__editor_call("copy"),
                   QtGui.QKeySequence.Copy)
        add_action(edit_menu, "paste", "Paste", lambda: self.__editor_call("paste"),
                   QtGui.QKeySequence.Paste)
        add_action(edit_menu, "select_all", "Select All", lambda: self.__editor_call("selectAll"),
                   QtGui.QKeySequence.SelectAll)
        edit_menu.addSeparator()

        line_menu = edit_menu.addMenu("Line")
        add_action(line_menu, "duplicate_lines", "Duplicate Line(s)",
                   lambda: self.__editor_call("duplicate_lines"), QtGui.QKeySequence("Ctrl+D"))
        add_action(line_menu, "delete_lines", "Delete Line(s)",
                   lambda: self.__editor_call("delete_lines"), QtGui.QKeySequence("Ctrl+Shift+K"))
        add_action(line_menu, "move_lines_up", "Move Line(s) Up",
                   lambda: self.__editor_call("move_lines_up"), QtGui.QKeySequence("Alt+Up"))
        add_action(line_menu, "move_lines_down", "Move Line(s) Down",
                   lambda: self.__editor_call("move_lines_down"), QtGui.QKeySequence("Alt+Down"))
        add_action(line_menu, "select_lines", "Select Line(s)",
                   lambda: self.__editor_call("select_lines"), QtGui.QKeySequence("Ctrl+L"))
        add_action(line_menu, "join_lines", "Join Lines",
                   lambda: self.__editor_call("join_lines"), QtGui.QKeySequence("Ctrl+J"))

        add_action(edit_menu, "toggle_comment", "Toggle Comment",
                   lambda: self.__editor_call("toggle_comment"))
        edit_menu.addSeparator()
        add_action(edit_menu, "find", "Find...", lambda: self.find_bar.show_find(False),
                   QtGui.QKeySequence.Find)
        add_action(edit_menu, "replace", "Replace...", lambda: self.find_bar.show_find(True),
                   QtGui.QKeySequence.Replace)
        add_action(edit_menu, "find_next", "Find Next", self.find_bar.find_next,
                   QtGui.QKeySequence.FindNext)
        add_action(edit_menu, "find_previous", "Find Previous", self.find_bar.find_previous,
                   QtGui.QKeySequence.FindPrevious)
        add_action(edit_menu, "find_in_tabs", "Find in All Tabs",
                   self.__find_in_all_tabs, QtGui.QKeySequence("Ctrl+Shift+F"))
        add_action(edit_menu, "find_in_files", "Find in Files", self.__find_in_files)
        edit_menu.addSeparator()
        add_action(edit_menu, "go_to_line", "Go to Line...", self.__go_to_line,
                   QtGui.QKeySequence("Ctrl+G"))
        add_action(edit_menu, "go_to_symbol", "Go to Symbol...", self.__go_to_symbol,
                   QtGui.QKeySequence("Ctrl+Shift+O"))

        view_menu = self.menuBar().addMenu("View")
        self.action_split = add_action(view_menu, "split_editor", "Split Editor",
                                       self.__toggle_split, QtGui.QKeySequence("Ctrl+Alt+S"),
                                       checkable=True)
        self.action_split_layout = add_action(view_menu, "split_layout", "Split Side by Side",
                                              self.__toggle_split_layout, checkable=True)
        view_menu.addSeparator()
        add_action(view_menu, "next_tab", "Next Tab", self.__next_tab,
                   QtGui.QKeySequence("Ctrl+Tab"))
        add_action(view_menu, "previous_tab", "Previous Tab", self.__previous_tab,
                   QtGui.QKeySequence("Ctrl+Shift+Tab"))
        view_menu.addSeparator()
        add_action(view_menu, "show_whitespace", "Show Whitespace",
                   self.__set_show_whitespace, checkable=True)
        add_action(view_menu, "word_wrap", "Word Wrap", self.__set_word_wrap, checkable=True)
        view_menu.addSeparator()
        add_action(view_menu, "zoom_in", "Increase Font Size", self.__zoom_in,
                   QtGui.QKeySequence.ZoomIn)
        add_action(view_menu, "zoom_out", "Decrease Font Size", self.__zoom_out,
                   QtGui.QKeySequence.ZoomOut)
        add_action(view_menu, "zoom_reset", "Reset Font Size", self.__zoom_reset,
                   QtGui.QKeySequence("Ctrl+0"))
        view_menu.addSeparator()
        self.action_toggle_output = add_action(view_menu, "toggle_output", "Show Output",
                                               self.__set_output_visible, checkable=True)
        self.action_toggle_output.setChecked(True)
        view_menu.addAction(self.workspace_dock.toggleViewAction())
        self.__actions["workspace"] = self.workspace_dock.toggleViewAction()
        view_menu.addAction(self.outline_dock.toggleViewAction())
        self.__actions["outline"] = self.outline_dock.toggleViewAction()

        run_menu = self.menuBar().addMenu("Run")
        add_action(run_menu, "execute", "Execute", self.__execute,
                   [QtGui.QKeySequence("Ctrl+Return"), QtGui.QKeySequence("Ctrl+Enter")])
        add_action(run_menu, "execute_all", "Execute All", self.__execute_all,
                   [QtGui.QKeySequence("Ctrl+Shift+Return"), QtGui.QKeySequence("Ctrl+Shift+Enter")])
        add_action(run_menu, "execute_line", "Execute Current Line", self.__execute_line,
                   [QtGui.QKeySequence("Ctrl+Alt+Return"), QtGui.QKeySequence("Ctrl+Alt+Enter")])
        run_menu.addSeparator()
        add_action(run_menu, "check_code", "Check Code", self.__check_code_now)
        add_action(run_menu, "environment_variables", "Environment Variables",
                   self.__print_environment)

        output_menu = self.menuBar().addMenu("Output")
        add_action(output_menu, "clear_output", "Clear Output", self.textedit_output.clear,
                   QtGui.QKeySequence("Ctrl+Shift+D"))
        add_action(output_menu, "write_output_to_file", "Write Output to File",
                   self.__set_write_output_to_file, checkable=True)

    # ---- workspace --------------------------------------------------------

    def __build_workspace_dock(self):
        self.workspace = WorkspaceView()
        self.workspace.fileActivated.connect(self.open_path)

        self.workspace_dock = QtWidgets.QDockWidget("Workspace", self)
        self.workspace_dock.setObjectName("WorkspaceDock")
        self.workspace_dock.setWidget(self.workspace)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.workspace_dock)
        self.workspace_dock.hide()

    def __search_workspace_files(self, text, case_sensitive):
        MAX_RESULTS = 500
        MAX_FILE_SIZE = 1024 * 1024

        needle = text if case_sensitive else text.lower()
        results = []

        for folder in self.workspace.folders():
            for root, dirs, files in os.walk(folder):
                dirs[:] = [d for d in dirs
                           if not d.startswith(".") and d != "__pycache__"]
                for name in files:
                    if not name.endswith(".py"):
                        continue
                    path = os.path.join(root, name)
                    try:
                        if os.path.getsize(path) > MAX_FILE_SIZE:
                            continue
                        with open(path, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read()
                    except OSError:
                        continue

                    haystack = content if case_sensitive else content.lower()
                    pos = haystack.find(needle)
                    while pos >= 0 and len(results) < MAX_RESULTS:
                        line = content.count("\n", 0, pos) + 1
                        line_start = content.rfind("\n", 0, pos) + 1
                        line_end = content.find("\n", pos)
                        if line_end == -1:
                            line_end = len(content)
                        results.append({
                            "kind": "file",
                            "label": f"{os.path.basename(path)}  {line}: "
                                     f"{content[line_start:line_end].strip()}",
                            "path": path,
                            "line": line,
                            "col": pos - line_start,
                        })
                        pos = haystack.find(needle, pos + 1)

                    if len(results) >= MAX_RESULTS:
                        return results
        return results

    # ---- outline ----------------------------------------------------------

    def __build_outline_dock(self):
        self.outline_tree = QtWidgets.QTreeWidget()
        self.outline_tree.setHeaderHidden(True)
        self.outline_tree.itemActivated.connect(self.__activate_outline_item)
        self.outline_tree.itemClicked.connect(self.__activate_outline_item)

        self.outline_dock = QtWidgets.QDockWidget("Outline", self)
        self.outline_dock.setObjectName("OutlineDock")
        self.outline_dock.setWidget(self.outline_tree)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.outline_dock)
        self.outline_dock.hide()

    def __refresh_outline(self):
        pane = self.__current_pane()
        if pane is None:
            self.outline_tree.clear()
            return

        try:
            tree = ast.parse(pane.editor.toPlainText())
        except SyntaxError:
            return  # keep the previous outline while the code does not parse

        self.outline_tree.clear()

        def add_nodes(body, parent):
            for node in body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    kind = "class" if isinstance(node, ast.ClassDef) else "def"
                    item = QtWidgets.QTreeWidgetItem([f"{kind} {node.name}"])
                    item.setData(0, QtCore.Qt.UserRole, node.lineno)
                    if isinstance(parent, QtWidgets.QTreeWidgetItem):
                        parent.addChild(item)
                    else:
                        parent.addTopLevelItem(item)
                    add_nodes(node.body, item)

        add_nodes(tree.body, self.outline_tree)
        self.outline_tree.expandAll()

    def __activate_outline_item(self, item, column=0):
        line = item.data(0, QtCore.Qt.UserRole)
        if line is not None:
            self.__go_to_position_in_current(line=line)

    def __collect_symbols(self):
        pane = self.__current_pane()
        if pane is None:
            return []

        try:
            tree = ast.parse(pane.editor.toPlainText())
        except SyntaxError:
            return []

        symbols = []

        def collect(body, prefix):
            for node in body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    kind = "class" if isinstance(node, ast.ClassDef) else "def"
                    label = prefix + node.name
                    symbols.append((f"{kind} {label}", node.lineno))
                    collect(node.body, label + ".")

        collect(tree.body, "")
        return symbols

    def __go_to_symbol(self):
        symbols = self.__collect_symbols()
        dialog = GoToSymbolDialog(symbols, self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted and dialog.selected_line is not None:
            self.__go_to_position_in_current(line=dialog.selected_line)

    # ---- status bar -------------------------------------------------------

    def __build_status_bar(self):
        self.status_position = QtWidgets.QLabel("")
        self.statusBar().addWidget(self.status_position)

        self.status_problems = QtWidgets.QLabel("")
        self.statusBar().addPermanentWidget(self.status_problems)

    def __update_status_position(self):
        editor = self.__current_editor()
        if editor is None:
            self.status_position.setText("")
            return
        cursor = editor.textCursor()
        self.status_position.setText(
            f"Ln {cursor.blockNumber() + 1}, Col {cursor.positionInBlock() + 1}")

    def __update_status_problems(self, results):
        errors = sum(1 for r in results if r["kind"] == "error")
        warnings = len(results) - errors
        if errors == 0 and warnings == 0:
            self.status_problems.setText("")
        else:
            self.status_problems.setText(f"{errors} errors, {warnings} warnings")

    # ---- problems (code check results) ------------------------------------

    def __on_lint_updated(self, pane, results):
        if pane is self.__current_pane():
            self.__update_problems(results)
            self.__refresh_outline()

    def __update_problems(self, results):
        self.problems_list.clear()
        for result in results:
            mark = "[E]" if result["kind"] == "error" else "[W]"
            item = QtWidgets.QListWidgetItem(
                f"{mark} Line {result['line']}: {result['message']}")
            if result["kind"] == "error":
                item.setForeground(QtGui.QColor("#ff5555"))
            item.setData(QtCore.Qt.UserRole, (result["line"], result["col"]))
            self.problems_list.addItem(item)
        self.problems_list.setVisible(len(results) > 0)
        self.__update_status_problems(results)

    def __activate_problem(self, item):
        line, col = item.data(QtCore.Qt.UserRole)
        self.__go_to_position_in_current(line=line, col=col)

    def __check_code_now(self):
        pane = self.__current_pane()
        if pane is not None:
            pane.editor.run_lint()

    # ---- tabs -------------------------------------------------------------

    def __add_tab(self, file_path=None, content=None, modified=False):
        pane = EditorPane(self.settings)
        pane.file_path = file_path

        if content is not None:
            pane.editor.setPlainText(content)
        elif file_path is not None:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    pane.editor.setPlainText(f.read())
            except:
                import traceback
                traceback.print_exc()

        pane.editor.document().setModified(modified)
        pane.editor.document().modificationChanged.connect(
            lambda _, p=pane: self.__update_tab_text(p))
        pane.editor.lintUpdated.connect(
            lambda results, p=pane: self.__on_lint_updated(p, results))
        self.__setup_editor(pane.editor)

        index = self.tabs.addTab(pane, self.__tab_name(pane))
        self.tabs.setTabToolTip(index, "" if file_path is None else file_path)
        self.tabs.setCurrentIndex(index)
        pane.editor.setFocus()
        return pane

    def __setup_editor(self, editor):
        """Apply window-level view options and connections to a newly created editor."""
        self.__apply_whitespace_option(editor)
        editor.set_word_wrap(self.__word_wrap)
        if self.__font_delta != 0:
            editor.set_font_size(int(self.settings.get("font_size", 10)) + self.__font_delta)
        editor.cursorPositionChanged.connect(self.__update_status_position)

    def __tab_name(self, pane):
        name = "untitled" if pane.file_path is None else os.path.basename(pane.file_path)
        if pane.editor.document().isModified():
            name += "*"
        return name

    def __update_tab_text(self, pane):
        index = self.tabs.indexOf(pane)
        if index >= 0:
            self.tabs.setTabText(index, self.__tab_name(pane))
            self.tabs.setTabToolTip(index, "" if pane.file_path is None else pane.file_path)
        self.__update_title()

    def __current_pane(self):
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, EditorPane) else None

    def __current_editor(self):
        pane = self.__current_pane()
        return None if pane is None else pane.active_editor()

    def __editor_call(self, method_name):
        editor = self.__current_editor()
        if editor is not None:
            getattr(editor, method_name)()

    def __all_tabs(self):
        tabs = []
        for index in range(self.tabs.count()):
            pane = self.tabs.widget(index)
            if isinstance(pane, EditorPane):
                tabs.append((self.__tab_name(pane), pane.editor, index))
        return tabs

    def __panes(self):
        return [self.tabs.widget(i) for i in range(self.tabs.count())
                if isinstance(self.tabs.widget(i), EditorPane)]

    def __close_tab(self, index):
        pane = self.tabs.widget(index)
        if not isinstance(pane, EditorPane):
            return
        if not self.__maybe_save(pane):
            return

        self.tabs.removeTab(index)
        pane.deleteLater()

        if self.tabs.count() == 0:
            self.__add_tab()
        self.__save_session()

    def __close_current_tab(self):
        index = self.tabs.currentIndex()
        if index >= 0:
            self.__close_tab(index)

    def __close_all_tabs(self):
        for pane in self.__panes():
            if not self.__maybe_save(pane):
                return

        self.tabs.clear()
        for pane in self.__panes():
            pane.deleteLater()
        self.__add_tab()
        self.__save_session()

    def __next_tab(self):
        if self.tabs.count() > 0:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % self.tabs.count())

    def __previous_tab(self):
        if self.tabs.count() > 0:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() - 1) % self.tabs.count())

    def __on_current_tab_changed(self, *args):
        self.__update_title()
        pane = self.__current_pane()
        if pane is not None:
            self.action_split.blockSignals(True)
            self.action_split.setChecked(pane.is_split())
            self.action_split.blockSignals(False)
            self.action_split_layout.blockSignals(True)
            self.action_split_layout.setChecked(pane.is_split_horizontal())
            self.action_split_layout.blockSignals(False)
            self.__update_problems(pane.editor.lint_results)
        self.__refresh_outline()
        self.__update_status_position()

    def __update_title(self, *args):
        pane = self.__current_pane()
        if pane is None:
            self.setWindowTitle("AE Python")
            return
        name = "untitled" if pane.file_path is None else os.path.basename(pane.file_path)
        self.setWindowTitle(f"AE Python - {name}[*]")
        self.setWindowModified(pane.editor.document().isModified())

    # ---- view -------------------------------------------------------------

    def __toggle_split(self, checked):
        pane = self.__current_pane()
        if pane is None:
            return
        second = pane.set_split(checked)
        if second is not None:
            self.__setup_editor(second)

    def __toggle_split_layout(self, checked):
        pane = self.__current_pane()
        if pane is not None:
            pane.set_split_orientation(checked)

    def __set_show_whitespace(self, checked):
        self.__show_whitespace = checked
        for pane in self.__panes():
            for editor in pane.editors():
                self.__apply_whitespace_option(editor)

    def __apply_whitespace_option(self, editor):
        option = editor.document().defaultTextOption()
        if self.__show_whitespace:
            option.setFlags(option.flags() | QtGui.QTextOption.ShowTabsAndSpaces)
        else:
            option.setFlags(option.flags() & ~QtGui.QTextOption.ShowTabsAndSpaces)
        editor.document().setDefaultTextOption(option)

    def __set_word_wrap(self, checked):
        self.__word_wrap = checked
        for pane in self.__panes():
            for editor in pane.editors():
                editor.set_word_wrap(checked)

    def __apply_font_delta(self):
        size = int(self.settings.get("font_size", 10)) + self.__font_delta
        for pane in self.__panes():
            for editor in pane.editors():
                editor.set_font_size(size)

    def __zoom_in(self):
        self.__font_delta += 1
        self.__apply_font_delta()

    def __zoom_out(self):
        self.__font_delta -= 1
        self.__apply_font_delta()

    def __zoom_reset(self):
        self.__font_delta = 0
        self.__apply_font_delta()

    def __set_output_visible(self, checked):
        self.output_widget.setVisible(checked)

    # ---- output -----------------------------------------------------------

    def __set_write_output_to_file(self, checked):
        if checked and self.__log_file is None:
            try:
                os.makedirs(self.CONFIG_DIR, exist_ok=True)
                self.__log_file = open(self.OUTPUT_LOG_FILE, 'a', encoding='utf-8')
            except OSError:
                import traceback
                traceback.print_exc()
        elif not checked and self.__log_file is not None:
            self.__log_file.close()
            self.__log_file = None

    def __write_output_log(self, message):
        if self.__log_file is not None:
            try:
                self.__log_file.write(message)
                self.__log_file.flush()
            except OSError:
                pass

    def __print_environment(self):
        print("Environment Variables:")
        for key in sorted(os.environ):
            print(f"    {key} = {os.environ[key]}")

    # ---- file operations --------------------------------------------------

    def __maybe_save(self, pane):
        if not pane.editor.document().isModified():
            return True
        if pane.editor.toPlainText() == "" and pane.file_path is None:
            return True

        self.tabs.setCurrentWidget(pane)
        ret = QtWidgets.QMessageBox.warning(
            self, "AE Python",
            f"'{self.__tab_name(pane).rstrip('*')}' has been modified.\n"
            "Do you want to save your changes?",
            QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel)

        if ret == QtWidgets.QMessageBox.Save:
            return self.__save_file()
        return ret == QtWidgets.QMessageBox.Discard

    def __new_file(self):
        self.__add_tab()
        self.__save_session()

    def open_path(self, file_path):
        """Open a file in a tab (activates the existing tab when already open)."""
        for index in range(self.tabs.count()):
            pane = self.tabs.widget(index)
            if isinstance(pane, EditorPane) and pane.file_path == file_path:
                self.tabs.setCurrentIndex(index)
                return pane

        # reuse an empty untitled tab
        current = self.__current_pane()
        if current is not None and current.file_path is None \
                and current.editor.toPlainText() == "" \
                and not current.editor.document().isModified():
            self.tabs.removeTab(self.tabs.indexOf(current))
            current.deleteLater()

        pane = self.__add_tab(file_path=file_path)
        self.__add_recent_file(file_path)
        self.__save_session()
        return pane

    def __open_file(self):
        file_path = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Python File", self.__default_dir(), "Python (*.py)")[0]
        if file_path != '':
            self.open_path(file_path)

    def __save_pane(self, pane):
        if pane.file_path is None:
            self.tabs.setCurrentWidget(pane)
            return self.__save_file_as()

        try:
            with open(pane.file_path, 'w', encoding='utf-8') as f:
                f.write(pane.editor.toPlainText())
        except:
            import traceback
            traceback.print_exc()
            return False

        pane.editor.document().setModified(False)
        self.__save_session()
        return True

    def __save_file(self):
        pane = self.__current_pane()
        if pane is None:
            return False
        return self.__save_pane(pane)

    def __save_file_as(self):
        pane = self.__current_pane()
        if pane is None:
            return False

        file_path = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Python File", self.__default_dir(), "Python (*.py)")[0]
        if file_path == '':
            return False

        pane.file_path = file_path
        self.__update_tab_text(pane)
        self.__add_recent_file(file_path)
        return self.__save_pane(pane)

    def __save_all(self):
        for pane in self.__panes():
            if pane.file_path is not None and pane.editor.document().isModified():
                self.__save_pane(pane)

    def __rename_file(self):
        pane = self.__current_pane()
        if pane is None:
            return
        if pane.file_path is None:
            self.__save_file_as()
            return

        old_path = pane.file_path
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Rename", "New name:", text=os.path.basename(old_path))
        if not ok or name == "" or name == os.path.basename(old_path):
            return

        new_path = os.path.join(os.path.dirname(old_path), name)
        try:
            os.rename(old_path, new_path)
        except OSError:
            import traceback
            traceback.print_exc()
            return

        pane.file_path = new_path
        self.__update_tab_text(pane)
        self.__add_recent_file(new_path)
        self.__save_session()

    def __revert_file(self):
        pane = self.__current_pane()
        if pane is None or pane.file_path is None or not os.path.isfile(pane.file_path):
            return

        try:
            with open(pane.file_path, 'r', encoding='utf-8') as f:
                pane.editor.setPlainText(f.read())
        except:
            import traceback
            traceback.print_exc()
            return

        pane.editor.document().setModified(False)
        self.__update_tab_text(pane)

    def __default_dir(self):
        pane = self.__current_pane()
        if pane is None or pane.file_path is None:
            return ""
        return os.path.dirname(pane.file_path)

    # ---- recent files -----------------------------------------------------

    def __add_recent_file(self, file_path):
        if file_path in self.__recent_files:
            self.__recent_files.remove(file_path)
        self.__recent_files.insert(0, file_path)
        del self.__recent_files[self.MAX_RECENT_FILES:]

    def __rebuild_recent_menu(self):
        self.recent_menu.clear()
        for file_path in self.__recent_files:
            action = QtWidgets.QAction(file_path, self)
            action.triggered.connect(lambda checked=False, p=file_path: self.open_path(p))
            action.setEnabled(os.path.isfile(file_path))
            self.recent_menu.addAction(action)

        if len(self.__recent_files) > 0:
            self.recent_menu.addSeparator()
        clear_action = QtWidgets.QAction("Clear Recently Opened", self)
        clear_action.triggered.connect(self.__recent_files.clear)
        clear_action.setEnabled(len(self.__recent_files) > 0)
        self.recent_menu.addAction(clear_action)

    # ---- session ----------------------------------------------------------

    def __save_session(self):
        try:
            tabs = []
            for pane in self.__panes():
                modified = pane.editor.document().isModified()
                content = pane.editor.toPlainText() if (pane.file_path is None or modified) else None
                tabs.append({
                    "file_path": pane.file_path,
                    "content": content,
                    "modified": modified,
                })

            os.makedirs(self.CONFIG_DIR, exist_ok=True)
            with open(self.SESSION_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    "tabs": tabs,
                    "current": self.tabs.currentIndex(),
                    "recent": self.__recent_files,
                    "workspace": self.workspace.folders(),
                }, f)
        except:
            import traceback
            traceback.print_exc()

    def __restore_session(self):
        try:
            if not os.path.isfile(self.SESSION_FILE):
                return False
            with open(self.SESSION_FILE, 'r', encoding='utf-8') as f:
                session = json.load(f)

            self.__recent_files = [p for p in session.get("recent", [])
                                   if isinstance(p, str)][:self.MAX_RECENT_FILES]
            self.workspace.set_folders(session.get("workspace", []))

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

    def __undo(self):
        editor = self.__current_editor()
        if editor is not None:
            editor.undo()

    def __redo(self):
        editor = self.__current_editor()
        if editor is not None:
            editor.redo()

    def __go_to_position_in_current(self, line, col=0):
        editor = self.__current_editor()
        if editor is None:
            return

        block = editor.document().findBlockByNumber(line - 1)
        if not block.isValid():
            return
        cursor = QtGui.QTextCursor(block)
        cursor.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.MoveAnchor,
                            min(col, len(block.text())))
        editor.setTextCursor(cursor)
        editor.centerCursor()
        editor.setFocus()

    def __go_to_line(self):
        editor = self.__current_editor()
        if editor is None:
            return

        line, ok = QtWidgets.QInputDialog.getInt(
            self, "Go to Line", "Line:",
            editor.textCursor().blockNumber() + 1, 1, editor.blockCount())
        if ok:
            self.__go_to_position_in_current(line=line)

    def __find_in_all_tabs(self):
        self.find_bar.show_find(False)
        if self.find_bar.find_edit.text() != "":
            self.find_bar.search_all_tabs()

    def __find_in_files(self):
        self.find_bar.show_find(False)
        if self.find_bar.find_edit.text() != "":
            self.find_bar.search_in_files()

    def __activate_search_result(self, result):
        if result["kind"] == "tab":
            self.tabs.setCurrentIndex(result["tab"])
            pane = self.__current_pane()
            if pane is None:
                return
            editor = pane.editor
            cursor = QtGui.QTextCursor(editor.document())
            cursor.setPosition(result["start"])
            cursor.setPosition(result["end"], QtGui.QTextCursor.KeepAnchor)
            editor.setTextCursor(cursor)
            editor.centerCursor()
            editor.setFocus()
        else:
            self.open_path(result["path"])
            self.__go_to_position_in_current(line=result["line"], col=result["col"])

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

    def __execute_all(self):
        editor = self.__current_editor()
        if editor is not None:
            self.__run_code(editor.toPlainText())

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
