"""
Testing API endpoints.

Backs the Testing page with real operations: live ffmpeg test scenarios and
on-demand integration / stress / recovery suites.
"""

from flask import Blueprint, jsonify, request

from app.services.test_runner import TestRunner

testing_bp = Blueprint("testing", __name__)
runner = TestRunner()


@testing_bp.route("/scenarios", methods=["GET"])
def list_scenarios():
    return jsonify({"scenarios": runner.list_scenarios()})


@testing_bp.route("/scenarios/<scenario_id>/start", methods=["POST"])
def start_scenario(scenario_id: str):
    result = runner.start_scenario(scenario_id)
    return jsonify(result), (200 if result.get("success") else 400)


@testing_bp.route("/scenarios/<scenario_id>/stop", methods=["POST"])
def stop_scenario(scenario_id: str):
    result = runner.stop_scenario(scenario_id)
    return jsonify(result), (200 if result.get("success") else 400)


@testing_bp.route("/suite/integration", methods=["POST"])
def run_integration():
    return jsonify(runner.run_integration())


@testing_bp.route("/suite/stress", methods=["POST"])
def run_stress():
    data = request.get_json(silent=True) or {}
    result = runner.run_stress(
        url=data.get("url", ""),
        protocol=data.get("protocol", "rtsp"),
        concurrency=int(data.get("concurrency", 5)),
    )
    return jsonify(result), (200 if result.get("success") is not False else 400)


@testing_bp.route("/suite/recovery", methods=["POST"])
def run_recovery():
    data = request.get_json(silent=True) or {}
    result = runner.run_recovery(stream_id=data.get("stream_id"))
    return jsonify(result), (200 if result.get("success") is not False else 400)
