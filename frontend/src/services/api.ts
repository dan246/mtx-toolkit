import axios from 'axios'
import type {
  Stream,
  MediaMTXNode,
  StreamEvent,
  Recording,
  ConfigSnapshot,
  DashboardOverview,
  ProbeResult,
  RetentionStatus,
  SessionsResponse,
  SessionsSummary,
  LivenessStatus,
  LivenessProbeHistory,
  FallbackStatus,
  PlaybackReport,
  PlaybackHealthSummary,
  PipelineDashboard,
  PipelineMetrics,
} from '../types'

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Dashboard
export const dashboardApi = {
  getOverview: () => api.get<DashboardOverview>('/dashboard/overview').then(r => r.data),
  getStreamsStatus: () => api.get('/dashboard/streams/status').then(r => r.data),
  getRecentEvents: (limit = 50) => api.get<{ events: StreamEvent[] }>(`/dashboard/events/recent?limit=${limit}`).then(r => r.data),
  getActiveAlerts: () => api.get('/dashboard/alerts/active').then(r => r.data),
  getNodesStatus: () => api.get('/dashboard/nodes/status').then(r => r.data),
  // Event management
  cleanupEvents: (days = 7, resolvedOnly = false) =>
    api.post('/dashboard/events/cleanup', { days, resolved_only: resolvedOnly }).then(r => r.data),
  resolveAllEvents: () => api.post('/dashboard/events/resolve-all').then(r => r.data),
  clearResolvedEvents: () => api.post('/dashboard/events/clear-resolved').then(r => r.data),
  // Phase 1: Liveness
  getLivenessSummary: () => api.get<Record<string, number>>('/dashboard/liveness').then(r => r.data),
  // Phase 4: Playback health
  getPlaybackHealth: () => api.get<PlaybackHealthSummary>('/dashboard/playback-health').then(r => r.data),
  // Phase 5: Pipeline
  getPipelineSummary: () => api.get<PipelineDashboard>('/dashboard/pipeline').then(r => r.data),
}

// Health
export const healthApi = {
  getStatus: () => api.get('/health/').then(r => r.data),
  getStreamsHealth: (nodeId?: number, status?: string) => {
    const params = new URLSearchParams()
    if (nodeId) params.set('node_id', String(nodeId))
    if (status) params.set('status', status)
    return api.get(`/health/streams?${params}`).then(r => r.data)
  },
  getStreamHealth: (streamId: number) => api.get(`/health/streams/${streamId}`).then(r => r.data),
  probeStream: (streamId: number) => api.post<ProbeResult>(`/health/streams/${streamId}/probe`).then(r => r.data),
  probeUrl: (url: string, protocol = 'rtsp') =>
    api.post<ProbeResult>('/health/probe', { url, protocol }).then(r => r.data),
  // Phase 4: Playback reports
  submitPlaybackReport: (data: {
    stream_id: number
    client_id?: string
    stall_count?: number
    stall_duration_ms?: number
    buffer_underrun_count?: number
    frames_decoded?: number
    frames_dropped?: number
    current_level?: number
    recovery_action?: string
    error_type?: string
  }) => api.post('/health/playback-report', data).then(r => r.data),
  getPlaybackReports: (streamId: number, limit = 50) =>
    api.get<{ stream_id: number; reports: PlaybackReport[]; total: number }>(
      `/health/playback-reports/${streamId}?limit=${limit}`
    ).then(r => r.data),
}

// Streams
export const streamsApi = {
  list: (params?: { node_id?: number; status?: string; search?: string; page?: number; per_page?: number }) =>
    api.get('/streams/', { params }).then(r => r.data),
  get: (id: number) => api.get<Stream>(`/streams/${id}`).then(r => r.data),
  create: (data: Partial<Stream>) => api.post('/streams/', data).then(r => r.data),
  update: (id: number, data: Partial<Stream>) => api.put(`/streams/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/streams/${id}`).then(r => r.data),
  remediate: (id: number) => api.post(`/streams/${id}/remediate`).then(r => r.data),
  getPlayback: (id: number) => api.get(`/streams/${id}/playback`).then(r => r.data),
  getPlaybackConfig: () => api.get('/streams/playback/config').then(r => r.data),
  getThumbnailUrl: (id: number) => `/api/streams/${id}/thumbnail?t=${Date.now()}`,
  generateThumbnails: (streamIds?: number[], force?: boolean) =>
    api.post('/streams/thumbnail/batch', { stream_ids: streamIds, force }).then(r => r.data),
  // Phase 2: Protocol revival
  softReset: (id: number) => api.post(`/streams/${id}/soft-reset`).then(r => r.data),
  revive: (id: number) => api.post(`/streams/${id}/revive`).then(r => r.data),
}

// Fleet
export const fleetApi = {
  listNodes: (params?: { environment?: string; active_only?: boolean }) =>
    api.get('/fleet/nodes', { params }).then(r => r.data),
  getNode: (id: number) => api.get<MediaMTXNode>(`/fleet/nodes/${id}`).then(r => r.data),
  createNode: (data: Partial<MediaMTXNode>) => api.post('/fleet/nodes', data).then(r => r.data),
  updateNode: (id: number, data: Partial<MediaMTXNode>) => api.put(`/fleet/nodes/${id}`, data).then(r => r.data),
  deleteNode: (id: number) => api.delete(`/fleet/nodes/${id}`).then(r => r.data),
  syncNode: (id: number) => api.post(`/fleet/nodes/${id}/sync`).then(r => r.data),
  syncAll: () => api.post('/fleet/sync-all').then(r => r.data),
  getOverview: () => api.get('/fleet/overview').then(r => r.data),
  rollingUpdate: (data: { environment?: string; config_snapshot_id: number }) =>
    api.post('/fleet/rolling-update', data).then(r => r.data),
}

// Config
export const configApi = {
  listSnapshots: (params?: { node_id?: number; environment?: string; limit?: number }) =>
    api.get('/config/snapshots', { params }).then(r => r.data),
  getSnapshot: (id: number) => api.get<ConfigSnapshot>(`/config/snapshots/${id}`).then(r => r.data),
  plan: (data: { node_id?: number; config_yaml: string; environment?: string }) =>
    api.post('/config/plan', data).then(r => r.data),
  apply: (data: { node_id?: number; config_yaml: string; environment?: string; notes?: string }) =>
    api.post('/config/apply', data).then(r => r.data),
  rollback: (snapshotId: number) => api.post('/config/rollback', { snapshot_id: snapshotId }).then(r => r.data),
  validate: (configYaml: string) => api.post('/config/validate', { config_yaml: configYaml }).then(r => r.data),
  diff: (oldConfig: string, newConfig: string) =>
    api.post('/config/diff', { old_config: oldConfig, new_config: newConfig }).then(r => r.data),
  exportConfig: (nodeId: number) => api.get(`/config/export/${nodeId}`).then(r => r.data),
}

// Recordings
export const recordingsApi = {
  list: (params?: { stream_id?: number; segment_type?: string; search?: string; page?: number; per_page?: number }) =>
    api.get('/recordings/', { params }).then(r => r.data),
  get: (id: number) => api.get<Recording>(`/recordings/${id}`).then(r => r.data),
  archive: (id: number) => api.post(`/recordings/${id}/archive`).then(r => r.data),
  getRetentionStatus: () => api.get<RetentionStatus>('/recordings/retention/status').then(r => r.data),
  triggerCleanup: (dryRun = false) => api.post(`/recordings/retention/cleanup?dry_run=${dryRun}`).then(r => r.data),
  getPolicy: () => api.get('/recordings/retention/policy').then(r => r.data),
  updatePolicy: (policy: Record<string, unknown>) => api.put('/recordings/retention/policy', policy).then(r => r.data),
  search: (params: { stream_path?: string; start_time?: string; end_time?: string }) =>
    api.get('/recordings/search', { params }).then(r => r.data),
  getPlaybackUrl: (id: number) => api.get(`/recordings/playback/${id}`).then(r => r.data),
  scan: (params?: { node_id?: number; force_rescan?: boolean }) =>
    api.post('/recordings/scan', params || {}).then(r => r.data),
}

// Sessions (Viewers)
export const sessionsApi = {
  list: (params?: { node_id?: number; protocol?: string; path?: string; page?: number; per_page?: number }) =>
    api.get<SessionsResponse>('/sessions/', { params }).then(r => r.data),
  getSummary: () => api.get<{ summary: SessionsSummary; total_viewers: number }>('/sessions/summary').then(r => r.data),
  getByNode: (nodeId: number, params?: { protocol?: string; page?: number; per_page?: number }) =>
    api.get<SessionsResponse>(`/sessions/node/${nodeId}`, { params }).then(r => r.data),
  getByStream: (streamId: number, params?: { page?: number; per_page?: number }) =>
    api.get<SessionsResponse>(`/sessions/stream/${streamId}`, { params }).then(r => r.data),
  getByPath: (path: string, params?: { page?: number; per_page?: number }) =>
    api.get<SessionsResponse>(`/sessions/path/${path}`, { params }).then(r => r.data),
  kick: (
    nodeId: number,
    sessionId: string,
    protocol: string,
  ) =>
    api.post<{ success: boolean; message?: string; error?: string }>('/sessions/kick', {
      node_id: nodeId,
      session_id: sessionId,
      protocol: protocol,
    }).then(r => r.data),
}

// Phase 1: Liveness
export const livenessApi = {
  listStreams: (classification?: string) =>
    api.get<{ streams: LivenessStatus[]; total: number }>('/liveness/streams', {
      params: classification ? { classification } : undefined,
    }).then(r => r.data),
  getStream: (streamId: number) => api.get(`/liveness/streams/${streamId}`).then(r => r.data),
  triggerProbe: (streamId: number) => api.post(`/liveness/streams/${streamId}/probe`).then(r => r.data),
  getHistory: (streamId: number, limit = 100) =>
    api.get<{ stream_id: number; probes: LivenessProbeHistory[]; total: number }>(
      `/liveness/history/${streamId}?limit=${limit}`
    ).then(r => r.data),
}

// Phase 3: Fallback
export const fallbackApi = {
  getConfig: (streamId: number) => api.get<FallbackStatus>(`/fallback/streams/${streamId}`).then(r => r.data),
  configure: (streamId: number, data: { fallback_type: string; image_path?: string }) =>
    api.put(`/fallback/streams/${streamId}`, data).then(r => r.data),
  activate: (streamId: number) => api.post(`/fallback/streams/${streamId}/activate`).then(r => r.data),
  deactivate: (streamId: number) => api.post(`/fallback/streams/${streamId}/deactivate`).then(r => r.data),
  listActive: () => api.get('/fallback/active').then(r => r.data),
}

// Phase 5: Pipeline
export const pipelineApi = {
  getStatus: () => api.get<PipelineDashboard>('/pipeline/status').then(r => r.data),
  getStreamPipeline: (streamId: number) => api.get(`/pipeline/streams/${streamId}`).then(r => r.data),
  getStreamMetrics: (streamId: number, limit = 100) =>
    api.get<{ stream_id: number; metrics: PipelineMetrics[]; total: number }>(
      `/pipeline/streams/${streamId}/metrics?limit=${limit}`
    ).then(r => r.data),
  getGaps: () => api.get('/pipeline/gaps').then(r => r.data),
  triggerCheck: (streamId: number) => api.post(`/pipeline/streams/${streamId}/check`).then(r => r.data),
}

export default api
