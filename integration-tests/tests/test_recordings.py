"""
Integration tests for recording and retention management.
"""
import pytest
import httpx


@pytest.mark.asyncio
async def test_list_recordings(http_client: httpx.AsyncClient):
    """Test listing recordings."""
    response = await http_client.get("/api/recordings/")
    assert response.status_code == 200

    data = response.json()
    assert 'recordings' in data
    assert 'total' in data


@pytest.mark.asyncio
async def test_retention_status(http_client: httpx.AsyncClient):
    """Test retention status endpoint."""
    response = await http_client.get("/api/recordings/retention/status")
    assert response.status_code == 200

    data = response.json()
    assert 'disk' in data
    assert 'recordings' in data

    # Check disk info
    assert 'total_gb' in data['disk']
    assert 'free_gb' in data['disk']
    assert 'usage_percent' in data['disk']

    # Check recording stats
    assert 'total' in data['recordings']
    assert 'by_type' in data['recordings']


@pytest.mark.asyncio
async def test_retention_policy(http_client: httpx.AsyncClient):
    """Test getting retention policy."""
    response = await http_client.get("/api/recordings/retention/policy")
    assert response.status_code == 200

    data = response.json()
    assert 'continuous_retention_days' in data
    assert 'event_retention_days' in data


@pytest.mark.asyncio
async def test_update_retention_policy(http_client: httpx.AsyncClient):
    """Test updating retention policy."""
    new_policy = {
        "continuous_retention_days": 14,
        "event_retention_days": 60
    }

    response = await http_client.put(
        "/api/recordings/retention/policy",
        json=new_policy
    )
    assert response.status_code == 200

    data = response.json()
    assert data.get('success') is True


@pytest.mark.asyncio
async def test_search_recordings(http_client: httpx.AsyncClient):
    """Test searching recordings."""
    response = await http_client.get("/api/recordings/search")
    assert response.status_code == 200

    data = response.json()
    assert 'results' in data


@pytest.mark.asyncio
async def test_cleanup_dry_run(http_client: httpx.AsyncClient):
    """Test cleanup in dry-run mode."""
    response = await http_client.post("/api/recordings/retention/cleanup?dry_run=true")
    assert response.status_code == 200

    data = response.json()
    assert data.get('dry_run') is True
    assert 'deleted_count' in data
