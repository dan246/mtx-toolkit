import { useQuery } from '@tanstack/react-query'
import {
  Radio,
  Server,
  AlertTriangle,
  Film,
  Activity,
  CheckCircle,
  XCircle,
} from 'lucide-react'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import StatCard from '../components/StatCard'
import Card from '../components/Card'
import StatusBadge from '../components/StatusBadge'
import { dashboardApi } from '../services/api'
import type { StreamEvent } from '../types'


export default function Dashboard() {
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
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-gray-500 mt-1">Stream reliability overview</p>
        </div>
        <div className="text-sm text-gray-500">
          Last updated: {overview?.timestamp ? new Date(overview.timestamp).toLocaleTimeString() : '-'}
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Total Streams"
          value={overview?.streams.total || 0}
          subtitle={`${overview?.streams.health_rate || 0}% healthy`}
          icon={<Radio className="w-6 h-6" />}
          color="default"
        />
        <StatCard
          title="Active Nodes"
          value={overview?.nodes.total || 0}
          icon={<Server className="w-6 h-6" />}
          color="success"
        />
        <StatCard
          title="Active Alerts"
          value={alerts?.total || 0}
          subtitle={`${alerts?.by_severity?.critical || 0} critical`}
          icon={<AlertTriangle className="w-6 h-6" />}
          color={alerts?.by_severity?.critical > 0 ? 'danger' : 'warning'}
        />
        <StatCard
          title="Recordings Today"
          value={overview?.recordings.today || 0}
          subtitle={`${overview?.recordings.total_size_gb || 0} GB total`}
          icon={<Film className="w-6 h-6" />}
          color="default"
        />
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Stream Health Chart */}
        <Card title="Stream Health" className="lg:col-span-1">
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
              <p className="text-gray-500">No streams configured</p>
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
        <Card title="Recent Events" className="lg:col-span-2" padding="none">
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
                No recent events
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Active Alerts */}
      {alerts?.alerts?.length > 0 && (
        <Card title="Active Alerts" subtitle={`${alerts.total} unresolved alerts`}>
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
        </Card>
      )}
    </div>
  )
}
