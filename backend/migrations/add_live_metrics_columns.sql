-- Live stream metrics sourced from the MediaMTX path API
-- (viewers, bandwidth, frames-in-error, uptime, codec/resolution).
-- Populated every quick-check (no ffprobe required).
-- Run on existing deployments before restarting containers; db.create_all()
-- only creates missing tables, not missing columns.

ALTER TABLE streams ADD COLUMN IF NOT EXISTS viewers INTEGER DEFAULT 0;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS bytes_received BIGINT;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS bytes_sent BIGINT;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS frames_in_error BIGINT;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS online_since TIMESTAMP;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS source_type VARCHAR(50);
ALTER TABLE streams ADD COLUMN IF NOT EXISTS codec VARCHAR(50);
ALTER TABLE streams ADD COLUMN IF NOT EXISTS width INTEGER;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS height INTEGER;
