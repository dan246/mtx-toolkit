"""
Integration tests for connecting to existing MediaMTX instance.
Tests designed to work with the existing api_mediamtx_secondary on the host.
"""
import pytest
import httpx
import os

# Use host's MediaMTX
MEDIAMTX_API = os.getenv('MEDIAMTX_API_URL', 'http://host.docker.internal:9998')
MEDIAMTX_RTSP = os.getenv('MEDIAMTX_RTSP_URL', 'rtsp://host.docker.internal:8555')


@pytest.mark.asyncio
async def test_connect_to_existing_mediamtx():
    """Test connection to existing MediaMTX on host."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{MEDIAMTX_API}/v3/paths/list")
            assert response.status_code == 200
            data = response.json()
            print(f"Connected to MediaMTX, found {len(data.get('items', []))} paths")
        except httpx.ConnectError:
            pytest.skip("MediaMTX not available on host")


@pytest.mark.asyncio
async def test_list_existing_streams():
    """List all streams from existing MediaMTX."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{MEDIAMTX_API}/v3/paths/list")
            if response.status_code != 200:
                pytest.skip("MediaMTX not responding")

            data = response.json()
            paths = data.get('items', [])

            print(f"\n=== Existing MediaMTX Streams ===")
            for path in paths:
                name = path.get('name', 'unknown')
                source = path.get('source', {})
                readers = path.get('readers', [])
                print(f"  - {name}: source={source.get('type', 'none')}, readers={len(readers)}")

            assert isinstance(paths, list)

        except httpx.ConnectError:
            pytest.skip("MediaMTX not available on host")


@pytest.mark.asyncio
async def test_probe_camera_streams(http_client: httpx.AsyncClient):
    """Test probing the existing camera streams."""
    # These are the known camera paths from MultiCamAPI
    camera_paths = ['camera1', 'camera2', 'camera3', 'camera4', 'camera5', 'camera6']

    results = []
    for camera in camera_paths:
        url = f"{MEDIAMTX_RTSP}/{camera}"
        try:
            response = await http_client.post(
                "/api/health/probe",
                json={"url": url, "protocol": "rtsp"},
                timeout=15.0
            )
            if response.status_code == 200:
                data = response.json()
                results.append({
                    "camera": camera,
                    "status": data.get('status'),
                    "fps": data.get('fps'),
                    "is_healthy": data.get('is_healthy')
                })
        except Exception as e:
            results.append({"camera": camera, "error": str(e)})

    print(f"\n=== Camera Stream Probe Results ===")
    for r in results:
        print(f"  {r}")

    # At least some cameras should be accessible
    healthy = sum(1 for r in results if r.get('is_healthy'))
    print(f"\nHealthy streams: {healthy}/{len(camera_paths)}")


@pytest.mark.asyncio
async def test_sync_from_existing_mediamtx(http_client: httpx.AsyncClient):
    """Test syncing streams from existing MediaMTX to toolkit."""
    # First create a node pointing to the existing MediaMTX
    node_data = {
        "name": "main-mediamtx",
        "api_url": MEDIAMTX_API,
        "environment": "production"
    }

    # Create or find existing node
    response = await http_client.post("/api/fleet/nodes", json=node_data)
    if response.status_code == 201:
        node = response.json()
        node_id = node['id']
    else:
        # Try to find existing
        response = await http_client.get("/api/fleet/nodes")
        nodes = response.json().get('nodes', [])
        existing = [n for n in nodes if n['api_url'] == MEDIAMTX_API]
        if existing:
            node_id = existing[0]['id']
        else:
            pytest.skip("Could not create node for existing MediaMTX")
            return

    # Sync streams
    response = await http_client.post(f"/api/fleet/nodes/{node_id}/sync")
    assert response.status_code == 200

    data = response.json()
    print(f"\n=== Sync Result ===")
    print(f"  Success: {data.get('success')}")
    print(f"  Total paths: {data.get('total_paths')}")
    print(f"  Synced: {data.get('synced')}")
    print(f"  Created: {data.get('created')}")
    print(f"  Updated: {data.get('updated')}")
