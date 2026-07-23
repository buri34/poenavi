"""
攻略ガイドデータ管理
ゾーンIDをキーに、攻略テキスト（HTML対応）を返す。
データは PoEバージョンごとの guide_data*.json から読み込み。ユーザー編集可能。
"""

import html
import json
import os
import re
import shutil
import sys
from datetime import datetime

from src.utils.poe_version_data import POE1, get_guide_filename
from src.utils.i18n import DEFAULT_LOCALE, get_locale, tr
from src.utils.config_manager import ConfigManager

# デフォルトガイド（guide_data.json がない場合のフォールバック）
DEFAULT_GUIDE = {
    "act1_area1": {
        "tips": "・左クリックに移動を割り当て、押しやすいボタンに攻撃スキルをセット"
    },
    "act1_area2": {
        "objective": "ウェイポイント（WP）を確保し、先へ進む",
        "layout": "【レイアウト情報】\n・入口の向きが右下なら、上に進む\n・入口の向きが左下を向いてるなら、下か右下（→右）に進む",
        "tips": "・ここの敵は経験値も大して美味しくないので、スルー推奨"
    },
}

_GUIDE_DATA_CACHE: dict[str, tuple[int, dict]] = {}

def get_guide_dir():
    """ガイドデータファイルのディレクトリ（exeフォルダ優先 → _MEIPASS）"""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        return getattr(sys, '_MEIPASS', exe_dir) if not os.path.exists(exe_dir) else exe_dir
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_guide_path(poe_version: str = POE1, language: str = DEFAULT_LOCALE) -> str:
    guide_file = get_guide_filename(poe_version, language)
    guide_dir = get_guide_dir()

    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        exe_path = os.path.join(exe_dir, guide_file)
        if os.path.exists(exe_path):
            return exe_path
        return os.path.join(getattr(sys, '_MEIPASS', exe_dir), guide_file)

    return os.path.join(guide_dir, guide_file)


def load_guide_data(poe_version: str = POE1, language: str = DEFAULT_LOCALE) -> dict:
    """ガイドデータを読み込み"""
    requested_path = get_guide_path(poe_version, language)
    paths = [requested_path]
    if str(language).lower().replace("_", "-").startswith("en"):
        fallback_path = get_guide_path(poe_version, DEFAULT_LOCALE)
        if fallback_path != requested_path:
            paths.append(fallback_path)

    for path in paths:
        try:
            modified_ns = os.stat(path).st_mtime_ns
        except OSError:
            continue

        cached = _GUIDE_DATA_CACHE.get(path)
        if cached and cached[0] == modified_ns:
            return cached[1]

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _GUIDE_DATA_CACHE[path] = (modified_ns, data)
            return data
        except Exception as e:
            print(f"[GuideData] Failed to load ({poe_version}): {e}")
    return DEFAULT_GUIDE if poe_version == POE1 else {}


def save_guide_data(data: dict, poe_version: str = POE1, language: str = DEFAULT_LOCALE):
    """ガイドデータを保存"""
    path = get_guide_path(poe_version, language)
    try:
        if (
            poe_version == POE1
            and os.environ.get("POENAVI_ACT1_GUIDE_DEV") == "1"
            and os.path.exists(path)
        ):
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup_path = os.path.join(
                os.path.dirname(path),
                f"guide_data.backup-before-act1-guide-edit-{timestamp}.json",
            )
            shutil.copy2(path, backup_path)
            print(f"[GuideData] Backup: {backup_path}")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _GUIDE_DATA_CACHE.pop(path, None)
        print(f"[GuideData] Saved ({poe_version}): {path}")
    except Exception as e:
        print(f"[GuideData] Failed to save ({poe_version}): {e}")


def _get_route_for_zone(zone_id: str, config: dict | None) -> str:
    """zone_idからAct判定してルート設定を取得。"standard"なら空文字を返す"""
    if not config or not zone_id:
        return ""
    if zone_id.startswith("act3_"):
        route = ConfigManager.effective_poe1_route_act3(config)
    elif zone_id.startswith("act8_"):
        route = ConfigManager.effective_poe1_route_act8(config)
    else:
        return ""
    return "" if route == "standard" else route


def _resolve_structured_flag_guide(entry: dict, active_flags: set[str] | None, flag_only: bool = False) -> dict | None:
    if not isinstance(entry, dict):
        return None
    default_guide = entry.get("default")
    flags = entry.get("flags", {})
    if not isinstance(default_guide, dict) and _entry_has_guide_payload(entry):
        default_guide = {k: v for k, v in entry.items() if k != "flags"}
    if active_flags and isinstance(flags, dict):
        # 複数フラグ条件（例: act1_draven_dead+act1_asinia_dead）を優先
        composite_keys = [k for k in flags.keys() if "+" in k]
        composite_keys.sort(key=lambda k: len(k.split("+")), reverse=True)
        for flag_key in composite_keys:
            required = [part.strip() for part in flag_key.split("+") if part.strip()]
            if required and all(r in active_flags for r in required):
                flagged = flags.get(flag_key)
                if isinstance(flagged, dict):
                    if isinstance(default_guide, dict):
                        merged = dict(default_guide)
                        merged.update(flagged)
                        return merged
                    return flagged
        # 単独フラグ
        for flag_name in active_flags:
            flagged = flags.get(flag_name)
            if isinstance(flagged, dict):
                if isinstance(default_guide, dict):
                    merged = dict(default_guide)
                    merged.update(flagged)
                    return merged
                return flagged
    if flag_only:
        return None
    return default_guide if isinstance(default_guide, dict) else None


def _is_structured_flag_entry(entry: dict) -> bool:
    return isinstance(entry, dict) and ("default" in entry or "flags" in entry)


def _is_visits_entry(entry: dict) -> bool:
    return isinstance(entry, dict) and ("visits" in entry or "routes" in entry)


def _visit_keys(visit: int) -> list[str]:
    keys = []
    if visit >= 2:
        keys.append(str(visit))
        if visit != 2:
            keys.append("2")
    keys.append("1")
    result = []
    for key in keys:
        if key not in result:
            result.append(key)
    return result


def _entry_has_guide_payload(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    guide_keys = {"objective", "layout", "tips", "direction", "summary", "level", "mini_navi"}
    return any(k in entry for k in guide_keys)


def _entry_has_display_content(entry: dict) -> bool:
    """実際に表示できる本文を持つガイドかどうか。

    directionだけの2回目ガイドや、objective/layout/tipsが空文字だけのガイドは
    「ガイド未設定」と扱い、1回目/defaultへフォールバックさせる。
    """
    if not isinstance(entry, dict):
        return False
    for key in ("objective", "layout", "tips", "summary"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if value and not isinstance(value, str):
            return True
    if entry.get("level"):
        return True
    mini_navi = entry.get("mini_navi")
    if isinstance(mini_navi, dict):
        text = mini_navi.get("text")
        if isinstance(text, str) and text.strip():
            return True
        pages = mini_navi.get("pages")
        if isinstance(pages, list) and pages:
            return True
    elif mini_navi:
        return True
    flags = entry.get("flags")
    if isinstance(flags, dict) and flags:
        return True
    return False


def get_mini_navi_content(guide: dict | None, max_lines: int | None = 4) -> dict | None:
    """みになび表示用の短文を取得する。

    優先順:
    1. guide["mini_navi"]["text"]
    2. guide["mini_navi"]["pages"] の先頭ページ
    3. guide["summary"] の先頭行
    4. guide["objective"] の先頭行
    """
    if not isinstance(guide, dict):
        return None

    mini_navi = guide.get("mini_navi")
    direction = guide.get("direction", "none") or "none"
    raw_lines: list[str] = []

    if isinstance(mini_navi, dict):
        direction = mini_navi.get("direction", direction) or "none"
        text = mini_navi.get("text")
        if isinstance(text, str) and text.strip():
            raw_lines = text.splitlines()
        elif isinstance(mini_navi.get("pages"), list) and mini_navi["pages"]:
            first_page = mini_navi["pages"][0]
            if isinstance(first_page, list):
                raw_lines = [str(line) for line in first_page]
            elif isinstance(first_page, str):
                raw_lines = first_page.splitlines()

    if not raw_lines:
        for key in ("summary", "objective"):
            value = guide.get(key)
            if isinstance(value, str) and value.strip():
                raw_lines = value.splitlines()
                break

    # 表示上のインデントや区切り用スペースを保持するため、行頭/行末の空白は削らない。
    lines = [str(line) for line in raw_lines if str(line).strip()]
    if not lines:
        return None

    if max_lines is None:
        return {"text": "\n".join(lines), "direction": direction}

    max_lines = max(4, min(int(max_lines or 4), 6))
    clipped = lines[:max_lines]
    if len(lines) > max_lines and clipped:
        clipped[-1] = clipped[-1].rstrip("…") + "…"
    return {"text": "\n".join(clipped), "direction": direction}


def _collect_visit_entries(entry: dict, visit: int) -> list[dict]:
    """visits構造のコンテナから、訪問回数に応じた候補を返す。"""
    if not isinstance(entry, dict):
        return []
    visits = entry.get("visits")
    if isinstance(visits, dict):
        return [visits[k] for k in _visit_keys(visit) if isinstance(visits.get(k), dict)]
    if _entry_has_guide_payload(entry) or _is_structured_flag_entry(entry):
        return [entry]
    return []


def _collect_guide_candidates(guide_data: dict, zone_id: str, visit: int, config: dict | None) -> list[dict]:
    """新visits構造を優先し、旧フラットキーも互換で候補に含める。"""
    base_entry = guide_data.get(zone_id)
    route = _get_route_for_zone(zone_id, config)
    candidates: list[dict] = []

    # 新構造: route → base の順。各コンテナ内は visit → fallback の順。
    if isinstance(base_entry, dict) and _is_visits_entry(base_entry):
        routes = base_entry.get("routes", {})
        if route and isinstance(routes, dict) and isinstance(routes.get(route), dict):
            candidates.extend(_collect_visit_entries(routes[route], visit))
        candidates.extend(_collect_visit_entries(base_entry, visit))

    # 旧構造互換: {zone_id}@2 / {zone_id}~route@2 など。
    legacy_keys = []
    if route and visit >= 2:
        legacy_keys.append(f"{zone_id}~{route}@{visit}")
        legacy_keys.append(f"{zone_id}~{route}@2")
    if route:
        legacy_keys.append(f"{zone_id}~{route}")
    if visit >= 2:
        for v in [visit, 2]:
            legacy_keys.append(f"{zone_id}@{v}")
    legacy_keys.append(zone_id)
    seen_ids = {id(c) for c in candidates}
    for key in legacy_keys:
        guide = guide_data.get(key)
        if isinstance(guide, dict) and id(guide) not in seen_ids:
            candidates.append(guide)
            seen_ids.add(id(guide))
    return candidates


def _resolve_guide_candidate(entry: dict, active_flags: set[str] | None, flag_only: bool = False) -> dict | None:
    if not isinstance(entry, dict):
        return None
    if _is_structured_flag_entry(entry):
        guide = _resolve_structured_flag_guide(entry, active_flags, flag_only=flag_only)
        return guide if _entry_has_display_content(guide) else None
    if flag_only or not _entry_has_display_content(entry):
        return None
    return entry


def _base_direction_from_entry(entry: dict) -> str | None:
    """方向継承用に、1回目/defaultのdirectionを取り出す。"""
    if not isinstance(entry, dict):
        return None
    if _is_visits_entry(entry):
        visits = entry.get("visits", {})
        if isinstance(visits, dict) and isinstance(visits.get("1"), dict):
            return _base_direction_from_entry(visits["1"])
    if _is_structured_flag_entry(entry):
        default = entry.get("default", {})
        return default.get("direction") if isinstance(default, dict) else None
    return entry.get("direction")

def get_zone_guide(guide_data: dict, zone_id: str, visit: int = 1, config: dict | None = None, active_flags: set[str] | None = None) -> dict | None:
    """
    ゾーンIDからガイドを検索（ルート対応版 + visits構造 + 構造化フラグ対応）

    新形式:
    {
      "zone_id": {
        "visits": {"1": {...}, "2": {...}},
        "routes": {"library_detour": {"visits": {"1": {...}, "2": {...}}}}
      }
    }

    旧形式の zone_id@2 / zone_id~route@2 も互換で読む。
    フラグが立っている場合は、訪問回数defaultよりフラグガイドを優先する。
    """
    base_entry = guide_data.get(zone_id)
    candidates = _collect_guide_candidates(guide_data, zone_id, visit, config)
    base_direction = _base_direction_from_entry(base_entry) if isinstance(base_entry, dict) else None

    # 非標準ルート選択中は、そのルート内でフラグ分岐→通常ガイドの順に確定する。
    # ベース側（標準ルート）のフラグガイドが別ルートに漏れるのを防ぐ。
    route = _get_route_for_zone(zone_id, config)
    if route and isinstance(base_entry, dict):
        routes = base_entry.get("routes", {})
        route_entry = routes.get(route) if isinstance(routes, dict) else None
        route_candidates = _collect_visit_entries(route_entry, visit) if isinstance(route_entry, dict) else []
        for flag_only in (True, False):
            if flag_only and not active_flags:
                continue
            for entry in route_candidates:
                guide = _resolve_guide_candidate(entry, active_flags, flag_only=flag_only)
                if guide:
                    if "direction" not in guide and base_direction:
                        guide = {**guide, "direction": base_direction}
                    return guide

        # ルート側が空な場合は標準ガイドへフォールバックするが、
        # 標準ルート専用のフラグ分岐は適用しない。
        active_flags = None

    # 1st pass: フラグが立っている場合は、訪問回数defaultよりフラグガイドを優先する。
    for flag_only in (True, False):
        if flag_only and not active_flags:
            continue
        for entry in candidates:
            guide = _resolve_guide_candidate(entry, active_flags, flag_only=flag_only)
            if not guide:
                continue
            # directionが未設定なら1回目/defaultから継承
            if "direction" not in guide and base_direction:
                guide = {**guide, "direction": base_direction}
            return guide

    return None


def get_zone_guide_level(guide_data: dict, zone_id: str, visit: int = 1, config: dict | None = None) -> int | None:
    """訪問回数・ルートに応じたガイド側のレベル上書きを返す。"""
    for entry in _collect_guide_candidates(guide_data, zone_id, visit, config):
        guide = _resolve_guide_candidate(entry, active_flags=None, flag_only=False)
        if isinstance(guide, dict) and guide.get("level"):
            return guide["level"]
    return None


def get_visit_guide_for_edit(guide_data: dict, zone_id: str, visit: int = 1, route: str = "") -> dict:
    """編集UI用: 新visits構造/旧フラットキーの両方から指定visitのガイドを取得。"""
    entry = guide_data.get(zone_id, {})
    if isinstance(entry, dict) and _is_visits_entry(entry):
        container = entry
        if route:
            routes = entry.get("routes", {})
            container = routes.get(route, {}) if isinstance(routes, dict) else {}
        visits = container.get("visits", {}) if isinstance(container, dict) else {}
        guide = visits.get(str(visit), {}) if isinstance(visits, dict) else {}
        return guide if isinstance(guide, dict) else {}
    key = zone_id if not route and visit == 1 else f"{zone_id}{'~' + route if route else ''}{'@' + str(visit) if visit != 1 else ''}"
    guide = guide_data.get(key, {})
    return guide if isinstance(guide, dict) else {}


def set_visit_guide_for_edit(guide_data: dict, zone_id: str, guide: dict, visit: int = 1, route: str = ""):
    """編集UI用: 指定visitのガイドを新visits構造に保存。"""
    entry = guide_data.get(zone_id)
    if not isinstance(entry, dict) or not _is_visits_entry(entry):
        old_base = entry if isinstance(entry, dict) and _entry_has_guide_payload(entry) else {}
        entry = {"visits": {}}
        if old_base:
            entry["visits"]["1"] = old_base
        guide_data[zone_id] = entry

    if route:
        routes = entry.setdefault("routes", {})
        container = routes.setdefault(route, {"visits": {}})
    else:
        container = entry
    visits = container.setdefault("visits", {})
    key = str(visit)
    if guide and any(v for v in guide.values()):
        visits[key] = guide
    else:
        visits.pop(key, None)



DIRECTION_ARROWS = {
    "n": "⬆", "s": "⬇", "e": "➡", "w": "⬅",
    "ne": "⬈", "nw": "⬉", "se": "⬊", "sw": "⬋",
    "none": None,
}


def _safe_html(text: str) -> str:
    """HTMLエスケープしつつ、<span style='color:...'> と </span> だけ許可"""
    escaped = html.escape(text)
    # エスケープされた color span タグを復元
    escaped = re.sub(
        r"&lt;span style=(?:&#x27;|&quot;)\s*color:\s*(#[0-9a-fA-F]{3,8})\s*;?\s*(?:&#x27;|&quot;)\s*&gt;",
        r"<span style='color:\1'>",
        escaped,
        flags=re.IGNORECASE,
    )
    escaped = escaped.replace("&lt;/span&gt;", "</span>")
    # ダブルクォートはHTMLコンテンツ内では無害なので戻す
    escaped = escaped.replace("&quot;", '"')
    escaped = escaped.replace("&#x27;", "'")
    return escaped


def format_guide_html(guide: dict, font_size: int = 12, show_direction: bool = True, guide_detail_level: str = "beginner") -> str:
    """ガイドデータをHTML形式にフォーマット"""
    if not guide:
        return ""
    
    summary = guide.get("summary", "")
    if guide_detail_level == "intermediate" and summary:
        summary_html = _safe_html(summary.strip()).replace("\n", "<br>")
        summary_html = summary_html.replace("　", "&nbsp;&nbsp;")
        summary_html = summary_html.replace("  ", "&nbsp;&nbsp;")
        return (
            f"<p style='margin:0;'>"
            f"<b style='color:#b0ff7b; font-size:{font_size}px;'>{tr('guide.heading.summary')}</b><br>"
            f"<span style='color:#ffffff;'>{summary_html}</span>"
            f"</p>"
        )
    
    parts = []
    
    # 方向矢印HTMLを先に作っておく（objectiveの後に挿入）
    direction = guide.get("direction", "")
    direction_html = ""
    if show_direction and direction and direction != "none":
        arrow = DIRECTION_ARROWS.get(direction, "")
        if arrow:
            arrow_size = max(font_size * 3, 36)
            direction_html = (
                f"<div style='margin: 4px 0;'>"
                f"<b style='color:#b0ff7b; font-size:{font_size}px;'>{tr('guide.heading.direction')}</b><br>"
                f"<span style='font-size:{arrow_size}px; color:#FF69B4;'>{arrow}</span>"
                f"</div>"
            )
    elif show_direction and direction == "none":
        direction_html = (
            f"<div style='margin: 4px 0;'>"
            f"<b style='color:#b0ff7b; font-size:{font_size}px;'>{tr('guide.heading.direction')}</b><br>"
            f"<span style='font-size:{font_size + 2}px; color:#888888;'>{tr('guide.heading.direction_reference')}</span>"
            f"</div>"
        )
    
    objective = guide.get("objective", "")
    if objective:
        obj_html = _safe_html(objective.strip()).replace("\n", "<br>")
        obj_html = obj_html.replace("　", "&nbsp;&nbsp;")
        obj_html = obj_html.replace("  ", "&nbsp;&nbsp;")
        parts.append(
            f"<p style='margin:0;'>"
            f"<b style='color:#b0ff7b; font-size:{font_size}px;'>{tr('guide.heading.objective')}</b><br>"
            f"<span style='color:#ffffff;'>{obj_html}</span>"
            f"</p>"
        )
    
    # 目標の後に基本方向を挿入
    if direction_html:
        parts.append(direction_html)
    
    layout = guide.get("layout", "")
    if layout:
        # 改行をbrに変換、全角スペースのインデントを保持
        layout_html = _safe_html(layout.strip()).replace("\n", "<br>")
        layout_html = layout_html.replace("　", "&nbsp;&nbsp;")  # 全角スペース→2つのnbsp
        layout_html = layout_html.replace("  ", "&nbsp;&nbsp;")  # 半角2連続スペースも保持
        parts.append(f"<p style='margin:0;'><b style='color:#b0ff7b;'>{tr('guide.heading.layout')}</b><br>{layout_html}</p>")
    
    tips = guide.get("tips", "")
    if tips:
        tips_html = _safe_html(tips.strip()).replace("\n", "<br>")
        tips_html = tips_html.replace("　", "&nbsp;&nbsp;")
        tips_html = tips_html.replace("  ", "&nbsp;&nbsp;")
        parts.append(f"<p style='margin:0;'><b style='color:#b0ff7b;'>{tr('guide.heading.tips')}</b><br><span style='color:#ffffff;'>{tips_html}</span></p>")
    
    return "<span style='font-size:6px; line-height:50%;'><br></span>".join(parts)
