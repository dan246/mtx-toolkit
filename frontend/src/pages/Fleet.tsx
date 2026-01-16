import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Server,
  RefreshCw,
  Plus,
  Trash2,
  Settings,
  Activity,
  CheckCircle,
  XCircle,
  Loader2,
} from 'lucide-react'
import Card from '../components/Card'
import StatCard from '../components/StatCard'
import Modal from '../components/Modal'
import { fleetApi } from '../services/api'
import { useLanguage } from '../i18n/LanguageContext'
import type { MediaMTXNode } from '../types'

interface NodeFormData {
  name: string
  api_url: string
  rtsp_url: string
  environment: string
}

const initialFormData: NodeFormData = {
  name: '',
  api_url: '',
  rtsp_url: '',
  environment: 'production',
}

export default function Fleet() {
  const { t } = useLanguage()
  const queryClient = useQueryClient()
  const [environment, setEnvironment] = useState<string>('')
  const [syncingId, setSyncingId] = useState<number | null>(null)

  // Modal states
  const [isAddModalOpen, setIsAddModalOpen] = useState(false)
  const [isEditModalOpen, setIsEditModalOpen] = useState(false)
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false)
  const [selectedNode, setSelectedNode] = useState<MediaMTXNode | null>(null)
  const [formData, setFormData] = useState<NodeFormData>(initialFormData)

  const { data: nodes, isLoading } = useQuery({
    queryKey: ['fleet-nodes', environment],
    queryFn: () => fleetApi.listNodes({ environment: environment || undefined }),
    refetchInterval: 30000,
  })

  const { data: overview } = useQuery({
    queryKey: ['fleet-overview'],
    queryFn: fleetApi.getOverview,
    refetchInterval: 30000,
  })

  const syncMutation = useMutation({
    mutationFn: (nodeId: number) => {
      setSyncingId(nodeId)
      return fleetApi.syncNode(nodeId)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['fleet-nodes'] })
      if (data.success) {
        alert(`同步完成: ${data.synced} 個串流 (新增: ${data.created}, 更新: ${data.updated})`)
      } else {
        alert(`同步失敗: ${data.error || '未知錯誤'}`)
      }
    },
    onError: (error) => {
      alert(`同步失敗: ${error}`)
    },
    onSettled: () => {
      setSyncingId(null)
    },
  })

  const syncAllMutation = useMutation({
    mutationFn: fleetApi.syncAll,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['fleet-nodes'] })
      alert(`全部同步完成: ${data.successful}/${data.total_nodes} 節點成功`)
    },
    onError: (error) => {
      alert(`同步失敗: ${error}`)
    },
  })

  const createMutation = useMutation({
    mutationFn: (data: NodeFormData) => fleetApi.createNode({
      ...data,
      environment: data.environment as 'development' | 'staging' | 'production',
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fleet-nodes'] })
      queryClient.invalidateQueries({ queryKey: ['fleet-overview'] })
      setIsAddModalOpen(false)
      setFormData(initialFormData)
      alert(t.fleet.nodeAdded)
    },
    onError: (error) => {
      alert(`新增失敗: ${error}`)
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: NodeFormData }) => fleetApi.updateNode(id, {
      ...data,
      environment: data.environment as 'development' | 'staging' | 'production',
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fleet-nodes'] })
      setIsEditModalOpen(false)
      setSelectedNode(null)
      setFormData(initialFormData)
      alert(t.fleet.nodeUpdated)
    },
    onError: (error) => {
      alert(`更新失敗: ${error}`)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => fleetApi.deleteNode(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fleet-nodes'] })
      queryClient.invalidateQueries({ queryKey: ['fleet-overview'] })
      setIsDeleteModalOpen(false)
      setSelectedNode(null)
      alert(t.fleet.nodeDeleted)
    },
    onError: (error) => {
      alert(`刪除失敗: ${error}`)
    },
  })

  const handleOpenAddModal = () => {
    setFormData(initialFormData)
    setIsAddModalOpen(true)
  }

  const handleOpenEditModal = (node: MediaMTXNode) => {
    setSelectedNode(node)
    setFormData({
      name: node.name,
      api_url: node.api_url,
      rtsp_url: node.rtsp_url || '',
      environment: node.environment,
    })
    setIsEditModalOpen(true)
  }

  const handleOpenDeleteModal = (node: MediaMTXNode) => {
    setSelectedNode(node)
    setIsDeleteModalOpen(true)
  }

  const handleSubmitAdd = (e: React.FormEvent) => {
    e.preventDefault()
    createMutation.mutate(formData)
  }

  const handleSubmitEdit = (e: React.FormEvent) => {
    e.preventDefault()
    if (selectedNode) {
      updateMutation.mutate({ id: selectedNode.id, data: formData })
    }
  }

  const handleConfirmDelete = () => {
    if (selectedNode) {
      deleteMutation.mutate(selectedNode.id)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t.fleet.title}</h1>
          <p className="text-gray-500 mt-1">{t.fleet.subtitle}</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => syncAllMutation.mutate()}
            disabled={syncAllMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            {syncAllMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            {t.fleet.syncAll}
          </button>
          <button
            onClick={handleOpenAddModal}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
          >
            <Plus className="w-4 h-4" />
            {t.fleet.addNode}
          </button>
        </div>
      </div>

      {/* Overview Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <StatCard
          title={t.fleet.totalNodes}
          value={overview?.nodes?.total || 0}
          icon={<Server className="w-6 h-6" />}
          color="default"
        />
        <StatCard
          title={t.fleet.production}
          value={overview?.nodes?.by_environment?.production || 0}
          icon={<Activity className="w-6 h-6" />}
          color="success"
        />
        <StatCard
          title={t.fleet.staging}
          value={overview?.nodes?.by_environment?.staging || 0}
          icon={<Activity className="w-6 h-6" />}
          color="warning"
        />
        <StatCard
          title={t.fleet.development}
          value={overview?.nodes?.by_environment?.development || 0}
          icon={<Activity className="w-6 h-6" />}
          color="default"
        />
      </div>

      {/* Filter */}
      <div className="flex gap-4">
        <select
          value={environment}
          onChange={(e) => setEnvironment(e.target.value)}
          className="px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="">{t.fleet.allEnvironments}</option>
          <option value="production">{t.fleet.production}</option>
          <option value="staging">{t.fleet.staging}</option>
          <option value="development">{t.fleet.development}</option>
        </select>
      </div>

      {/* Nodes Grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="w-8 h-8 animate-spin text-primary-500" />
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {nodes?.nodes?.map((node: MediaMTXNode) => (
            <Card key={node.id} padding="none">
              <div className="p-6">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${node.is_active ? 'bg-green-50' : 'bg-gray-50'}`}>
                      <Server className={`w-6 h-6 ${node.is_active ? 'text-green-600' : 'text-gray-400'}`} />
                    </div>
                    <div>
                      <h3 className="font-semibold text-gray-900">{node.name}</h3>
                      <p className="text-sm text-gray-500">{node.api_url}</p>
                    </div>
                  </div>
                  <span className={`px-2.5 py-1 text-xs font-medium rounded-full ${
                    node.environment === 'production' ? 'bg-green-100 text-green-800' :
                    node.environment === 'staging' ? 'bg-yellow-100 text-yellow-800' :
                    'bg-gray-100 text-gray-800'
                  }`}>
                    {node.environment}
                  </span>
                </div>

                {/* Stats */}
                <div className="grid grid-cols-4 gap-3 mb-4">
                  <div className="text-center">
                    <p className="text-xl font-bold text-gray-900">{node.stream_count}</p>
                    <p className="text-xs text-gray-500">{t.fleet.streams}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xl font-bold text-green-600">{node.healthy_streams}</p>
                    <p className="text-xs text-gray-500">{t.fleet.healthy}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xl font-bold text-yellow-600">{node.degraded_streams || 0}</p>
                    <p className="text-xs text-gray-500">{t.fleet.degraded}</p>
                  </div>
                  <div className="text-center">
                    <p className="text-xl font-bold text-red-600">{node.unhealthy_streams}</p>
                    <p className="text-xs text-gray-500">{t.fleet.unhealthy}</p>
                  </div>
                </div>

                {/* Status */}
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    {node.is_active ? (
                      <CheckCircle className="w-4 h-4 text-green-500" />
                    ) : (
                      <XCircle className="w-4 h-4 text-red-500" />
                    )}
                    <span className={node.is_active ? 'text-green-600' : 'text-red-600'}>
                      {node.is_active ? t.fleet.online : t.fleet.offline}
                    </span>
                  </div>
                  <span className="text-gray-400">
                    {node.last_seen
                      ? `${t.fleet.lastSeen}: ${new Date(node.last_seen).toLocaleTimeString()}`
                      : t.fleet.neverSeen}
                  </span>
                </div>
              </div>

              {/* Actions */}
              <div className="border-t border-gray-100 px-6 py-3 flex justify-end gap-2">
                <button
                  onClick={() => syncMutation.mutate(node.id)}
                  disabled={syncingId === node.id}
                  className="p-2 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg disabled:opacity-50"
                  title="Sync Streams"
                >
                  {syncingId === node.id ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <RefreshCw className="w-4 h-4" />
                  )}
                </button>
                <button
                  onClick={() => handleOpenEditModal(node)}
                  className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg"
                  title="Settings"
                >
                  <Settings className="w-4 h-4" />
                </button>
                <button
                  onClick={() => handleOpenDeleteModal(node)}
                  className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg"
                  title="Remove"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </Card>
          ))}

          {/* Add Node Card */}
          <button
            onClick={handleOpenAddModal}
            className="flex flex-col items-center justify-center p-6 border-2 border-dashed border-gray-300 rounded-xl hover:border-primary-400 hover:bg-primary-50 transition-colors"
          >
            <Plus className="w-8 h-8 text-gray-400 mb-2" />
            <span className="text-gray-600 font-medium">{t.fleet.addNewNode}</span>
          </button>
        </div>
      )}

      {/* Add Node Modal */}
      <Modal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        title={t.fleet.addNode}
      >
        <form onSubmit={handleSubmitAdd} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t.fleet.nodeName}
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              required
              placeholder="main-mediamtx"
              className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t.fleet.apiUrl}
            </label>
            <input
              type="text"
              value={formData.api_url}
              onChange={(e) => setFormData({ ...formData, api_url: e.target.value })}
              required
              placeholder="http://localhost:9998"
              className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t.fleet.rtspUrl}
            </label>
            <input
              type="text"
              value={formData.rtsp_url}
              onChange={(e) => setFormData({ ...formData, rtsp_url: e.target.value })}
              placeholder="rtsp://localhost:8554"
              className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t.fleet.environment}
            </label>
            <select
              value={formData.environment}
              onChange={(e) => setFormData({ ...formData, environment: e.target.value })}
              className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="production">{t.fleet.production}</option>
              <option value="staging">{t.fleet.staging}</option>
              <option value="development">{t.fleet.development}</option>
            </select>
          </div>
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

      {/* Edit Node Modal */}
      <Modal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        title={t.fleet.editNode}
      >
        <form onSubmit={handleSubmitEdit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t.fleet.nodeName}
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              required
              className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t.fleet.apiUrl}
            </label>
            <input
              type="text"
              value={formData.api_url}
              onChange={(e) => setFormData({ ...formData, api_url: e.target.value })}
              required
              className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t.fleet.rtspUrl}
            </label>
            <input
              type="text"
              value={formData.rtsp_url}
              onChange={(e) => setFormData({ ...formData, rtsp_url: e.target.value })}
              className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t.fleet.environment}
            </label>
            <select
              value={formData.environment}
              onChange={(e) => setFormData({ ...formData, environment: e.target.value })}
              className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="production">{t.fleet.production}</option>
              <option value="staging">{t.fleet.staging}</option>
              <option value="development">{t.fleet.development}</option>
            </select>
          </div>
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
        title={t.fleet.deleteNode}
        size="sm"
      >
        <div className="space-y-4">
          <p className="text-gray-600">
            {t.fleet.confirmDelete}
          </p>
          {selectedNode && (
            <div className="p-3 bg-gray-50 rounded-lg">
              <p className="font-medium text-gray-900">{selectedNode.name}</p>
              <p className="text-sm text-gray-500">{selectedNode.api_url}</p>
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
    </div>
  )
}
