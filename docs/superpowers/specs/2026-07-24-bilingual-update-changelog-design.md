# Bilingual Update Changelog Design

## Goal

Give the existing v2.6.3 prerelease a useful bilingual changelog and ensure
future updater dialogs render curated release notes with working links.

## Existing v2.6.3 Release

Replace the generated release body with plain-text-friendly Markdown. It must
remain readable in the already-built v2.6.2 updater, which displays release
notes as plain text, while also rendering cleanly on GitHub and in future
updater versions.

Use this release body:

```markdown
# English

## What's changed

- Added a tooltip explaining the Automatic / First time / Second time guide toggle.
- Fixed Japanese acquisition badges appearing beside gems in the English interface. They now display Quest or Buy.

## Testing

- This prerelease is being used to validate the complete v2.6.2 to v2.6.3 automatic-update flow.

# 日本語

## 変更内容

- ガイドの「自動 / 1回目 / 2回目」切り替えの動作を説明するツールチップを追加しました。
- 英語インターフェースのジェム入手情報に日本語のバッジが表示される問題を修正しました。英語では Quest または Buy と表示されます。

## テスト

- このプレリリースは、v2.6.2 から v2.6.3 への自動更新フロー全体を検証するために使用しています。

Full changelog / 完全な変更履歴:
https://github.com/fuubox/poenavi-localisation/compare/v2.6.2...v2.6.3
```

Editing the release body does not rebuild or move the v2.6.3 tag. Restarting
the v2.6.2 test application causes it to fetch the revised body.

## Curated Release-Note Source

Store each release body at:

```text
docs/releases/vMAJOR.MINOR.PATCH.md
```

Add `docs/releases/v2.6.3.md` containing the exact body above. A release tag
must have a matching file based on `GITHUB_REF_NAME`.

The release workflow must check that the file exists before building and pass
it to `gh release create` with `--notes-file`. Remove `--generate-notes`.
This makes a missing changelog fail explicitly instead of silently publishing
only a comparison link.

Release-note files are bilingual. Put English first and Japanese second, then
include a full-changelog comparison URL.

## Updater Rendering

Keep `ReleaseInfo.notes` as the raw GitHub release-body string. The release
client does not transform Markdown.

In `UpdateAvailableDialog`, render `release.notes` with
`QTextBrowser.setMarkdown()` and enable `setOpenExternalLinks(True)`.
The dialog continues to use the existing application stylesheet and minimum
size.

The release body is controlled by this repository. Do not add a separate HTML
fetch, Markdown dependency, or custom link handler.

The v2.6.3 package cannot gain this renderer after it has been built. The
renderer ships in the next application release, while editing the v2.6.3
release body immediately improves what the v2.6.2 plain-text dialog displays.

## Verification

Add a focused Qt test that creates `UpdateAvailableDialog` with Markdown notes
and verifies:

- the notes widget is a `QTextBrowser`;
- Markdown syntax is rendered rather than shown literally;
- a release-note URL becomes an anchor; and
- external links are enabled.

Verify the release workflow selects
`docs/releases/$env:GITHUB_REF_NAME.md` and no longer uses
`--generate-notes`.

Run the focused updater tests, the full test suite, locale validation, and
`git diff --check`.

After editing the existing GitHub release, query the public release API and
confirm its body exactly matches `docs/releases/v2.6.3.md`, its prerelease
status remains true, and both updater assets remain attached.
