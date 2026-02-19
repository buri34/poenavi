"""
攻略ガイドデータ管理
ゾーンIDをキーに、攻略テキスト（HTML対応）を返す。
データは guide_data.json から読み込み。ユーザー編集可能。
"""

import json
import os

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

GUIDE_FILE = "guide_data.json"


def get_guide_dir():
    """ガイドデータファイルのディレクトリ（exeと同じ場所）"""
    # main.pyの場所を基準にする
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_guide_data() -> dict:
    """ガイドデータを読み込み"""
    path = os.path.join(get_guide_dir(), GUIDE_FILE)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[GuideData] Failed to load: {e}")
    return DEFAULT_GUIDE


def save_guide_data(data: dict):
    """ガイドデータを保存"""
    path = os.path.join(get_guide_dir(), GUIDE_FILE)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[GuideData] Saved: {path}")
    except Exception as e:
        print(f"[GuideData] Failed to save: {e}")


def get_zone_guide(guide_data: dict, zone_id: str, visit: int = 1) -> dict | None:
    """
    ゾーンIDからガイドを検索
    visit>=2 の場合、"{zone_id}@2" を優先検索（再訪問対策）
    なければ {zone_id} にフォールバック
    
    Returns:
        {"objective": str, "layout": str, "tips": str, "direction": str?} or None
    """
    # 1回目のガイドを取得（フォールバック用）
    base_guide = guide_data.get(zone_id)
    
    # 2回目以降は @N キーを優先
    if visit >= 2:
        v_key = f"{zone_id}@{visit}"
        v_guide = guide_data.get(v_key)
        if v_guide:
            # directionが@Nに無ければ1回目から引き継ぐ
            if "direction" not in v_guide and base_guide and "direction" in base_guide:
                v_guide = {**v_guide, "direction": base_guide["direction"]}
            return v_guide
    
    return base_guide


DIRECTION_ARROWS = {
    "n": "⬆", "s": "⬇", "e": "➡", "w": "⬅",
    "ne": "⬈", "nw": "⬉", "se": "⬊", "sw": "⬋",
    "none": None,
}


def format_guide_html(guide: dict, font_size: int = 12) -> str:
    """ガイドデータをHTML形式にフォーマット"""
    if not guide:
        return ""
    
    parts = []
    
    # 方向矢印HTMLを先に作っておく（objectiveの後に挿入）
    direction = guide.get("direction", "")
    direction_html = ""
    if direction and direction != "none":
        arrow = DIRECTION_ARROWS.get(direction, "")
        if arrow:
            arrow_size = max(font_size * 3, 36)
            direction_html = (
                f"<div style='margin: 4px 0;'>"
                f"<b style='color:#b0ff7b; font-size:{font_size}px;'>🧭 基本方向</b><br>"
                f"<span style='font-size:{arrow_size}px; color:#FF69B4;'>{arrow}</span>"
                f"</div>"
            )
    elif direction == "none":
        direction_html = (
            f"<div style='margin: 4px 0;'>"
            f"<b style='color:#b0ff7b; font-size:{font_size}px;'>🧭 基本方向</b><br>"
            f"<span style='font-size:{font_size + 2}px; color:#888888;'>📖 ガイド参照</span>"
            f"</div>"
        )
    
    objective = guide.get("objective", "")
    if objective:
        obj_html = objective.replace("\n", "<br>")
        obj_html = obj_html.replace("　", "&nbsp;&nbsp;")
        obj_html = obj_html.replace("  ", "&nbsp;&nbsp;")
        parts.append(f"<b style='color:#b0ff7b; font-size:{font_size}px;'>📋 {obj_html}</b>")
    
    # 目標の後に基本方向を挿入
    if direction_html:
        parts.append(direction_html)
    
    layout = guide.get("layout", "")
    if layout:
        # 改行をbrに変換、全角スペースのインデントを保持
        layout_html = layout.replace("\n", "<br>")
        layout_html = layout_html.replace("　", "&nbsp;&nbsp;")  # 全角スペース→2つのnbsp
        layout_html = layout_html.replace("  ", "&nbsp;&nbsp;")  # 半角2連続スペースも保持
        parts.append(f"<div style='margin-top:5px;'><b style='color:#b0ff7b;'>🗺️ レイアウト情報</b><br>{layout_html}</div>")
    
    tips = guide.get("tips", "")
    if tips:
        tips_html = tips.replace("\n", "<br>")
        tips_html = tips_html.replace("　", "&nbsp;&nbsp;")
        tips_html = tips_html.replace("  ", "&nbsp;&nbsp;")
        parts.append(f"<div style='margin-top:5px; color:#aaaaaa;'>{tips_html}</div>")
    
    return "<br>".join(parts)
