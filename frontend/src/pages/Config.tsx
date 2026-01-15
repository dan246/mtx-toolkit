import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Settings,
  Play,
  Check,
  X,
  RotateCcw,
  Clock,
  FileText,
  AlertTriangle,
} from 'lucide-react'
import Card from '../components/Card'
import { configApi, fleetApi } from '../services/api'
import type { ConfigSnapshot } from '../types'

export default function Config() {
  const queryClient = useQueryClient()
  const [configYaml, setConfigYaml] = useState('')
  const [selectedNode, setSelectedNode] = useState<number | null>(null)
  const [planResult, setPlanResult] = useState<any>(null)

  const { data: nodes } = useQuery({
    queryKey: ['fleet-nodes'],
    queryFn: () => fleetApi.listNodes(),
  })

  const { data: snapshots } = useQuery({
    queryKey: ['config-snapshots', selectedNode],
    queryFn: () => configApi.listSnapshots({ node_id: selectedNode || undefined, limit: 10 }),
  })

  const planMutation = useMutation({
    mutationFn: () => configApi.plan({
      node_id: selectedNode || undefined,
      config_yaml: configYaml,
    }),
    onSuccess: (data) => {
      setPlanResult(data)
    },
  })

  const applyMutation = useMutation({
    mutationFn: () => configApi.apply({
      node_id: selectedNode || undefined,
      config_yaml: configYaml,
      notes: 'Applied from UI',
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config-snapshots'] })
      setPlanResult(null)
      setConfigYaml('')
    },
  })

  const rollbackMutation = useMutation({
    mutationFn: (snapshotId: number) => configApi.rollback(snapshotId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config-snapshots'] })
    },
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Config Management</h1>
          <p className="text-gray-500 mt-1">Terraform-like plan/apply workflow</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Config Editor */}
        <div className="lg:col-span-2 space-y-6">
          <Card title="Configuration Editor">
            <div className="space-y-4">
              {/* Node Selector */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Target Node
                </label>
                <select
                  value={selectedNode || ''}
                  onChange={(e) => setSelectedNode(e.target.value ? Number(e.target.value) : null)}
                  className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                >
                  <option value="">All Nodes (Fleet-wide)</option>
                  {nodes?.nodes?.map((node: any) => (
                    <option key={node.id} value={node.id}>
                      {node.name} ({node.environment})
                    </option>
                  ))}
                </select>
              </div>

              {/* YAML Editor */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Configuration (YAML)
                </label>
                <textarea
                  value={configYaml}
                  onChange={(e) => setConfigYaml(e.target.value)}
                  placeholder={`# MediaMTX Configuration
paths:
  cam1:
    source: rtsp://user:pass@192.168.1.100:554/stream
  cam2:
    source: rtsp://user:pass@192.168.1.101:554/stream`}
                  className="w-full h-64 px-4 py-3 font-mono text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>

              {/* Actions */}
              <div className="flex gap-3">
                <button
                  onClick={() => planMutation.mutate()}
                  disabled={!configYaml || planMutation.isPending}
                  className="flex items-center gap-2 px-4 py-2 bg-yellow-500 text-white rounded-lg hover:bg-yellow-600 disabled:opacity-50"
                >
                  <Play className="w-4 h-4" />
                  Plan
                </button>
                <button
                  onClick={() => applyMutation.mutate()}
                  disabled={!planResult?.can_apply || applyMutation.isPending}
                  className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                >
                  <Check className="w-4 h-4" />
                  Apply
                </button>
                <button
                  onClick={() => {
                    setPlanResult(null)
                    setConfigYaml('')
                  }}
                  className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-lg hover:bg-gray-50"
                >
                  <X className="w-4 h-4" />
                  Clear
                </button>
              </div>
            </div>
          </Card>

          {/* Plan Result */}
          {planResult && (
            <Card title="Plan Result">
              <div className="space-y-4">
                {/* Validation */}
                <div className={`p-4 rounded-lg ${
                  planResult.validation?.valid
                    ? 'bg-green-50 border border-green-200'
                    : 'bg-red-50 border border-red-200'
                }`}>
                  <div className="flex items-center gap-2 mb-2">
                    {planResult.validation?.valid ? (
                      <Check className="w-5 h-5 text-green-600" />
                    ) : (
                      <AlertTriangle className="w-5 h-5 text-red-600" />
                    )}
                    <span className="font-medium">
                      {planResult.validation?.valid ? 'Validation Passed' : 'Validation Failed'}
                    </span>
                  </div>
                  {planResult.validation?.errors?.length > 0 && (
                    <ul className="list-disc list-inside text-sm text-red-600">
                      {planResult.validation.errors.map((err: string, i: number) => (
                        <li key={i}>{err}</li>
                      ))}
                    </ul>
                  )}
                  {planResult.validation?.warnings?.length > 0 && (
                    <ul className="list-disc list-inside text-sm text-yellow-600 mt-2">
                      {planResult.validation.warnings.map((warn: string, i: number) => (
                        <li key={i}>{warn}</li>
                      ))}
                    </ul>
                  )}
                </div>

                {/* Diff */}
                {planResult.diff?.has_changes && (
                  <div>
                    <h4 className="font-medium text-gray-700 mb-2">Changes</h4>
                    <pre className="p-4 bg-gray-900 text-gray-100 rounded-lg text-sm overflow-x-auto">
                      {planResult.diff.unified_diff}
                    </pre>
                  </div>
                )}

                {!planResult.diff?.has_changes && planResult.can_apply && (
                  <p className="text-gray-500">No changes detected</p>
                )}
              </div>
            </Card>
          )}
        </div>

        {/* Snapshots History */}
        <Card title="Recent Snapshots" padding="none">
          <div className="divide-y divide-gray-100 max-h-[600px] overflow-y-auto">
            {snapshots?.snapshots?.length > 0 ? (
              snapshots.snapshots.map((snapshot: ConfigSnapshot) => (
                <div key={snapshot.id} className="p-4 hover:bg-gray-50">
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-gray-400" />
                      <span className="font-mono text-sm text-gray-600">
                        {snapshot.config_hash}
                      </span>
                    </div>
                    {snapshot.applied && (
                      <span className="px-2 py-0.5 text-xs bg-green-100 text-green-800 rounded-full">
                        Applied
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-gray-500 space-y-1">
                    {snapshot.notes && <p>{snapshot.notes}</p>}
                    <div className="flex items-center gap-4">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(snapshot.created_at).toLocaleString()}
                      </span>
                      {snapshot.applied_by && (
                        <span>by {snapshot.applied_by}</span>
                      )}
                    </div>
                  </div>
                  <div className="mt-2">
                    <button
                      onClick={() => rollbackMutation.mutate(snapshot.id)}
                      disabled={rollbackMutation.isPending}
                      className="flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700"
                    >
                      <RotateCcw className="w-3 h-3" />
                      Rollback to this
                    </button>
                  </div>
                </div>
              ))
            ) : (
              <div className="p-8 text-center text-gray-500">
                <Settings className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                No snapshots yet
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}
