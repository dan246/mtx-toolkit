import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import {
  Radio,
  Server,
  AlertTriangle,
  Film,
  Activity,
  CheckCircle,
  XCircle,
  Trash2,
  Users,
} from 'lucide-react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import StatCard from '../components/StatCard'
import Card from '../components/Card'
import StatusBadge from '../components/StatusBadge'
import { dashboardApi, sessionsApi } from '../services/api'
import type { PipelineDashboard, PlaybackHealthSummary } from '../types'
import { useLanguage } from '../i18n/LanguageContext'
import { useToast } from '../contexts/ToastContext'
import { useConfirm } from '../contexts/ConfirmContext'
import type { StreamEvent } from '../types'


export default function Dashboard() {
  const { t } = useLanguage()
  const toast = useToast()
  const { confirm, prompt } = useConfirm()
  const queryClient = useQueryClient()
  const [isClearing, setIsClearing] = useState(false)

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ['dashboard-overview'],
    queryFn: dashboardApi.getOverview,
    refetchInterval: 30000,
  })

  const { data: events } = useQuery({
    queryKey: ['dashboard-events'],
    queryFn: () => dashboardApi.getRecentEvents(20),
    refetchInterval: 10000,
  })

  const { data: alerts } = useQuery({
    queryKey: ['dashboard-alerts'],
    queryFn: dashboardApi.getActiveAlerts,
    refetchInterval: 10000,
  })

  const { data: viewersSummary } = useQuery({
    queryKey: ['sessions-summary'],
    queryFn: sessionsApi.getSummary,
    refetchInterval: 10000,
  })

  const { data: livenessSummary } = useQuery({
    queryKey: ['dashboard-liveness'],
    queryFn: dashboardApi.getLivenessSummary,
    refetchInterval: 15000,
  })

  const { data: pipelineSummary } = useQuery<PipelineDashboard>({
    queryKey: ['dashboard-pipeline'],
    queryFn: dashboardApi.getPipelineSummary,
    refetchInterval: 30000,
  })

  const { data: playbackHealth } = useQuery<PlaybackHealthSummary>({
    queryKey: ['dashboard-playback-health'],
    queryFn: dashboardApi.getPlaybackHealth,
    refetchInterval: 30000,
  })

  // Shared runner: invalidate the three event-related queries, surface a
  // success toast, and report any failure — used by all event actions below.
  const runEventAction = async (
    action: () => Promise<unknown>,
    onSuccess: (result: unknown) => string,
  ) => {
    setIsClearing(true)
    try {
      const result = await action()
      ;['dashboard-alerts', 'dashboard-events', 'dashboard-overview'].forEach(key =>
        queryClient.invalidateQueries({ queryKey: [key] })
      )
      toast.success(onSuccess(result))
    } catch (error) {
      toast.error(`${t.common.error}: ${error}`)
    } finally {
      setIsClearing(false)
    }
  }

  const clearedMessage = (result: unknown) =>
    `${t.dashboard.eventsCleared} (${(result as { deleted_count?: number })?.deleted_count ?? 0})`

  const handleResolveAll = () =>
    runEventAction(dashboardApi.resolveAllEvents, () => t.dashboard.eventsResolved)

  const handleClearResolved = async () => {
    if (!(await confirm({ message: t.dashboard.confirmClearEvents }))) return
    runEventAction(dashboardApi.clearResolvedEvents, clearedMessage)
  }

  const handleCleanupOldEvents = async () => {
    const days = await prompt({ message: t.messages.cleanupDaysPrompt, defaultValue: '7', inputType: 'number' })
    if (!days) return
    runEventAction(() => dashboardApi.cleanupEvents(parseInt(days), false), clearedMessage)
  }

  if (overviewLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Activity className="w-8 h-8 animate-spin text-primary-500" />
      </div>
    )
  }

  const streamChartData = overview ? [
    { name: 'Healthy', value: overview.streams.healthy, color: '#22c55e' },
    { name: 'Degraded', value: overview.streams.degraded, color: '#eab308' },
    { name: 'Unhealthy', value: overview.streams.unhealthy, color: '#ef4444' },
  ] : []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t.dashboard.title}</h1>
          <p className="text-gray-500 mt-1">{t.dashboard.subtitle}</p>
        </div>
        <div className="text-sm text-gray-500">
          {t.dashboard.lastUpdated}: {overview?.timestamp ? new Date(overview.timestamp).toLocaleTimeString() : '-'}
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
        <StatCard
          title={t.dashboard.totalStreams}
          value={overview?.streams.total || 0}
          subtitle={`${overview?.streams.health_rate || 0}% ${t.dashboard.healthy}`}
          icon={<Radio className="w-6 h-6" />}
          color="default"
        />
        <StatCard
          title={t.dashboard.activeViewers}
          value={viewersSummary?.total_viewers || 0}
          subtitle={`${viewersSummary?.summary?.by_protocol?.rtsp || 0} RTSP, ${viewersSummary?.summary?.by_protocol?.webrtc || 0} WebRTC`}
          icon={<Users className="w-6 h-6" />}
          color="default"
        />
        <StatCard
          title={t.dashboard.activeNodes}
          value={overview?.nodes.total || 0}
          icon={<Server className="w-6 h-6" />}
          color="success"
        />
        <StatCard
          title={t.dashboard.activeAlerts}
          value={alerts?.total || 0}
          subtitle={`${alerts?.by_severity?.critical || 0} ${t.dashboard.critical}`}
          icon={<AlertTriangle className="w-6 h-6" />}
          color={alerts?.by_severity?.critical > 0 ? 'danger' : 'warning'}
        />
        <StatCard
          title={t.dashboard.recordingsToday}
          value={overview?.recordings.today || 0}
          subtitle={`${overview?.recordings.total_size_gb || 0} GB total`}
          icon={<Film className="w-6 h-6" />}
          color="default"
        />
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Stream Health Chart */}
        <Card title={t.dashboard.streamHealth} className="lg:col-span-1">
          <div className="h-64 flex items-center justify-center">
            {(overview?.streams?.total ?? 0) > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={streamChartData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {streamChartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-gray-500">{t.dashboard.noStreamsConfigured}</p>
            )}
          </div>
          <div className="flex justify-center gap-6 mt-4">
            {streamChartData.map((item) => (
              <div key={item.name} className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: item.color }}
                />
                <span className="text-sm text-gray-600">
                  {item.name}: {item.value}
                </span>
              </div>
            ))}
          </div>
        </Card>

        {/* Recent Events */}
        <Card title={t.dashboard.recentEvents} className="lg:col-span-2" padding="none">
          <div className="divide-y divide-gray-100 max-h-96 overflow-y-auto">
            {(events?.events?.length ?? 0) > 0 ? (
              events?.events?.map((event: StreamEvent) => (
                <div key={event.id} className="px-6 py-3 flex items-center justify-between hover:bg-gray-50">
                  <div className="flex items-center gap-3">
                    {event.resolved ? (
                      <CheckCircle className="w-5 h-5 text-green-500" />
                    ) : (
                      <XCircle className="w-5 h-5 text-red-500" />
                    )}
                    <div>
                      <p className="text-sm font-medium text-gray-900">
                        {event.event_type.replace(/_/g, ' ')}
                      </p>
                      <p className="text-xs text-gray-500">
                        {event.stream_path || `Stream #${event.stream_id}`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <StatusBadge status={event.severity} size="sm" />
                    <span className="text-xs text-gray-400">
                      {new Date(event.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                </div>
              ))
            ) : (
              <div className="px-6 py-8 text-center text-gray-500">
                {t.dashboard.noRecentEvents}
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Liveness, Pipeline & Playback Widgets */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Liveness Summary */}
        <Card title={t.dashboard.streamLiveness}>
          <div className="space-y-3">
            {livenessSummary && Object.entries(livenessSummary).map(([key, count]) => {
              const livenessKeyMap: Record<string, keyof typeof t.liveness> = {
                live: 'live', frozen: 'frozen', black_screen: 'black',
                stale: 'stale', silent: 'silent', unknown: 'unknown',
              }
              return (
                <div key={key} className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">{t.liveness[livenessKeyMap[key] || 'unknown']}</span>
                  <span className={`text-sm font-semibold ${
                    key === 'live' ? 'text-green-600' :
                    key === 'frozen' ? 'text-blue-600' :
                    key === 'black_screen' ? 'text-gray-800' :
                    key === 'stale' ? 'text-orange-600' :
                    key === 'silent' ? 'text-gray-500' :
                    'text-gray-400'
                  }`}>
                    {count as number}
                  </span>
                </div>
              )
            })}
            {!livenessSummary && <p className="text-sm text-gray-400">{t.dashboard.noData}</p>}
          </div>
        </Card>

        {/* Pipeline Health */}
        <Card title={t.dashboard.recordingPipeline}>
          <div className="space-y-3">
            {pipelineSummary ? (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">{t.dashboard.recordingStreams}</span>
                  <span className="text-sm font-semibold">{pipelineSummary.total_recording_streams}</span>
                </div>
                {Object.entries(pipelineSummary.by_status).map(([status, count]) => {
                  const pipelineKeyMap: Record<string, keyof typeof t.pipeline> = {
                    healthy: 'healthy', warning: 'warning', critical: 'critical', unknown: 'unknown',
                  }
                  return (
                    <div key={status} className="flex items-center justify-between">
                      <span className="text-sm text-gray-600">{t.pipeline[pipelineKeyMap[status] || 'unknown']}</span>
                      <span className={`text-sm font-semibold ${
                        status === 'healthy' ? 'text-green-600' :
                        status === 'warning' ? 'text-yellow-600' :
                        status === 'critical' ? 'text-red-600' :
                        'text-gray-400'
                      }`}>{count}</span>
                    </div>
                  )
                })}
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">{t.dashboard.avgWriteLatency}</span>
                  <span className="text-sm font-semibold">
                    {pipelineSummary.avg_write_latency_ms != null
                      ? `${pipelineSummary.avg_write_latency_ms}ms`
                      : '-'}
                  </span>
                </div>
              </>
            ) : (
              <p className="text-sm text-gray-400">{t.dashboard.noData}</p>
            )}
          </div>
        </Card>

        {/* Playback Health */}
        <Card title={t.dashboard.clientPlayback}>
          <div className="space-y-3">
            {playbackHealth ? (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">{t.dashboard.reportsLastHour}</span>
                  <span className="text-sm font-semibold">{playbackHealth.total_reports}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">{t.dashboard.totalStalls}</span>
                  <span className="text-sm font-semibold text-orange-600">{playbackHealth.total_stalls}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">{t.dashboard.frameDropRate}</span>
                  <span className={`text-sm font-semibold ${
                    playbackHealth.drop_rate > 5 ? 'text-red-600' :
                    playbackHealth.drop_rate > 1 ? 'text-yellow-600' :
                    'text-green-600'
                  }`}>{playbackHealth.drop_rate}%</span>
                </div>
              </>
            ) : (
              <p className="text-sm text-gray-400">{t.dashboard.noData}</p>
            )}
          </div>
        </Card>
      </div>

      {/* Active Alerts & Event Management */}
      <Card
        title={t.dashboard.activeAlerts}
        subtitle={`${alerts?.total || 0} ${t.dashboard.unresolvedAlerts}`}
        action={
          <div className="flex gap-2">
            <button
              onClick={handleResolveAll}
              disabled={isClearing}
              className="px-3 py-1.5 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 flex items-center gap-1"
            >
              <CheckCircle className="w-4 h-4" />
              {t.dashboard.resolveAll}
            </button>
            <button
              onClick={handleClearResolved}
              disabled={isClearing}
              className="px-3 py-1.5 text-sm bg-orange-500 text-white rounded-lg hover:bg-orange-600 disabled:opacity-50 flex items-center gap-1"
            >
              <Trash2 className="w-4 h-4" />
              {t.dashboard.clearResolved}
            </button>
            <button
              onClick={handleCleanupOldEvents}
              disabled={isClearing}
              className="px-3 py-1.5 text-sm bg-gray-500 text-white rounded-lg hover:bg-gray-600 disabled:opacity-50 flex items-center gap-1"
            >
              <Trash2 className="w-4 h-4" />
              {t.dashboard.cleanupOldEvents}
            </button>
          </div>
        }
      >
        {alerts?.alerts?.length > 0 ? (
          <div className="space-y-3">
            {alerts.alerts.slice(0, 5).map((alert: StreamEvent & { duration_minutes: number }) => (
              <div
                key={alert.id}
                className="flex items-center justify-between p-4 bg-red-50 border border-red-100 rounded-lg"
              >
                <div className="flex items-center gap-3">
                  <AlertTriangle className="w-5 h-5 text-red-500" />
                  <div>
                    <p className="font-medium text-gray-900">{alert.message}</p>
                    <p className="text-sm text-gray-500">
                      {alert.stream_path} - {alert.duration_minutes} min ago
                    </p>
                  </div>
                </div>
                <StatusBadge status={alert.severity} />
              </div>
            ))}
          </div>
        ) : (
          <div className="py-8 text-center text-gray-500">
            {t.dashboard.noRecentEvents}
          </div>
        )}
      </Card>
    </div>
  )
}
