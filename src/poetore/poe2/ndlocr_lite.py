"""Persistent NDLOCR-Lite sidecar used only for safe numeric rescue."""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class NdlOcrResult:
    text: str
    confidence: float | None = None


@dataclass(frozen=True)
class NdlOcrRequestMetrics:
    cold_start: bool
    startup_ms: float | None
    wall_startup_ms: float | None
    inference_ms: float | None


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
    """Convert the upstream one-shot JSON format (kept for compatibility tests)."""

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
    """Lazily start and reuse the bundled CPU-only NDLOCR process."""

    def __init__(
        self,
        *,
        helper: Path | None = None,
        timeout: float = 90.0,
        idle_timeout: float = 180.0,
        process_factory: Callable[..., Any] = subprocess.Popen,
        timer_factory: Callable[..., Any] = threading.Timer,
        event_callback: Callable[..., None] | None = None,
    ):
        self.helper = helper
        self.timeout = timeout
        self.idle_timeout = idle_timeout
        self._process_factory = process_factory
        self._timer_factory = timer_factory
        self._event_callback = event_callback
        self._state_lock = threading.RLock()
        self._operation_lock = threading.Lock()
        self._process = None
        self._responses: queue.Queue[dict[str, object] | None] = queue.Queue()
        self._stderr_tail: deque[str] = deque(maxlen=20)
        self._timer = None
        self._timer_generation = 0
        self._session_dir: Path | None = None
        self._request_number = 0
        self._ready = False
        self.last_metrics: NdlOcrRequestMetrics | None = None

    @property
    def is_ready(self) -> bool:
        with self._state_lock:
            return bool(
                self._ready
                and self._process is not None
                and self._process.poll() is None
            )

    @property
    def session_dir(self) -> Path | None:
        with self._state_lock:
            return self._session_dir

    def _emit(self, event: str, **details: object) -> None:
        if self._event_callback is None:
            return
        try:
            self._event_callback(event, **details)
        except Exception:  # noqa: BLE001 - telemetry must never break OCR
            return

    @staticmethod
    def _read_stdout(process, responses) -> None:
        try:
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    responses.put(payload)
        finally:
            responses.put(None)

    @staticmethod
    def _read_stderr(process, stderr_tail) -> None:
        try:
            while True:
                line = process.stderr.readline()
                if not line:
                    break
                stderr_tail.append(line.strip())
        except Exception:  # noqa: BLE001 - diagnostic stream only
            return

    def _next_message(self, timeout: float) -> dict[str, object]:
        try:
            message = self._responses.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError("NDLOCRの応答がタイムアウトしました。") from exc
        if message is None:
            details = "\n".join(self._stderr_tail).strip()
            raise RuntimeError(details or "NDLOCRが予期せず終了しました。")
        return message

    def _start_if_needed(self) -> bool:
        if self.is_ready:
            return False
        with self._state_lock:
            old_process = self._process
            old_session_dir = self._session_dir
        if old_process is not None:
            self._shutdown_process(
                old_process, old_session_dir, reason="unexpected_exit",
            )
        helper = self.helper or _helper_path()
        if not helper.is_file():
            raise RuntimeError(f"NDLOCRヘルパーが見つかりません: {helper}")
        self._emit("ndl_resident_start_requested")
        started = time.perf_counter()
        session_dir = Path(tempfile.mkdtemp(prefix="poenavi-ndlocr-"))
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        environment["PYTHONIOENCODING"] = "utf-8"
        try:
            process = self._process_factory(
                [str(helper), "--server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=str(helper.parent),
                env=environment,
                creationflags=creationflags,
            )
        except Exception:
            shutil.rmtree(session_dir, ignore_errors=True)
            self._emit("ndl_resident_stopped", reason="startup_failed")
            raise
        responses: queue.Queue[dict[str, object] | None] = queue.Queue()
        stderr_tail: deque[str] = deque(maxlen=20)
        with self._state_lock:
            self._process = process
            self._session_dir = session_dir
            self._ready = False
            self._responses = responses
            self._stderr_tail = stderr_tail
        threading.Thread(
            target=self._read_stdout,
            args=(process, responses),
            name="ndlocr-stdout",
            daemon=True,
        ).start()
        threading.Thread(
            target=self._read_stderr,
            args=(process, stderr_tail),
            name="ndlocr-stderr",
            daemon=True,
        ).start()
        try:
            message = self._next_message(self.timeout)
            if message.get("event") != "ready":
                raise RuntimeError("NDLOCRの準備完了応答が不正です。")
            startup_ms = _optional_float(message.get("startup_ms"))
            wall_startup_ms = (time.perf_counter() - started) * 1000
            with self._state_lock:
                self._ready = True
            self.last_metrics = NdlOcrRequestMetrics(
                cold_start=True,
                startup_ms=startup_ms,
                wall_startup_ms=wall_startup_ms,
                inference_ms=None,
            )
            self._emit(
                "ndl_resident_ready",
                startup_ms=startup_ms,
                wall_startup_ms=round(wall_startup_ms, 3),
            )
            return True
        except Exception:
            self._shutdown_process(process, session_dir, reason="startup_failed")
            raise

    def recognize(self, images: Sequence[bytes]) -> list[NdlOcrResult]:
        if not images:
            return []
        with self._operation_lock:
            cold_start = self._start_if_needed()
            with self._state_lock:
                process = self._process
                session_dir = self._session_dir
                self._request_number += 1
                request_number = self._request_number
            if process is None or session_dir is None or process.stdin is None:
                raise RuntimeError("NDLOCRが起動していません。")
            request_id = f"{request_number}-{uuid4().hex}"
            request_dir = session_dir / request_id
            request_dir.mkdir(parents=True)
            paths: list[str] = []
            try:
                for index, image in enumerate(images):
                    path = request_dir / f"choice-{index:03d}.bmp"
                    path.write_bytes(image)
                    paths.append(str(path))
                request_started = time.perf_counter()
                process.stdin.write(json.dumps({
                    "command": "recognize",
                    "request_id": request_id,
                    "images": paths,
                }, ensure_ascii=False) + "\n")
                process.stdin.flush()
                while True:
                    message = self._next_message(self.timeout)
                    if (
                        message.get("event") == "result"
                        and message.get("request_id") == request_id
                    ):
                        break
                wall_inference_ms = (time.perf_counter() - request_started) * 1000
                if not message.get("ok"):
                    error_type = str(message.get("error_type") or "UnknownError")
                    raise RuntimeError(f"NDLOCRの推論に失敗しました: {error_type}")
                raw_results = message.get("results")
                if not isinstance(raw_results, list) or len(raw_results) != len(images):
                    raise RuntimeError("NDLOCRの結果件数が一致しません。")
                results = [
                    NdlOcrResult(
                        text=str(item.get("text") or ""),
                        confidence=_optional_float(item.get("confidence")),
                    )
                    for item in raw_results
                    if isinstance(item, dict)
                ]
                if len(results) != len(images):
                    raise RuntimeError("NDLOCRの結果形式が不正です。")
                inference_ms = _optional_float(message.get("inference_ms"))
                prior = self.last_metrics
                self.last_metrics = NdlOcrRequestMetrics(
                    cold_start=cold_start,
                    startup_ms=(prior.startup_ms if cold_start and prior else None),
                    wall_startup_ms=(
                        prior.wall_startup_ms if cold_start and prior else None
                    ),
                    inference_ms=inference_ms,
                )
                self._emit(
                    "ndl_request_completed",
                    cold_start=cold_start,
                    inference_ms=inference_ms,
                    wall_inference_ms=round(wall_inference_ms, 3),
                    image_count=len(images),
                )
                self._schedule_idle_stop()
                return results
            except Exception as exc:
                self._emit(
                    "ndl_request_failed",
                    cold_start=cold_start,
                    error_type=type(exc).__name__,
                )
                if isinstance(exc, TimeoutError) or process.poll() is not None:
                    self._shutdown_process(
                        process,
                        session_dir,
                        reason=(
                            "timeout"
                            if isinstance(exc, TimeoutError)
                            else "unexpected_exit"
                        ),
                    )
                else:
                    self._schedule_idle_stop()
                raise
            finally:
                shutil.rmtree(request_dir, ignore_errors=True)

    def _schedule_idle_stop(self) -> None:
        with self._state_lock:
            if not self._ready:
                return
            if self._timer is not None:
                self._timer.cancel()
            self._timer_generation += 1
            generation = self._timer_generation
            timer = self._timer_factory(
                self.idle_timeout,
                lambda: self._idle_stop(generation),
            )
            timer.daemon = True
            self._timer = timer
            timer.start()

    def touch_if_running(self) -> bool:
        """Refresh idle expiry without starting NDLOCR when it is stopped."""

        if not self.is_ready:
            return False
        self._schedule_idle_stop()
        self._emit("ndl_resident_touched", source="desecration_hotkey")
        return True

    def _idle_stop(self, generation: int) -> None:
        with self._state_lock:
            if generation != self._timer_generation:
                return
        self._stop(reason="idle_timeout")

    def _shutdown_process(self, process, session_dir: Path | None, *, reason: str) -> None:
        try:
            if process.poll() is None and process.stdin is not None:
                process.stdin.write(json.dumps({"command": "shutdown"}) + "\n")
                process.stdin.flush()
                process.wait(timeout=2)
        except Exception:  # noqa: BLE001 - force cleanup below
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:  # noqa: BLE001
                try:
                    process.kill()
                except Exception:  # noqa: BLE001
                    return
        finally:
            if session_dir is not None:
                shutil.rmtree(session_dir, ignore_errors=True)
            with self._state_lock:
                if self._process is process:
                    self._process = None
                    self._session_dir = None
                    self._ready = False
            self._emit("ndl_resident_stopped", reason=reason)

    def _stop(self, *, reason: str) -> None:
        with self._operation_lock:
            with self._state_lock:
                timer = self._timer
                self._timer = None
                self._timer_generation += 1
                process = self._process
                session_dir = self._session_dir
            if timer is not None:
                timer.cancel()
            if process is not None:
                self._shutdown_process(process, session_dir, reason=reason)

    def close(self) -> None:
        # Explicit application/mode shutdown must not wait for a long inference.
        with self._state_lock:
            timer = self._timer
            self._timer = None
            self._timer_generation += 1
            process = self._process
            session_dir = self._session_dir
            self._ready = False
        if timer is not None:
            timer.cancel()
        if process is not None:
            self._shutdown_process(
                process, session_dir, reason="controller_close",
            )


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None
