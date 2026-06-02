import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Users, RefreshCw, Radio, UserX, Loader2 } from 'lucide-react'
import Modal from './Modal'
import { sessionsApi } from '../services/api'
import { useLanguage } from '../i18n/LanguageContext'
import { useToast } from '../contexts/ToastContext'
import { useConfirm } from '../contexts/ConfirmContext'
import type { ViewerSession, SessionProtocol } from '../types'

interface StreamViewersModalProps {
  isOpen: boolean
  onClose: () => void
  streamId: number
  streamPath: string
}

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

export default function StreamViewersModal({
  isOpen,
  onClose,
  streamId,
  streamPath,
}: StreamViewersModalProps) {
  const { t } = useLanguage()
  const toast = useToast()
  const { confirm } = useConfirm()
  const queryClient = useQueryClient()
  const [kickingId, setKickingId] = useState<string | null>(null)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['stream-viewers', streamId],
    queryFn: () => sessionsApi.getByStream(streamId),
    enabled: isOpen,
    refetchInterval: isOpen ? 10000 : false,
  })

  const kickMutation = useMutation({
    mutationFn: ({ nodeId, sessionId, protocol }: { nodeId: number; sessionId: string; protocol: string }) => {
      setKickingId(sessionId)
      return sessionsApi.kick(nodeId, sessionId, protocol)
    },
    onSuccess: (data) => {
      if (data.success) {
        queryClient.invalidateQueries({ queryKey: ['stream-viewers', streamId] })
        queryClient.invalidateQueries({ queryKey: ['sessions'] })
        queryClient.invalidateQueries({ queryKey: ['sessions-summary'] })
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

  const handleKick = async (session: ViewerSession) => {
    if (await confirm({ message: `${t.viewers.confirmKick} ${session.client_ip}?`, danger: true })) {
      kickMutation.mutate({
        nodeId: session.node_id,
        sessionId: session.id,
        protocol: session.protocol,
      })
    }
  }

  const sessions = data?.sessions || []

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={
        <div className="flex items-center gap-2">
          <Users className="w-5 h-5" />
          <span>{t.viewers.streamViewers}: {streamPath}</span>
        </div>
      }
      size="lg"
    >
      <div className="space-y-4">
        {/* Header with count and refresh */}
        <div className="flex items-center justify-between">
          <div className="text-sm text-gray-500">
            {sessions.length} {t.viewers.activeConnections}
          </div>
          <button
            onClick={() => refetch()}
            disabled={isLoading}
            className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-lg"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            {t.viewers.refresh}
          </button>
        </div>

        {/* Sessions list */}
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <RefreshCw className="w-6 h-6 animate-spin text-primary-500" />
          </div>
        ) : sessions.length > 0 ? (
          <div className="max-h-96 overflow-y-auto">
            <table className="w-full">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">{t.viewers.clientIP}</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">{t.viewers.protocol}</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">{t.viewers.node}</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">{t.viewers.connected}</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">{t.viewers.dataSent}</th>
                  <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {sessions.map((session: ViewerSession) => (
                  <tr key={session.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <div>
                        <p className="text-gray-900 text-sm">{session.client_ip}</p>
                        {session.client_port > 0 && (
                          <p className="text-xs text-gray-500">:{session.client_port}</p>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${protocolColors[session.protocol] || 'bg-gray-100 text-gray-800'}`}>
                        {session.protocol.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {session.node_name}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {formatDuration(session.duration_seconds)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {formatBytes(session.bytes_sent)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => handleKick(session)}
                        disabled={kickingId === session.id}
                        className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg disabled:opacity-50"
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
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-8">
            <Radio className="w-10 h-10 text-gray-300 mb-3" />
            <p className="text-gray-500 text-sm">{t.viewers.noViewersForStream}</p>
          </div>
        )}
      </div>
    </Modal>
  )
}
