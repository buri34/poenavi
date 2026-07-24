"""キャンペーン中のエリア区間時間を記録する。"""

import copy


class SegmentRecorder:
    """エリア入場イベントから、完了した区間を生成する。"""

    def __init__(self, state: list[dict] | dict | None = None):
        if isinstance(state, dict):
            segments = state.get("segments")
            current = state.get("current")
            visits = state.get("visits")
        else:
            segments = state
            current = None
            visits = None

        self.segments = copy.deepcopy(list(segments or []))
        self._current = copy.deepcopy(current) if isinstance(current, dict) else None
        self._visits = {}

        for segment in self.segments:
            zone_id = segment.get("zone_id")
            visit = segment.get("visit")
            if zone_id and isinstance(visit, int):
                self._visits[zone_id] = max(self._visits.get(zone_id, 0), visit)
        if isinstance(visits, dict):
            for zone_id, visit in visits.items():
                if zone_id and isinstance(visit, int):
                    self._visits[zone_id] = max(self._visits.get(zone_id, 0), visit)
        if self._current:
            zone_id = self._current.get("zone_id")
            visit = self._current.get("visit")
            if zone_id and isinstance(visit, int):
                self._visits[zone_id] = max(self._visits.get(zone_id, 0), visit)

    def to_state(self) -> dict:
        return {
            "segments": copy.deepcopy(self.segments),
            "current": copy.deepcopy(self._current),
            "visits": dict(self._visits),
        }

    def record_entry(self, zone_id: str, zone_name: str, elapsed_time: float) -> dict | None:
        """入場時に直前エリアの区間を確定し、新しい区間を開始する。"""
        zone_id = zone_id or zone_name
        if self._current and self._current["zone_id"] == zone_id:
            return None

        completed = None
        if self._current:
            completed = {
                **self._current,
                "ended_at": elapsed_time,
                "duration": max(0.0, elapsed_time - self._current["started_at"]),
            }
            self.segments.append(completed)

        visit = self._visits.get(zone_id, 0) + 1
        self._visits[zone_id] = visit
        self._current = {
            "zone_id": zone_id,
            "zone_name": zone_name,
            "visit": visit,
            "started_at": elapsed_time,
        }
        return completed

    def reset(self):
        self.segments = []
        self._current = None
        self._visits = {}

    def slowest_segments(self) -> list[dict]:
        return sorted(self.segments, key=lambda segment: segment.get("duration", 0.0), reverse=True)[:3]

    def summary(self) -> dict:
        """画面表示用に直近区間と遅い区間をまとめる。"""
        return {
            "latest": self.segments[-1] if self.segments else None,
            "slowest": self.slowest_segments(),
        }
