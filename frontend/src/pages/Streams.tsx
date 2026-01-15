import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Radio,
  RefreshCw,
  Play,
  Settings,
  Plus,
  Search,
  Wrench,
} from 'lucide-react'
import Card from '../components/Card'
import StatusBadge from '../components/StatusBadge'
import { streamsApi, healthApi } from '../services/api'
import type { Stream, StreamStatus } from '../types'

export default function Streams() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StreamStatus | ''>('')

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['streams', statusFilter],
    queryFn: () => streamsApi.list({ status: statusFilter || undefined }),
    refetchInterval: 30000,
  })

  const probeMutation = useMutation({
    mutationFn: (streamId: number) => healthApi.probeStream(streamId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['streams'] })
    },
  })

  const remediateMutation = useMutation({
    mutationFn: (streamId: number) => streamsApi.remediate(streamId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['streams'] })
    },
  })

  const filteredStreams = data?.streams?.filter((stream: Stream) =>
    stream.path.toLowerCase().includes(search.toLowerCase()) ||
    stream.name?.toLowerCase().includes(search.toLowerCase())
  ) || []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Streams</h1>
          <p className="text-gray-500 mt-1">Monitor and manage stream health</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => refetch()}
            className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-lg hover:bg-gray-50"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700">
            <Plus className="w-4 h-4" />
            Add Stream
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type="text"
            placeholder="Search streams..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StreamStatus | '')}
          className="px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="">All Status</option>
          <option value="healthy">Healthy</option>
          <option value="degraded">Degraded</option>
          <option value="unhealthy">Unhealthy</option>
          <option value="unknown">Unknown</option>
        </select>
      </div>

      {/* Stream List */}
      <Card padding="none">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw className="w-8 h-8 animate-spin text-primary-500" />
          </div>
        ) : filteredStreams.length > 0 ? (
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Stream</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">FPS</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Bitrate</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Latency</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Last Check</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {filteredStreams.map((stream: Stream) => (
                <tr key={stream.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <Radio className="w-5 h-5 text-gray-400" />
                      <div>
                        <p className="font-medium text-gray-900">{stream.path}</p>
                        {stream.name && (
                          <p className="text-sm text-gray-500">{stream.name}</p>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <StatusBadge status={stream.status} />
                  </td>
                  <td className="px-6 py-4 text-gray-600">
                    {stream.fps ? `${stream.fps.toFixed(1)} fps` : '-'}
                  </td>
                  <td className="px-6 py-4 text-gray-600">
                    {stream.bitrate ? `${(stream.bitrate / 1000).toFixed(0)} kbps` : '-'}
                  </td>
                  <td className="px-6 py-4 text-gray-600">
                    {stream.latency_ms ? `${stream.latency_ms} ms` : '-'}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {stream.last_check
                      ? new Date(stream.last_check).toLocaleTimeString()
                      : 'Never'}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => probeMutation.mutate(stream.id)}
                        disabled={probeMutation.isPending}
                        className="p-2 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg"
                        title="Probe Stream"
                      >
                        <Play className="w-4 h-4" />
                      </button>
                      {stream.status === 'unhealthy' && stream.auto_remediate && (
                        <button
                          onClick={() => remediateMutation.mutate(stream.id)}
                          disabled={remediateMutation.isPending}
                          className="p-2 text-gray-400 hover:text-yellow-600 hover:bg-yellow-50 rounded-lg"
                          title="Remediate"
                        >
                          <Wrench className="w-4 h-4" />
                        </button>
                      )}
                      <button
                        onClick={() => console.log('Settings for', stream.path)}
                        className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg"
                        title="Settings"
                      >
                        <Settings className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="flex flex-col items-center justify-center py-12">
            <Radio className="w-12 h-12 text-gray-300 mb-4" />
            <p className="text-gray-500">No streams found</p>
          </div>
        )}
      </Card>

      {/* Summary */}
      {data && (
        <div className="text-sm text-gray-500">
          Showing {filteredStreams.length} of {data.total} streams
        </div>
      )}
    </div>
  )
}
