"""
PoE Client.txt ログ監視モジュール
エリア入場とレベルアップを検知してシグナルを発行する。
PoE1/PoE2で最終クリアイベントの文言が異なる可能性を考慮する。
"""

import os
import re
from PySide6.QtCore import QObject, QTimer, Signal

from src.utils.poe_version_data import POE1


class LogWatcher(QObject):
    """Client.txtをポーリングで監視し、イベントをシグナルで通知"""
    
    # シグナル定義
    zone_entered = Signal(str)      # エリア名 (例: "地下墓地")
    actual_zone_entered = Signal(str)  # Client.txtの明示的な入場ログ（復元・Set Sourceを除く）
    level_up = Signal(str, int)     # キャラ名, レベル
    kitava_defeated = Signal()      # Act5キタヴァ討伐検知
    act10_cleared = Signal()        # Act10キタヴァ討伐検知
    act4_cleared = Signal()         # PoE2 Act4クリア検知
    progress_flag_detected = Signal(str)  # PoE2進行フラグ (例: act1_rustking_dead)
    
    # ログ行のパターン（日本語クライアント）
    # "あなたは地下墓地に入場しました。"
    ZONE_PATTERN_JA = re.compile(r"あなたは(.+?)に入場しました。")
    # "testshadwwww  (シャドウ )はレベル24になりました"
    LEVEL_PATTERN_JA = re.compile(r"(.+?)\s*(?:\(.+?\)\s*)?はレベル(\d+)になりました")
    
    # English client patterns (fallback)
    ZONE_PATTERN_EN = re.compile(r": You have entered (.+?)\.")
    LEVEL_PATTERN_EN = re.compile(r"(.+?) \(.+?\) is now level (\d+)")
    
    # Set Source pattern (works regardless of chat tab settings)
    # e.g. "[SCENE] Set Source [ハイゲート]" or "[SCENE] Set Source [The Coast]"
    SET_SOURCE_PATTERN = re.compile(r"\[SCENE\] Set Source \[(.+?)\]")
    
    def __init__(self, log_path: str = "", poll_interval_ms: int = 500, parent=None):
        super().__init__(parent)
        self.log_path = log_path
        self.poll_interval_ms = poll_interval_ms
        self.poe_version = POE1
        self._file_pos = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._active = False
    
    def set_log_path(self, path: str):
        """ログファイルパスを設定（監視中なら再起動）"""
        was_active = self._active
        if was_active:
            self.stop()
        self.log_path = path
        self._file_pos = 0
        if was_active:
            self.start()

    def set_poe_version(self, poe_version: str):
        self.poe_version = poe_version

    @property
    def is_active(self) -> bool:
        return self._active

    def set_poll_interval(self, interval_ms: int):
        """監視間隔を変更し、監視中なら即時反映する。"""
        self.poll_interval_ms = max(1, int(interval_ms))
        if self._active:
            self._timer.start(self.poll_interval_ms)
    
    def start(self):
        """監視開始"""
        if not self.log_path or not os.path.exists(self.log_path):
            print(f"[LogWatcher] File not found: {self.log_path}")
            return False
        
        # 起動時に最新のレベルとゾーンを復元
        self._restore_latest_state()
        
        # ファイル末尾にシーク（過去ログは無視）
        try:
            self._file_pos = os.path.getsize(self.log_path)
        except OSError:
            self._file_pos = 0
        
        self._active = True
        self._timer.start(self.poll_interval_ms)
        print(f"[LogWatcher] Started watching: {self.log_path}")
        return True
    
    def _restore_latest_state(self):
        """ログファイル末尾から最新のレベルとゾーンを復元"""
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                # 末尾から読む（大きいファイルなので全部は読まない）
                f.seek(0, 2)
                file_size = f.tell()
                # 最大500KB分だけ末尾から読む（十分な量）
                read_size = min(file_size, 512 * 1024)
                f.seek(file_size - read_size)
                tail = f.read()
            
            lines = tail.splitlines()
            
            found_level = False
            found_zone = False
            
            # 末尾から逆順に検索
            for line in reversed(lines):
                if not found_level:
                    m = self.LEVEL_PATTERN_JA.search(line)
                    if not m:
                        m = self.LEVEL_PATTERN_EN.search(line)
                    if m:
                        char_name = m.group(1).strip()
                        level = int(m.group(2))
                        self.level_up.emit(char_name, level)
                        found_level = True
                        print(f"[LogWatcher] Restored level: {char_name} Lv.{level}")
                
                if not found_zone:
                    m = self.ZONE_PATTERN_JA.search(line)
                    if not m:
                        m = self.ZONE_PATTERN_EN.search(line)
                    if not m:
                        m = self.SET_SOURCE_PATTERN.search(line)
                    if m:
                        zone_name = m.group(1).strip()
                        if zone_name in ("(null)", "(unknown)"):
                            continue  # 無効エントリをスキップ
                        self.zone_entered.emit(zone_name)
                        found_zone = True
                        print(f"[LogWatcher] Restored zone: {zone_name}")
                
                if found_level and found_zone:
                    break
                    
        except Exception as e:
            print(f"[LogWatcher] Failed to restore state: {e}")
    
    def stop(self):
        """監視停止"""
        self._active = False
        self._timer.stop()
        print("[LogWatcher] Stopped")
    
    def _poll(self):
        """定期的にファイルの新規行を読み取る"""
        if not self.log_path or not os.path.exists(self.log_path):
            return
        
        try:
            current_size = os.path.getsize(self.log_path)
            
            # ファイルが小さくなった場合（ログリセット）
            if current_size < self._file_pos:
                self._file_pos = 0
            
            if current_size == self._file_pos:
                return  # 変更なし
            
            with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(self._file_pos)
                new_data = f.read()
                self._file_pos = f.tell()
            
            lines = new_data.splitlines()
            if lines:
                print(f"[LogWatcher] Read {len(lines)} new lines (pos={self._file_pos})")
            for line in lines:
                self._parse_line(line)
                
        except Exception as e:
            print(f"[LogWatcher] Error polling: {e}")
    
    def _parse_line(self, line: str):
        """1行をパースしてシグナルを発行"""
        # エリア入場チェック（日本語）
        m = self.ZONE_PATTERN_JA.search(line)
        if m:
            zone_name = m.group(1).strip()
            print(f"[LogWatcher] Zone detected: {zone_name} (pos={self._file_pos}, line={line.strip()[:80]})")
            self.actual_zone_entered.emit(zone_name)
            self.zone_entered.emit(zone_name)
            return
        
        # エリア入場チェック（英語）
        m = self.ZONE_PATTERN_EN.search(line)
        if m:
            zone_name = m.group(1).strip()
            print(f"[LogWatcher] Zone detected: {zone_name} (pos={self._file_pos}, line={line.strip()[:80]})")
            self.actual_zone_entered.emit(zone_name)
            self.zone_entered.emit(zone_name)
            return
        
        # Set Source検知（Local chat tab無効時のフォールバック）
        m = self.SET_SOURCE_PATTERN.search(line)
        if m:
            zone_name = m.group(1).strip()
            if zone_name in ("(null)", "(unknown)"):
                return  # 遷移時に出る無効なエントリを無視
            if (
                re.fullmatch(r"アクト\d+", zone_name)
                or re.fullmatch(r"Act\s*\d+", zone_name, re.IGNORECASE)
                or zone_name in ("幕間", "Interlude")
            ):
                return  # ウェイポイント帰還などで一瞬出る章名はガイド更新対象にしない
            print(f"[LogWatcher] Zone detected (Set Source): {zone_name} (pos={self._file_pos}, line={line.strip()[:80]})")
            self.zone_entered.emit(zone_name)
            return
        
        if self.poe_version != POE1:
            if "錆の王:" in line or "The Rust King:" in line:
                self.progress_flag_detected.emit("act1_rustking_dead")
                return
            if "永遠なる法務官、" in line or "Draven, the Eternal Praetor:" in line:
                self.progress_flag_detected.emit("act1_draven_dead")
                return
            if "法務官の妻、" in line or "Asinia, the Praetor's Consort:" in line:
                self.progress_flag_detected.emit("act1_asinia_dead")
                return
            if "汚物の女王:" in line or "Queen of Filth:" in line:
                self.progress_flag_detected.emit("act3_queenfilth_dead")
                return
            if "ハートリン船長:" in line or "Captain Hartlin:" in line:
                self.progress_flag_detected.emit("act4_hartlin_dead")
                return
            if "フードをかぶった者: 終わりだ、タヴァカイ。" in line or "The Hooded One: It is over, Tavakai." in line:
                self.progress_flag_detected.emit("act4_tavakai_dead")
                self.act4_cleared.emit()
                return
            if "ウーナ: 自然の精たちが！何を" in line or "Una: The fey spirits!" in line:
                self.progress_flag_detected.emit("interlude1_siora_dead")
                return
            if "恐怖の看守、オスウィン:" in line or "Oswin, The Dread Warden:" in line:
                self.progress_flag_detected.emit("interlude1_veynar_dead")
                return

        # PoE1固有: Act10キタヴァ討伐チェック（無慈悲 = Act10）
        if self.poe_version == POE1 and (
           "プレイヤーはキタヴァの無慈悲な苦悩により永続的に弱体化した" in line or \
           "Kitava's merciless affliction" in line):
            self.act10_cleared.emit()
            return
        
        # PoE1固有: Act5キタヴァ討伐チェック（残酷 = Act5）
        if self.poe_version == POE1 and (
           "プレイヤーはキタヴァの残酷な苦悩により永続的に弱体化した" in line or \
           "Kitava's cruel affliction" in line):
            self.kitava_defeated.emit()
            return
        
        # レベルアップチェック（日本語）
        m = self.LEVEL_PATTERN_JA.search(line)
        if m:
            char_name = m.group(1).strip()
            level = int(m.group(2))
            self.level_up.emit(char_name, level)
            return
        
        # レベルアップチェック（英語）
        m = self.LEVEL_PATTERN_EN.search(line)
        if m:
            char_name = m.group(1).strip()
            level = int(m.group(2))
            self.level_up.emit(char_name, level)
            return
