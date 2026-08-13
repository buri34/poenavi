# Security checks for contributors

PoENavi scans every Git-tracked text file for credential-shaped values and
invisible Unicode payloads before code is shared.

## Local pre-push check

Enable the repository-managed hook once per clone:

```bash
git config core.hooksPath .githooks
```

Every `git push` then runs:

```bash
python scripts/security_scan.py
```

A finding exits with a non-zero status and blocks the push. The scanner does
not print the suspected secret itself.

## GitHub check

`.github/workflows/security.yml` runs the same scanner on every branch push
and pull request. This provides a second check if a contributor has not
enabled the local hook or bypasses it with `--no-verify`.

## Invisible Unicode policy

The scanner rejects:

- supplementary variation selectors (`U+E0100`–`U+E01EF`) used by GlassWorm;
- non-emoji, consecutive, or excessive variation selectors;
- bidirectional controls and unexpected zero-width controls;
- byte-order marks embedded anywhere except the start of a text file.

Legitimate emoji presentation selectors and a single leading CSV/text BOM are
allowed. If an invisible character is genuinely required, document the reason
and narrow the scanner rule with a regression test instead of bypassing it.
