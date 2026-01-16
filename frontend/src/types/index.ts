// Stream types
export type StreamStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown'

export interface Stream {
  id: number
  node_id: number
  path: string
  name: string | null
  source_url: string | null
  protocol: string
  status: StreamStatus
  fps: number | null
  bitrate: number | null
  latency_ms: number | null
  keyframe_interval: number | null
  auto_remediate: boolean
  remediation_count: number
  last_remediation: string | null
  recording_enabled: boolean
  last_check: string | null
  created_at: string
  updated_at: string
}

// Node types
export interface MediaMTXNode {
  id: number
  name: string
  api_url: string
  rtsp_url?: string
  environment: 'development' | 'staging' | 'production'
  is_active: boolean
  last_seen: string | null
  stream_count: number
  healthy_streams: number
  degraded_streams: number
  unhealthy_streams: number
}

// Event types
export type EventSeverity = 'info' | 'warning' | 'error' | 'critical'

export interface StreamEvent {
  id: number
  stream_id: number
  stream_path: string | null
  event_type: string
  severity: EventSeverity
  message: string
  resolved: boolean
  created_at: string
}

// Recording types
export interface Recording {
  id: number
  stream_id: number
  stream_path: string | null
  file_path: string
  file_size: number | null
  duration_seconds: number | null
  start_time: string
  end_time: string | null
  segment_type: 'continuous' | 'event' | 'manual'
  is_archived: boolean
  expires_at: string | null
}

// Config types
export interface ConfigSnapshot {
  id: number
  node_id: number | null
  config_hash: string
  config_yaml: string
  environment: string | null
  applied: boolean
  applied_at: string | null
  applied_by: string | null
  notes: string | null
  created_at: string
}

// Dashboard types
export interface DashboardOverview {
  nodes: {
    total: number
  }
  streams: {
    total: number
    healthy: number
    degraded: number
    unhealthy: number
    health_rate: number
  }
  events: {
    last_24h: number
    critical_unresolved: number
  }
  recordings: {
    today: number
    total_size_gb: number
  }
  timestamp: string
}

// Probe result
export interface ProbeResult {
  is_healthy: boolean
  status: StreamStatus
  url: string
  protocol: string
  fps: number | null
  bitrate: number | null
  latency_ms: number | null
  width: number | null
  height: number | null
  codec: string | null
  audio_codec: string | null
  issues: string[]
  error?: string
}

// Retention status
export interface RetentionStatus {
  disk: {
    total_gb: number
    used_gb: number
    free_gb: number
    usage_percent: number
    threshold_percent: number
    is_critical: boolean
  }
  recordings: {
    total: number
    total_size_gb: number
    by_type: {
      continuous: number
      event: number
      manual: number
    }
    expiring_soon: number
    archived: number
  }
}

// API response types
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pages: number
}
