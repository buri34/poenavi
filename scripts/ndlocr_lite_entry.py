"""PoENavi NDLOCR-Lite entry point with one-shot and resident modes."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import TextIO


def _resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _runtime_args(resource_root: Path) -> SimpleNamespace:
    paths = {
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


class PersistentNdlOcrEngine:
    """Load all four ONNX sessions once and reuse them for every request."""

    def __init__(self, resource_root: Path | None = None):
        import numpy as np
        from ocr import _run_ocr_on_image_array, get_detector, get_recognizer
        from PIL import Image

        self._np = np
        self._image = Image
        self._run_ocr = _run_ocr_on_image_array
        args = _runtime_args(resource_root or _resource_root())
        # Upstream model loading reports progress on stdout. Keep stdout reserved
        # for the JSON Lines protocol and move all such output to stderr.
        with contextlib.redirect_stdout(sys.stderr):
            self._detector = get_detector(args)
            self._recognizer100 = get_recognizer(args=args)
            self._recognizer30 = get_recognizer(
                args=args, weights_path=args.rec_weights30,
            )
            self._recognizer50 = get_recognizer(
                args=args, weights_path=args.rec_weights50,
            )

    def recognize(self, image_path: str | Path) -> dict[str, object]:
        path = Path(image_path)
        image = self._np.array(self._image.open(path).convert("RGB"))
        with contextlib.redirect_stdout(sys.stderr):
            result = self._run_ocr(
                detector=self._detector,
                recognizer30=self._recognizer30,
                recognizer50=self._recognizer50,
                recognizer100=self._recognizer100,
                inputname=path.name,
                img=image,
                outputpath=str(path.parent),
                save_viz=False,
            )
        lines = result.get("json_lines") or []
        confidences = [
            float(line["confidence"])
            for line in lines
            if isinstance(line, dict)
            and isinstance(line.get("confidence"), (int, float))
        ]
        return {
            "text": str(result.get("text") or ""),
            "confidence": min(confidences) if confidences else None,
        }


def _write_message(writer: TextIO, payload: dict[str, object]) -> None:
    writer.write(json.dumps(payload, ensure_ascii=False) + "\n")
    writer.flush()


def serve(
    reader: TextIO,
    writer: TextIO,
    *,
    engine_factory=PersistentNdlOcrEngine,
) -> int:
    """Serve blocking JSON Lines requests until stdin closes or shutdown arrives."""

    started = time.perf_counter()
    engine = engine_factory()
    _write_message(writer, {
        "event": "ready",
        "pid": os.getpid(),
        "startup_ms": round((time.perf_counter() - started) * 1000, 3),
    })
    for raw_line in reader:
        try:
            request = json.loads(raw_line)
        except (TypeError, json.JSONDecodeError):
            _write_message(writer, {"event": "protocol_error"})
            continue
        if request.get("command") == "shutdown":
            break
        request_id = str(request.get("request_id") or "")
        if request.get("command") != "recognize":
            _write_message(writer, {
                "event": "result",
                "request_id": request_id,
                "ok": False,
                "error_type": "UnsupportedCommand",
            })
            continue
        try:
            request_started = time.perf_counter()
            results = [engine.recognize(path) for path in request.get("images", [])]
            _write_message(writer, {
                "event": "result",
                "request_id": request_id,
                "ok": True,
                "inference_ms": round(
                    (time.perf_counter() - request_started) * 1000, 3,
                ),
                "results": results,
            })
        except Exception as exc:  # noqa: BLE001 - isolate individual requests
            print(f"NDLOCR request failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            _write_message(writer, {
                "event": "result",
                "request_id": request_id,
                "ok": False,
                "error_type": type(exc).__name__,
            })
    _write_message(writer, {"event": "stopped"})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--server", action="store_true")
    known, _remaining = parser.parse_known_args()
    if not known.server:
        # Preserve the upstream CLI used by existing verification and tooling.
        from ocr import main as upstream_main

        return int(upstream_main() or 0)
    return serve(sys.stdin, sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
