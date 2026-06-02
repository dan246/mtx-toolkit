import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Users,
  RefreshCw,
  Search,
  Server,
  Radio,
  Wifi,
  ChevronLeft,
  ChevronRight,
  UserX,
  Loader2,
} from 'lucide-react'
import Card from '../components/Card'
import StatCard from '../components/StatCard'
import Modal from '../components/Modal'
import { sessionsApi, fleetApi } from '../services/api'
import { useLanguage } from '../i18n/LanguageContext'
import { useToast } from '../contexts/ToastContext'
import type { ViewerSession, MediaMTXNode, SessionProtocol } from '../types'

const protocolColors: Record<SessionProtocol, string> = {
  rtsp: 'bg-blue-100 text-blue-800',
  rtsps: 'bg-indigo-100 text-indigo-800',
  webrtc: 'bg-green-100 text-green-800',
  rtmp: 'bg-orange-100 text-orange-800',
  srt: 'bg-purple-100 text-purple-800',
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return `${hours}h ${minutes}m`
}

export default function Viewers() {
  const { t } = useLanguage()
  const toast = useToast()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [protocolFilter, setProtocolFilter] = useState<SessionProtocol | ''>('')
  const [nodeFilter, setNodeFilter] = useState<number | ''>('')
  const [currentPage, setCurrentPage] = useState(1)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [kickingId, setKickingId] = useState<string | null>(null)
  const perPage = 50

  // Kick modal state
  const [kickModalOpen, setKickModalOpen] = useState(false)
  const [selectedSession, setSelectedSession] = useState<ViewerSession | null>(null)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['sessions', protocolFilter, nodeFilter, currentPage],
    queryFn: () => sessionsApi.list({
      protocol: protocolFilter || undefined,
      node_id: nodeFilter || undefined,
      page: currentPage,
      per_page: perPage,
    }),
    refetchInterval: 10000,
  })

  const { data: nodesData } = useQuery({
    queryKey: ['fleet-nodes'],
    queryFn: () => fleetApi.listNodes(),
  })

  const kickMutation = useMutation({
    mutationFn: async (session: ViewerSession) => {
      setKickingId(session.id)
      return sessionsApi.kick(
        session.node_id,
        session.id,
        session.protocol,
      )
    },
    onSuccess: (data) => {
      if (data.success) {
        queryClient.invalidateQueries({ queryKey: ['sessions'] })
        queryClient.invalidateQueries({ queryKey: ['sessions-summary'] })
        setKickModalOpen(false)
        setSelectedSession(null)
      } else {
        toast.error(`${t.viewers.kickFailed}: ${data.error}`)
      }
    },
    onError: (error) => {
      toast.error(`${t.viewers.kickFailed}: ${error}`)
    },
    onSettled: () => {
      setKickingId(null)
    },
  })

  const handleOpenKickModal = (session: ViewerSession) => {
    setSelectedSession(session)
    setKickModalOpen(true)
  }

  const handleKick = () => {
    if (selectedSession) {
      kickMutation.mutate(selectedSession)
    }
  }

  const handleRefresh = async () => {
    setIsRefreshing(true)
    await refetch()
    setTimeout(() => setIsRefreshing(false), 500)
  }

  // Filter by search (client IP or path)
  const filteredSessions = data?.sessions?.filter((session: ViewerSession) =>
    session.client_ip.toLowerCase().includes(search.toLowerCase()) ||
    session.path.toLowerCase().includes(search.toLowerCase()) ||
    session.node_name.toLowerCase().includes(search.toLowerCase())
  ) || []

  const summary = data?.summary

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t.viewers.title}</h1>
          <p className="text-gray-500 mt-1">{t.viewers.subtitle}</p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={isRefreshing}
          className={`flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-lg transition-colors ${
            isRefreshing ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-50'
          }`}
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          {t.viewers.refresh}
        </button>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
        <StatCard
          title={t.viewers.totalViewers}
          value={summary?.total_viewers || 0}
          icon={<Users className="w-6 h-6" />}
          color="default"
        />
        <StatCard
          title="RTSP"
          value={summary?.by_protocol?.rtsp || 0}
          subtitle={summary?.by_protocol?.rtsps ? `+${summary.by_protocol.rtsps} RTSPS` : undefined}
          icon={<Radio className="w-6 h-6" />}
          color="default"
        />
        <StatCard
          title="WebRTC"
          value={summary?.by_protocol?.webrtc || 0}
          icon={<Wifi className="w-6 h-6" />}
          color="success"
        />
        <StatCard
          title={t.viewers.activeNodes}
          value={Object.keys(summary?.by_node || {}).length}
          icon={<Server className="w-6 h-6" />}
          color="default"
        />
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-4">
        <div className="relative flex-1 min-w-[200px] max-w-md">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type="text"
            placeholder={t.viewers.searchPlaceholder}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
        <select
          value={protocolFilter}
          onChange={(e) => {
            setProtocolFilter(e.target.value as SessionProtocol | '')
            setCurrentPage(1)
          }}
          className="px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="">{t.viewers.allProtocols}</option>
          <option value="rtsp">RTSP</option>
          <option value="rtsps">RTSPS</option>
          <option value="webrtc">WebRTC</option>
          <option value="rtmp">RTMP</option>
          <option value="srt">SRT</option>
        </select>
        <select
          value={nodeFilter}
          onChange={(e) => {
            setNodeFilter(e.target.value ? Number(e.target.value) : '')
            setCurrentPage(1)
          }}
          className="px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="">{t.viewers.allNodes}</option>
          {nodesData?.nodes?.map((node: MediaMTXNode) => (
            <option key={node.id} value={node.id}>
              {node.name}
            </option>
          ))}
        </select>
      </div>

      {/* Sessions Table */}
      <Card padding="none">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw className="w-8 h-8 animate-spin text-primary-500" />
          </div>
        ) : filteredSessions.length > 0 ? (
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t.viewers.streamPath}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t.viewers.clientIP}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t.viewers.protocol}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t.viewers.node}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t.viewers.connected}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t.viewers.dataSent}</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">{t.viewers.state}</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">{t.viewers.actions}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {filteredSessions.map((session: ViewerSession) => (
                <tr key={session.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      <Radio className="w-4 h-4 text-gray-400" />
                      <span className="font-medium text-gray-900">{session.path || '-'}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div>
                      <p className="text-gray-900">{session.client_ip}</p>
                      {session.client_port > 0 && (
                        <p className="text-xs text-gray-500">:{session.client_port}</p>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${protocolColors[session.protocol] || 'bg-gray-100 text-gray-800'}`}>
                      {session.protocol.toUpperCase()}
                    </span>
                    {session.transport && (
                      <span className="ml-1 text-xs text-gray-500">({session.transport})</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-gray-600">
                    {session.node_name}
                  </td>
                  <td className="px-6 py-4 text-gray-600">
                    {formatDuration(session.duration_seconds)}
                  </td>
                  <td className="px-6 py-4 text-gray-600">
                    {formatBytes(session.bytes_sent)}
                  </td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                      session.state === 'read' ? 'bg-green-100 text-green-800' :
                      session.state === 'publish' ? 'bg-blue-100 text-blue-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {session.state}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button
                      onClick={() => handleOpenKickModal(session)}
                      disabled={kickingId === session.id}
                      className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg disabled:opacity-50"
                      title={t.viewers.kick}
                    >
                      {kickingId === session.id ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <UserX className="w-4 h-4" />
                      )}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="flex flex-col items-center justify-center py-12">
            <Users className="w-12 h-12 text-gray-300 mb-4" />
            <p className="text-gray-500">{t.viewers.noViewersFound}</p>
          </div>
        )}
      </Card>

      {/* Pagination */}
      {data && data.total > 0 && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-gray-500">
            {t.viewers.showing} {((currentPage - 1) * perPage) + 1}-{Math.min(currentPage * perPage, data.total)} {t.viewers.of} {data.total} {t.viewers.viewers}
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

      {/* Kick Modal */}
      <Modal
        isOpen={kickModalOpen}
        onClose={() => {
          setKickModalOpen(false)
          setSelectedSession(null)
        }}
        title={
          <div className="flex items-center gap-2">
            <UserX className="w-5 h-5 text-red-500" />
            <span>{t.viewers.kickViewer}</span>
          </div>
        }
        size="md"
      >
        {selectedSession && (
          <div className="space-y-4">
            {/* Session info */}
            <div className="p-3 bg-gray-50 rounded-lg">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-gray-500">{t.viewers.clientIP}:</span>
                  <span className="ml-2 font-medium">{selectedSession.client_ip}</span>
                </div>
                <div>
                  <span className="text-gray-500">{t.viewers.streamPath}:</span>
                  <span className="ml-2 font-medium">{selectedSession.path}</span>
                </div>
                <div>
                  <span className="text-gray-500">{t.viewers.protocol}:</span>
                  <span className="ml-2 font-medium">{selectedSession.protocol.toUpperCase()}</span>
                </div>
                <div>
                  <span className="text-gray-500">{t.viewers.connected}:</span>
                  <span className="ml-2 font-medium">{formatDuration(selectedSession.duration_seconds)}</span>
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => {
                  setKickModalOpen(false)
                  setSelectedSession(null)
                }}
                className="px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg"
              >
                {t.common.cancel}
              </button>
              <button
                onClick={handleKick}
                disabled={kickMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 text-white rounded-lg disabled:opacity-50 bg-orange-500 hover:bg-orange-600"
              >
                {kickMutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                {t.viewers.kick}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
