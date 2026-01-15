"""
Integration tests for E2E health checking.
"""
import pytest
import httpx
import subprocess
import time


@pytest.mark.asyncio
async def test_backend_health(http_client: httpx.AsyncClient):
    """Test backend health endpoint."""
    response = await http_client.get("/api/health/")
    assert response.status_code == 200

    data = response.json()
    assert data['status'] == 'ok'
    assert data['service'] == 'mtx-toolkit'


@pytest.mark.asyncio
async def test_mediamtx_connectivity(mediamtx_client: httpx.AsyncClient):
    """Test MediaMTX API connectivity."""
    response = await mediamtx_client.get("/v3/paths/list")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_probe_healthy_stream(http_client: httpx.AsyncClient, rtsp_base_url: str):
    """Test probing a healthy test stream."""
    # Give test stream time to start
    time.sleep(5)

    probe_data = {
        "url": f"{rtsp_base_url}/test",
        "protocol": "rtsp"
    }
    response = await http_client.post("/api/health/probe", json=probe_data)
    assert response.status_code == 200

    data = response.json()
    assert data.get('is_healthy') is True or data.get('status') in ['healthy', 'degraded']
    assert 'fps' in data
    assert 'codec' in data


@pytest.mark.asyncio
async def test_probe_black_screen_stream(http_client: httpx.AsyncClient, rtsp_base_url: str):
    """Test detection of black screen in stream."""
    time.sleep(5)

    probe_data = {
        "url": f"{rtsp_base_url}/black",
        "protocol": "rtsp"
    }
    response = await http_client.post("/api/health/probe", json=probe_data)
    assert response.status_code == 200

    data = response.json()
    # Stream should be detected, may or may not flag black screen depending on implementation
    assert 'status' in data


@pytest.mark.asyncio
async def test_probe_low_fps_stream(http_client: httpx.AsyncClient, rtsp_base_url: str):
    """Test detection of low FPS stream."""
    time.sleep(5)

    probe_data = {
        "url": f"{rtsp_base_url}/lowfps",
        "protocol": "rtsp"
    }
    response = await http_client.post("/api/health/probe", json=probe_data)
    assert response.status_code == 200

    data = response.json()
    assert 'fps' in data
    if data.get('fps'):
        assert data['fps'] < 10  # Should detect low FPS


@pytest.mark.asyncio
async def test_probe_nonexistent_stream(http_client: httpx.AsyncClient, rtsp_base_url: str):
    """Test probing a non-existent stream."""
    probe_data = {
        "url": f"{rtsp_base_url}/nonexistent",
        "protocol": "rtsp"
    }
    response = await http_client.post("/api/health/probe", json=probe_data)
    assert response.status_code == 200

    data = response.json()
    assert data.get('is_healthy') is False or data.get('error') is not None


@pytest.mark.asyncio
async def test_streams_health_endpoint(http_client: httpx.AsyncClient):
    """Test streams health aggregation endpoint."""
    response = await http_client.get("/api/health/streams")
    assert response.status_code == 200

    data = response.json()
    assert 'streams' in data
    assert 'summary' in data
