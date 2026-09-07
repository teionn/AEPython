# AE Python
After Effects 内部用 Python プラグイン

***Read this document in other languages: [English](./README.md)***

## 特徴
* After Effect 上のデータを Python スクリプトで直接編集
* After Effects 標準スクリプト（ExtendScript, JavaScript）と同名のクラス・関数を利用可能
  * クラス・関数リファレンス： https://ae-scripting.docsforadobe.dev/introduction/overview.html
* Javascript <--> Python の相互連携
* Qt ([PySide2](https://pypi.org/project/PySide2/)) による GUI開発
* コードエディター標準搭載（シンタックスハイライト・行番号・オートインデント）

## 動作環境
* Adobe After Effects CS6 / CC~
* Windows 10 / 11
* [Python 3.10.9](https://www.python.org/downloads/release/python-3109/) （配布 Zip に同梱）

## インストール
配布 Zip 内の各項目をそれぞれ下記の場所にコピー
* AEPython フォルダ -> C:\Program Files\Adobe\Adobe After Effects {バージョン}\Support Files\Plug-ins\AEPython
* AEPython.jsx -> C:\Program Files\Adobe\Adobe After Effects {バージョン}\Support Files\Scripts\Startup\AEPython.jsx

## ライセンス
MITライセンス（[LICENSE](./LICENSE) を参照）

## スクリプティングガイド

### Python Window から Python スクリプトを実行
Window メニュー -> Python を選択

Code 欄は PySide 製のコードエディターになっており、以下の機能を利用できます。
* Python と JSX（ExtendScript）の両対応：タブごとに言語を持ち、.jsx / .js を開くと自動判定。File -> New JSX Tab（Ctrl+Shift+N）で JSX タブを作成し、同じショートカットでそのまま実行（結果は Output に表示）。File -> Execute JSX File で .jsx ファイルを直接実行
* マルチドキュメントタブ（並べ替え・Ctrl+W で閉じる・Ctrl+Tab でタブ切り替え）
* Python / JSX シンタックスハイライト（コメントトグルやオートインデントも言語に応じて動作）
* 行番号表示・現在行ハイライト・インデントガイド
* 対応括弧のハイライト・カーソル下の単語と同じ単語のハイライト
* 括弧・クォートの自動補完
* オートコンプリート（キーワード・組み込み関数・スクリプト内の単語）
* オートインデント（`:` の後で自動的に字下げ）
* Tab / Shift+Tab で選択行の一括インデント / インデント解除
* Ctrl+/ でコメントアウトの切り替え
* 行操作：行の複製（Ctrl+D）・削除（Ctrl+Shift+K）・上下移動（Alt+Up / Alt+Down）・行選択（Ctrl+L）・行結合（Ctrl+J）
* 検索・置換（Ctrl+F / Ctrl+H、F3 で次を検索）・指定行へ移動（Ctrl+G）・シンボルへ移動（Ctrl+Shift+O）
* Ctrl+Enter でコード（選択中は選択範囲のみ）を実行、Ctrl+Shift+Enter で全体を実行、Ctrl+Alt+Enter で現在行を実行
* コードチェック：入力を止めると自動で構文エラーと静的解析（pyflakes）の結果を波線と問題リストに表示
* コードアウトライン：class / def のツリー表示（View メニュー、クリックでジャンプ）
* 分割表示：同じスクリプトを 2 画面で編集（View -> Split Editor、Ctrl+Alt+S。Split Side by Side で左右分割）
* ワークスペース：フォルダーをツリー表示し、ダブルクリックで .py を開くサイドパネル（View メニュー）
* 全タブ検索（Ctrl+Shift+F）・ワークスペース内ファイル検索（Edit -> Find in Files）、結果クリックでジャンプ
* 空白文字の表示切り替え・折り返し表示（Word Wrap）・フォントサイズ変更（Ctrl+= / Ctrl+- / Ctrl+0）
* ステータスバーにカーソル位置とエラー / 警告数を表示
* Output メニュー：出力のクリア、出力のログファイル書き出し、`settings.json` によるカスタムハイライト
* 実行時オートセーブ：実行のたびにタブの内容をセッションとして保存し、次回起動時に復元（未保存のコードも失われません）
* File メニューから .py ファイルの New / Open（Open Recent）/ Save / Save As / Save All / Rename / Revert
* カスタマイズ：`%APPDATA%/AEPython/settings.json` でフォント・インデント幅・配色・ショートカット・出力ハイライトを変更可能

```Python
comp = ae.app.project.items.addComp("Comp1", 1920, 1080, 1, 10, 24)
comp.bgColor = [1.0, 1.0, 1.0]

text_layer = comp.layers.addText("This is an AE Python sample.")

text_prop = text_layer.property("Source Text")
text_document = text_prop.value
text_document.fontSize = 50
text_prop.setValue(text_document)
```

### Python Window から .py ファイルを実行
AEPython ウインドウの File -> Execute Python File から .py ファイルを選択

[sample.py]
```Python
import AEPython as ae
ae.alert(ae.app.project.file)
```

### ExtendScript から Python スクリプトを実行
```JavaScript
Python.exec("ae.app.project.activeItem.name = 'New Name'");
```

### ExtendScript から .py ファイルを実行
```JavaScript
Python.execFile("D:/sample.py");
```

### Qt で GUI を作成
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