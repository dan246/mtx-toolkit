import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Play,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Radio,
  Wifi,
  Activity,
  Loader2,
  Square,
  Copy,
  Check,
} from 'lucide-react'
import Card from '../components/Card'
import StatusBadge from '../components/StatusBadge'
import { healthApi, testingApi, TestScenario } from '../services/api'
import { useLanguage } from '../i18n/LanguageContext'
import { useToast } from '../contexts/ToastContext'
import type { ProbeResult } from '../types'

type SuiteType = 'integration' | 'stress' | 'recovery'

export default function Testing() {
  const { t } = useLanguage()
  const toast = useToast()
  const queryClient = useQueryClient()
  const [testUrl, setTestUrl] = useState('')
  const [protocol, setProtocol] = useState('rtsp')
  const [probeResult, setProbeResult] = useState<ProbeResult | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [suiteResults, setSuiteResults] = useState<Record<SuiteType, { success: boolean; message: string }>>(
    {} as Record<SuiteType, { success: boolean; message: string }>
  )

  // Real scenarios from the backend (running state reflects live ffmpeg procs).
  const { data: scenarioData } = useQuery({
    queryKey: ['test-scenarios'],
    queryFn: testingApi.listScenarios,
    refetchInterval: 5000,
  })
  const scenarios: TestScenario[] = scenarioData?.scenarios ?? []

  const probeMutation = useMutation({
    mutationFn: () => healthApi.probeUrl(testUrl, protocol),
    onSuccess: (data) => setProbeResult(data),
    onError: (error) => toast.error(`${t.messages.probeFailed}: ${error}`),
  })

  const startMutation = useMutation({
    mutationFn: (id: string) => testingApi.startScenario(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['test-scenarios'] }),
    onError: (error) => toast.error(`${t.testing.scenarioStartFailed}: ${error}`),
  })

  const stopMutation = useMutation({
    mutationFn: (id: string) => testingApi.stopScenario(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['test-scenarios'] }),
    onError: (error) => toast.error(`${t.testing.scenarioStopFailed}: ${error}`),
  })

  const [runningSuite, setRunningSuite] = useState<SuiteType | null>(null)

  const handleCopyCommand = (scenario: TestScenario) => {
    navigator.clipboard.writeText(scenario.command)
    setCopiedId(scenario.id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const runSuite = async (type: SuiteType) => {
    if (type === 'stress' && !testUrl) {
      toast.error(t.testing.stressUrlRequired)
      return
    }
    setRunningSuite(type)
    try {
      let message = ''
      let success = false
      if (type === 'integration') {
        const r = await testingApi.runIntegration()
        success = r.success
        message = `${r.passed}/${r.total} ${t.testing.passed}`
      } else if (type === 'stress') {
        const r = await testingApi.runStress(testUrl, protocol)
        success = r.success
        message = `${r.succeeded}/${r.concurrency} · ${t.testing.avgLatency} ${r.avg_latency_ms}ms`
      } else {
        const r = await testingApi.runRecovery()
        success = r.success
        message = `${r.path}: ${r.before} → ${r.after}`
      }
      setSuiteResults(prev => ({ ...prev, [type]: { success, message } }))
      success ? toast.success(`${t.testing.testPassed}: ${message}`) : toast.error(`${t.testing.testFailed}: ${message}`)
    } catch (error) {
      setSuiteResults(prev => ({ ...prev, [type]: { success: false, message: String(error) } }))
      toast.error(`${t.testing.testFailed}: ${error}`)
    } finally {
      setRunningSuite(null)
    }
  }

  const getScenarioStatusBadge = (status: TestScenario['status']) => {
    switch (status) {
      case 'running':
        return <span className="px-2 py-1 text-xs rounded-full bg-blue-100 text-blue-800 flex items-center gap-1">
          <Loader2 className="w-3 h-3 animate-spin" /> {t.testing.running}
        </span>
      default:
        return <span className="px-2 py-1 text-xs rounded-full bg-gray-100 text-gray-800">{t.testing.ready}</span>
    }
  }

  const suiteCards: { type: SuiteType; title: string; description: string; icon: typeof Play; btnClass: string; label: string }[] = [
    { type: 'integration', title: t.testing.fullIntegrationTest, description: t.testing.integrationDescription, icon: Play, btnClass: 'bg-green-600 hover:bg-green-700', label: t.testing.runAllTests },
    { type: 'stress', title: t.testing.stressTest, description: t.testing.stressDescription, icon: Activity, btnClass: 'bg-yellow-600 hover:bg-yellow-700', label: t.testing.runStressTest },
    { type: 'recovery', title: t.testing.recoveryTest, description: t.testing.recoveryDescription, icon: Wifi, btnClass: 'bg-red-600 hover:bg-red-700', label: t.testing.runRecoveryTest },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{t.testing.title}</h1>
          <p className="text-gray-500 mt-1">{t.testing.subtitle}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Stream Probe */}
        <Card title={t.testing.streamProbe} subtitle={t.testing.testUrlHealthCheck}>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t.testing.streamUrl}
              </label>
              <input
                type="text"
                value={testUrl}
                onChange={(e) => setTestUrl(e.target.value)}
                placeholder="rtsp://localhost:8554/stream"
                className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                {t.testing.protocol}
              </label>
              <select
                value={protocol}
                onChange={(e) => setProtocol(e.target.value)}
                className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                <option value="rtsp">RTSP</option>
                <option value="rtmp">RTMP</option>
                <option value="hls">HLS</option>
                <option value="webrtc">WebRTC</option>
              </select>
            </div>

            <button
              onClick={() => probeMutation.mutate()}
              disabled={!testUrl || probeMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
            >
              {probeMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              {t.testing.runProbe}
            </button>
          </div>
        </Card>

        {/* Probe Result */}
        <Card title={t.testing.probeResult} subtitle="Analysis output">
          {probeResult ? (
            <div className="space-y-4">
              {/* Status */}
              <div className={`p-4 rounded-lg ${
                probeResult.is_healthy
                  ? 'bg-green-50 border border-green-200'
                  : 'bg-red-50 border border-red-200'
              }`}>
                <div className="flex items-center gap-2 mb-2">
                  {probeResult.is_healthy ? (
                    <CheckCircle className="w-6 h-6 text-green-600" />
                  ) : (
                    <XCircle className="w-6 h-6 text-red-600" />
                  )}
                  <span className="font-semibold text-lg">
                    {probeResult.is_healthy ? t.testing.streamHealthy : t.testing.streamUnhealthy}
                  </span>
                </div>
                <StatusBadge status={probeResult.status} />
              </div>

              {/* Metrics */}
              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-sm text-gray-500">{t.streams.fps}</p>
                  <p className="text-lg font-semibold">{probeResult.fps?.toFixed(1) || '-'}</p>
                </div>
                <div className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-sm text-gray-500">{t.streams.bitrate}</p>
                  <p className="text-lg font-semibold">
                    {probeResult.bitrate ? `${(probeResult.bitrate / 1000).toFixed(0)} kbps` : '-'}
                  </p>
                </div>
                <div className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-sm text-gray-500">Resolution</p>
                  <p className="text-lg font-semibold">
                    {probeResult.width && probeResult.height
                      ? `${probeResult.width}x${probeResult.height}`
                      : '-'}
                  </p>
                </div>
                <div className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-sm text-gray-500">Codec</p>
                  <p className="text-lg font-semibold">{probeResult.codec || '-'}</p>
                </div>
              </div>

              {/* Issues */}
              {probeResult.issues && probeResult.issues.length > 0 && (
                <div>
                  <h4 className="font-medium text-gray-700 mb-2">{t.testing.issuesDetected}</h4>
                  <ul className="space-y-2">
                    {probeResult.issues.map((issue, i) => (
                      <li key={i} className="flex items-center gap-2 text-yellow-700">
                        <AlertTriangle className="w-4 h-4" />
                        {issue}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Error */}
              {probeResult.error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                  <p className="text-red-700">{probeResult.error}</p>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-gray-400">
              <Radio className="w-12 h-12 mb-4" />
              <p>{t.testing.runProbeSeeResults}</p>
            </div>
          )}
        </Card>
      </div>

      {/* Test Scenarios */}
      <Card title={t.testing.testScenarios} subtitle={t.testing.preConfiguredTestStreams}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {scenarios.map((scenario) => (
            <div
              key={scenario.id}
              className="p-4 border border-gray-200 rounded-lg hover:border-primary-300 transition-colors"
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <h4 className="font-medium text-gray-900">{scenario.name}</h4>
                  <p className="text-sm text-gray-500">{scenario.description}</p>
                </div>
                {getScenarioStatusBadge(scenario.status)}
              </div>

              <div className="mt-3 p-2 bg-gray-900 text-gray-300 rounded font-mono text-xs overflow-x-auto">
                {scenario.command}
              </div>

              <div className="mt-3 flex gap-2">
                {scenario.status === 'running' ? (
                  <button
                    onClick={() => stopMutation.mutate(scenario.id)}
                    disabled={stopMutation.isPending}
                    className="flex items-center gap-1 px-3 py-1.5 text-sm bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
                  >
                    <Square className="w-3 h-3" />
                    {t.testing.stop}
                  </button>
                ) : (
                  <button
                    onClick={() => startMutation.mutate(scenario.id)}
                    disabled={startMutation.isPending}
                    className="flex items-center gap-1 px-3 py-1.5 text-sm bg-primary-600 text-white rounded hover:bg-primary-700 disabled:opacity-50"
                  >
                    <Play className="w-3 h-3" />
                    {t.testing.start}
                  </button>
                )}
                <button
                  onClick={() => handleCopyCommand(scenario)}
                  className="flex items-center gap-1 px-3 py-1.5 text-sm border border-gray-200 rounded hover:bg-gray-50"
                >
                  {copiedId === scenario.id ? (
                    <Check className="w-3 h-3 text-green-600" />
                  ) : (
                    <Copy className="w-3 h-3" />
                  )}
                  {copiedId === scenario.id ? t.streams.copied : t.testing.copy}
                </button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Integration Test Suite */}
      <Card title={t.testing.integrationTestSuite} subtitle={t.testing.automatedTestRunners}>
        <div className="space-y-4">
          {suiteCards.map(({ type, title, description, icon: Icon, btnClass, label }) => (
            <div key={type} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
              <div className="flex-1">
                <h4 className="font-medium text-gray-900">{title}</h4>
                <p className="text-sm text-gray-500">{description}</p>
                {suiteResults[type] && (
                  <p className={`text-sm mt-1 ${suiteResults[type].success ? 'text-green-600' : 'text-red-600'}`}>
                    {suiteResults[type].message}
                  </p>
                )}
              </div>
              <button
                onClick={() => runSuite(type)}
                disabled={runningSuite !== null}
                className={`flex items-center gap-2 px-4 py-2 text-white rounded-lg disabled:opacity-50 ${btnClass}`}
              >
                {runningSuite === type ? <Loader2 className="w-4 h-4 animate-spin" /> : <Icon className="w-4 h-4" />}
                {label}
              </button>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
