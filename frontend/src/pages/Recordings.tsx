import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Film,
  HardDrive,
  Archive,
  Trash2,
  Play,
  Download,
  Search,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react'
import Card from '../components/Card'
import StatCard from '../components/StatCard'
import { recordingsApi } from '../services/api'
import type { Recording } from '../types'

export default function Recordings() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [segmentType, setSegmentType] = useState('')

  const { data: recordings, isLoading } = useQuery({
    queryKey: ['recordings', segmentType],
    queryFn: () => recordingsApi.list({ segment_type: segmentType || undefined }),
    refetchInterval: 30000,
  })

  const { data: status } = useQuery({
    queryKey: ['retention-status'],
    queryFn: recordingsApi.getRetentionStatus,
    refetchInterval: 60000,
  })

  const archiveMutation = useMutation({
    mutationFn: (id: number) => recordingsApi.archive(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recordings'] })
    },
  })

  const cleanupMutation = useMutation({
    mutationFn: () => recordingsApi.triggerCleanup(false),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recordings'] })
      queryClient.invalidateQueries({ queryKey: ['retention-status'] })
    },
  })

  const filteredRecordings = recordings?.recordings?.filter((rec: Recording) =>
    rec.stream_path?.toLowerCase().includes(search.toLowerCase()) ||
    rec.file_path.toLowerCase().includes(search.toLowerCase())
  ) || []

  const formatSize = (bytes: number | null) => {
    if (!bytes) return '-'
    if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
    if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(2)} MB`
    return `${(bytes / 1024).toFixed(2)} KB`
  }

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return '-'
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = seconds % 60
    if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Recordings</h1>
          <p className="text-gray-500 mt-1">Recording management and retention</p>
        </div>
        <button
          onClick={() => cleanupMutation.mutate()}
          disabled={cleanupMutation.isPending}
          className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-lg hover:bg-gray-50"
        >
          <Trash2 className="w-4 h-4" />
          Run Cleanup
        </button>
      </div>

      {/* Storage Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <StatCard
          title="Total Recordings"
          value={status?.recordings.total || 0}
          icon={<Film className="w-6 h-6" />}
          color="default"
        />
        <StatCard
          title="Total Size"
          value={`${status?.recordings.total_size_gb || 0} GB`}
          icon={<HardDrive className="w-6 h-6" />}
          color="default"
        />
        <StatCard
          title="Disk Usage"
          value={`${status?.disk.usage_percent || 0}%`}
          subtitle={`${status?.disk.free_gb || 0} GB free`}
          icon={<HardDrive className="w-6 h-6" />}
          color={status?.disk.is_critical ? 'danger' : 'success'}
        />
        <StatCard
          title="Archived"
          value={status?.recordings.archived || 0}
          icon={<Archive className="w-6 h-6" />}
          color="default"
        />
      </div>

      {/* Disk Warning */}
      {status?.disk.is_critical && (
        <div className="flex items-center gap-3 p-4 bg-red-50 border border-red-200 rounded-lg">
          <AlertTriangle className="w-6 h-6 text-red-600" />
          <div>
            <p className="font-medium text-red-800">Disk space critical!</p>
            <p className="text-sm text-red-600">
              Usage is at {status.disk.usage_percent}%. Consider archiving or deleting old recordings.
            </p>
          </div>
        </div>
      )}

      {/* Recording Stats by Type */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-blue-50 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-blue-700">{status?.recordings.by_type.continuous || 0}</p>
          <p className="text-sm text-blue-600">Continuous</p>
        </div>
        <div className="bg-yellow-50 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-yellow-700">{status?.recordings.by_type.event || 0}</p>
          <p className="text-sm text-yellow-600">Event-triggered</p>
        </div>
        <div className="bg-purple-50 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-purple-700">{status?.recordings.by_type.manual || 0}</p>
          <p className="text-sm text-purple-600">Manual</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type="text"
            placeholder="Search recordings..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
        <select
          value={segmentType}
          onChange={(e) => setSegmentType(e.target.value)}
          className="px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="">All Types</option>
          <option value="continuous">Continuous</option>
          <option value="event">Event-triggered</option>
          <option value="manual">Manual</option>
        </select>
      </div>

      {/* Recordings List */}
      <Card padding="none">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw className="w-8 h-8 animate-spin text-primary-500" />
          </div>
        ) : filteredRecordings.length > 0 ? (
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Stream</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Start Time</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Duration</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Size</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {filteredRecordings.map((recording: Recording) => (
                <tr key={recording.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <Film className="w-5 h-5 text-gray-400" />
                      <span className="font-medium text-gray-900">
                        {recording.stream_path || `Stream #${recording.stream_id}`}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`px-2.5 py-1 text-xs font-medium rounded-full ${
                      recording.segment_type === 'continuous' ? 'bg-blue-100 text-blue-800' :
                      recording.segment_type === 'event' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-purple-100 text-purple-800'
                    }`}>
                      {recording.segment_type}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-gray-600">
                    {new Date(recording.start_time).toLocaleString()}
                  </td>
                  <td className="px-6 py-4 text-gray-600">
                    {formatDuration(recording.duration_seconds)}
                  </td>
                  <td className="px-6 py-4 text-gray-600">
                    {formatSize(recording.file_size)}
                  </td>
                  <td className="px-6 py-4">
                    {recording.is_archived ? (
                      <span className="flex items-center gap-1 text-green-600">
                        <Archive className="w-4 h-4" />
                        Archived
                      </span>
                    ) : recording.expires_at ? (
                      <span className="text-gray-500 text-sm">
                        Expires {new Date(recording.expires_at).toLocaleDateString()}
                      </span>
                    ) : (
                      <span className="text-gray-400">-</span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        className="p-2 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg"
                        title="Play"
                      >
                        <Play className="w-4 h-4" />
                      </button>
                      <button
                        className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg"
                        title="Download"
                      >
                        <Download className="w-4 h-4" />
                      </button>
                      {!recording.is_archived && (
                        <button
                          onClick={() => archiveMutation.mutate(recording.id)}
                          disabled={archiveMutation.isPending}
                          className="p-2 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded-lg"
                          title="Archive"
                        >
                          <Archive className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="flex flex-col items-center justify-center py-12">
            <Film className="w-12 h-12 text-gray-300 mb-4" />
            <p className="text-gray-500">No recordings found</p>
          </div>
        )}
      </Card>

      {/* Pagination Info */}
      {recordings && (
        <div className="text-sm text-gray-500">
          Showing {filteredRecordings.length} of {recordings.total} recordings
        </div>
      )}
    </div>
  )
}
