# ぽえなび（PoENavi）

Path of Exile 1 / Path of Exile 2向けの、Windows用レベリング支援ツールです。

`Client.txt`から現在地や進行状況を検知し、攻略ガイド、マップ画像、RTAタイマーなどを表示します。PoE1では、日本語版アイテムの価格検索を行う「ぽえとれ」も利用できます。

> [!IMPORTANT]
> 本ツールはGrinding Gear Gamesとは提携しておらず、同社による公認・承認を受けたものではありません。

## 主な機能

- PoE1 / PoE2のエリア移動・レベルアップ・Act進行を自動検知
- 攻略ガイド、マップ画像、経験値効率の目安を表示
- 自動ラップ対応のRTAタイマー
- 小型オーバーレイ「みになび」（PoE1）
- PoBからのジェム取得リスト作成（PoE1）
- 日本語アイテム価格検索「ぽえとれ」（PoE1）
- Map Modチェック、検索プリセット、メモ、Cheat sheets
- 自動アップデート

詳しい機能説明と画像付きの使い方は、以下の記事へまとめています。

- [ぽえなびの使い方を解説](https://note.com/buri8857/n/nd1e6a07b8a29)
- ぽえとれの詳しい使い方：準備中

## ダウンロード

1. [Releases](../../releases)から最新版の`PoENavi.zip`をダウンロード
2. ZIPを右クリックし、Windows標準の「すべて展開」で解凍
3. 解凍先の`PoENavi.exe`を起動

Pythonのインストールは不要です。設定やメモは`%APPDATA%\PoENavi\`へ保存されるため、アプリを更新しても引き継がれます。

> [!WARNING]
> 現在の配布版はコード署名証明書を使用していません。また、PyInstaller製アプリの内部構造や利用実績などにより、SmartScreenの警告や一部のウイルス対策ソフトによる誤検知が発生する場合があります。
>
> SmartScreenが表示された場合は、発行元とダウンロード元がこのリポジトリであることを確認したうえで、「詳細情報」から実行できます。不安な場合は実行せず、公開ソースから直接起動してください。

## 最初に行う設定

1. 起動時に「ぽえなび」または「ぽえとれ」を選択
2. ぽえなびではPoE1 / PoE2を選択
3. 設定画面で`Client.txt`の場所を確認
4. PoE側のチャット設定で「ローカル」を有効化

`Client.txt`は一般的に次の場所にあります。通常は自動検出されます。

```text
PoE1 Steam: C:\Program Files (x86)\Steam\steamapps\common\Path of Exile\logs\Client.txt
PoE2 Steam: C:\Program Files (x86)\Steam\steamapps\common\Path of Exile 2\logs\Client.txt
```

## 対応環境・制約

- 正式対応：Windows 10 / 11
- 対応ゲーム：Path of Exile 1 / Path of Exile 2
- ぽえとれ、みになび、PoBインポート：PoE1のみ
- Linux：非公式サポート。一部のWindows依存機能は動作保証外
- PoEのローカルチャットログが無効だと、一部の自動ラップやガイド切替を検知できません

## 安全性と外部通信

PoENaviはゲームとは独立して動作し、処理内容をこのリポジトリで公開しています。

### PC内で読み取る情報

- PoEの`Client.txt`：エリア、レベル、Act進行の検知
- ユーザーがコピーしたアイテム情報：ぽえとれの価格検索
- PoEウィンドウの位置とプロセス名：対象ウィンドウの識別

設定、メモ、タイマー記録、価格キャッシュなどはPC内へ保存します。`Client.txt`の内容や個人メモを外部へ送信することはありません。

### 行わないこと

- ゲームメモリの読み取り・書き換え
- ゲームプロセスへのコード注入
- ゲームクライアントやゲームファイルの改変
- ネットワークパケットの傍受・改ざん
- 自律的な戦闘・移動・アイテム操作
- PoEアカウントの認証情報やセッション情報の収集

### 外部通信先

- GitHub Releases：アップデート確認・取得
- Path of Exile公式Trade API：アイテム名、MOD、数値などの検索条件を送信
- poe.ninja：通貨・アイテムの参考価格取得
- Path of Exile公式CDNなど：アイテム画像取得
- PoELab：ユーザー操作時にWebページを開く

ユーザー操作を起点に、検索文字列やチャットコマンドなどのキー入力をPoEへ送る機能があります。ログアウト機能を有効にしてホットキーを押した場合は、PoEクライアントのTCP接続を切断します。

## アップデート

起動時にGitHub Releasesの安定版を確認します。「今すぐアップデート」を選ぶと、ZIPのダウンロードとSHA-256検証を行い、ファイル更新後にPoENaviを再起動します。

手動確認は、設定画面の「アプリ情報 → アップデートを確認」から行えます。

## 不具合報告・要望

[GitHub Issues](../../issues)へ、次の情報を添えて報告してください。

- PoENaviのバージョン
- PoE1 / PoE2と、ぽえなび / ぽえとれのどちらか
- 再現手順と期待した動作
- エラーメッセージやスクリーンショット

個人情報、PoEの認証情報、APIキーなどは掲載しないでください。

## ソースから起動

```bash
git clone https://github.com/buri34/poenavi.git
cd poenavi
pip install -r requirements.txt
python main.py
```

テストは次のコマンドで実行できます。

```bash
python -m pytest -q
```

## 技術構成

- Python 3.12+
- PySide6（Qt 6）
- pynput / keyboard
- urllib3
- PyInstaller

## License・免責・Credits

- [MIT License](LICENSE)
- [第三者ライセンス・データ出典](THIRD_PARTY_NOTICES.md)
- [Path of Exile](https://www.pathofexile.com/) by Grinding Gear Games
- Built with ❤️ by [Buri](https://github.com/buri34)

Path of Exile、ゲーム内名称、アイテムおよび関連ゲームデータの権利はGrinding Gear Gamesに帰属します。

## サポート

ぽえなびを気に入っていただけたら、開発環境の維持・改善を応援していただけると嬉しいです。

- [OFUSE（おふせ）](https://ofuse.me/48eca107)
- [Ko-fi](https://ko-fi.com/buri8857)
- [Patreon](https://www.patreon.com/cw/Buri8857)
