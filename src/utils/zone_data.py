"""
PoE Act進行ゾーンの適正レベルデータ管理
ユーザーがSettings画面で編集可能。config.jsonに保存。
"""

# デフォルトの適正レベルデータ（PoE1 Act1-10）
# zone_name: エリア名（日本語クライアント準拠）
# level: そのエリアの適正レベル（モンスターレベル基準）
DEFAULT_ZONE_DATA = {
    "Act 1": [
        {"id": "act1_area1", "zone": "黄昏の岸辺", "level": 1},
        {"id": "act1_area2", "zone": "海岸", "level": 2},
        {"id": "act1_area3", "zone": "ぬかるみの干潟", "level": 3},
        {"id": "act1_area4", "zone": "海底通路", "level": 3},
        {"id": "act1_area5", "zone": "陸続きの島", "level": 4},
        {"id": "act1_area6", "zone": "岩棚", "level": 5},
        {"id": "act1_area7", "zone": "険しい山道", "level": 5},
        {"id": "act1_area8", "zone": "牢獄 -下層-", "level": 6},
        {"id": "act1_area9", "zone": "水没した海底洞窟", "level": 6},
        {"id": "act1_area10", "zone": "牢獄 -上層-", "level": 7},
        {"id": "act1_area11", "zone": "監獄長の宿舎", "level": 7},
        {"id": "act1_area12", "zone": "囚人の門", "level": 8},
        {"id": "act1_area13", "zone": "船の墓場", "level": 8},
        {"id": "act1_area14", "zone": "憤怒の洞窟", "level": 8},
        {"id": "act1_area15", "zone": "船の墓場の洞窟", "level": 8},
    ],
    "Act 2": [
        {"id": "act2_area1", "zone": "南方の森", "level": 10},
        {"id": "act2_area2", "zone": "荒廃農地", "level": 10},
        {"id": "act2_area3", "zone": "十字路", "level": 11},
        {"id": "act2_area4", "zone": "獣の巣", "level": 11},
        {"id": "act2_area5", "zone": "罪の間 -第一層-", "level": 12},
        {"id": "act2_area6", "zone": "罪の間 -第二層-", "level": 12},
        {"id": "act2_area7", "zone": "川沿いの道", "level": 12},
        {"id": "act2_area8", "zone": "西の森", "level": 13},
        {"id": "act2_area9", "zone": "編む者の巣穴", "level": 13},
        {"id": "act2_area10", "zone": "壊れた橋", "level": 13},
        {"id": "act2_area11", "zone": "フェルシュラインの遺跡", "level": 13},
        {"id": "act2_area12", "zone": "地下聖堂 lv1", "level": 14},
        {"id": "act2_area13", "zone": "地下聖堂 lv2", "level": 14},
        {"id": "act2_area14", "zone": "湿地", "level": 14},
        {"id": "act2_area15", "zone": "ヴァールの遺跡", "level": 15},
        {"id": "act2_area16", "zone": "北の森", "level": 15},
        {"id": "act2_area17", "zone": "大洞窟", "level": 15},
        {"id": "act2_area18", "zone": "古代のピラミッド", "level": 16},
    ],
    "Act 3": [
        {"id": "act3_area1", "zone": "サーン市街", "level": 16},
        {"id": "act3_area2", "zone": "スラム", "level": 16},
        {"id": "act3_area3", "zone": "火葬場", "level": 17},
        {"id": "act3_area4", "zone": "下水道", "level": 17},
        {"id": "act3_area5", "zone": "市場", "level": 18},
        {"id": "act3_area6", "zone": "地下墓地", "level": 18},
        {"id": "act3_area7", "zone": "戦場", "level": 19},
        {"id": "act3_area8", "zone": "船着場", "level": 19},
        {"id": "act3_area9", "zone": "ソラリス寺院 -第一層-", "level": 19},
        {"id": "act3_area10", "zone": "ソラリス寺院 -第二層-", "level": 20},
        {"id": "act3_area11", "zone": "永遠なる研究所", "level": 20},
        {"id": "act3_area12", "zone": "黒檀の兵舎", "level": 21},
        {"id": "act3_area13", "zone": "ルナリス寺院 -第一層-", "level": 21},
        {"id": "act3_area14", "zone": "ルナリス寺院 -第二層-", "level": 22},
        {"id": "act3_area15", "zone": "帝国の庭園", "level": 22},
        {"id": "act3_area16", "zone": "図書館", "level": 22},
        {"id": "act3_area17", "zone": "公文書館", "level": 22},
        {"id": "act3_area18", "zone": "神の杖", "level": 23},
    ],
    "Act 4": [
        {"id": "act4_area1", "zone": "水道橋", "level": 24},
        {"id": "act4_area2", "zone": "干上がった湖", "level": 24},
        {"id": "act4_area3", "zone": "志す者の広場", "level": 24},
        {"id": "act4_area4", "zone": "鉱山", "level": 25},
        {"id": "act4_area5", "zone": "鉱山 -第二層-", "level": 25},
        {"id": "act4_area6", "zone": "水晶鉱脈", "level": 26},
        {"id": "act4_area7", "zone": "ダレッソの夢", "level": 26},
        {"id": "act4_area8", "zone": "大闘技場", "level": 26},
        {"id": "act4_area9", "zone": "カオムの夢", "level": 26},
        {"id": "act4_area10", "zone": "カオムの要塞", "level": 27},
        {"id": "act4_area11", "zone": "魔獣の内部 lvl1", "level": 27},
        {"id": "act4_area12", "zone": "魔獣の内部 lvl2", "level": 27},
        {"id": "act4_area13", "zone": "魔獣の深部", "level": 27},
        {"id": "act4_area14", "zone": "摘出", "level": 28},
        {"id": "act4_area15", "zone": "ブラックコア", "level": 28},
        {"id": "act4_area16", "zone": "頂への道", "level": 28},
    ],
    "Act 5": [
        {"id": "act5_area1", "zone": "奴隷収容所", "level": 29},
        {"id": "act5_area2", "zone": "奴隷管理区間", "level": 30},
        {"id": "act5_area3", "zone": "オリアス広場", "level": 30},
        {"id": "act5_area4", "zone": "テンプラーの裁判所", "level": 31},
        {"id": "act5_area5", "zone": "イノセンスの間", "level": 31},
        {"id": "act5_area6", "zone": "イノセンスの聖域", "level": 31},
        {"id": "act5_area7", "zone": "焼けた裁判所", "level": 32},
        {"id": "act5_area8", "zone": "破壊された広場", "level": 32},
        {"id": "act5_area9", "zone": "納骨堂", "level": 32},
        {"id": "act5_area10", "zone": "聖廟", "level": 33},
        {"id": "act5_area11", "zone": "大聖堂の屋上", "level": 33},
    ],
    "Act 6": [
        {"id": "act6_area1", "zone": "黄昏の岸辺", "level": 34},
        {"id": "act6_area2", "zone": "海岸", "level": 35},
        {"id": "act6_area3", "zone": "ぬかるみの干潟", "level": 35},
        {"id": "act6_area4", "zone": "カルイの要塞", "level": 35},
        {"id": "act6_area5", "zone": "トゥコハマの砦", "level": 36},
        {"id": "act6_area6", "zone": "尾根", "level": 36},
        {"id": "act6_area7", "zone": "牢獄 -下層-", "level": 37},
        {"id": "act6_area8", "zone": "シャヴロンの塔", "level": 37},
        {"id": "act6_area9", "zone": "監獄長の拷問部屋", "level": 37},
        {"id": "act6_area10", "zone": "囚人の門", "level": 38},
        {"id": "act6_area11", "zone": "西の森", "level": 38},
        {"id": "act6_area12", "zone": "川沿いの道", "level": 38},
        {"id": "act6_area13", "zone": "湿地", "level": 39},
        {"id": "act6_area14", "zone": "産卵場所", "level": 39},
        {"id": "act6_area15", "zone": "南の森", "level": 39},
        {"id": "act6_area16", "zone": "怒りの洞窟", "level": 40},
        {"id": "act6_area17", "zone": "ビーコン", "level": 40},
        {"id": "act6_area18", "zone": "海水の王の岩礁", "level": 40},
        {"id": "act6_area19", "zone": "海水の王の玉座", "level": 40},
    ],
    "Act 7": [
        {"id": "act7_area1", "zone": "壊れた橋", "level": 41},
        {"id": "act7_area2", "zone": "十字路", "level": 42},
        {"id": "act7_area3", "zone": "フェルシュラインの遺跡", "level": 42},
        {"id": "act7_area4", "zone": "地下聖堂", "level": 42},
        {"id": "act7_area5", "zone": "地下聖堂　地下１階", "level": 43},
        {"id": "act7_area6", "zone": "罪の間 lvl1", "level": 43},
        {"id": "act7_area7", "zone": "マリガロの聖域", "level": 43},
        {"id": "act7_area8", "zone": "罪の間 lvl2", "level": 43},
        {"id": "act7_area9", "zone": "獣の巣", "level": 44},
        {"id": "act7_area10", "zone": "焼け野原", "level": 44},
        {"id": "act7_area11", "zone": "要塞の野営地", "level": 44},
        {"id": "act7_area12", "zone": "北の森", "level": 44},
        {"id": "act7_area13", "zone": "囚人の門", "level": 45},
        {"id": "act7_area14", "zone": "火を飲む者の谷", "level": 45},
        {"id": "act7_area15", "zone": "恐怖の密林", "level": 45},
        {"id": "act7_area16", "zone": "絶望のねぐら", "level": 45},
        {"id": "act7_area17", "zone": "土手道", "level": 46},
        {"id": "act7_area18", "zone": "ヴァールの街", "level": 46},
        {"id": "act7_area19", "zone": "堕落の寺院 lvl1", "level": 46},
        {"id": "act7_area20", "zone": "堕落の寺院 lvl2", "level": 46},
        {"id": "act7_area21", "zone": "アラカーリの巣", "level": 47},
    ],
    "Act 8": [
        {"id": "act8_area1", "zone": "サーンの城壁", "level": 46},
        {"id": "act8_area2", "zone": "志す者の広場", "level": 46},
        {"id": "act8_area3", "zone": "有毒な排水路", "level": 47},
        {"id": "act8_area4", "zone": "ドードゥリの汚水槽", "level": 47},
        {"id": "act8_area5", "zone": "大釜", "level": 48},
        {"id": "act8_area6", "zone": "波止場", "level": 48},
        {"id": "act8_area7", "zone": "復活の地", "level": 48},
        {"id": "act8_area8", "zone": "穀物倉庫", "level": 49},
        {"id": "act8_area9", "zone": "帝国の穀倉地帯", "level": 49},
        {"id": "act8_area10", "zone": "ソラリス寺院 lvl1", "level": 49},
        {"id": "act8_area11", "zone": "ソラリス寺院 lvl2", "level": 50},
        {"id": "act8_area12", "zone": "ソラリスの中央広場", "level": 50},
        {"id": "act8_area13", "zone": "港の橋", "level": 50},
        {"id": "act8_area14", "zone": "ルナリスの中央広場", "level": 50},
        {"id": "act8_area15", "zone": "ルナリス寺院 lvl1", "level": 50},
        {"id": "act8_area16", "zone": "ルナリス寺院 lvl2", "level": 51},
        {"id": "act8_area17", "zone": "天空神殿", "level": 51},
        {"id": "act8_area18", "zone": "血の水道橋", "level": 51},
        {"id": "act8_area19", "zone": "浴場", "level": 52},
        {"id": "act8_area20", "zone": "空中庭園", "level": 52},
        {"id": "act8_area21", "zone": "恐怖の池", "level": 52},
    ],
    "Act 9": [
        {"id": "act9_area1", "zone": "谷底への道", "level": 53},
        {"id": "act9_area2", "zone": "ヴァスティリ砂漠", "level": 53},
        {"id": "act9_area3", "zone": "オアシス", "level": 54},
        {"id": "act9_area4", "zone": "砂のくぼみ", "level": 54},
        {"id": "act9_area5", "zone": "山麓", "level": 55},
        {"id": "act9_area6", "zone": "沸き立つ湖", "level": 55},
        {"id": "act9_area7", "zone": "坑道", "level": 55},
        {"id": "act9_area8", "zone": "採石場", "level": 56},
        {"id": "act9_area9", "zone": "精錬所", "level": 56},
        {"id": "act9_area10", "zone": "風の祠", "level": 56},
        {"id": "act9_area11", "zone": "魔獣の内部", "level": 57},
        {"id": "act9_area12", "zone": "腐った核", "level": 57},
        {"id": "act9_area13", "zone": "ブラックコア", "level": 57},
        {"id": "act9_area14", "zone": "ブラックハード", "level": 58},
    ],
    "Act 10": [
        {"id": "act10_area1", "zone": "大聖堂の屋上", "level": 58},
        {"id": "act10_area2", "zone": "聖堂の屋上", "level": 58},
        {"id": "act10_area3", "zone": "荒廃した広場", "level": 59},
        {"id": "act10_area4", "zone": "奴隷管理区間", "level": 59},
        {"id": "act10_area5", "zone": "アリーナ", "level": 59},
        {"id": "act10_area6", "zone": "納骨堂", "level": 60},
        {"id": "act10_area7", "zone": "骨の穴", "level": 60},
        {"id": "act10_area8", "zone": "焼けた裁判所", "level": 60},
        {"id": "act10_area9", "zone": "冒涜された広間", "level": 61},
        {"id": "act10_area10", "zone": "イノセンスの聖域", "level": 61},
        {"id": "act10_area11", "zone": "志す者の広場", "level": 62},
        {"id": "act10_area12", "zone": "オリアスの船着場（街）", "level": 62},
        {"id": "act10_area13", "zone": "運河", "level": 63},
        {"id": "act10_area14", "zone": "餌場", "level": 64},
        {"id": "act10_area15", "zone": "渇望の祭壇", "level": 67},
    ],
}


def get_zone_info(zone_data: dict, zone_name: str, part2: bool = False) -> tuple:
    """
    エリア名から適正レベルとAct情報を検索
    part2=True の場合、Act 6-10を優先検索（同名エリア対策）
    
    Returns:
        (act_name, zone_level) or (None, None) if not found
    """
    if part2:
        # Part 2: Act 6-10を先に検索
        search_order = [k for k in zone_data if k in ("Act 6","Act 7","Act 8","Act 9","Act 10")]
        search_order += [k for k in zone_data if k not in search_order]
    else:
        # Part 1: Act 1-5を先に検索
        search_order = [k for k in zone_data if k in ("Act 1","Act 2","Act 3","Act 4","Act 5")]
        search_order += [k for k in zone_data if k not in search_order]
    
    for act_name in search_order:
        for z in zone_data.get(act_name, []):
            if z["zone"] == zone_name:
                return act_name, z["level"]
    return None, None


def get_level_advice(player_level: int, zone_level: int) -> tuple:
    """
    PoE公式XPペナルティ計算式に基づくレベルアドバイス
    
    - ペナルティ許容範囲 = player_level // 16 + 3
    - 最適レベル範囲 = player_level // 16 + 2（キャラLv ≤ エリアLv の場合）
    
    Returns:
        (message, color) — 表示メッセージとカラーコード
    """
    safe_range = player_level // 16 + 3      # ペナルティなし範囲
    optimal_margin = player_level // 16 + 2  # 最適レベル余裕
    diff = player_level - zone_level  # 正=キャラ高い、負=キャラ低い
    
    if abs(diff) > safe_range:
        if diff > 0:
            return f"🔴 ペナルティ (+{diff}) — レベル超過！経験値減少中", "#ff4444"
        else:
            return f"🔴 ペナルティ ({diff:+d}) — レベル不足！経験値減少中", "#ff4444"
    
    # ペナルティなし範囲内
    if diff <= 0 and abs(diff) <= optimal_margin:
        # キャラがエリアと同じか低い、かつ最適マージン内
        if diff == 0:
            return "🟢 最適レベル (±0)", "#b0ff7b"
        return f"🟢 最適レベル ({diff:+d})", "#b0ff7b"
    
    # ペナルティなし（最適ではない）
    if diff > 0:
        return f"🟡 ペナルティなし (+{diff}) — ややレベル上がり気味", "#ffff66"
    else:
        return f"🟡 ペナルティなし ({diff:+d}) — ややレベル不足気味", "#ffff66"
