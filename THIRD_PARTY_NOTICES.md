# Third-party notices

PoENavi「ぽえとれ」は無料の非公式コミュニティツールであり、Grinding Gear Gamesとの
提携・承認関係はありません。Path of Exile、ゲーム内名称、アイテムおよび関連ゲーム
データの権利はGrinding Gear Gamesに帰属します。

## Awakened PoE Trade

ぽえとれの設計・UI・検索ロジックの検討、およびModの共通参照・検索メタデータ生成時に、
Awakened PoE Tradeの公開仕様・ソースコード・データを参照しています。ぽえとれは日本語版
Path of Exile向けに独自実装しています。

MIT License — Copyright (c) 2020 Alexander Drozdov

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

<https://github.com/SnosMe/awakened-poe-trade>

## Exiled Exchange 2

ぽえとれPoE2モードのParser fixture、カテゴリ、検索クエリ境界の検討、および
Related Items台帳（`item-drop.json`）に、Exiled Exchange 2の公開ソースコードとデータを参照しています。PoENavi側は
公式Trade2 APIと固定fixtureで検証し、Pythonで独立実装しています。

MIT License — Copyright (c) 2020 Alexander Drozdov

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

<https://github.com/Kvan7/Exiled-Exchange-2>

## RePoE

Tier、付与条件、ローカルstat情報の派生インデックス生成時にRePoEを参照します。RePoEの
全データはアプリへ同梱しません。

MIT License — Copyright (c) 2016 brather1ng

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

RePoEの生成データはGrinding Gear Gamesが権利を保有し、同社の利用規約に従います。

<https://github.com/repoe-fork/repoe>

## Packaged open-source runtime components

PoENavi's Windows distribution is created with PyInstaller and includes upstream runtime libraries. These upstream binaries are not developed or represented as PoENavi project binaries.

- **Python 3.12** — Python Software Foundation License Version 2
  - <https://docs.python.org/3/license.html>
- **PySide6 / Shiboken6 / Qt 6** — GNU Lesser General Public License v3, GNU General Public License v2, or GNU General Public License v3, as offered by the respective packages
  - <https://www.qt.io/licensing/open-source-lgpl-obligations>
  - <https://code.qt.io/cgit/pyside/pyside-setup.git/tree/LICENSES>
- **pynput** — GNU Lesser General Public License v3
  - <https://github.com/moses-palmer/pynput>
- **urllib3** — MIT License
  - <https://github.com/urllib3/urllib3>
- **PyInstaller bootloader** — GNU General Public License v2 or later with the PyInstaller bootloader exception
  - <https://pyinstaller.org/en/stable/license.html>
- **OpenSSL runtime libraries** — Apache License 2.0
  - <https://www.openssl.org/source/license.html>

Exact versions used for an official release are pinned in `requirements.txt` and `requirements-build.txt`, and are recorded in the public GitHub Actions build log.
