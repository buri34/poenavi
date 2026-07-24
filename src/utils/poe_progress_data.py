"""PoEバージョン別の進行・ラップ・クリアメッセージ定義"""

from src.utils.poe_version_data import POE1, POE2
from src.utils.i18n import EN, get_locale

AUTO_LAP_TRIGGERS = {
    POE1: {
        "南の森": 1, "The Southern Forest": 1,
        "サーン市街": 2, "The City of Sarn": 2,
        "水道橋": 3, "The Aqueduct": 3,
        "奴隷収容所": 4, "The Slave Pens": 4,
        "橋の野営地": 6, "The Bridge Encampment": 6,
        "サーンの城壁": 7, "The Sarn Ramparts": 7,
        "血の水道橋": 8, "The Blood Aqueduct": 8,
        "オリアスの船着場": 9, "Oriath Docks": 9,
    },
    POE2: {
        "ヴァスティリ郊外": 1,
        "Vastiri Outskirts": 1,
        "砂原の沼地": 2,
        "Sandswept Marsh": 2,
        "キングスマーチ": 3,
        "Kingsmarch": 3,
        "ジッグラトの避難所": 8,
        "The Ziggurat Refuge": 8,
    },
}

CLEAR_MESSAGES = {
    POE1: {
        "final": (
            '<div style="text-align: center; padding: 20px;">'
            '<span style="font-size: 24px; color: #ffd700;">🎉</span><br>'
            '<span style="font-size: 18px; color: #ffd700; font-weight: bold;">'
            'Act10クリア！</span><br><br>'
            '<span style="font-size: 16px; color: #e0e0e0;">'
            'お疲れ様でした！</span><br><br>'
            '<span style="font-size: 13px; color: #b0ffb0;">'
            'チャットコマンドに「/passives」を入力して、パッシブポイントの取り忘れがないかチェックしましょう。<br>'
            'Act2のバンディットクエストで全員倒していれば24pt、それ以外は23ptになっていればOK</span>'
            '</div>'
        )
    },
    POE2: {
        "final": (
            '<div style="text-align: center; padding: 20px;">'
            '<span style="font-size: 18px; color: #ffd700; font-weight: bold;">'
            '🎉キャンペーンクリア！</span><br><br>'
            '<span style="font-size: 18px; color: #e0e0e0;">'
            'パッシブツリーを確認し、パッシブポイントの取り忘れがないかチェックしましょう。<br>'
            '右上の武器セットポイントが24になっていればOK</span>'
            '</div>'
        )
    },
}

SPECIAL_LAP_EVENTS = {
    POE1: {
        "kitava_act5": 5,
        "final_clear": 10,
    },
    POE2: {
        "act4_clear": 4,
        "final_clear": 8,
    },
}


def get_auto_lap_triggers(poe_version: str) -> dict:
    return AUTO_LAP_TRIGGERS.get(poe_version, {})


def get_clear_message(poe_version: str, key: str = "final") -> str:
    message = CLEAR_MESSAGES.get(poe_version, {}).get(key, "")
    if get_locale() != EN or key != "final":
        return message
    if poe_version == POE1:
        return (
            '<div style="text-align: center; padding: 20px;">'
            '<span style="font-size: 24px; color: #ffd700;">🎉</span><br>'
            '<span style="font-size: 18px; color: #ffd700; font-weight: bold;">Act 10 complete!</span><br><br>'
            '<span style="font-size: 16px; color: #e0e0e0;">Well done!</span><br><br>'
            '<span style="font-size: 13px; color: #b0ffb0;">'
            'Enter "/passives" in chat and check that no passive points are missing.<br>'
            'If you defeated all bandits in Act 2, the total should be 24 points; otherwise it should be 23.</span>'
            '</div>'
        )
    return (
        '<div style="text-align: center; padding: 20px;">'
        '<span style="font-size: 18px; color: #ffd700; font-weight: bold;">🎉 Campaign complete!</span><br><br>'
        '<span style="font-size: 18px; color: #e0e0e0;">Check your passive tree and make sure no passive points are missing.<br>'
        'Your weapon set points in the top-right should be 24.</span>'
        '</div>'
    )


def get_special_lap_event(poe_version: str, key: str):
    return SPECIAL_LAP_EVENTS.get(poe_version, {}).get(key)
