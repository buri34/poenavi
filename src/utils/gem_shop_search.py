"""PoEショップ用のAct別ジェム検索文字列を組み立てる。"""
from collections.abc import Mapping
from functools import lru_cache


# 同じ長さの一意候補が複数ある場合に、ゲーム内で見分けやすい通称を優先する。
PREFERRED_SEARCH_TERMS = {
    "spectral throw": "ラルスロ",
}


class HoldTrigger:
    """長押しタイマーの古い発火と連続実行を防ぐ状態。"""

    def __init__(self) -> None:
        self._generation = 0
        self._held = False
        self._consumed = False

    def start(self) -> int:
        if self._held:
            return self._generation
        self._generation += 1
        self._held = True
        self._consumed = False
        return self._generation

    def release(self) -> None:
        self._held = False

    def consume_if_current(self, generation: int) -> bool:
        if generation != self._generation or not self._held or self._consumed:
            return False
        self._consumed = True
        return True


def validate_gem_shop_search_term_override(
    gem_key: str,
    term: str,
    gem_names_ja: Mapping[str, str],
) -> str | None:
    """正式名に含まれ、全ジェムで一意な短縮語だけを受け付ける。"""
    candidate = term.strip()
    gem_name = gem_names_ja.get(gem_key, "")
    if len(candidate) < 4 or candidate not in gem_name:
        return None
    return candidate if sum(candidate in name for name in gem_names_ja.values()) == 1 else None


def build_unique_gem_search_terms(
    gem_names_ja: Mapping[str, str],
    term_overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """各公式名から、他ジェム名と重複しない最短4文字以上の検索語を選ぶ。"""
    entries = tuple(sorted((key, name) for key, name in gem_names_ja.items() if name))
    terms = dict(_build_unique_gem_search_terms(entries))
    for key, term in (term_overrides or {}).items():
        valid_term = validate_gem_shop_search_term_override(key, term, gem_names_ja)
        if valid_term:
            terms[key] = valid_term
    return terms


@lru_cache(maxsize=4)
def _build_unique_gem_search_terms(entries: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    names = tuple(name for _, name in entries)
    terms = []
    for key, name in entries:
        preferred = PREFERRED_SEARCH_TERMS.get(key, "")
        term = preferred if sum(preferred in other for other in names) == 1 else ""
        if not term:
            for length in range(4, len(name) + 1):
                for start in range(len(name) - length + 1):
                    candidate = name[start:start + length]
                    if sum(candidate in other for other in names) == 1:
                        term = candidate
                        break
                if term:
                    break
        if term:
            terms.append((key, term))
    return tuple(terms)


def build_act_vendor_gem_query(
    acquisition_plan: list[dict],
    act: int,
    gem_names_ja: Mapping[str, str],
    exclude_quest_rewards: bool,
    term_overrides: Mapping[str, str] | None = None,
) -> str:
    """現在Actのジェムを一意な公式日本語短縮語のOR検索にする。"""
    search_terms = build_unique_gem_search_terms(gem_names_ja, term_overrides)
    terms: list[str] = []
    seen: set[str] = set()
    for entry in acquisition_plan:
        if entry.get("act") != act:
            continue
        for gem in entry.get("gems", []):
            if exclude_quest_rewards and gem.get("type") == "quest":
                continue
            name = gem.get("name", "")
            term = search_terms.get(name, "")
            if term and term not in seen:
                seen.add(term)
                terms.append(term)
    return "|".join(terms)


def format_gem_shop_search_preview(query: str) -> str:
    """現在Actのショップ検索語をプレビュー用に整形する。"""
    return f"ショップRegex: {query}" if query else "ショップRegex: 対象ジェムなし"


def get_gem_shop_search_feedback(act: int, query: str, poe_is_foreground: bool) -> str:
    """長押し検索の結果を控えめな通知文言へ変換する。"""
    if not query:
        return "対象ジェムがありません"
    if not poe_is_foreground:
        return "PoEが前面でないため入力しません"
    return f"Act {act}: {query.count('|') + 1}件を検索します"
