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
  Loader2,
  Trash2,
  ChevronLeft,
  ChevronRight,
  Users,
  RotateCcw,
  Zap,
} from 'lucide-react'
import Card from '../components/Card'
import Modal from '../components/Modal'
import StatusBadge from '../components/StatusBadge'
import LivenessBadge from '../components/LivenessBadge'
import FallbackIndicator from '../components/FallbackIndicator'
import StreamViewersModal from '../components/StreamViewersModal'
import { streamsApi, healthApi, fleetApi, sessionsApi } from '../services/api'
import { useLanguage } from '../i18n/LanguageContext'
import { useToast } from '../contexts/ToastContext'
import type { Stream, StreamStatus, MediaMTXNode, LivenessClassification } from '../types'

function formatBytes(bytes?: number | null): string {
  if (bytes == null) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i += 1
  }
  return `${value.toFixed(value >= 10 || i === 0 ? 0 : 1)} ${units[i]}`
}

function formatUptime(seconds?: number | null): string {
  if (seconds == null) return '-'
  if (seconds < 60) return `${seconds}s`
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

interface StreamFormData {
  path: string
  name: string
  source_url: string
  node_id: number | null
  auto_remediate: boolean
}

const initialFormData: StreamFormData = {
  path: '',
  name: '',
  source_url: '',
  node_id: null,
  auto_remediate: true,
}

// Shared field set for both the Add and Edit stream modals. idSuffix keeps the
// checkbox id unique when both modals exist in the DOM.
function StreamFormFields({
  formData,
  setFormData,
  nodes,
  idSuffix,
}: {
  formData: StreamFormData
  setFormData: (data: StreamFormData) => void
  nodes: MediaMTXNode[]
  idSuffix: string
}) {
  const { t } = useLanguage()
  const inputClass =
    'w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500'
  return (
    <>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t.streams.streamPath} *
        </label>
        <input
          type="text"
          value={formData.path}
          onChange={(e) => setFormData({ ...formData, path: e.target.value })}
          required
          placeholder="cam1"
          className={inputClass}
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t.streams.streamName}
        </label>
        <input
          type="text"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          placeholder="Camera 1"
          className={inputClass}
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t.streams.sourceUrl}
        </label>
        <input
          type="text"
          value={formData.source_url}
          onChange={(e) => setFormData({ ...formData, source_url: e.target.value })}
          placeholder="rtsp://user:pass@192.168.1.100:554/stream"
          className={inputClass}
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          {t.streams.selectNode}
        </label>
        <select
          value={formData.node_id || ''}
          onChange={(e) => setFormData({ ...formData, node_id: e.target.value ? Number(e.target.value) : null })}
          className={inputClass}
        >
          <option value="">-- {t.streams.selectNode} --</option>
          {nodes.map((node: MediaMTXNode) => (
            <option key={node.id} value={node.id}>
              {node.name} ({node.environment})
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id={`auto_remediate_${idSuffix}`}
          checked={formData.auto_remediate}
          onChange={(e) => setFormData({ ...formData, auto_remediate: e.target.checked })}
          className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
        />
        <label htmlFor={`auto_remediate_${idSuffix}`} className="text-sm text-gray-700">
          {t.streams.autoRemediate}
        </label>
      </div>
    </>
  )
}

export default function Streams() {
  const { t } = useLanguage()
  const toast = useToast()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StreamStatus | ''>('')
  const [currentPage, setCurrentPage] = useState(1)
  const [probingId, setProbingId] = useState<number | null>(null)
  const [remediatingId, setRemediatingId] = useState<number | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const perPage = 50

  // Modal states
  const [isAddModalOpen, setIsAddModalOpen] = useState(false)
  const [isEditModalOpen, setIsEditModalOpen] = useState(false)
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false)
  const [isViewersModalOpen, setIsViewersModalOpen] = useState(false)
  const [selectedStream, setSelectedStream] = useState<Stream | null>(null)
  const [formData, setFormData] = useState<StreamFormData>(initialFormData)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['streams', statusFilter, currentPage],
    queryFn: () => streamsApi.list({
      status: statusFilter || undefined,
      page: currentPage,
      per_page: perPage,
    }),
    refetchInterval: 30000,
  })

  const handleRefresh = async () => {
    setIsRefreshing(true)
    await refetch()
    // Keep spinning for at least 500ms so user sees feedback
    setTimeout(() => setIsRefreshing(false), 500)
  }

  const { data: nodesData } = useQuery({
    queryKey: ['fleet-nodes'],
    queryFn: () => fleetApi.listNodes(),
  })

  // Get sessions summary to show viewer counts per stream
  const { data: sessionsData } = useQuery({
    queryKey: ['sessions-list'],
    queryFn: () => sessionsApi.list({ per_page: 10000 }),
    refetchInterval: 10000,
  })

  // Calculate viewer count per path
  const viewersByPath: Record<string, number> = {}
  if (sessionsData?.sessions) {
    for (const session of sessionsData.sessions) {
      viewersByPath[session.path] = (viewersByPath[session.path] || 0) + 1
    }
  }

  const handleOpenViewersModal = (stream: Stream) => {
    setSelectedStream(stream)
    setIsViewersModalOpen(true)
  }

  const probeMutation = useMutation({
    mutationFn: (streamId: number) => {
      setProbingId(streamId)
      return healthApi.probeStream(streamId)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['streams'] })
      toast.success(`${t.messages.probeComplete}: ${data.status} - FPS: ${data.fps || 'N/A'}`)
    },
    onError: (error) => {
      toast.error(`${t.messages.probeFailed}: ${error}`)
    },
    onSettled: () => {
      setProbingId(null)
    },
  })

  const remediateMutation = useMutation({
    mutationFn: (streamId: number) => {
      setRemediatingId(streamId)
      return streamsApi.remediate(streamId)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['streams'] })
      data.success
        ? toast.success(`${t.messages.remediateComplete}: ${data.total_attempts} ${t.messages.attempts}`)
        : toast.error(`${t.messages.remediateFailed}: ${data.total_attempts} ${t.messages.attempts}`)
    },
    onError: (error) => {
      toast.error(`${t.messages.remediateFailed}: ${error}`)
    },
    onSettled: () => {
      setRemediatingId(null)
    },
  })

  const softResetMutation = useMutation({
    mutationFn: (streamId: number) => streamsApi.softReset(streamId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['streams'] })
      data.success
        ? toast.success(`${t.streams.softReset} ${t.common.success}`)
        : toast.error(`${t.streams.softReset} ${t.common.error}`)
    },
    onError: (error) => {
      toast.error(`${t.streams.softReset} ${t.common.error}: ${error}`)
    },
  })

  const reviveMutation = useMutation({
    mutationFn: (streamId: number) => streamsApi.revive(streamId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['streams'] })
      data.success
        ? toast.success(`${t.streams.protocolRevival} ${t.common.success}: ${data.message || ''}`)
        : toast.error(`${t.streams.protocolRevival} ${t.common.error}: ${data.message || ''}`)
    },
    onError: (error) => {
      toast.error(`${t.streams.protocolRevival} ${t.common.error}: ${error}`)
    },
  })

  const createMutation = useMutation({
    mutationFn: (data: StreamFormData) => streamsApi.create({
      ...data,
      node_id: data.node_id ?? undefined,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['streams'] })
      setIsAddModalOpen(false)
      setFormData(initialFormData)
      toast.success(t.streams.streamAdded)
    },
    onError: (error) => {
      toast.error(`${t.messages.addFailed}: ${error}`)
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: StreamFormData }) => streamsApi.update(id, {
      ...data,
      node_id: data.node_id ?? undefined,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['streams'] })
      setIsEditModalOpen(false)
      setSelectedStream(null)
      setFormData(initialFormData)
      toast.success(t.streams.streamUpdated)
    },
    onError: (error) => {
      toast.error(`${t.messages.updateFailed}: ${error}`)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => streamsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['streams'] })
      setIsDeleteModalOpen(false)
      setSelectedStream(null)
      toast.success(t.streams.streamDeleted)
    },
    onError: (error) => {
      toast.error(`${t.messages.deleteFailed}: ${error}`)
    },
  })

  const filteredStreams = data?.streams?.filter((stream: Stream) =>
    stream.path.toLowerCase().includes(search.toLowerCase()) ||
    stream.name?.toLowerCase().includes(search.toLowerCase())
  ) || []

  const handleOpenAddModal = () => {
    setFormData(initialFormData)
    setIsAddModalOpen(true)
  }

  const handleOpenEditModal = (stream: Stream) => {
    setSelectedStream(stream)
    setFormData({
      path: stream.path,
      name: stream.name || '',
      source_url: stream.source_url || '',
      node_id: stream.node_id,
      auto_remediate: stream.auto_remediate,
    })
    setIsEditModalOpen(true)
  }

  const handleOpenDeleteModal = (stream: Stream) => {
    setSelectedStream(stream)
    setIsDeleteModalOpen(true)
  }

  const handleSubmitAdd = (e: React.FormEvent) => {
    e.preventDefault()
    createMutation.mutate(formData)
  }

  const handleSubmitEdit = (e: React.FormEvent) => {
    e.preventDefault()
    if (selectedStream) {
      updateMutation.mutate({ id: selectedStream.id, data: formData })
    }
  }

  const handleConfirmDelete = () => {
    if (selectedStream) {
      deleteMutation.mutate(selectedStream.id)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t.streams.title}</h1>
          <p className="text-gray-500 mt-1">{t.streams.subtitle}</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className={`flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-lg transition-colors ${
              isRefreshing ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-50'
            }`}
          >
            <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            {t.streams.refresh}
          </button>
          <button
            onClick={handleOpenAddModal}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
          >
            <Plus className="w-4 h-4" />
            {t.streams.addStream}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type="text"
            placeholder={t.streams.searchStreams}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value as StreamStatus | '')
            setCurrentPage(1)
          }}
          className="px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="">{t.streams.allStatus}</option>
          <option value="healthy">{t.streams.healthy}</option>
          <option value="degraded">{t.streams.degraded}</option>
          <option value="unhealthy">{t.streams.unhealthy}</option>
          <option value="unknown">{t.streams.unknown}</option>
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
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t.streams.stream}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t.streams.status}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t.streams.viewers}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t.streams.fps}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t.streams.bitrate}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t.streams.uptime}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t.streams.bandwidth}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t.streams.resolution}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t.streams.errors}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t.streams.lastCheck}</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">{t.streams.actions}</th>
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
                    <div className="flex items-center gap-2">
                      <StatusBadge status={stream.status} />
                      {stream.liveness_classification && stream.liveness_classification !== 'unknown' && stream.liveness_classification !== 'live' && (
                        <LivenessBadge classification={stream.liveness_classification as LivenessClassification} />
                      )}
                      {stream.fallback_active && (
                        <FallbackIndicator fallbackType={stream.fallback_type} />
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <button
                      onClick={() => handleOpenViewersModal(stream)}
                      className="flex items-center gap-1.5 px-2 py-1 text-sm rounded hover:bg-gray-100 transition-colors"
                    >
                      <Users className="w-4 h-4 text-gray-400" />
                      <span className="text-gray-600">{viewersByPath[stream.path] || 0}</span>
                    </button>
                  </td>
                  <td className="px-6 py-4 text-gray-600">
                    {stream.fps ? `${stream.fps.toFixed(1)} fps` : '-'}
                  </td>
                  <td className="px-6 py-4 text-gray-600">
                    {stream.bitrate != null ? `${(stream.bitrate / 1000).toFixed(0)} kbps` : '-'}
                  </td>
                  <td className="px-6 py-4 text-gray-600 whitespace-nowrap">
                    {formatUptime(stream.uptime_seconds)}
                  </td>
                  <td className="px-6 py-4 text-gray-600 whitespace-nowrap">
                    {stream.bytes_sent != null || stream.bytes_received != null ? (
                      <span title={`↓ ${formatBytes(stream.bytes_received)} / ↑ ${formatBytes(stream.bytes_sent)}`}>
                        ↑ {formatBytes(stream.bytes_sent)}
                      </span>
                    ) : (
                      '-'
                    )}
                  </td>
                  <td className="px-6 py-4 text-gray-600 whitespace-nowrap">
                    {stream.width && stream.height
                      ? `${stream.width}×${stream.height}${stream.codec ? ` ${stream.codec}` : ''}`
                      : '-'}
                  </td>
                  <td className="px-6 py-4 text-gray-600">
                    {stream.frames_in_error != null ? (
                      <span className={stream.frames_in_error > 0 ? 'text-red-600 font-medium' : ''}>
                        {stream.frames_in_error}
                      </span>
                    ) : (
                      '-'
                    )}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {stream.last_check
                      ? new Date(stream.last_check).toLocaleTimeString()
                      : t.streams.never}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => probeMutation.mutate(stream.id)}
                        disabled={probingId === stream.id}
                        className="p-2 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg disabled:opacity-50"
                        title={t.streams.probeStream}
                      >
                        {probingId === stream.id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Play className="w-4 h-4" />
                        )}
                      </button>
                      <button
                        onClick={() => softResetMutation.mutate(stream.id)}
                        disabled={softResetMutation.isPending}
                        className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg disabled:opacity-50"
                        title={t.streams.softReset}
                      >
                        {softResetMutation.isPending && softResetMutation.variables === stream.id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <RotateCcw className="w-4 h-4" />
                        )}
                      </button>
                      <button
                        onClick={() => reviveMutation.mutate(stream.id)}
                        disabled={reviveMutation.isPending}
                        className="p-2 text-gray-400 hover:text-purple-600 hover:bg-purple-50 rounded-lg disabled:opacity-50"
                        title={t.streams.protocolRevival}
                      >
                        {reviveMutation.isPending && reviveMutation.variables === stream.id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Zap className="w-4 h-4" />
                        )}
                      </button>
                      {stream.auto_remediate && (
                        <button
                          onClick={() => remediateMutation.mutate(stream.id)}
                          disabled={remediatingId === stream.id}
                          className="p-2 text-gray-400 hover:text-yellow-600 hover:bg-yellow-50 rounded-lg disabled:opacity-50"
                          title={t.streams.remediate}
                        >
                          {remediatingId === stream.id ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Wrench className="w-4 h-4" />
                          )}
                        </button>
                      )}
                      <button
                        onClick={() => handleOpenEditModal(stream)}
                        className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg"
                        title={t.common.settings}
                      >
                        <Settings className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleOpenDeleteModal(stream)}
                        className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg"
                        title={t.common.delete}
                      >
                        <Trash2 className="w-4 h-4" />
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
            <p className="text-gray-500">{t.streams.noStreamsFound}</p>
          </div>
        )}
      </Card>

      {/* Pagination */}
      {data && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-gray-500">
            {t.streams.showing} {((currentPage - 1) * perPage) + 1}-{Math.min(currentPage * perPage, data.total)} {t.streams.of} {data.total} streams
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="flex items-center gap-1 px-3 py-1.5 text-sm bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-sm text-gray-600">
              {currentPage} / {data.pages || 1}
            </span>
            <button
              onClick={() => setCurrentPage(p => Math.min(data.pages || 1, p + 1))}
              disabled={currentPage >= (data.pages || 1)}
              className="flex items-center gap-1 px-3 py-1.5 text-sm bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Add Stream Modal */}
      <Modal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        title={t.streams.addStream}
      >
        <form onSubmit={handleSubmitAdd} className="space-y-4">
          <StreamFormFields
            formData={formData}
            setFormData={setFormData}
            nodes={nodesData?.nodes ?? []}
            idSuffix="add"
          />
          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={() => setIsAddModalOpen(false)}
              className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg"
            >
              {t.common.cancel}
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
            >
              {createMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
              {t.common.save}
            </button>
          </div>
        </form>
      </Modal>

      {/* Edit Stream Modal */}
      <Modal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        title={t.streams.editStream}
      >
        <form onSubmit={handleSubmitEdit} className="space-y-4">
          <StreamFormFields
            formData={formData}
            setFormData={setFormData}
            nodes={nodesData?.nodes ?? []}
            idSuffix="edit"
          />
          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={() => setIsEditModalOpen(false)}
              className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg"
            >
              {t.common.cancel}
            </button>
            <button
              type="submit"
              disabled={updateMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
            >
              {updateMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
              {t.common.save}
            </button>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        title={t.streams.deleteStream}
        size="sm"
      >
        <div className="space-y-4">
          <p className="text-gray-600">
            {t.streams.confirmDeleteStream}
          </p>
          {selectedStream && (
            <div className="p-3 bg-gray-50 rounded-lg">
              <p className="font-medium text-gray-900">{selectedStream.path}</p>
              {selectedStream.name && (
                <p className="text-sm text-gray-500">{selectedStream.name}</p>
              )}
            </div>
          )}
          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={() => setIsDeleteModalOpen(false)}
              className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg"
            >
              {t.common.cancel}
            </button>
            <button
              onClick={handleConfirmDelete}
              disabled={deleteMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
            >
              {deleteMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
              {t.common.delete}
            </button>
          </div>
        </div>
      </Modal>

      {/* Stream Viewers Modal */}
      {selectedStream && (
        <StreamViewersModal
          isOpen={isViewersModalOpen}
          onClose={() => {
            setIsViewersModalOpen(false)
            setSelectedStream(null)
          }}
          streamId={selectedStream.id}
          streamPath={selectedStream.path}
        />
      )}
    </div>
  )
}
