# SignPath準備変更の仕分け

作成日: 2026-08-29
対象: PoENaviのSignPath Foundation申請準備として追加・変更した内容
目的: SignPathから一定期間返答がなく申請を断念する場合に、削除するものと継続して残すものを事前に明確にする

## 結論

SignPathを断念しても、準備時に追加した変更の大部分は、通常のリリース品質・利用者への説明・ライセンス順守に役立つため残す。

削除対象は、SignPathへの申請・審査・署名フローだけを説明している文書や表示、およびそれらの存在を強制するテストに限定する。依存関係の固定、Windows EXEのバージョン情報、Windowsビルド検証、第三者ライセンス本文の同梱、Privacy Policy、アンインストール説明は残す。

現時点では仕分けのみを行い、ファイルや記述の削除は行わない。

## 調査対象

SignPath準備に直接関係する次のコミットを基準に、現在のブランチに残る内容と後続変更を確認した。

- `e08abaa` — SignPath申請準備の本体（13ファイル、400行追加・8行削除）
- `5d98b99d` — Windowsビルド検証ワークフローの追加
- `c408bc3d` — 配布物への第三者ライセンス全文の収集・同梱
- `7f1ba320` — READMEへのSignPath申請中の案内追加
- `6811056d` — 上記準備ブランチのマージ

## SignPath断念時に削除するもの

### 1. `README.md`の「コード署名」節

削除する内容:

- SignPath.io / SignPath Foundationのクレジット
- SignPath Foundationへ申請中である旨
- 現在の配布版が未署名である旨を、この申請と結び付けて説明する文章

理由:

申請を断念した後は事実と異なる「申請中」の表示になる。SignPathから提供を受けていない状態でクレジットを残す必要もない。

補足:

SmartScreenの一般的な注意書きは、未署名配布を続ける限り利用者に必要なので残す。

### 2. `README.md`末尾のCode signing policyリンク

削除する内容:

- `[Code signing policy](docs/CODE_SIGNING_POLICY.md)`

理由:

リンク先がSignPath採用を前提にしたポリシーであり、断念後は運用実態と一致しない。

補足:

`[Privacy policy](PRIVACY.md)`は残す。

### 3. `docs/CODE_SIGNING_POLICY.md`

判定: ファイル全体を削除する。

理由:

SignPathの無料コード署名、申請承認者、署名要求の手動承認、SignPathへの成果物送信、署名後の検証という未導入の運用だけを定義している。断念後に残すと、実際に署名済みである、または記載された署名運用が稼働しているとの誤解を招く。

### 4. `docs/signpath-application-draft.md`

判定: ファイル全体を削除する。

理由:

SignPath Foundationへ提出するための申請文案であり、通常の開発・配布には使われない。プロジェクト説明など一部に一般情報を含むが、同等の情報はREADME、Privacy Policy、第三者通知に存在する。

### 5. `docs/signpath-readiness-checklist.md`

判定: ファイル全体を削除する。

理由:

申請資格、SignPath MFA、署名要求、審査確認など、SignPath申請の進行管理専用文書である。ライセンス同梱など完了済みの成果は実装・テスト側に残るため、チェックリスト自体を保存する必要はない。

### 6. `tests/test_poetore_distribution.py`内のSignPath専用テスト

削除・再編する対象:

- `test_signpath_policy_and_privacy_documents_are_linked_and_complete`

理由:

このテストは、READMEにCode signing policyへのリンクがあること、SignPathのクレジットがあること、署名対象や手動承認がポリシーに書かれていることを強制している。関連文書を削除するとテストが失敗するため、SignPath専用の検証は取り除く必要がある。

ただし、Privacy Policyの存在と最低限の内容を検証する部分は有用なので、SignPathとは独立したPrivacy Policy用テストとして残す。

## SignPathを断念しても残すもの

### 1. `PRIVACY.md`

判定: 残す。

理由:

ローカルで処理する情報、外部接続先、グローバルホットキー、ログアウト機能、アップデート、アンインストール方法を利用者へ説明している。コード署名の有無とは無関係に、外部通信とデータ取扱いの透明性を高める重要な文書である。

### 2. `README.md`のアンインストール説明とPrivacy Policyリンク

判定: 残す。

理由:

ポータブルZIPの削除方法と`%APPDATA%\PoENavi\`に残る設定データの消し方は、利用者がアプリを完全に削除するために必要である。Privacy Policyへの導線も通常の利用者向け情報として有用である。

### 3. `THIRD_PARTY_NOTICES.md`のランタイム部品説明

判定: 残す。

理由:

配布物に含まれるPython、PySide6 / Qt、pynput、urllib3、PyInstaller、OpenSSLなどの由来とライセンスを示す記述である。これはSignPathの審査対策だけではなく、OSSライセンス順守と利用者への通知のために必要である。

### 4. `scripts/collect_third_party_licenses.py`と対応テスト

対象:

- `scripts/collect_third_party_licenses.py`
- `tests/test_collect_third_party_licenses.py`
- `scripts/build_release.ps1`の`THIRD_PARTY_LICENSES/`生成・同梱・監査処理
- `tests/test_poetore_distribution.py`の第三者ライセンス同梱検証

判定: 残す。

理由:

実際のリリース環境に入っている各パッケージから完全なライセンス本文を収集し、配布ZIPへ同梱する仕組みである。SignPathを使わなくても、第三者ライセンス条件を満たすために価値がある。

### 5. `requirements.txt`のバージョン固定

判定: 残す。

理由:

PySide6、pynput、urllib3のバージョン固定は、同じソースから異なる依存バージョンが入って挙動や配布物が変わるのを防ぐ。リリースの再現性と障害調査に役立つ。

注意:

固定バージョンは恒久的に放置せず、更新時にテストとライセンス監査を行う必要がある。

### 6. `requirements-build.txt`

判定: 残す。

理由:

実行時依存と、PyInstaller・pytest・pytest-qtなどのビルド／検証依存を分離して固定している。ローカルビルドとGitHub Actionsで同じ依存セットを使えるため、SignPathとは独立して有用である。

### 7. `.github/workflows/release.yml`のPython・依存固定

判定: 残す。

対象:

- Pythonを`3.12.10`へ固定
- `requirements-build.txt`から依存を導入

理由:

公式リリースのビルド環境を安定させ、突然のPythonやパッケージ更新によるビルド失敗・成果物差異を減らす。コード署名を使わない場合にも必要な品質管理である。

### 8. Windows EXEの製品名・バージョン情報

対象:

- `scripts/generate_windows_version_info.py`
- `scripts/build_release.ps1`のバージョン情報生成と`--version-file`指定
- `tests/test_windows_version_info.py`
- `tests/test_poetore_distribution.py`のバージョンファイル指定検証

判定: 残す。

理由:

Windowsのファイルプロパティに`ProductName=PoENavi`、正しい`ProductVersion`、`FileVersion`、元ファイル名を設定する機能である。署名されていなくても、利用者の識別、サポート、更新時の版確認に役立つ。

補足:

テスト名`test_render_version_info_sets_signpath_required_metadata`は機能自体を残したまま、`test_render_version_info_sets_product_metadata`などSignPathに依存しない名称へ変更するのが望ましい。

### 9. `.github/workflows/windows-build.yml`と対応テスト

判定: 残す。

理由:

Pull Requestや手動実行で、Windows上の全テスト、実際の配布ビルド、両EXEの製品名・バージョン、ZIP生成まで検証する。macOS上だけでは検出できないWindows固有のビルド不具合を防げる。

補足:

成果物名`PoENavi-unsigned-windows`の`unsigned`は現状を正確に表している。将来も署名しない方針を明確にするならそのままで問題ない。単なる検証成果物として中立化したい場合は`PoENavi-windows-verification`へ変更できるが、必須ではない。

### 10. `scripts/build_release.ps1`からの未使用`keyboard` hidden import削除

判定: 残す。

理由:

SignPathとは無関係な不要依存の整理である。現在の入力処理は別実装を使っており、未使用モジュールを配布物へ含めないほうが構成が明確になる。

## 要判断・将来条件で見直すもの

### 1. コード署名そのものに関する一般説明

現時点のREADMEにはSmartScreenが表示された場合の一般案内がある。この説明は未署名配布を続ける間は残す。

将来、SignPath以外の証明書で署名する場合は、新しい署名方式と発行者に合わせて案内を書き直す。今回のSignPath用ポリシーをそのまま流用しない。

### 2. `THIRD_PARTY_NOTICES.md`の「固定バージョンはGitHub Actionsログに記録される」という表現

現在のビルド方式と一致しているため残してよい。将来GitHub Actions以外で公式リリースを作る運用へ変えた場合だけ更新する。

## 断念時の推奨作業単位

SignPath断念時は、次の1コミットに限定して撤去する。

1. READMEのSignPath申請中の節とCode signing policyリンクを削除する。
2. SignPath専用の3文書を削除する。
3. SignPath専用テストをPrivacy Policy単独のテストへ再編する。
4. Windowsバージョン情報テスト名からSignPath固有名を外す。
5. 関連テスト、Markdownリンク、`rg -i signpath`を実行し、意図した履歴資料以外にSignPath表記が残っていないことを確認する。

この作業では、依存固定、ライセンス同梱、Windowsメタデータ、Windows CI、Privacy Policy、アンインストール説明を削除しない。
