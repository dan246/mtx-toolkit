import type { PipelineStatus } from '../types'
import { useLanguage } from '../i18n/LanguageContext'

interface PipelineHealthBarProps {
  status: PipelineStatus
  writeLatencyMs?: number | null
  className?: string
}

const statusColors: Record<PipelineStatus, { color: string; bgColor: string }> = {
  healthy: { color: 'bg-green-500', bgColor: 'bg-green-100' },
  warning: { color: 'bg-yellow-500', bgColor: 'bg-yellow-100' },
  critical: { color: 'bg-red-500', bgColor: 'bg-red-100' },
  unknown: { color: 'bg-gray-300', bgColor: 'bg-gray-100' },
}

const statusKeys: Record<PipelineStatus, keyof typeof import('../i18n/translations').translations.en.pipeline> = {
  healthy: 'healthy',
  warning: 'warning',
  critical: 'critical',
  unknown: 'unknown',
}

export default function PipelineHealthBar({ status, writeLatencyMs, className = '' }: PipelineHealthBarProps) {
  const { t } = useLanguage()
  const colors = statusColors[status] || statusColors.unknown
  const label = t.pipeline[statusKeys[status] || 'unknown']

  // Calculate bar width based on latency (0-2000ms range)
  const maxLatency = 2000
  const latencyPercent = writeLatencyMs != null
    ? Math.min(100, (writeLatencyMs / maxLatency) * 100)
    : 0

  return (
    <div className={`space-y-1 ${className}`}>
      <div className="flex items-center justify-between text-xs">
        <span className={`font-medium ${
          status === 'healthy' ? 'text-green-700' :
          status === 'warning' ? 'text-yellow-700' :
          status === 'critical' ? 'text-red-700' :
          'text-gray-500'
        }`}>
          {label}
        </span>
        {writeLatencyMs != null && (
          <span className="text-gray-500">{writeLatencyMs.toFixed(0)}ms</span>
        )}
      </div>
      <div className={`w-full h-2 rounded-full ${colors.bgColor}`}>
        <div
          className={`h-2 rounded-full transition-all duration-300 ${colors.color}`}
          style={{ width: `${writeLatencyMs != null ? latencyPercent : (status === 'unknown' ? 0 : 100)}%` }}
        />
      </div>
    </div>
  )
}
