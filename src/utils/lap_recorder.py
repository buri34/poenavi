import json
import os
from datetime import datetime

class LapRecorder:
    """ラップタイムをファイルに保存するクラス"""
    
    RUNS_DIR = "runs"
    
    @classmethod
    def ensure_runs_dir(cls):
        """runsディレクトリを作成"""
        if not os.path.exists(cls.RUNS_DIR):
            os.makedirs(cls.RUNS_DIR)
    
    @classmethod
    def save_run(cls, lap_times: list, total_time: float) -> str:
        """
        ラン記録を保存
        
        Args:
            lap_times: Act 1-10のラップタイム（秒）のリスト。未記録はNone。
            total_time: 総経過時間（秒）
            
        Returns:
            保存したファイルパス
        """
        cls.ensure_runs_dir()
        
        timestamp = datetime.now()
        filename = timestamp.strftime("%Y%m%d_%H%M%S") + ".json"
        filepath = os.path.join(cls.RUNS_DIR, filename)
        
        # ラップデータを辞書形式に変換
        laps = {}
        for i, lap_time in enumerate(lap_times):
            act_name = f"Act {i + 1}"
            laps[act_name] = lap_time  # Noneの場合もそのまま保存
        
        data = {
            "timestamp": timestamp.isoformat(),
            "total_time": total_time,
            "laps": laps
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"Run saved: {filepath}")
        return filepath
    
    @classmethod
    def load_runs(cls) -> list:
        """
        過去のラン記録を読み込み
        
        Returns:
            ラン記録のリスト（新しい順）
        """
        cls.ensure_runs_dir()
        
        runs = []
        for filename in os.listdir(cls.RUNS_DIR):
            if filename.endswith(".json"):
                filepath = os.path.join(cls.RUNS_DIR, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        data["filename"] = filename
                        runs.append(data)
                except Exception as e:
                    print(f"Failed to load {filename}: {e}")
        
        # 新しい順にソート
        runs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return runs
