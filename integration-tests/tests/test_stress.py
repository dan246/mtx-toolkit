"""
Stress tests for stream reliability toolkit.
"""
import pytest
import httpx
import asyncio
from typing import List


@pytest.mark.asyncio
async def test_concurrent_probes(http_client: httpx.AsyncClient, rtsp_base_url: str):
    """Test multiple concurrent stream probes."""
    streams = ['test', 'black', 'lowfps', 'silent']
    urls = [f"{rtsp_base_url}/{s}" for s in streams]

    async def probe_stream(url: str) -> dict:
        try:
            response = await http_client.post(
                "/api/health/probe",
                json={"url": url, "protocol": "rtsp"},
                timeout=30.0
            )
            return {"url": url, "status": response.status_code, "data": response.json()}
        except Exception as e:
            return {"url": url, "error": str(e)}

    # Run 4 concurrent probes
    tasks = [probe_stream(url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # All probes should complete
    successful = sum(1 for r in results if isinstance(r, dict) and r.get('status') == 200)
    assert successful >= 2, f"At least 2 probes should succeed, got {successful}"


@pytest.mark.asyncio
async def test_rapid_api_calls(http_client: httpx.AsyncClient):
    """Test rapid sequential API calls."""
    endpoints = [
        "/api/health/",
        "/api/fleet/nodes",
        "/api/dashboard/overview",
        "/api/streams/",
        "/api/recordings/",
    ]

    results = []
    for _ in range(10):  # 10 iterations
        for endpoint in endpoints:
            try:
                response = await http_client.get(endpoint, timeout=10.0)
                results.append(response.status_code)
            except Exception:
                results.append(500)

    # Calculate success rate
    success_rate = sum(1 for r in results if r == 200) / len(results)
    assert success_rate >= 0.9, f"Success rate should be >= 90%, got {success_rate * 100}%"


@pytest.mark.asyncio
async def test_concurrent_stream_list(http_client: httpx.AsyncClient):
    """Test concurrent requests to stream list endpoint."""
    async def list_streams():
        response = await http_client.get("/api/streams/", timeout=10.0)
        return response.status_code

    # Run 20 concurrent requests
    tasks = [list_streams() for _ in range(20)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successful = sum(1 for r in results if r == 200)
    assert successful >= 18, f"At least 18/20 requests should succeed, got {successful}"


@pytest.mark.asyncio
async def test_dashboard_under_load(http_client: httpx.AsyncClient):
    """Test dashboard endpoints under load."""
    endpoints = [
        "/api/dashboard/overview",
        "/api/dashboard/streams/status",
        "/api/dashboard/events/recent",
        "/api/dashboard/alerts/active",
    ]

    async def call_endpoint(endpoint: str) -> int:
        try:
            response = await http_client.get(endpoint, timeout=10.0)
            return response.status_code
        except Exception:
            return 500

    # 5 iterations of all endpoints
    tasks = []
    for _ in range(5):
        for endpoint in endpoints:
            tasks.append(call_endpoint(endpoint))

    results = await asyncio.gather(*tasks)

    success_rate = sum(1 for r in results if r == 200) / len(results)
    assert success_rate >= 0.95, f"Success rate should be >= 95%, got {success_rate * 100}%"
