import re

from PySide2 import QtCore, QtGui, QtWidgets


def _format(color, bold=False, italic=False):
    fmt = QtGui.QTextCharFormat()
    fmt.setForeground(QtGui.QColor(color))
    if bold:
        fmt.setFontWeight(QtGui.QFont.Bold)
    if italic:
        fmt.setFontItalic(True)
    return fmt


class PythonHighlighter(QtGui.QSyntaxHighlighter):
    KEYWORDS = [
        "False", "None", "True", "and", "as", "assert", "async", "await",
        "break", "class", "continue", "def", "del", "elif", "else", "except",
        "finally", "for", "from", "global", "if", "import", "in", "is",
        "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
        "while", "with", "yield", "match", "case"
    ]

    BUILTINS = [
        "abs", "all", "any", "bool", "bytes", "callable", "chr", "dict",
        "dir", "enumerate", "eval", "exec", "filter", "float", "format",
        "getattr", "hasattr", "hash", "help", "hex", "id", "input", "int",
        "isinstance", "issubclass", "iter", "len", "list", "map", "max",
        "min", "next", "object", "open", "ord", "pow", "print", "property",
        "range", "repr", "reversed", "round", "set", "setattr", "sorted",
        "staticmethod", "classmethod", "str", "sum", "super", "tuple",
        "type", "vars", "zip", "__import__"
    ]

    # block states for unterminated triple-quoted strings
    STATE_NONE = 0
    STATE_TRIPLE_SINGLE = 1
    STATE_TRIPLE_DOUBLE = 2

    def __init__(self, document):
        super().__init__(document)

        self.format_keyword = _format("#cc7832", bold=True)
        self.format_builtin = _format("#8ab1d0")
        self.format_string = _format("#6a8759")
        self.format_comment = _format("#808080", italic=True)
        self.format_number = _format("#6897bb")
        self.format_decorator = _format("#bbb529")
        self.format_definition = _format("#ffc66b")
        self.format_self = _format("#94558d")

        self.rules = [
            (re.compile(r"\b(?:%s)\b" % "|".join(self.KEYWORDS)), self.format_keyword),
            (re.compile(r"\b(?:%s)\b" % "|".join(self.BUILTINS)), self.format_builtin),
            (re.compile(r"\b(?:self|cls)\b"), self.format_self),
            (re.compile(r"(?<=\bdef\s)\s*\w+|(?<=\bclass\s)\s*\w+"), self.format_definition),
            (re.compile(r"\b0[xX][0-9a-fA-F]+\b|\b0[oO][0-7]+\b|\b0[bB][01]+\b|"
                        r"\b\d+(?:\.\d*)?(?:[eE][+-]?\d+)?\b|\.\d+(?:[eE][+-]?\d+)?\b"), self.format_number),
            (re.compile(r"^\s*@\w+(?:\.\w+)*"), self.format_decorator),
        ]

    def highlightBlock(self, text):
        self.setCurrentBlockState(self.STATE_NONE)

        # spans occupied by strings or comments (other rules do not apply there)
        protected = []
        pos = 0

        state = self.previousBlockState()
        if state in (self.STATE_TRIPLE_SINGLE, self.STATE_TRIPLE_DOUBLE):
            delimiter = "'''" if state == self.STATE_TRIPLE_SINGLE else '"""'
            end = text.find(delimiter)
            if end == -1:
                self.setFormat(0, len(text), self.format_string)
                self.setCurrentBlockState(state)
                return
            self.setFormat(0, end + 3, self.format_string)
            protected.append((0, end + 3))
            pos = end + 3

        i = pos
        length = len(text)
        while i < length:
            c = text[i]
            if c == "#":
                self.setFormat(i, length - i, self.format_comment)
                protected.append((i, length))
                break
            elif text.startswith("'''", i) or text.startswith('"""', i):
                delimiter = text[i:i + 3]
                start = self._string_start(text, i)
                end = text.find(delimiter, i + 3)
                if end == -1:
                    self.setFormat(start, length - start, self.format_string)
                    protected.append((start, length))
                    self.setCurrentBlockState(
                        self.STATE_TRIPLE_SINGLE if delimiter == "'''" else self.STATE_TRIPLE_DOUBLE)
                    break
                self.setFormat(start, end + 3 - start, self.format_string)
                protected.append((start, end + 3))
                i = end + 3
            elif c in "'\"":
                start = self._string_start(text, i)
                end = self._find_string_end(text, i, c)
                self.setFormat(start, end - start, self.format_string)
                protected.append((start, end))
                i = end
            else:
                i += 1

        def is_protected(index):
            return any(s <= index < e for s, e in protected)

        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                if not is_protected(match.start()):
                    self.setFormat(match.start(), match.end() - match.start(), fmt)

    @staticmethod
    def _string_start(text, quote_index):
        # include string prefixes such as r"", f"", rb""
        start = quote_index
        while start > 0 and text[start - 1] in "rRbBuUfF":
            start -= 1
        return start

    @staticmethod
    def _find_string_end(text, quote_index, quote):
        i = quote_index + 1
        while i < len(text):
            if text[i] == "\\":
                i += 2
                continue
            if text[i] == quote:
                return i + 1
            i += 1
        return len(text)


class LineNumberArea(QtWidgets.QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QtCore.QSize(self.editor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        self.editor.lineNumberAreaPaintEvent(event)


class CodeEditor(QtWidgets.QPlainTextEdit):
    INDENT = "    "

    BRACKETS = {"(": ")", "[": "]", "{": "}"}
    QUOTES = "'\""
    MAX_WORD_HIGHLIGHTS = 200

    COLOR_BACKGROUND = QtGui.QColor("#2b2b2b")
    COLOR_TEXT = QtGui.QColor("#a9b7c6")
    COLOR_CURRENT_LINE = QtGui.QColor("#323232")
    COLOR_LINE_NUMBER_BACKGROUND = QtGui.QColor("#313335")
    COLOR_LINE_NUMBER = QtGui.QColor("#606366")
    COLOR_LINE_NUMBER_CURRENT = QtGui.QColor("#a4a3a3")
    COLOR_MATCHING_WORD = QtGui.QColor("#4e5254")
    COLOR_MATCHING_BRACE = QtGui.QColor("#36587f")
    COLOR_UNMATCHED_BRACE = QtGui.QColor("#6e2b28")
    COLOR_INDENT_GUIDE = QtGui.QColor(255, 255, 255, 25)

    def __init__(self, parent=None):
        super().__init__(parent)

        font = QtGui.QFont("Consolas")
        font.setStyleHint(QtGui.QFont.Monospace)
        font.setPointSize(10)
        self.setFont(font)

        self.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.setTabStopDistance(
            QtGui.QFontMetricsF(self.font()).horizontalAdvance(" ") * len(self.INDENT))

        palette = self.palette()
        palette.setColor(QtGui.QPalette.Base, self.COLOR_BACKGROUND)
        palette.setColor(QtGui.QPalette.Text, self.COLOR_TEXT)
        self.setPalette(palette)

        self.highlighter = PythonHighlighter(self.document())

        self.lineNumberArea = LineNumberArea(self)
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.updateExtraSelections)

        self._completer = QtWidgets.QCompleter(self)
        self._completer.setWidget(self)
        self._completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        self._completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self._completer_model = QtCore.QStringListModel(self._completer)
        self._completer.setModel(self._completer_model)
        self._completer.activated.connect(self._insert_completion)

        self.updateLineNumberAreaWidth(0)
        self.updateExtraSelections()

    # ---- line number area -------------------------------------------------

    def lineNumberAreaWidth(self):
        digits = max(2, len(str(self.blockCount())))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy != 0:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(
            QtCore.QRect(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height()))

    def lineNumberAreaPaintEvent(self, event):
        painter = QtGui.QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), self.COLOR_LINE_NUMBER_BACKGROUND)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        current_block = self.textCursor().blockNumber()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                if block_number == current_block:
                    painter.setPen(self.COLOR_LINE_NUMBER_CURRENT)
                else:
                    painter.setPen(self.COLOR_LINE_NUMBER)
                painter.drawText(0, top, self.lineNumberArea.width() - 6,
                                 self.fontMetrics().height(),
                                 QtCore.Qt.AlignRight, str(block_number + 1))

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    # ---- indent guides ----------------------------------------------------

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QtGui.QPainter(self.viewport())
        painter.setPen(self.COLOR_INDENT_GUIDE)

        space_width = self.fontMetrics().horizontalAdvance(" ")
        left = self.contentOffset().x() + self.document().documentMargin()

        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        previous_levels = 0

        while block.isValid() and top <= event.rect().bottom():
            bottom = top + round(self.blockBoundingRect(block).height())
            text = block.text()
            if text.strip() != "":
                indent = len(text) - len(text.lstrip(" "))
                levels = indent // len(self.INDENT)
                previous_levels = levels
            else:
                levels = previous_levels

            if block.isVisible() and bottom >= event.rect().top():
                for level in range(1, levels):
                    x = round(left + space_width * len(self.INDENT) * level)
                    painter.drawLine(x, top, x, bottom)

            block = block.next()
            top = bottom

    # ---- extra selections (current line / braces / matching words) --------

    def updateExtraSelections(self):
        selections = []

        if not self.isReadOnly():
            selection = QtWidgets.QTextEdit.ExtraSelection()
            selection.format.setBackground(self.COLOR_CURRENT_LINE)
            selection.format.setProperty(QtGui.QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            selections.append(selection)

        selections += self._matching_word_selections()
        selections += self._brace_selections()

        self.setExtraSelections(selections)
        self.lineNumberArea.update()

    def _make_range_selection(self, start, end, color):
        selection = QtWidgets.QTextEdit.ExtraSelection()
        selection.format.setBackground(color)
        cursor = QtGui.QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QtGui.QTextCursor.KeepAnchor)
        selection.cursor = cursor
        return selection

    def _matching_word_selections(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            word = cursor.selectedText()
        else:
            word_cursor = QtGui.QTextCursor(cursor)
            word_cursor.select(QtGui.QTextCursor.WordUnderCursor)
            word = word_cursor.selectedText()

        if len(word) < 2 or re.fullmatch(r"[A-Za-z_]\w*", word) is None:
            return []

        matches = re.finditer(r"\b%s\b" % re.escape(word), self.toPlainText())
        matches = [m for _, m in zip(range(self.MAX_WORD_HIGHLIGHTS + 1), matches)]
        if len(matches) < 2 or len(matches) > self.MAX_WORD_HIGHLIGHTS:
            return []

        return [self._make_range_selection(m.start(), m.end(), self.COLOR_MATCHING_WORD)
                for m in matches]

    def _brace_selections(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            return []

        text = self.toPlainText()
        pos = cursor.position()

        index = None
        if pos > 0 and text[pos - 1] in "()[]{}":
            index = pos - 1
        elif pos < len(text) and text[pos] in "()[]{}":
            index = pos
        if index is None:
            return []

        match = self._find_matching_brace(text, index)
        if match is None:
            return [self._make_range_selection(index, index + 1, self.COLOR_UNMATCHED_BRACE)]
        return [self._make_range_selection(index, index + 1, self.COLOR_MATCHING_BRACE),
                self._make_range_selection(match, match + 1, self.COLOR_MATCHING_BRACE)]

    @staticmethod
    def _find_matching_brace(text, index):
        char = text[index]
        pairs = {"(": ")", "[": "]", "{": "}", ")": "(", "]": "[", "}": "{"}
        other = pairs[char]
        step = 1 if char in "([{" else -1

        depth = 0
        i = index + step
        while 0 <= i < len(text):
            c = text[i]
            if c == char:
                depth += 1
            elif c == other:
                if depth == 0:
                    return i
                depth -= 1
            i += step
        return None

    # ---- key handling -----------------------------------------------------

    def keyPressEvent(self, event):
        if self._completer.popup().isVisible() and event.key() in (
                QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Tab,
                QtCore.Qt.Key_Backtab, QtCore.Qt.Key_Escape):
            event.ignore()
            return

        if not self._handle_editing_keys(event) and not self._handle_auto_close(event):
            super().keyPressEvent(event)

        self._update_completion(event)

    def _handle_editing_keys(self, event):
        key = event.key()
        modifiers = event.modifiers()

        if key == QtCore.Qt.Key_Tab and modifiers == QtCore.Qt.NoModifier:
            if self.textCursor().hasSelection():
                self._indent_selection()
            else:
                self._insert_indent()
            return True
        if key == QtCore.Qt.Key_Backtab:
            self._unindent_selection()
            return True
        if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and modifiers in (
                QtCore.Qt.NoModifier, QtCore.Qt.KeypadModifier):
            self._insert_newline_with_indent()
            return True
        if key == QtCore.Qt.Key_Backspace and modifiers == QtCore.Qt.NoModifier:
            if self._backspace_delete_pair():
                return True
            if self._backspace_unindent():
                return True
        if key == QtCore.Qt.Key_Slash and modifiers == QtCore.Qt.ControlModifier:
            self.toggle_comment()
            return True
        return False

    def _neighbor_chars(self):
        cursor = self.textCursor()
        text = cursor.block().text()
        column = cursor.positionInBlock()
        previous_char = text[column - 1] if column > 0 else ""
        next_char = text[column] if column < len(text) else ""
        return previous_char, next_char

    def _handle_auto_close(self, event):
        text = event.text()
        if text == "" or text not in "([{)]}\"'":
            return False

        cursor = self.textCursor()

        if cursor.hasSelection() and (text in self.BRACKETS or text in self.QUOTES):
            selected = cursor.selectedText()
            closing = self.BRACKETS.get(text, text)
            cursor.insertText(text + selected + closing)
            return True

        previous_char, next_char = self._neighbor_chars()

        if text in ")]}" or text in self.QUOTES:
            if next_char == text:
                cursor.movePosition(QtGui.QTextCursor.Right)
                self.setTextCursor(cursor)
                return True

        pair_allowed = next_char == "" or next_char in " \t)]},:;"

        if text in self.BRACKETS and pair_allowed:
            cursor.insertText(text + self.BRACKETS[text])
            cursor.movePosition(QtGui.QTextCursor.Left)
            self.setTextCursor(cursor)
            return True

        # do not pair when completing a triple quote
        if text in self.QUOTES and pair_allowed and previous_char != text:
            cursor.insertText(text + text)
            cursor.movePosition(QtGui.QTextCursor.Left)
            self.setTextCursor(cursor)
            return True

        return False

    def _backspace_delete_pair(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False

        previous_char, next_char = self._neighbor_chars()
        is_pair = (self.BRACKETS.get(previous_char) == next_char or
                   (previous_char in self.QUOTES and previous_char == next_char))
        if not is_pair:
            return False

        cursor.movePosition(QtGui.QTextCursor.Left)
        cursor.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.KeepAnchor, 2)
        cursor.removeSelectedText()
        return True

    def _selected_blocks(self):
        cursor = self.textCursor()
        document = self.document()
        start_block = document.findBlock(cursor.selectionStart())
        end_position = cursor.selectionEnd()
        end_block = document.findBlock(end_position)
        # a selection ending at the very start of a line does not include that line
        if cursor.hasSelection() and end_block.position() == end_position \
                and end_block.blockNumber() > start_block.blockNumber():
            end_block = end_block.previous()
        return start_block, end_block

    def _insert_indent(self):
        cursor = self.textCursor()
        column = cursor.positionInBlock()
        count = len(self.INDENT) - (column % len(self.INDENT))
        cursor.insertText(" " * count)

    def _insert_newline_with_indent(self):
        cursor = self.textCursor()
        text_before = cursor.block().text()[:cursor.positionInBlock()]
        indent = re.match(r"[ \t]*", text_before).group(0)
        if text_before.rstrip().endswith(":"):
            indent += self.INDENT
        cursor.insertText("\n" + indent)
        self.ensureCursorVisible()

    def _backspace_unindent(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            return False

        column = cursor.positionInBlock()
        text_before = cursor.block().text()[:column]
        if column == 0 or text_before.strip() != "" or "\t" in text_before:
            return False

        count = column % len(self.INDENT)
        if count == 0:
            count = len(self.INDENT)
        cursor.movePosition(QtGui.QTextCursor.Left, QtGui.QTextCursor.KeepAnchor, count)
        cursor.removeSelectedText()
        return True

    def _indent_selection(self):
        start_block, end_block = self._selected_blocks()
        cursor = self.textCursor()
        cursor.beginEditBlock()
        block = start_block
        while True:
            if block.text() != "":
                block_cursor = QtGui.QTextCursor(block)
                block_cursor.insertText(self.INDENT)
            if block == end_block:
                break
            block = block.next()
        cursor.endEditBlock()

    def _unindent_selection(self):
        start_block, end_block = self._selected_blocks()
        cursor = self.textCursor()
        cursor.beginEditBlock()
        block = start_block
        while True:
            text = block.text()
            count = 0
            while count < len(self.INDENT) and count < len(text) and text[count] == " ":
                count += 1
            if count == 0 and text.startswith("\t"):
                count = 1
            if count > 0:
                block_cursor = QtGui.QTextCursor(block)
                block_cursor.movePosition(QtGui.QTextCursor.Right,
                                          QtGui.QTextCursor.KeepAnchor, count)
                block_cursor.removeSelectedText()
            if block == end_block:
                break
            block = block.next()
        cursor.endEditBlock()

    def toggle_comment(self):
        start_block, end_block = self._selected_blocks()

        # comment out only when there is a non-empty line not yet commented
        add_comment = False
        block = start_block
        while True:
            text = block.text()
            if text.strip() != "" and not text.lstrip().startswith("#"):
                add_comment = True
                break
            if block == end_block:
                break
            block = block.next()

        cursor = self.textCursor()
        cursor.beginEditBlock()
        block = start_block
        while True:
            text = block.text()
            block_cursor = QtGui.QTextCursor(block)
            if add_comment:
                if text.strip() != "":
                    block_cursor.insertText("# ")
            else:
                stripped = text.lstrip()
                if stripped.startswith("#"):
                    indent_len = len(text) - len(stripped)
                    remove = 2 if stripped.startswith("# ") else 1
                    block_cursor.movePosition(QtGui.QTextCursor.Right,
                                              QtGui.QTextCursor.MoveAnchor, indent_len)
                    block_cursor.movePosition(QtGui.QTextCursor.Right,
                                              QtGui.QTextCursor.KeepAnchor, remove)
                    block_cursor.removeSelectedText()
            if block == end_block:
                break
            block = block.next()
        cursor.endEditBlock()

    # ---- auto-complete ----------------------------------------------------

    def _completion_prefix(self):
        cursor = self.textCursor()
        text_before = cursor.block().text()[:cursor.positionInBlock()]
        match = re.search(r"[A-Za-z_]\w*$", text_before)
        return "" if match is None else match.group(0)

    def _update_completion(self, event):
        popup = self._completer.popup()
        prefix = self._completion_prefix()

        if event.text() == "" or len(prefix) < 2:
            popup.hide()
            return

        words = set(PythonHighlighter.KEYWORDS) | set(PythonHighlighter.BUILTINS)
        words |= set(re.findall(r"[A-Za-z_]\w{2,}", self.toPlainText()))
        words.discard(prefix)
        self._completer_model.setStringList(sorted(words))

        self._completer.setCompletionPrefix(prefix)
        if self._completer.completionCount() == 0:
            popup.hide()
            return

        popup.setCurrentIndex(self._completer.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width())
        self._completer.complete(rect)

    def _insert_completion(self, completion):
        cursor = self.textCursor()
        prefix = self._completion_prefix()
        if prefix != "":
            cursor.movePosition(QtGui.QTextCursor.Left, QtGui.QTextCursor.KeepAnchor, len(prefix))
        cursor.insertText(completion)
        self.setTextCursor(cursor)
