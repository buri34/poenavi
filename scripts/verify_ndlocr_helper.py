"""Smoke-test the packaged NDLOCR helper with the reported physical-64 image."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from PySide6.QtGui import QImage

from src.poetore.poe2.desecration_ocr import image_bytes, prepare_desecration_frame
from src.poetore.poe2.ndlocr_lite import NdlOcrLiteServer

EXPECTED = "物理ダメージが64%増加する"


def verify(helper: Path, image_path: Path) -> str:
    image = QImage(str(image_path))
    prepared = prepare_desecration_frame(image)
    if image.isNull() or not prepared.valid_panel or len(prepared.ndl_images) != 3:
        raise RuntimeError("NDLOCRスモークテスト画像を切り出せませんでした。")
    result = NdlOcrLiteServer(helper=helper, timeout=120).recognize([
        image_bytes(prepared.ndl_images[0]),
    ])[0]
    compact = re.sub(r"\s+", "", result.text)
    if compact != EXPECTED:
        raise RuntimeError(f"NDLOCRスモークテスト不一致: {result.text!r}")
    return compact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    args = parser.parse_args()
    print(verify(args.helper, args.image))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
