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
} from 'lucide-react'
import Card from '../components/Card'
import StatCard from '../components/StatCard'
import { fleetApi } from '../services/api'
import type { MediaMTXNode } from '../types'

export default function Fleet() {
  const queryClient = useQueryClient()
  const [environment, setEnvironment] = useState<string>('')

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
    mutationFn: (nodeId: number) => fleetApi.syncNode(nodeId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fleet-nodes'] })
    },
  })

  const syncAllMutation = useMutation({
    mutationFn: fleetApi.syncAll,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fleet-nodes'] })
    },
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Fleet Management</h1>
          <p className="text-gray-500 mt-1">Manage MediaMTX nodes across environments</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => syncAllMutation.mutate()}
            disabled={syncAllMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-lg hover:bg-gray-50"
          >
            <RefreshCw className={`w-4 h-4 ${syncAllMutation.isPending ? 'animate-spin' : ''}`} />
            Sync All
          </button>
          <button className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700">
            <Plus className="w-4 h-4" />
            Add Node
          </button>
        </div>
      </div>

      {/* Overview Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <StatCard
          title="Total Nodes"
          value={overview?.nodes?.total || 0}
          icon={<Server className="w-6 h-6" />}
          color="default"
        />
        <StatCard
          title="Production"
          value={overview?.nodes?.by_environment?.production || 0}
          icon={<Activity className="w-6 h-6" />}
          color="success"
        />
        <StatCard
          title="Staging"
          value={overview?.nodes?.by_environment?.staging || 0}
          icon={<Activity className="w-6 h-6" />}
          color="warning"
        />
        <StatCard
          title="Development"
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
          <option value="">All Environments</option>
          <option value="production">Production</option>
          <option value="staging">Staging</option>
          <option value="development">Development</option>
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
                <div className="grid grid-cols-3 gap-4 mb-4">
                  <div className="text-center">
                    <p className="text-2xl font-bold text-gray-900">{node.stream_count}</p>
                    <p className="text-xs text-gray-500">Streams</p>
                  </div>
                  <div className="text-center">
                    <p className="text-2xl font-bold text-green-600">{node.healthy_streams}</p>
                    <p className="text-xs text-gray-500">Healthy</p>
                  </div>
                  <div className="text-center">
                    <p className="text-2xl font-bold text-red-600">{node.unhealthy_streams}</p>
                    <p className="text-xs text-gray-500">Unhealthy</p>
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
                      {node.is_active ? 'Online' : 'Offline'}
                    </span>
                  </div>
                  <span className="text-gray-400">
                    {node.last_seen
                      ? `Last seen: ${new Date(node.last_seen).toLocaleTimeString()}`
                      : 'Never seen'}
                  </span>
                </div>
              </div>

              {/* Actions */}
              <div className="border-t border-gray-100 px-6 py-3 flex justify-end gap-2">
                <button
                  onClick={() => syncMutation.mutate(node.id)}
                  disabled={syncMutation.isPending}
                  className="p-2 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg"
                  title="Sync Streams"
                >
                  <RefreshCw className={`w-4 h-4 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
                </button>
                <button
                  className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg"
                  title="Settings"
                >
                  <Settings className="w-4 h-4" />
                </button>
                <button
                  className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg"
                  title="Remove"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </Card>
          ))}

          {/* Add Node Card */}
          <button className="flex flex-col items-center justify-center p-6 border-2 border-dashed border-gray-300 rounded-xl hover:border-primary-400 hover:bg-primary-50 transition-colors">
            <Plus className="w-8 h-8 text-gray-400 mb-2" />
            <span className="text-gray-600 font-medium">Add New Node</span>
          </button>
        </div>
      )}
    </div>
  )
}
