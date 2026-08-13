from scripts import security_scan


def kinds(text: str) -> set[str]:
    return {finding.kind for finding in security_scan.scan_text("sample.py", text)}


def test_allows_normal_japanese_and_emoji_variation_selector():
    assert kinds('message = "更新完了 ✔️"\n') == set()


def test_detects_glassworm_supplementary_variation_selector():
    assert "GlassWorm variation selector" in kinds("safe = 1\U000e0100")


def test_detects_non_emoji_and_consecutive_variation_selectors():
    result = kinds("value = 'A\ufe0f\ufe00'")
    assert "variation selector outside emoji" in result
    assert "unexpected variation selector" in result
    assert "consecutive variation selectors" in result


def test_detects_bidi_and_zero_width_controls_but_allows_initial_bom():
    assert "bidirectional control" in kinds("safe # \u202e hidden")
    assert "invisible control" in kinds("safe\u200bhidden")
    assert kinds("\ufeffheader,value\n") == set()
    assert "embedded byte-order mark" in kinds("header\ufeffvalue")


def test_detects_credential_shapes_without_echoing_secret():
    value = "ghp_" + "A" * 36
    findings = security_scan.scan_text("sample.py", f'token = "{value}"')
    assert findings[0].kind == "GitHub token"
    assert value not in findings[0].detail
