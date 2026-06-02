"""
Fallback Manager Service.
Reader-preserving repair via fallback stream sources.
"""

from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from flask import current_app

from app import db
from app.models import EventType, FallbackType, Stream, StreamEvent


class FallbackManager:
    """
    Manages fallback streams to keep readers connected during remediation.
    Works by patching the MediaMTX path source to an ffmpeg-generated stream.
    """

    def __init__(self):
        self.assets_path = (
            current_app.config.get("FALLBACK_ASSETS_PATH", "/fallback-assets")
            if current_app
            else "/fallback-assets"
        )

    def activate_fallback(self, stream: Stream) -> Dict[str, Any]:
        """Activate fallback source for a stream."""
        if stream.fallback_type == FallbackType.NONE.value:
            return {"success": False, "message": "No fallback configured"}

        if stream.fallback_active:
            return {"success": False, "message": "Fallback already active"}

        node = stream.node
        api_url = node.api_url

        try:
            # Get stream params for matching
            params = self._get_stream_params(stream, api_url)

            # Generate fallback source based on type
            fallback_source = None
            if stream.fallback_type == FallbackType.COLOR_BARS.value:
                fallback_source = self._generate_color_bars_source(stream, params)
            elif stream.fallback_type == FallbackType.CUSTOM_IMAGE.value:
                fallback_source = self._generate_image_source(stream, params)
            elif stream.fallback_type == FallbackType.LAST_FRAME.value:
                fallback_source = self._generate_last_frame_source(stream, params)

            if not fallback_source:
                return {
                    "success": False,
                    "message": "Failed to generate fallback source",
                }

            # Patch MediaMTX path source to fallback
            patch_resp = httpx.patch(
                f"{api_url}/v3/config/paths/patch/{stream.path}",
                json={"source": fallback_source},
                timeout=10,
            )

            if patch_resp.status_code not in [200, 204]:
                return {
                    "success": False,
                    "message": f"Failed to patch path: HTTP {patch_resp.status_code}",
                }

            # Update stream state
            stream.fallback_active = True
            stream.fallback_activated_at = datetime.utcnow()

            # Create event
            event = StreamEvent(
                stream_id=stream.id,
                event_type=EventType.FALLBACK_ACTIVATED.value,
                severity="info",
                message=f"Fallback activated ({stream.fallback_type}) for {stream.path}",
            )
            db.session.add(event)
            db.session.commit()

            return {
                "success": True,
                "message": f"Fallback ({stream.fallback_type}) activated",
                "fallback_source": fallback_source,
            }

        except Exception as e:
            return {"success": False, "message": f"Fallback activation failed: {e}"}

    def deactivate_fallback(self, stream: Stream) -> Dict[str, Any]:
        """Deactivate fallback and restore original source."""
        if not stream.fallback_active:
            return {"success": False, "message": "No fallback is active"}

        node = stream.node
        api_url = node.api_url

        try:
            # Restore original source
            original_source = stream.source_url or ""
            patch_resp = httpx.patch(
                f"{api_url}/v3/config/paths/patch/{stream.path}",
                json={"source": original_source},
                timeout=10,
            )

            if patch_resp.status_code not in [200, 204]:
                return {
                    "success": False,
                    "message": f"Failed to restore source: HTTP {patch_resp.status_code}",
                }

            # Update stream state
            stream.fallback_active = False
            stream.fallback_activated_at = None

            # Create event
            event = StreamEvent(
                stream_id=stream.id,
                event_type=EventType.FALLBACK_DEACTIVATED.value,
                severity="info",
                message=f"Fallback deactivated for {stream.path}",
            )
            db.session.add(event)
            db.session.commit()

            return {"success": True, "message": "Fallback deactivated, source restored"}

        except Exception as e:
            return {"success": False, "message": f"Fallback deactivation failed: {e}"}

    def configure_fallback(
        self,
        stream_id: int,
        fallback_type: str,
        image_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Configure fallback type for a stream."""
        stream = Stream.query.get(stream_id)
        if not stream:
            return {"success": False, "message": "Stream not found"}

        if fallback_type not in [ft.value for ft in FallbackType]:
            return {
                "success": False,
                "message": f"Invalid fallback type: {fallback_type}",
            }

        stream.fallback_type = fallback_type
        if image_path:
            stream.fallback_image_path = image_path

        db.session.commit()

        return {
            "success": True,
            "message": f"Fallback configured: {fallback_type}",
            "stream_id": stream_id,
            "fallback_type": fallback_type,
        }

    def get_fallback_status(self, stream_id: int) -> Optional[Dict[str, Any]]:
        """Get fallback status for a stream."""
        stream = Stream.query.get(stream_id)
        if not stream:
            return None

        return {
            "stream_id": stream.id,
            "fallback_type": stream.fallback_type,
            "fallback_active": stream.fallback_active,
            "fallback_activated_at": (
                stream.fallback_activated_at.isoformat()
                if stream.fallback_activated_at
                else None
            ),
            "fallback_image_path": stream.fallback_image_path,
        }

    def _get_stream_params(self, stream: Stream, api_url: str) -> Dict[str, Any]:
        """Get codec/resolution info from stream for fallback matching."""
        params = {
            "width": 1920,
            "height": 1080,
            "fps": 25,
            "codec": "libx264",
        }

        # Try to get actual params from stream metrics
        if stream.fps:
            params["fps"] = int(stream.fps)

        return params

    def _generate_color_bars_source(
        self, stream: Stream, params: Dict
    ) -> Optional[str]:
        """Generate ffmpeg testsrc2 source URL for color bars."""
        w = params.get("width", 1920)
        h = params.get("height", 1080)
        fps = params.get("fps", 25)
        return f"ffmpeg:testsrc2=size={w}x{h}:rate={fps}"

    def _generate_image_source(self, stream: Stream, params: Dict) -> Optional[str]:
        """Generate ffmpeg image loop source."""
        image_path = stream.fallback_image_path
        if not image_path:
            image_path = f"{self.assets_path}/fallback.png"

        fps = params.get("fps", 25)
        return f"ffmpeg:loop=1:i={image_path}:rate={fps}"

    def _generate_last_frame_source(
        self, stream: Stream, params: Dict
    ) -> Optional[str]:
        """Generate ffmpeg loop of last thumbnail."""
        from app.services.thumbnail_service import thumbnail_service

        thumb_path = thumbnail_service.get_cached_thumbnail(stream.path, stream.node_id)
        if thumb_path:
            fps = params.get("fps", 25)
            return f"ffmpeg:loop=1:i={thumb_path}:rate={fps}"
        # Fall back to color bars
        return self._generate_color_bars_source(stream, params)
