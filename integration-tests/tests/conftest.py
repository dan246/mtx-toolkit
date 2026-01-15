"""
Integration test fixtures and configuration.
"""
import os
import pytest
import httpx
import asyncio
from typing import AsyncGenerator

# Environment variables
BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:5000')
MEDIAMTX_URL = os.getenv('MEDIAMTX_URL', 'http://localhost:9997')
RTSP_URL = os.getenv('RTSP_URL', 'rtsp://localhost:8554')
RTMP_URL = os.getenv('RTMP_URL', 'rtmp://localhost:1935')


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create HTTP client for API calls."""
    async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="session")
async def mediamtx_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create HTTP client for MediaMTX API calls."""
    async with httpx.AsyncClient(base_url=MEDIAMTX_URL, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="session")
def backend_url() -> str:
    return BACKEND_URL


@pytest.fixture(scope="session")
def mediamtx_url() -> str:
    return MEDIAMTX_URL


@pytest.fixture(scope="session")
def rtsp_base_url() -> str:
    return RTSP_URL


@pytest.fixture(scope="session")
def rtmp_base_url() -> str:
    return RTMP_URL


@pytest.fixture(scope="function")
async def test_node(http_client: httpx.AsyncClient):
    """Create a test node for testing."""
    node_data = {
        "name": "test-node",
        "api_url": MEDIAMTX_URL,
        "environment": "testing"
    }
    response = await http_client.post("/api/fleet/nodes", json=node_data)
    if response.status_code == 201:
        node = response.json()
        yield node
        # Cleanup
        await http_client.delete(f"/api/fleet/nodes/{node['id']}")
    else:
        # Node might already exist
        response = await http_client.get("/api/fleet/nodes")
        nodes = response.json().get('nodes', [])
        test_nodes = [n for n in nodes if n['name'] == 'test-node']
        if test_nodes:
            yield test_nodes[0]
        else:
            pytest.skip("Could not create test node")
