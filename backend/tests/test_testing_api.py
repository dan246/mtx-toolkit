"""Tests for the Testing API (scenarios + suites). No real ffmpeg is spawned."""

from unittest.mock import MagicMock, patch

from app.services.test_runner import TestRunner


class TestScenarioListing:
    def test_list_scenarios(self, client, app_context):
        resp = client.get("/api/testing/scenarios")
        assert resp.status_code == 200
        scenarios = resp.get_json()["scenarios"]
        ids = {s["id"] for s in scenarios}
        assert {"testsrc", "black", "silence", "lowfps"} <= ids
        # every scenario advertises a command + ready status
        assert all(s["status"] in ("ready", "running") for s in scenarios)

    def test_unknown_scenario_start_rejected(self, client, app_context):
        resp = client.post("/api/testing/scenarios/does-not-exist/start")
        assert resp.status_code == 400


class TestScenarioLifecycle:
    @patch("app.services.test_runner.subprocess.Popen")
    def test_start_and_stop(self, mock_popen, client, app_context):
        proc = MagicMock()
        proc.poll.return_value = None  # still running
        proc.pid = 4321
        mock_popen.return_value = proc

        TestRunner._processes.clear()
        start = client.post("/api/testing/scenarios/testsrc/start")
        assert start.status_code == 200
        assert start.get_json()["pid"] == 4321

        proc.wait.return_value = 0
        stop = client.post("/api/testing/scenarios/testsrc/stop")
        assert stop.status_code == 200
        assert stop.get_json()["success"] is True

    @patch("app.services.test_runner.subprocess.Popen")
    def test_start_reports_ffmpeg_missing(self, mock_popen, client, app_context):
        mock_popen.side_effect = FileNotFoundError()
        TestRunner._processes.clear()
        resp = client.post("/api/testing/scenarios/black/start")
        assert resp.status_code == 400
        assert "ffmpeg" in resp.get_json()["error"]


class TestSuites:
    def test_integration_no_streams(self, client, app_context):
        resp = client.post("/api/testing/suite/integration")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["type"] == "integration"
        assert data["total"] == 0

    def test_integration_with_stream(self, client, sample_stream):
        with patch.object(
            TestRunner, "run_integration", wraps=TestRunner().run_integration
        ):
            with patch(
                "app.services.test_runner.HealthChecker"
            ) as MockChecker:
                MockChecker.return_value.probe_stream.return_value = {
                    "is_healthy": True,
                    "status": "healthy",
                    "issues": [],
                }
                resp = client.post("/api/testing/suite/integration")
        data = resp.get_json()
        assert data["total"] == 1
        assert data["passed"] == 1
        assert data["success"] is True

    def test_stress_requires_url(self, client, app_context):
        resp = client.post("/api/testing/suite/stress", json={})
        assert resp.status_code == 400

    def test_stress_runs_concurrent_probes(self, client, app_context):
        with patch("app.services.test_runner.HealthChecker") as MockChecker:
            MockChecker.return_value.probe_url.return_value = {"is_healthy": True}
            resp = client.post(
                "/api/testing/suite/stress",
                json={"url": "rtsp://localhost:8554/test", "concurrency": 4},
            )
        data = resp.get_json()
        assert data["concurrency"] == 4
        assert data["succeeded"] == 4
        assert data["success"] is True
