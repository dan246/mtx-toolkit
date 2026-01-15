"""
Integration tests for config-as-code management.
"""
import pytest
import httpx


TEST_CONFIG = """
paths:
  test:
    source: publisher
  cam1:
    source: rtsp://example.com/stream
"""

INVALID_CONFIG = """
this is not: valid
  yaml: [
"""


@pytest.mark.asyncio
async def test_validate_valid_config(http_client: httpx.AsyncClient):
    """Test validating a valid configuration."""
    response = await http_client.post(
        "/api/config/validate",
        json={"config_yaml": TEST_CONFIG}
    )
    assert response.status_code == 200

    data = response.json()
    assert data.get('valid') is True
    assert len(data.get('errors', [])) == 0


@pytest.mark.asyncio
async def test_validate_invalid_config(http_client: httpx.AsyncClient):
    """Test validating an invalid configuration."""
    response = await http_client.post(
        "/api/config/validate",
        json={"config_yaml": INVALID_CONFIG}
    )
    assert response.status_code == 200

    data = response.json()
    assert data.get('valid') is False
    assert len(data.get('errors', [])) > 0


@pytest.mark.asyncio
async def test_plan_config_change(http_client: httpx.AsyncClient):
    """Test planning a config change."""
    response = await http_client.post(
        "/api/config/plan",
        json={"config_yaml": TEST_CONFIG}
    )
    assert response.status_code == 200

    data = response.json()
    assert 'can_apply' in data
    assert 'validation' in data
    assert 'diff' in data


@pytest.mark.asyncio
async def test_diff_configs(http_client: httpx.AsyncClient):
    """Test diffing two configurations."""
    old_config = """
paths:
  cam1:
    source: rtsp://old.com/stream
"""
    new_config = """
paths:
  cam1:
    source: rtsp://new.com/stream
  cam2:
    source: rtsp://added.com/stream
"""

    response = await http_client.post(
        "/api/config/diff",
        json={
            "old_config": old_config,
            "new_config": new_config
        }
    )
    assert response.status_code == 200

    data = response.json()
    assert data.get('has_changes') is True
    assert 'unified_diff' in data
    assert 'changes' in data


@pytest.mark.asyncio
async def test_list_snapshots(http_client: httpx.AsyncClient):
    """Test listing config snapshots."""
    response = await http_client.get("/api/config/snapshots")
    assert response.status_code == 200

    data = response.json()
    assert 'snapshots' in data


@pytest.mark.asyncio
async def test_list_environments(http_client: httpx.AsyncClient):
    """Test listing environments."""
    response = await http_client.get("/api/config/environments")
    assert response.status_code == 200

    data = response.json()
    assert 'environments' in data
    assert 'development' in data['environments']
    assert 'production' in data['environments']
