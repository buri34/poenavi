# ぽえとれ 手順12 配布・権利・セキュリティ監査

監査日: 2026-07-20

## 完了した監査

- `data/poetore/`の配布対象は`mod_metadata.json` 1ファイルのみ
- 派生インデックスは9,270件、約5.2 MiBで、許可した最小フィールドだけを保持
- Awakened PoE Trade／RePoEの元データ、source lock、差分レポート、テストfixtureは非同梱
- `LICENSE`、`README.md`、`THIRD_PARTY_NOTICES.md`を配布物へ追加
- README、第三者通知、ぽえとれ画面に無料・非公式・GGG非提携／非承認を明記
- Awakened PoE Trade MIT、RePoE MIT、GGGの権利・出典表記を確認
- APIは識別可能なUser-Agentを使用し、429時は`Retry-After`に従って1回だけ再試行
- APIログは検索JSONと応答概要のみ。認証情報やクリップボード原文を出力しない
- 機密文字列スキャンでAPIキー、token、password等の混入なし
- 公式Trade APIで代表検索JSONが受理され、検索ID発行に成功
- 全自動テスト、compileall、Qt offscreenスモークを実行

## ビルド時の自動監査

`scripts/build_release.ps1`はZIP作成後に内容を開き、次を自動検査する。

- 必須: `LICENSE`、`README.md`、`THIRD_PARTY_NOTICES.md`、`mod_metadata.json`
- 禁止: tests、build、`__pycache__`、source lock、候補ファイル、RePoE元JSON
- `mod_metadata.json`が8 MiB以下

違反があればSHA-256作成前にReleaseビルドを失敗させる。

## Windowsで残る最終確認

macOSではWindows用PyInstaller成果物を生成できないため、次はWindows実機で行う。

1. `build_exe.bat`で`PoENavi.zip`を生成し、自動ZIP監査が成功すること
2. 展開したexeでPoENavi通常画面、更新確認、ガイド、みになびが起動すること
3. PoE1でAlt+Dから解析、初回検索、条件編集、再検索が成功すること
4. ぽえとれ下部に非公式・GGG非提携／非承認の表示があること

この実機確認と鰤さんの公開承認が終わるまで、GitHubへpush／PRしない。
