import clsx from 'clsx'
import type { StreamStatus, EventSeverity } from '../types'

interface StatusBadgeProps {
  status: StreamStatus | EventSeverity
  size?: 'sm' | 'md'
}

const statusColors: Record<string, string> = {
  healthy: 'bg-green-100 text-green-800 border-green-200',
  degraded: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  unhealthy: 'bg-red-100 text-red-800 border-red-200',
  unknown: 'bg-gray-100 text-gray-800 border-gray-200',
  info: 'bg-blue-100 text-blue-800 border-blue-200',
  warning: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  error: 'bg-orange-100 text-orange-800 border-orange-200',
  critical: 'bg-red-100 text-red-800 border-red-200',
}

export default function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center font-medium border rounded-full capitalize',
        statusColors[status] || statusColors.unknown,
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm'
      )}
    >
      <span
        className={clsx(
          'rounded-full mr-1.5',
          size === 'sm' ? 'w-1.5 h-1.5' : 'w-2 h-2',
          status === 'healthy' && 'bg-green-500',
          status === 'degraded' && 'bg-yellow-500',
          status === 'unhealthy' && 'bg-red-500',
          status === 'unknown' && 'bg-gray-500',
          status === 'info' && 'bg-blue-500',
          status === 'warning' && 'bg-yellow-500',
          status === 'error' && 'bg-orange-500',
          status === 'critical' && 'bg-red-500 animate-pulse'
        )}
      />
      {status}
    </span>
  )
}
