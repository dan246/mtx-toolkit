"""
Test Runner Service.

Powers the Testing page with REAL operations (no simulated results):

  * Test scenarios   -> spawn/stop real ffmpeg test-pattern publishers against
                        the configured MediaMTX RTSP endpoint.
  * Integration test -> probe every registered stream and aggregate pass/fail.
  * Stress test      -> fire N concurrent probes at a URL and report latency.

Scenarios are defined server-side as fixed argument lists (never shell strings
built from client input) so there is no command-injection surface.
"""

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from flask import current_app

from app import db
from app.models import Stream
from app.services.health_checker import HealthChecker
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _rtsp_base() -> str:
    base = current_app.config.get("MEDIAMTX_RTSP_URL", "rtsp://localhost:8554")
    return base.rstrip("/")


# Scenario id -> (label, description, ffmpeg input args, target path)
_SCENARIO_DEFS = {
    "testsrc": {
        "name": "FFmpeg Test Source",
        "description": "Generate a test pattern stream for validation",
        "input": ["-re", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30"],
        "path": "test",
    },
    "black": {
        "name": "Black Screen Test",
        "description": "Generate a black screen to exercise black-screen detection",
        "input": ["-re", "-f", "lavfi", "-i", "color=black:size=1280x720:rate=30"],
        "path": "black",
    },
    "silence": {
        "name": "Audio Silence Test",
        "description": "Publish silent audio to exercise silence detection",
        "input": ["-re", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"],
        "path": "silent",
    },
    "lowfps": {
        "name": "Low FPS Test",
        "description": "Generate a low-framerate stream",
        "input": ["-re", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=5"],
        "path": "lowfps",
    },
}


class TestRunner:
    """Manages live test scenarios and on-demand test suites."""

    # Process registry shared across instances (single web process).
    _processes: Dict[str, subprocess.Popen] = {}

    # ---- Scenarios -----------------------------------------------------

    def _command(self, scenario_id: str) -> List[str]:
        spec = _SCENARIO_DEFS[scenario_id]
        target = f"{_rtsp_base()}/{spec['path']}"
        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            *spec["input"],
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-f",
            "rtsp",
            "-rtsp_transport",
            "tcp",
            target,
        ]

    def _is_running(self, scenario_id: str) -> bool:
        proc = self._processes.get(scenario_id)
        return proc is not None and proc.poll() is None

    def list_scenarios(self) -> List[Dict[str, Any]]:
        scenarios = []
        for sid, spec in _SCENARIO_DEFS.items():
            target = f"{_rtsp_base()}/{spec['path']}"
            scenarios.append(
                {
                    "id": sid,
                    "name": spec["name"],
                    "description": spec["description"],
                    "command": " ".join(self._command(sid)),
                    "target": target,
                    "status": "running" if self._is_running(sid) else "ready",
                }
            )
        return scenarios

    def start_scenario(self, scenario_id: str) -> Dict[str, Any]:
        if scenario_id not in _SCENARIO_DEFS:
            return {"success": False, "error": f"unknown scenario '{scenario_id}'"}
        if self._is_running(scenario_id):
            return {"success": False, "error": "scenario already running"}

        cmd = self._command(scenario_id)
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            return {"success": False, "error": "ffmpeg not found on server"}
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "scenario_start_failed", scenario=scenario_id, error=str(exc)
            )
            return {"success": False, "error": str(exc)}

        # Give ffmpeg a moment; if it exits immediately, surface the error.
        time.sleep(0.5)
        if proc.poll() is not None:
            err = (proc.stderr.read().decode("utf-8", "ignore") if proc.stderr else "")[
                -500:
            ]
            logger.warning("scenario_exited_early", scenario=scenario_id, stderr=err)
            return {"success": False, "error": err or "ffmpeg exited immediately"}

        self._processes[scenario_id] = proc
        logger.info("scenario_started", scenario=scenario_id, pid=proc.pid)
        return {"success": True, "scenario_id": scenario_id, "pid": proc.pid}

    def stop_scenario(self, scenario_id: str) -> Dict[str, Any]:
        proc = self._processes.get(scenario_id)
        if proc is None or proc.poll() is not None:
            self._processes.pop(scenario_id, None)
            return {"success": True, "message": "not running"}
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        self._processes.pop(scenario_id, None)
        logger.info("scenario_stopped", scenario=scenario_id)
        return {"success": True, "scenario_id": scenario_id}

    # ---- Suites --------------------------------------------------------

    def run_integration(self) -> Dict[str, Any]:
        """Probe every registered stream and aggregate the outcome."""
        checker = HealthChecker()
        streams = Stream.query.all()
        results = []
        passed = 0
        for stream in streams:
            res = checker.probe_stream(stream.id)
            ok = bool(res.get("is_healthy"))
            passed += 1 if ok else 0
            results.append(
                {
                    "stream_id": stream.id,
                    "path": stream.path,
                    "healthy": ok,
                    "status": res.get("status"),
                    "issues": res.get("issues", []),
                }
            )
        total = len(streams)
        return {
            "type": "integration",
            "success": total > 0 and passed == total,
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "results": results,
        }

    def run_stress(
        self, url: str, protocol: str = "rtsp", concurrency: int = 5
    ) -> Dict[str, Any]:
        """Fire N concurrent probes at a URL and report latency/success."""
        if not url:
            return {"success": False, "error": "url is required"}
        concurrency = max(1, min(concurrency, 50))
        checker = HealthChecker()

        def _probe() -> Dict[str, Any]:
            start = time.time()
            res = checker.probe_url(url, protocol)
            return {
                "ok": bool(res.get("is_healthy")),
                "latency_ms": int((time.time() - start) * 1000),
            }

        latencies: List[int] = []
        ok_count = 0
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(_probe) for _ in range(concurrency)]
            for fut in as_completed(futures):
                r = fut.result()
                latencies.append(r["latency_ms"])
                ok_count += 1 if r["ok"] else 0

        return {
            "type": "stress",
            "success": ok_count == concurrency,
            "concurrency": concurrency,
            "succeeded": ok_count,
            "failed": concurrency - ok_count,
            "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
            "max_latency_ms": max(latencies) if latencies else 0,
        }

    def run_recovery(self, stream_id: Optional[int] = None) -> Dict[str, Any]:
        """Real fault-recovery test: trigger a soft reset and re-probe.

        Picks the given stream (or the first unhealthy/any stream), runs a
        protocol soft-reset via remediation level 0, then re-probes to confirm
        the pipeline recovered. No simulated outcomes.
        """
        from app.services.auto_remediation import AutoRemediation

        stream = (
            db.session.get(Stream, stream_id)
            if stream_id is not None
            else Stream.query.first()
        )
        if stream is None:
            return {"success": False, "error": "no streams available to test"}

        checker = HealthChecker()
        before = checker.probe_stream(stream.id)

        remediation = AutoRemediation()
        remediation.remediate_stream(stream, force_level=0, trigger_source="manual")

        after = checker.probe_stream(stream.id)
        return {
            "type": "recovery",
            "success": bool(after.get("is_healthy")),
            "stream_id": stream.id,
            "path": stream.path,
            "before": before.get("status"),
            "after": after.get("status"),
        }
