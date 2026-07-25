# ぽえとれ Modメタデータ基盤

## 目的と境界

PoE 1の武器・防具・装飾品について、日本語コピー文を共通Mod定義とTrade API stat IDへ
対応付ける。アプリにはRePoEの全データを同梱せず、検索に必要な項目だけへ変換した
`data/poetore/mod_metadata.json`を同梱する。

新リーグ時の日英アイテム／Stat同期、pseudo差分、代表Trade API確認まで含む総合更新フローの
実装前設計は`docs/poetore-league-data-update-plan.md`を参照する。

## 情報源

- Awakened PoE Trade: 共通ref、数値の良し悪し、Trade API ID、反転・完全一致ルール、
  防具ベースの可変防御値範囲
- RePoE: Tier範囲、必要レベル、Prefix/Suffix等の生成種別、ローカルstat判定
- 日本語公式Trade API: 日本語matcherとTrade API stat ID

生成物には各取得元URL、Awakenedのcommit、取得内容のSHA-256を記録する。
`scripts/poetore-sources.lock.json`を開発時の入力正本とし、通常の再生成では取得内容が
lockと一致しなければ停止する。

### 固定入力での再現・検査

```bash
PYTHONPATH=. python scripts/build_poetore_metadata.py
```

このコマンドは次を行うが、`mod_metadata.json`は置換しない。

- 全入力のSHA-256検証とAwakened commit表示
- `build/poetore-metadata-report.json`への新規／削除／変更Modの出力
- ルール、Tier、日本語matcher、曖昧matcher、未解決公式statの監査
- 件数、重複stat ID、空matcher、10%超または100件超の大量削除検査
- 候補データを使った全pytest回帰テスト

### リーグ更新時

1. Awakenedを更新する場合は、レビュー対象commitへlockのURLと`revision`を変更する。
2. 次のdry-runで新しいSHA、差分レポート、全テスト結果を確認する。

```bash
PYTHONPATH=. python scripts/build_poetore_metadata.py --refresh-lock
```

3. 差分が意図した内容なら、テスト成功後だけ正本とlockを原子的に更新する。

```bash
PYTHONPATH=. python scripts/build_poetore_metadata.py --refresh-lock --apply
```

大量削除は既定で拒否する。上流の意図した削除だと確認できた場合だけ、レビュー記録を残して
`--allow-large-removal`を追加する。候補ファイルは正本と同じディレクトリへ一時生成され、
失敗時には削除される。RePoE元JSONは保存・同梱しない。

## 独自スキーマ

- 共通Mod: `ref`, `stat_id`, `kind`, `better`, `inverted`, `exact`, `local`
- 日本語matcher: `japanese`
- Tier: `tier`, `minimum`, `maximum`, `required_level`, `generation`, `mod_id`
- 防具ベース: `base_armour`配下の英語ベースタイプと`ar`／`ev`／`es`／`ward`の最小・最大値
- 実アイテム解析: `stat_id`, `ref`, `confidence`, `roll_min/max`, `better`, `inverted`

一致が一意なら確度1.0、同一日本語表記に複数候補があれば0.75、未解決は0.0とする。
未解決値を正本へ推測で書かず、従来の公式Trade API照合へフォールバックする。

## 数値検索

- `better=1`: 最小値を使用
- `better=-1`: 最大値を使用
- `better=0`または`exact=true`: 最小値と最大値を同値にする
- `inverted=true`: Trade API送信時に符号反転し、min/maxを入れ替える
- 通常レア: 実数値を既定割合で緩和
- ユニーク: 可変幅を基準に緩和し、完璧ロールは緩和しない

## 配布ルール

- RePoEの元JSONを配布物へ丸ごと含めない。
- ぽえとれに必要な最小フィールドだけを派生インデックスへ保存する。
- 無料・非公式ツールとして提供し、`THIRD_PARTY_NOTICES.md`の表示を維持する。
- 一般公開前に生成物の内容・サイズ・権利表記を再監査する。
- source lock、差分レポート、テストfixtureは開発用であり、配布物へ同梱しない。
