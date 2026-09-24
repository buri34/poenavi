# ぽえなび（PoENavi）

Path of Exile 1 / Path of Exile 2向けの、Windows用プレイ支援ツールです。

攻略・レベリングを支援する「ぽえなび」と、日本語アイテムの価格検索・取引検索を支援する「ぽえとれ」を、起動時に選択して利用できます。

> [!IMPORTANT]
> 本ツールはGrinding Gear Gamesとは提携しておらず、同社による公認・承認を受けたものではありません。

## ぽえなびの主な機能

- PoE1 / PoE2のエリア移動・レベルアップ・Act進行を自動検知
- 攻略ガイド、マップ画像、経験値効率の目安を表示
- 自動ラップ対応のRTAタイマー
- 小型オーバーレイ「みになび」（PoE1 / PoE2）
- VOICEVOXによるみになびの音声案内（PoE2）
- PoBからのジェム取得リスト作成（PoE1）
- エリアメモ、ガイド編集、切り離し可能な補助パネル

## ぽえとれの主な機能

- 日本語版でコピーしたアイテムを解析し、公式Trade APIで検索（PoE1 / PoE2）
- MOD・数値範囲・アイテム状態・検索プリセットを画面上で調整
- 価格一覧、価格推移、関連アイテムの参考価格を表示
- 操作モードとAUTO-HIDEに対応した変更可能な検索ホットキー
- Map Modチェック、メモ、画像管理、Cheat sheets
- OBS配信用の専用検索結果ウィンドウ
- PoE2のエクスペディション報酬を読み取り、poe.ninja価格を高貴なオーブ換算で表示

## 共通機能

- PoE1 / PoE2と、ぽえなび / ぽえとれの起動モードを選択
- タスクトレイへの格納と復帰
- 自動アップデート

詳しい機能説明と画像付きの使い方は、以下の記事へまとめています。

- [ぽえなびの使い方を解説](https://note.com/buri8857/n/nd1e6a07b8a29)
- [ぽえとれの使い方を解説](https://note.com/buri8857/n/n8a5047edab08)

## ダウンロード

1. [Releases](../../releases)から最新版の`PoENavi.zip`をダウンロード
2. ZIPを右クリックし、Windows標準の「すべて展開」で解凍
3. 解凍先の`PoENavi.exe`を起動

Pythonのインストールは不要です。設定やメモは`%APPDATA%\PoENavi\`へ保存されるため、アプリを更新しても引き継がれます。

> [!WARNING]
> 現在の配布版はコード署名証明書を使用していません。また、PyInstaller製アプリの内部構造や利用実績などにより、SmartScreenの警告や一部のウイルス対策ソフトによる誤検知が発生する場合があります。
>
> SmartScreenが表示された場合は、発行元とダウンロード元がこのリポジトリであることを確認したうえで、「詳細情報」から実行できます。不安な場合は実行せず、公開ソースから直接起動してください。

### コード署名

Free code signing provided by [SignPath.io](https://signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).

PoENaviは、今後のWindows向けリリースを署名するためSignPath Foundationのオープンソース向けコード署名プログラムへ申請しています。審査・導入が完了するまで、現在の配布版は未署名です。

## 最初に行う設定

1. 起動時にPoE1 / PoE2を選択
2. 「ぽえなび」または「ぽえとれ」を選択
3. ぽえなびを使う場合は、設定画面で`Client.txt`の場所を確認
4. ぽえなびを使う場合は、PoE側のチャット設定で「ローカル」を有効化

ぽえとれは、ゲーム内でアイテム情報をコピーして検索ホットキーを押すと利用できます。PoE2のエクスペディション報酬価格チェックは初期状態では無効です。ぽえとれ上部の専用ボタンから有効化し、環境に合わせて読取範囲を指定してください。

`Client.txt`は一般的に次の場所にあります。通常は自動検出されます。

```text
PoE1 Steam: C:\Program Files (x86)\Steam\steamapps\common\Path of Exile\logs\Client.txt
PoE2 Steam: C:\Program Files (x86)\Steam\steamapps\common\Path of Exile 2\logs\Client.txt
```

## 対応環境・制約

- 正式対応：Windows 10 / 11
- 対応ゲーム：Path of Exile 1 / Path of Exile 2
- ぽえとれ：PoE1 / PoE2
- PoBインポート：PoE1のみ
- VOICEVOX読み上げ：PoE2のみ（VOICEVOX本体の起動が必要）
- エクスペディション報酬価格チェック：PoE2版ぽえとれ・Windows 10 / 11のみ
- Linux：非公式サポート。一部のWindows依存機能は動作保証外
- PoEのローカルチャットログが無効だと、一部の自動ラップやガイド切替を検知できません

## 安全性と外部通信

PoENaviはゲームとは独立して動作し、処理内容をこのリポジトリで公開しています。

### PC内で読み取る情報

- PoEの`Client.txt`：エリア、レベル、Act進行の検知
- ユーザーがコピーしたアイテム情報：ぽえとれの価格検索
- PoEウィンドウの位置とプロセス名：対象ウィンドウの識別
- ユーザーが指定したPoE2画面範囲の画像：エクスペディション報酬とアビス冒涜ModのローカルOCR

設定、メモ、タイマー記録、価格キャッシュ、OCR用画像処理はPC内で扱います。`Client.txt`の内容、個人メモ、キャプチャ画像を外部へ送信することはありません。

### 行わないこと

- ゲームメモリの読み取り・書き換え
- ゲームプロセスへのコード注入
- ゲームクライアントやゲームファイルの改変
- ネットワークパケットの傍受・改ざん
- 自律的な戦闘・移動・アイテム操作
- PoEアカウントの認証情報やセッション情報の収集

### OCRを使用する画面読取機能

PoE2の「エクスペディション報酬価格チェック」と「アビス冒涜Modティアチェック」は、ユーザーが設定したホットキーを押した時だけ実行されます。

処理の流れは次のとおりです。

1. OSの画面キャプチャ機能で、ユーザーが指定したPoE画面の範囲を取得
2. Windows OCRを使ってPC内で文字を解析
   - アビス冒涜Modで、Windows OCRが本文を安定して認識したものの数字だけ欠落した場合に限り、同梱のNDLOCR-Liteでその行を再確認
3. 解析結果をPoENaviの独立したウィンドウとして表示

これらのOCR機能は、ゲームメモリやゲームファイルを読み取らず、ゲームプロセスへのコード注入も行いません。また、OCR結果を使った自動クリック、キー入力、Mod選択などのゲーム操作は行いません。

キャプチャ画像やOCRで読み取った文章は外部へ送信されません。エクスペディション報酬の参考価格はpoe.ninjaから取得し、アビス冒涜ModのTier判定にはPoENaviへ同梱したローカルデータを使用します。

Grinding Gear GamesのDeveloper Policyでは、ゲームとは独立して動作する実行アプリは「推奨はしないが許可する」とされる一方、ゲームクライアント、メモリ、ゲームファイルへの介入や、画面認識を起点とした自動操作は禁止されています。

PoENaviのOCR機能は、この方針を考慮して「ユーザーによる手動実行・画面の読取専用・ローカル解析・独立ウィンドウへの表示」という設計にしています。

この説明はGrinding Gear Gamesによる個別の承認を意味するものではありません。最新の方針は公式Developer Policyをご確認ください。

- [Path of Exile Developer Policy](https://www.pathofexile.com/developer/docs/index#policy)
- [Path of Exile Terms of Use](https://www.pathofexile.com/legal/terms-of-use-and-privacy-policy)

### 外部通信先

- GitHub Releases：アップデート確認・取得
- Path of Exile公式Trade API：アイテム名、MOD、数値などの検索条件を送信
- poe.ninja：通貨・アイテムの参考価格取得
- Path of Exile公式CDNなど：アイテム画像取得

ユーザー操作を起点に、検索文字列やチャットコマンドなどのキー入力をPoEへ送る機能があります。ログアウト機能を有効にしてホットキーを押した場合は、PoEクライアントのTCP接続を切断します。

## Safety and External Communications (English)

PoENavi runs independently from the game, and its source code is publicly available in this repository.

### Information Read Locally

- PoE's `Client.txt`: used to detect areas, levels, and Act progression
- Item information copied by the user: used for trade searches in Poetore
- The PoE window position and process name: used to identify the target window
- Images of PoE2 screen regions selected by the user: used for local OCR of Expedition rewards and Abyss Desecration modifiers

Settings, notes, timer records, price caches, screenshots, and OCR processing remain on the user's PC. The contents of `Client.txt`, personal notes, captured images, and OCR text are not uploaded.

### What PoENavi Does Not Do

- Read or modify game memory
- Inject code into the game process
- Modify the game client or game files
- Intercept or alter network packets
- Automate combat, movement, or item interaction
- Collect PoE account credentials or session information

### OCR-Based Screen Reading

The PoE2 Expedition reward price checker and Abyss Desecration modifier Tier checker run only when the user presses the configured shortcut.

1. A user-configured region of the PoE screen is captured through the operating system's screen-capture API.
2. Text is recognized locally using Windows OCR.
   - For an Abyss Desecration modifier only, if Windows OCR has a stable body but is missing a number, the bundled NDLOCR-Lite rechecks that row locally.
3. The result is shown in a separate PoENavi window.

These OCR features do not read game memory or files, inject code, or interact with the game process. OCR results are never used to click, press keys, select modifiers, or perform any other in-game action automatically.

Captured images and recognized text are not sent to an external server. Expedition reference prices are obtained from poe.ninja, while Abyss Desecration modifier Tiers are determined using data bundled with PoENavi.

PoENavi's OCR features are designed with the Path of Exile Developer Policy in mind: they are manually initiated, read-only, processed locally, and displayed in a separate application window. This statement does not mean that PoENavi has been individually reviewed, endorsed, or approved by Grinding Gear Games. Please refer to the current official policies:

- [Path of Exile Developer Policy](https://www.pathofexile.com/developer/docs/index#policy)
- [Path of Exile Terms of Use](https://www.pathofexile.com/legal/terms-of-use-and-privacy-policy)

### External Connections

- GitHub Releases: checking for and downloading updates
- Official Path of Exile Trade API: submitting item names, modifiers, values, and other search conditions
- poe.ninja: obtaining reference prices for currencies and items
- Official Path of Exile CDN and related services: downloading item images

Some non-OCR features can send search text or chat commands to PoE, but only in response to an explicit user action. OCR results never initiate keyboard or mouse input to the game. When the logout feature is enabled and its shortcut is pressed, PoENavi disconnects the PoE client's TCP connection.

## アップデート

起動時にGitHub Releasesの安定版を確認します。「今すぐアップデート」を選ぶと、ZIPのダウンロードとSHA-256検証を行い、ファイル更新後にPoENaviを再起動します。

手動確認は、設定画面の「アプリ情報 → アップデートを確認」から行えます。

## アンインストール

PoENaviはインストーラーやWindowsサービスを使用しません。アンインストールするには、PoENaviを終了して、展開した`PoENavi`フォルダを削除してください。

設定、メモ、タイマー記録なども削除する場合は、`%APPDATA%\PoENavi\`を削除してください。必要な記録がある場合は、先にバックアップしてください。

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
- pynput / Windows API
- urllib3
- Windows OCR（PoE2エクスペディション報酬読取）
- NDLOCR-Lite 1.3.1（PoE2アビス冒涜Modの数字欠落時のみ補助）
- PyInstaller

## License・免責・Credits

- [MIT License](LICENSE)
- [第三者ライセンス・データ出典](THIRD_PARTY_NOTICES.md)
- [Privacy policy](PRIVACY.md)
- [Code signing policy](docs/CODE_SIGNING_POLICY.md)
- [Path of Exile](https://www.pathofexile.com/) by Grinding Gear Games
- Built with ❤️ by [Buri](https://github.com/buri34)

Path of Exile、ゲーム内名称、アイテムおよび関連ゲームデータの権利はGrinding Gear Gamesに帰属します。

## サポート

ぽえなびを気に入っていただけたら、開発環境の維持・改善を応援していただけると嬉しいです。

- [OFUSE（おふせ）](https://ofuse.me/48eca107)
- [Ko-fi](https://ko-fi.com/buri8857)
- [Patreon](https://www.patreon.com/cw/Buri8857)
