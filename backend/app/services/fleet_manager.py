"""
Fleet Manager Service.
Multi-node MediaMTX management with rolling updates.
"""
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
import httpx

from flask import current_app
from app import db
from app.models import MediaMTXNode, Stream, ConfigSnapshot, StreamStatus


class FleetManager:
    """
    Fleet management for multiple MediaMTX nodes.

    Features:
    - Node inventory and health monitoring
    - Stream sync across nodes
    - Rolling config updates
    - Centralized alerts
    """

    def __init__(self):
        self.timeout = 10

    def sync_node_streams(self, node: MediaMTXNode) -> Dict[str, Any]:
        """
        Sync streams from a MediaMTX node.
        Discovers all paths and updates local database.
        """
        try:
            # Fetch paths from MediaMTX API
            response = httpx.get(f"{node.api_url}/v3/paths/list", timeout=self.timeout)

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Failed to fetch paths: HTTP {response.status_code}",
                    "node_id": node.id
                }

            data = response.json()
            paths = data.get('items', [])

            synced = 0
            created = 0
            updated = 0

            for path_data in paths:
                path_name = path_data.get('name')
                if not path_name:
                    continue

                # Check if stream exists
                stream = Stream.query.filter_by(
                    node_id=node.id,
                    path=path_name
                ).first()

                if stream:
                    # Update existing
                    stream.source_url = path_data.get('source', {}).get('id')
                    updated += 1
                else:
                    # Create new
                    stream = Stream(
                        node_id=node.id,
                        path=path_name,
                        name=path_name,
                        source_url=path_data.get('source', {}).get('id'),
                        protocol=self._detect_protocol(path_data),
                        status=StreamStatus.UNKNOWN.value
                    )
                    db.session.add(stream)
                    created += 1

                synced += 1

            # Update node last_seen
            node.last_seen = datetime.utcnow()
            db.session.commit()

            return {
                "success": True,
                "node_id": node.id,
                "node_name": node.name,
                "total_paths": len(paths),
                "synced": synced,
                "created": created,
                "updated": updated
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "node_id": node.id
            }

    def _detect_protocol(self, path_data: Dict) -> str:
        """Detect protocol from path data."""
        source = path_data.get('source', {})
        source_type = source.get('type', '')

        if 'rtsp' in source_type.lower():
            return 'rtsp'
        elif 'rtmp' in source_type.lower():
            return 'rtmp'
        elif 'webrtc' in source_type.lower():
            return 'webrtc'
        elif 'hls' in source_type.lower():
            return 'hls'
        return 'unknown'

    def sync_all_nodes(self) -> Dict[str, Any]:
        """Sync streams from all active nodes."""
        nodes = MediaMTXNode.query.filter_by(is_active=True).all()
        results = []

        for node in nodes:
            result = self.sync_node_streams(node)
            results.append(result)

        return {
            "total_nodes": len(nodes),
            "successful": sum(1 for r in results if r.get('success')),
            "failed": sum(1 for r in results if not r.get('success')),
            "results": results
        }

    def rolling_update(
        self,
        environment: str = None,
        config_snapshot_id: int = None,
        batch_size: int = 1,
        delay_between_batches: float = 30.0
    ) -> Dict[str, Any]:
        """
        Perform a rolling config update across fleet.

        Args:
            environment: Only update nodes in this environment
            config_snapshot_id: Config to apply
            batch_size: Number of nodes to update at once
            delay_between_batches: Seconds to wait between batches
        """
        from app.services.config_manager import ConfigManager

        # Get config to apply
        if config_snapshot_id:
            snapshot = ConfigSnapshot.query.get(config_snapshot_id)
            if not snapshot:
                return {"success": False, "error": "Config snapshot not found"}
            config_yaml = snapshot.config_yaml
        else:
            return {"success": False, "error": "config_snapshot_id required"}

        # Get target nodes
        query = MediaMTXNode.query.filter_by(is_active=True)
        if environment:
            query = query.filter_by(environment=environment)
        nodes = query.all()

        if not nodes:
            return {"success": False, "error": "No nodes found"}

        config_manager = ConfigManager()
        results = []
        batches = [nodes[i:i+batch_size] for i in range(0, len(nodes), batch_size)]

        for batch_num, batch in enumerate(batches):
            batch_results = []

            for node in batch:
                result = config_manager.apply(
                    node_id=node.id,
                    new_config_yaml=config_yaml,
                    environment=environment,
                    notes=f"Rolling update batch {batch_num + 1}",
                    applied_by="fleet_manager"
                )
                batch_results.append({
                    "node_id": node.id,
                    "node_name": node.name,
                    **result
                })

            results.extend(batch_results)

            # Check if batch succeeded
            batch_failed = sum(1 for r in batch_results if not r.get('success'))
            if batch_failed > 0:
                return {
                    "success": False,
                    "error": f"Batch {batch_num + 1} had {batch_failed} failures, stopping rollout",
                    "completed_batches": batch_num + 1,
                    "results": results
                }

            # Delay before next batch (except for last batch)
            if batch_num < len(batches) - 1:
                time.sleep(delay_between_batches)

        return {
            "success": True,
            "total_nodes": len(nodes),
            "batches": len(batches),
            "results": results
        }

    def get_node_health(self, node: MediaMTXNode) -> Dict[str, Any]:
        """Get health status of a specific node."""
        try:
            # Check API connectivity
            response = httpx.get(f"{node.api_url}/v3/paths/list", timeout=self.timeout)
            api_healthy = response.status_code == 200

            # Get path count
            paths = []
            if api_healthy:
                data = response.json()
                paths = data.get('items', [])

            return {
                "node_id": node.id,
                "node_name": node.name,
                "is_healthy": api_healthy,
                "api_responsive": api_healthy,
                "path_count": len(paths),
                "last_seen": node.last_seen.isoformat() if node.last_seen else None,
                "checked_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            return {
                "node_id": node.id,
                "node_name": node.name,
                "is_healthy": False,
                "error": str(e),
                "checked_at": datetime.utcnow().isoformat()
            }

    def check_all_nodes_health(self) -> Dict[str, Any]:
        """Check health of all nodes in fleet."""
        nodes = MediaMTXNode.query.filter_by(is_active=True).all()
        results = []

        for node in nodes:
            health = self.get_node_health(node)
            results.append(health)

            # Update last_seen if healthy
            if health.get('is_healthy'):
                node.last_seen = datetime.utcnow()

        db.session.commit()

        return {
            "total_nodes": len(nodes),
            "healthy": sum(1 for r in results if r.get('is_healthy')),
            "unhealthy": sum(1 for r in results if not r.get('is_healthy')),
            "results": results
        }

    def apply_policy_to_fleet(
        self,
        policy: Dict[str, Any],
        environment: str = None
    ) -> Dict[str, Any]:
        """
        Apply a uniform policy across all nodes.

        Policy can include:
        - health_check_interval
        - auto_remediation_enabled
        - recording_enabled
        - retention_days
        """
        query = Stream.query.join(MediaMTXNode)
        if environment:
            query = query.filter(MediaMTXNode.environment == environment)

        streams = query.all()
        updated = 0

        for stream in streams:
            if 'auto_remediation_enabled' in policy:
                stream.auto_remediate = policy['auto_remediation_enabled']
            if 'recording_enabled' in policy:
                stream.recording_enabled = policy['recording_enabled']
            updated += 1

        db.session.commit()

        return {
            "success": True,
            "streams_updated": updated,
            "policy_applied": policy
        }

    def get_fleet_metrics(self) -> Dict[str, Any]:
        """Get aggregated metrics across the fleet."""
        nodes = MediaMTXNode.query.filter_by(is_active=True).all()

        total_streams = 0
        healthy_streams = 0
        total_bandwidth = 0

        for node in nodes:
            node_streams = node.streams.all()
            total_streams += len(node_streams)
            healthy_streams += sum(1 for s in node_streams if s.status == StreamStatus.HEALTHY.value)

            # Sum up bitrates
            for stream in node_streams:
                if stream.bitrate:
                    total_bandwidth += stream.bitrate

        return {
            "nodes": {
                "total": len(nodes),
                "by_environment": {
                    "production": sum(1 for n in nodes if n.environment == 'production'),
                    "staging": sum(1 for n in nodes if n.environment == 'staging'),
                    "development": sum(1 for n in nodes if n.environment == 'development')
                }
            },
            "streams": {
                "total": total_streams,
                "healthy": healthy_streams,
                "health_percentage": round(healthy_streams / total_streams * 100, 1) if total_streams > 0 else 0
            },
            "bandwidth": {
                "total_mbps": round(total_bandwidth / 1_000_000, 2)
            },
            "timestamp": datetime.utcnow().isoformat()
        }
