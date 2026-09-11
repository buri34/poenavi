# PoE2 冒涜Reveal Tierデータ

`data/poetore/poe2/desecration_tiers.json`は、冒涜Revealに出る通常Modと
冒涜専用ModをTier照合するための配布用派生データである。

## 固定ソース

- Path of Building Community PoE2:
  `ce566eac45ea8a86477f513c7ee65a1ebe60014e`
- 日本語・英語文面: `data/poetore/poe2/stat_index.json`
- 固定コミット、入力ファイルSHA-256、ベースデータ集合SHA-256は生成JSON内に記録する。

Tier番号はPoB2に直接収録されていない。Modのpool/type/groupと、実際のベースタグに
対する出現可否を組み合わせ、要求レベルを高い順に並べてT1、T2…を算出する。
PoB2の`weightKey`は先に一致したタグが優先されるため、順序を崩してはならない。

## 再生成

固定コミットをcheckoutしたPoB2のパスを指定する。

```text
python scripts/build_poetore_poe2_desecration_tiers.py \
  --pob2 <PathOfBuilding-PoE2> \
  --expected-revision ce566eac45ea8a86477f513c7ee65a1ebe60014e
```

生成結果は通常Mod 1,483件、冒涜専用装備Mod 198件、冒涜専用ジュエルMod
32件の計1,713件。現在38件はPoB2の表示文と公式Trade日本語テンプレートの意味・
極性が異なり、Tier自体は収録できるがOCR数値照合は未対応として診断欄へ残す。

## 固定した画像例

- 靴: アーマー+27 = T7、最大マナ+108 = T1、移動スピード30% = T2
- スピア: 火耐性貫通20% = T1、冷気26–43 = T5、物理28%＋命中57 = T6

元画像、転記文、期待Tierは`tests/fixtures/poetore/poe2/desecration/`に保存する。
