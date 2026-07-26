def split_query_patterns(query: str) -> list[str]:
    """検索文字列をトップレベルの | で分割する。"""
    query = (query or "").strip().strip("|")
    if not query:
        return []
    patterns = []
    buf = []
    paren_depth = 0
    bracket_depth = 0
    in_quote = False
    for ch in query:
        if ch == '"':
            in_quote = not in_quote
        elif not in_quote and ch == "(":
            paren_depth += 1
        elif not in_quote and ch == ")" and paren_depth > 0:
            paren_depth -= 1
        elif not in_quote and ch == "[":
            bracket_depth += 1
        elif not in_quote and ch == "]" and bracket_depth > 0:
            bracket_depth -= 1
        if ch == "|" and not in_quote and paren_depth == 0 and bracket_depth == 0:
            part = "".join(buf).strip()
            if part:
                patterns.append(part)
            buf = []
        else:
            buf.append(ch)
    part = "".join(buf).strip()
    if part:
        patterns.append(part)
    return patterns


def join_query_patterns(patterns: list[str]) -> str:
    """空文字と重複を除いて検索文字列を結合する。"""
    seen = []
    for pattern in patterns:
        pattern = (pattern or "").strip()
        if pattern and pattern not in seen:
            seen.append(pattern)
    return "|".join(seen)
