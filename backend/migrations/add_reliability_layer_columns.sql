-- Stream Reliability Layer - Database Migration
-- Run this BEFORE restarting containers if your DB already has the 'stream' table
-- New tables (liveness_probe_result, client_playback_report, recording_pipeline_metric)
-- will be created automatically by db.create_all()

-- Phase 1: Liveness Probe fields on Stream
ALTER TABLE streams ADD COLUMN IF NOT EXISTS liveness_classification VARCHAR(50) DEFAULT 'unknown';
ALTER TABLE streams ADD COLUMN IF NOT EXISTS liveness_last_check TIMESTAMP;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS last_pts BIGINT;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS last_frame_hash VARCHAR(64);
ALTER TABLE streams ADD COLUMN IF NOT EXISTS freeze_started_at TIMESTAMP;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS consecutive_freeze_checks INTEGER DEFAULT 0;

-- Phase 2: Protocol-Aware Path Revival
ALTER TABLE streams ADD COLUMN IF NOT EXISTS source_protocol VARCHAR(50) DEFAULT 'unknown';

-- Phase 3: Reader-Preserving Repair (Fallback)
ALTER TABLE streams ADD COLUMN IF NOT EXISTS fallback_type VARCHAR(50) DEFAULT 'none';
ALTER TABLE streams ADD COLUMN IF NOT EXISTS fallback_image_path VARCHAR(1024);
ALTER TABLE streams ADD COLUMN IF NOT EXISTS fallback_active BOOLEAN DEFAULT FALSE;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS fallback_activated_at TIMESTAMP;

-- Phase 5: Recording Pipeline Monitor
ALTER TABLE streams ADD COLUMN IF NOT EXISTS recording_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS recording_pipeline_status VARCHAR(50) DEFAULT 'unknown';
ALTER TABLE streams ADD COLUMN IF NOT EXISTS recording_last_segment_at TIMESTAMP;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS recording_avg_write_latency_ms FLOAT;
