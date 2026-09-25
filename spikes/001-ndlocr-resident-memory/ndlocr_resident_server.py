"""Persistent NDLOCR-Lite process used only by the Windows memory spike."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

EXPECTED_TEXT = "物理ダメージが64%増加する"


def model_paths(resource_root: Path) -> dict[str, Path]:
    return {
        "det_weights": resource_root / "model" / "deim-s-1024x1024.onnx",
        "det_classes": resource_root / "config" / "ndl.yaml",
        "rec_weights30": resource_root / "model"
        / "parseq-ndl-24x256-30-tiny-189epoch-tegaki3-r8data-202604.onnx",
        "rec_weights50": resource_root / "model"
        / "parseq-ndl-24x384-50-tiny-300epoch-tegaki3-r8data-202604.onnx",
        "rec_weights": resource_root / "model"
        / "parseq-ndl-24x768-100-tiny-153epoch-tegaki3-r8data-202604.onnx",
        "rec_classes": resource_root / "config" / "NDLmoji.yaml",
    }


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    os.replace(temporary, path)


def compact(text: str) -> str:
    return "".join(str(text or "").split())


def response_payload(result: dict, elapsed_ms: float) -> dict:
    text = str(result.get("text") or "")
    lines = result.get("json_lines") or []
    confidences = [
        float(line["confidence"])
        for line in lines
        if isinstance(line, dict) and isinstance(line.get("confidence"), (int, float))
    ]
    return {
        "ok": True,
        "elapsed_ms": round(elapsed_ms, 3),
        "text": text,
        "expected_text_found": compact(EXPECTED_TEXT) in compact(text),
        "minimum_confidence": min(confidences) if confidences else None,
    }


def _runtime_args(resource_root: Path) -> SimpleNamespace:
    paths = model_paths(resource_root)
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise RuntimeError("Missing NDLOCR resources: " + ", ".join(missing))
    return SimpleNamespace(
        **{name: str(path) for name, path in paths.items()},
        det_score_threshold=0.2,
        det_conf_threshold=0.25,
        det_iou_threshold=0.2,
        device="cpu",
        enable_tcy=False,
    )


def run(control_dir: Path, resource_root: Path | None = None) -> int:
    # Imported only in the packaged helper. Unit tests can inspect the protocol
    # helpers without installing NDLOCR's runtime dependencies on macOS.
    import numpy as np
    from ocr import (
        _run_ocr_on_image_array,
        get_detector,
        get_recognizer,
    )
    from PIL import Image

    control_dir.mkdir(parents=True, exist_ok=True)
    resource_root = resource_root or Path(
        getattr(sys, "_MEIPASS", Path(__file__).resolve().parent),
    )
    args = _runtime_args(resource_root)
    startup_started = time.perf_counter()
    detector = get_detector(args)
    recognizer100 = get_recognizer(args=args)
    recognizer30 = get_recognizer(args=args, weights_path=args.rec_weights30)
    recognizer50 = get_recognizer(args=args, weights_path=args.rec_weights50)
    atomic_json(control_dir / "ready.json", {
        "pid": os.getpid(),
        "startup_ms": round((time.perf_counter() - startup_started) * 1000, 3),
    })

    processed: set[str] = set()
    while not (control_dir / "shutdown.json").exists():
        for request_path in sorted(control_dir.glob("request-*.json")):
            if request_path.name in processed:
                continue
            processed.add(request_path.name)
            request = json.loads(request_path.read_text(encoding="utf-8-sig"))
            response_path = Path(request["response"])
            try:
                image_path = Path(request["image"])
                image = np.array(Image.open(image_path).convert("RGB"))
                started = time.perf_counter()
                result = _run_ocr_on_image_array(
                    detector=detector,
                    recognizer30=recognizer30,
                    recognizer50=recognizer50,
                    recognizer100=recognizer100,
                    inputname=image_path.name,
                    img=image,
                    outputpath=str(control_dir),
                    save_viz=False,
                )
                payload = response_payload(
                    result, (time.perf_counter() - started) * 1000,
                )
            except Exception as exc:  # noqa: BLE001  # pragma: no cover
                payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            atomic_json(response_path, payload)
        time.sleep(0.05)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-dir", type=Path, required=True)
    parser.add_argument("--resource-root", type=Path)
    args = parser.parse_args()
    return run(args.control_dir, args.resource_root)


if __name__ == "__main__":
    raise SystemExit(main())
