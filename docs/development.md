# Development Notes

## 開発用のユーザーデータ保存先

通常起動では、設定ファイルは `%APPDATA%\PoENavi\config.json` に保存されます。

config.json の構造変更・移行処理・設定保存まわりを検証するときは、普段使いの設定を汚さないように `run_dev.bat` から起動してください。

`run_dev.bat` は起動中だけ以下を設定します。

```bat
POENAVI_USER_DATA_DIR=%~dp0.dev-user-data
```

この場合、開発用の設定はアプリフォルダ内の `.dev-user-data\config.json` に保存されます。
Windows全体の環境変数として `POENAVI_USER_DATA_DIR` を恒久追加する必要はありません。


## 配布用の初期設定テンプレート

初回起動時の設定テンプレートは `default_config.json` です。
初期ホットキーや初期表示設定の正本はこのファイルです。配布前に初期設定を変えたい場合は、このファイルを編集してください。
コード内に初期設定辞書は持たない方針です。`default_config.json` が無い/壊れている場合は起動時に明確なエラーになります。

`build_exe.bat` は `default_config.json` をexe配布フォルダに同梱します。
一方、ユーザーごとの実設定は `%APPDATA%\PoENavi\config.json` に作成・保存されます。

旧バージョン互換のため、アプリ本体フォルダ直下に `config.json` が残っていて、かつ `%APPDATA%\PoENavi\config.json` がまだ無い場合だけ、その旧 `config.json` を移行します。
新規配布物には `config.json` を同梱しません。

## ぽえとれTradeデータ更新

新リーグや公式Tradeデータ変更時は、個別生成器を直接反映する前に総合入口を使います。

```bash
# 読み取り専用監査
python scripts/update_poetore_trade_data.py

# 最新データから隔離候補とJSON／Markdownレポートを生成
python scripts/update_poetore_trade_data.py --refresh

# 必要に応じて代表12 fixtureを公式Trade検索APIへ実送信
python scripts/update_poetore_trade_data.py --refresh --verify-api

# レビュー済みmanifestと候補だけを正本へ原子的に反映
python scripts/update_poetore_trade_data.py \
  --apply build/poetore-update-candidate/manifest.json
```

`--refresh`は正本を変更しません。`--apply`はレビュー時点の正本または候補のSHA-256が
変わっていれば停止し、複数ファイルの置換途中に失敗した場合は全正本を復元します。
Awakenedが取得不能な場合は`--official-mods-only`を付け、既存のAwakened由来派生情報を
保持したまま、公式Trade・RePoE・PoENavi独自台帳だけで監査・候補生成できます。

詳細は`docs/poetore-league-data-update-plan.md`を参照してください。
