"""
PoE Client.txt ログ監視モジュール
エリア入場とレベルアップを検知してシグナルを発行する。
"""

import os
import re
from PySide6.QtCore import QObject, QTimer, Signal


class LogWatcher(QObject):
    """Client.txtをポーリングで監視し、イベントをシグナルで通知"""
    
    # シグナル定義
    zone_entered = Signal(str)      # エリア名 (例: "地下墓地")
    level_up = Signal(str, int)     # キャラ名, レベル
    
    # ログ行のパターン（日本語クライアント）
    # "あなたは地下墓地に入場しました。"
    ZONE_PATTERN_JA = re.compile(r"あなたは(.+?)に入場しました。")
    # "testshadwwww  (シャドウ )はレベル24になりました"
    LEVEL_PATTERN_JA = re.compile(r"(.+?)\s*(?:\(.+?\)\s*)?はレベル(\d+)になりました")
    
    # English client patterns (fallback)
    ZONE_PATTERN_EN = re.compile(r": You have entered (.+?)\.")
    LEVEL_PATTERN_EN = re.compile(r"(.+?) \(.+?\) is now level (\d+)")
    
    def __init__(self, log_path: str = "", poll_interval_ms: int = 500, parent=None):
        super().__init__(parent)
        self.log_path = log_path
        self.poll_interval_ms = poll_interval_ms
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
                    if m:
                        zone_name = m.group(1).strip()
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
            self.zone_entered.emit(zone_name)
            return
        
        # エリア入場チェック（英語）
        m = self.ZONE_PATTERN_EN.search(line)
        if m:
            zone_name = m.group(1).strip()
            self.zone_entered.emit(zone_name)
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
