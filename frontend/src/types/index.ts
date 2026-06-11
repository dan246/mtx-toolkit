// Stream types
export type StreamStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown'

// Phase 1: Liveness
export type LivenessClassification = 'live' | 'frozen' | 'black_screen' | 'stale' | 'silent' | 'unknown'

// Phase 2: Source Protocol
export type SourceProtocol = 'rtsp' | 'rtmp' | 'whep' | 'whip' | 'hls' | 'srt' | 'unknown'

// Phase 3: Fallback
export type FallbackType = 'color_bars' | 'custom_image' | 'last_frame' | 'none'

// Phase 5: Pipeline
export type PipelineStatus = 'healthy' | 'warning' | 'critical' | 'unknown'

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
  // Live metrics from MediaMTX path API
  viewers?: number | null
  bytes_received?: number | null
  bytes_sent?: number | null
  frames_in_error?: number | null
  source_type?: string | null
  codec?: string | null
  width?: number | null
  height?: number | null
  online_since?: string | null
  uptime_seconds?: number | null
  auto_remediate: boolean
  remediation_count: number
  last_remediation: string | null
  recording_enabled: boolean
  last_check: string | null
  created_at: string
  updated_at: string
  // Phase 1: Liveness
  liveness_classification?: LivenessClassification
  liveness_last_check?: string | null
  consecutive_freeze_checks?: number
  freeze_started_at?: string | null
  // Phase 2: Source Protocol
  source_protocol?: SourceProtocol
  // Phase 3: Fallback
  fallback_type?: FallbackType
  fallback_active?: boolean
  fallback_activated_at?: string | null
  // Phase 5: Pipeline
  recording_pipeline_status?: PipelineStatus
  recording_avg_write_latency_ms?: number | null
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

// Config plan/apply result
export interface PlanResult {
  can_apply?: boolean
  validation?: {
    valid?: boolean
    errors?: string[]
    warnings?: string[]
  }
  diff?: {
    has_changes?: boolean
    unified_diff?: string
  }
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
  stream_name: string | null
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

// Session/Viewer types
export type SessionProtocol = 'rtsp' | 'rtsps' | 'webrtc' | 'rtmp' | 'srt'

export interface ViewerSession {
  id: string
  node_id: number
  node_name: string
  path: string
  protocol: SessionProtocol
  remote_addr: string
  client_ip: string
  client_port: number
  state: string
  created: string
  duration_seconds: number
  bytes_received: number
  bytes_sent: number
  transport?: string
}

export interface SessionsSummary {
  total_viewers: number
  by_protocol: Record<string, number>
  by_node: Record<string, number>
  by_path: Record<string, number>
}

export interface SessionsResponse {
  sessions: ViewerSession[]
  summary: SessionsSummary
  total: number
  page: number
  pages: number
  errors?: Array<{
    node_id: number
    node_name: string
    protocol: string
    error: string
  }>
}

// Phase 1: Liveness types
export interface LivenessStatus {
  id: number
  path: string
  name: string | null
  status: StreamStatus
  liveness_classification: LivenessClassification
  liveness_last_check: string | null
  consecutive_freeze_checks: number
  freeze_started_at: string | null
}

export interface LivenessProbeHistory {
  id: number
  classification: LivenessClassification
  pts_value: number | null
  pts_delta: number | null
  frame_hash_changed: boolean | null
  brightness: number | null
  audio_rms: number | null
  keyframe_present: boolean | null
  probe_duration_ms: number | null
  created_at: string
}

// Phase 3: Fallback types
export interface FallbackStatus {
  stream_id: number
  fallback_type: FallbackType
  fallback_active: boolean
  fallback_activated_at: string | null
  fallback_image_path: string | null
}

// Phase 4: Playback types
export interface PlaybackReport {
  id: number
  stream_id: number
  client_id: string | null
  client_ip: string | null
  stall_count: number
  stall_duration_ms: number
  buffer_underrun_count: number
  frames_decoded: number | null
  frames_dropped: number | null
  current_level: number | null
  recovery_action: string | null
  error_type: string | null
  created_at: string
}

export interface PlaybackHealthSummary {
  total_reports: number
  total_stalls: number
  total_frames_dropped: number
  total_frames_decoded: number
  drop_rate: number
  recovery_actions: Record<string, number>
}

export interface PlaybackIssue {
  type: 'stall' | 'buffer_underrun' | 'frame_drop'
  duration_ms?: number
  action: 'seek_nudge' | 'level_switch' | 'full_reload'
}

// Phase 5: Pipeline types
export interface PipelineMetrics {
  id: number
  segment_write_duration_ms: number | null
  segment_size_bytes: number | null
  disk_io_latency_ms: number | null
  segment_gap_seconds: number | null
  created_at: string
}

export interface PipelineDashboard {
  total_recording_streams: number
  by_status: Record<string, number>
  avg_write_latency_ms: number | null
  recent_gaps: number
}

// API response types
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pages: number
}
