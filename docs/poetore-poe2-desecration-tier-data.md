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
32件の計1,713件。PoB2の表示文と公式Trade日本語テンプレートの極性が異なる23件は、
増加／減少だけが厳密に反転する場合に正規化している。残る15件はTier自体は収録できるが、
OCR数値照合は未対応として診断欄へ残す。

## 固定した画像例

- 靴: アーマー+27 = T7、最大マナ+108 = T1、移動スピード30% = T2
- スピア: 火耐性貫通20% = T1、冷気26–43 = T5、物理28%＋命中57 = T6

元画像、転記文、期待Tierは`tests/fixtures/poetore/poe2/desecration/`に保存する。

## 新リーグ・ゲーム更新時に確認する情報源

役割の異なる情報を混同しない。確認順は次のとおり。

1. **GGG公式Patch Notes**
   - <https://www.pathofexile.com/forum/view-forum/patch-notes>
   - Mod追加・削除、数値変更、対応ベース変更、アビス／冒涜仕様変更の一次情報として使う。
   - Patch Notesに記載がないことを「変更なし」の証明にはしない。
2. **GGG公式Trade2 Stat API（日英）**
   - <https://www.pathofexile.com/api/trade2/data/stats>
   - <https://jp.pathofexile.com/api/trade2/data/stats>
   - Stat IDと英語・日本語テンプレートの一次情報として使う。
   - 出現プール、対応部位、要求レベル、Tier番号はこのAPIからは得られない。
3. **Path of Building Community PoE2**
   - <https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2>
   - `src/Data/ModItem.lua`: 通常装備Mod
   - `src/Data/ModJewel.lua`: 通常ジュエルMod
   - `src/Data/ModVeiled.lua`: 冒涜専用Mod
   - `src/Data/Bases/*.lua`: ベース種別と順序付きspawn weight判定用タグ
   - GGG公式ではなく二次ソースなので、変更候補の抽出と構造化入力に使い、採用判断は
     公式情報・実ゲーム画面・回帰fixtureでも確認する。
4. **日本語クライアントの実画面**
   - 最終的なOCR表示文、複合Modの改行、実際の出現部位を確認する。
   - PoB2のカテゴリ全体を、実際の冒涜出現プールと断定しない。

## 更新が必要か確認するタイミング

- 新リーグ／大型パッチ公開時
- Patch NotesにAbyss、Desecration、item modifier、base typeの変更がある時
- PoB2の上記4入力のいずれかが更新された時
- 公式Trade2の日英Stat snapshotのSHA-256が変わった時
- 実機で既知部位の新Modが`未対応`になる、またはTier／部位候補が明らかに不正な時

現在の配布JSONが参照するPoB2 revisionは次で確認する。

```bash
jq -r '.source.pob2_revision' data/poetore/poe2/desecration_tiers.json
```

PoB2の現在HEADは次で確認する。HEADが同じならPoB2由来の再生成は不要である。

```bash
git ls-remote https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2.git HEAD
```

## 非破壊の候補生成・差分監査

本番の`desecration_tiers.json`を直接上書きしない。PoB2を更新候補revisionへ固定し、
監査CLIでcandidateとreportを別ファイルへ生成する。

```bash
python3 scripts/audit_poetore_poe2_desecration_update.py \
  --pob2 <PathOfBuilding-PoE2> \
  --expected-revision <40文字の固定revision> \
  --candidate-output <一時領域>/desecration_tiers.candidate.json \
  --report <一時領域>/desecration_tiers.update-report.json
```

公式Trade2更新を別途監査して新しい`stat_index.json`候補を作った場合だけ、
`--stat-index <candidate-stat-index>`も指定する。公式snapshotの更新は
`scripts/snapshot_poetore_poe2_sources.py`と`docs/poetore-poe2-development.md`の
source lock手順に従い、冒涜JSONだけを先行して推測更新しない。

監査CLIは次を比較する。

- Modの追加・削除
- pool／Prefix・Suffix／group／要求レベル
- 対応ベースタグprofileとprofile別Tier
- Stat ID、日英文面、数値レンジ
- 新たな未解析行と解消した未解析行
- 数値骨格が同じで文面だけ異なる衝突

profile IDは生成順で変わり得るため、IDではなく`category + tags`で比較する。
candidate出力先に本番JSONを指定すると監査CLIは失敗し、上書きを拒否する。

## 採用前ゲート

`requires_review: false`なら生成結果に意味上の差分はない。`true`の場合は、少なくとも次を
確認するまで本番JSONへ反映しない。

1. `mods_added`: Patch Notes、PoB2該当行、可能なら実画面で存在を確認する。
2. `mods_removed`: PoB2から消えただけで即削除せず、公式変更または現リーグでの扱いを確認する。
3. `mods_changed`: 特に`profile_tiers`、`parts`、`type`の変更を個別確認する。
4. `new_unparsed_rows`: 0件であること。増えた場合は文面・極性・固定数字を解決する。
5. `numeric_skeleton_collisions`: 0件であること。衝突時はOCRで一意判定できるか設計する。
6. 新しいAbyss陣営タグや装備カテゴリが追加された場合は、生成器の
   `NAMED_DESECRATION_TAGS`、`BASE_TAGS`、`EXCLUDED_CATEGORIES`を見直す。
7. `MISSING_PROFILE_OVERRIDES`はPoB2欠損を補う例外なので、新revisionで不要になったか再確認する。

採用時はcandidateをそのまま信用せず、生成コマンドで本番JSONを再生成して次を実行する。

```bash
python3 -m pytest -q \
  tests/test_build_poetore_poe2_desecration_tiers.py \
  tests/test_audit_poetore_poe2_desecration_update.py \
  tests/test_poetore_poe2_desecration_tiers.py \
  tests/test_desecration_ocr.py \
  tests/test_desecration_overlay.py
```

さらに追加・変更Modの日本語実画面をfixtureへ保存し、部位候補・Tier・複数Tier・
Prefix/Suffix併記・未対応行の維持を回帰テストへ固定する。件数だけ一致しても完了としない。

## 2026-09-14 現行ソース確認

- PoB2 HEADと固定revisionはいずれも
  `ce566eac45ea8a86477f513c7ee65a1ebe60014e`で一致。
- 候補監査結果はprofiles 426、entries 1,713、fully matchable 1,698で現行と一致。
- Mod追加・削除・変更、新規未解析行、数値骨格衝突はいずれも0件。
- この時点ではTier DB更新は不要。
