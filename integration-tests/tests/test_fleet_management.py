"""
Integration tests for fleet management.
"""
import pytest
import httpx


@pytest.mark.asyncio
async def test_list_nodes(http_client: httpx.AsyncClient):
    """Test listing fleet nodes."""
    response = await http_client.get("/api/fleet/nodes")
    assert response.status_code == 200

    data = response.json()
    assert 'nodes' in data
    assert 'total' in data


@pytest.mark.asyncio
async def test_create_node(http_client: httpx.AsyncClient, mediamtx_url: str):
    """Test creating a new node."""
    node_data = {
        "name": "integration-test-node",
        "api_url": mediamtx_url,
        "environment": "testing"
    }

    response = await http_client.post("/api/fleet/nodes", json=node_data)
    assert response.status_code == 201

    data = response.json()
    assert 'id' in data
    node_id = data['id']

    # Cleanup
    await http_client.delete(f"/api/fleet/nodes/{node_id}")


@pytest.mark.asyncio
async def test_sync_node(http_client: httpx.AsyncClient, test_node):
    """Test syncing streams from a node."""
    response = await http_client.post(f"/api/fleet/nodes/{test_node['id']}/sync")
    assert response.status_code == 200

    data = response.json()
    assert 'success' in data
    assert 'synced' in data


@pytest.mark.asyncio
async def test_fleet_overview(http_client: httpx.AsyncClient):
    """Test fleet overview endpoint."""
    response = await http_client.get("/api/fleet/overview")
    assert response.status_code == 200

    data = response.json()
    assert 'nodes' in data
    assert 'streams' in data


@pytest.mark.asyncio
async def test_sync_all_nodes(http_client: httpx.AsyncClient):
    """Test syncing all nodes."""
    response = await http_client.post("/api/fleet/sync-all")
    assert response.status_code == 200

    data = response.json()
    assert 'total_nodes' in data
    assert 'results' in data
