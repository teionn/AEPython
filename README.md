# AE Python
Python scripting plugin for After Effects

***Read this document in other languages: [Japanese](./README_ja.md)***

## Features
* Directly edit data on After Effects with Python scripts
* Enabled to use classes and functions with the same names as After Effects default scripts (ExtendScript, JavaScript) 
  * Class and function reference: https://ae-scripting.docsforadobe.dev/introduction/overview.html
* Interoperation between Javascript and Python
* GUI development by Qt ([PySide2](https://pypi.org/project/PySide2/))
* Built-in code editor (syntax highlighting, line numbers, auto indent)

## System Requirements
* Adobe After Effects CS6 / CC~
* Windows 10 / 11
* [Python 3.10.9](https://www.python.org/downloads/release/python-3109/) (included in the distribution Zip)

## Installation
Copy each files and folders in the distribution Zip to the following locations.
* AEPython folder -> C:\Program Files\Adobe\Adobe After Effects {version}\Support Files\Plug-ins\AEPython
* AEPython.jsx -> C:\Program Files\Adobe\Adobe After Effects {version}\Support Files\Scripts\Startup\AEPython.jsx

## License
MIT License (see [LICENSE](./LICENSE).)

## Scripting Guide

### Run Python scripts from the Python Window
Select menu: Window -> Python

The Code area is a PySide-based code editor with the following features:
* Multi-document tabs (movable, Ctrl+W to close)
* Python syntax highlighting
* Line numbers, current line highlighting and indent guides
* Matching brace highlighting and matching word highlighting
* Automatic closing brace / quote insertion
* Auto-complete (keywords, builtins and words in the script)
* Auto indent (automatically indents after `:`)
* Tab / Shift+Tab to indent / unindent selected lines
* Ctrl+/ to toggle comments
* Find and replace (Ctrl+F / Ctrl+H, F3 for find next), go to line (Ctrl+G)
* Ctrl+Enter to execute the code (only the selection when there is one), Ctrl+Shift+Enter to execute the current line
* Code check: syntax errors and static analysis results (pyflakes) are shown automatically as wavy underlines and a problems list when you stop typing
* Code outline: class / def tree view (View menu, click to jump)
* Split-screen editing of the same script (View -> Split Editor, Ctrl+Alt+S)
* Search across all open tabs (Ctrl+Shift+F, click a result to jump)
* Show whitespace toggle (View -> Show Whitespace)
* Auto-save on execute: tab contents are saved as a session on every execution and restored on the next startup, so unsaved code is never lost
* Customization: change fonts, indent width, colors and shortcuts in `%APPDATA%/AEPython/settings.json`

```Python
comp = ae.app.project.items.addComp("Comp1", 1920, 1080, 1, 10, 24)
comp.bgColor = [1.0, 1.0, 1.0]

text_layer = comp.layers.addText("This is an AE Python sample.")

text_prop = text_layer.property("Source Text")
text_document = text_prop.value
text_document.fontSize = 50
text_prop.setValue(text_document)
```

### Run .py files from the Python Window
Select .py file from File -> "Execute Python File" in the AEPython window.

[sample.py]
```Python
import AEPython as ae
ae.alert(ae.app.project.file)
```

### Run Python scripts from ExtendScript
```JavaScript
Python.exec("ae.app.project.activeItem.name = 'New Name'");
```

### Run .py files from ExtendScript
```JavaScript
Python.execFile("D:/sample.py");
```

### GUI by Qt
```Python 
from PySide2 import QtWidgets

import AEPython as ae
import qtae

class MyDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout()

        self.text_input = QtWidgets.QLineEdit("")
        layout.addWidget(self.text_input)

        self.button = QtWidgets.QPushButton("Add Text Layer!")
        self.button.clicked.connect(self.onButtonClicked)
        layout.addWidget(self.button)

        self.setLayout(layout)

    def onButtonClicked(self):
        text = self.text_input.text()
        layer = ae.app.project.activeItem.layers.addText(text)
        layer.position.setValue([100,100])

dialog = MyDialog(qtae.GetQtAEMainWindow())
dialog.show()
```