"""Self-contained NDLOCR-Lite sidecar used only for safe numeric rescue."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NdlOcrResult:
    text: str
    confidence: float | None = None


def _helper_path() -> Path:
    configured = os.environ.get("POENAVI_NDLOCR_HELPER")
    if configured:
        helper = Path(configured)
        if helper.is_file():
            return helper
        raise RuntimeError(f"NDLOCRヘルパーが見つかりません: {helper}")
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    helper = root / "tools" / "NDLOcrLite" / "PoENaviNdlOcr.exe"
    if helper.is_file():
        return helper
    raise RuntimeError("NDLOCRヘルパーが配布物に含まれていません。")


def _payload_result(payload: dict) -> NdlOcrResult:
    lines: list[tuple[float, str]] = []
    confidences: list[float] = []
    for page in payload.get("contents", []):
        if not isinstance(page, list):
            continue
        for line in page:
            if not isinstance(line, dict):
                continue
            text = str(line.get("text") or "").strip()
            box = line.get("boundingBox") or []
            ys = [float(point[1]) for point in box if len(point) >= 2]
            center = sum(ys) / len(ys) if ys else float(len(lines))
            if text:
                lines.append((center, text))
            confidence = line.get("confidence")
            if isinstance(confidence, (int, float)):
                confidences.append(float(confidence))
    return NdlOcrResult(
        text="\n".join(text for _center, text in sorted(lines)),
        confidence=min(confidences) if confidences else None,
    )


class NdlOcrLiteServer:
    """Run the bundled CPU-only helper once for the requested image batch."""

    def __init__(self, *, helper: Path | None = None, timeout: float = 90.0):
        self.helper = helper
        self.timeout = timeout

    def recognize(self, images: Sequence[bytes]) -> list[NdlOcrResult]:
        if not images:
            return []
        helper = self.helper or _helper_path()
        if not helper.is_file():
            raise RuntimeError(f"NDLOCRヘルパーが見つかりません: {helper}")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with tempfile.TemporaryDirectory(prefix="poenavi-ndlocr-") as temporary:
            root = Path(temporary)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()
            output_dir.mkdir()
            for index, image in enumerate(images):
                (input_dir / f"choice-{index:03d}.bmp").write_bytes(image)
            completed = subprocess.run(
                [
                    str(helper), "--sourcedir", str(input_dir),
                    "--output", str(output_dir), "--json-only",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                creationflags=creationflags,
                check=False,
            )
            if completed.returncode != 0:
                details = completed.stderr.strip() or completed.stdout.strip()
                raise RuntimeError(details or "NDLOCRの実行に失敗しました。")
            results = []
            for index in range(len(images)):
                path = output_dir / f"choice-{index:03d}.json"
                if not path.is_file():
                    raise RuntimeError("NDLOCRの結果ファイルが不足しています。")
                results.append(_payload_result(json.loads(path.read_text(encoding="utf-8"))))
            return results

    def close(self) -> None:
        """The helper is one-shot, so no persistent process needs closing."""
