import { ReactNode } from 'react'
import clsx from 'clsx'

interface StatCardProps {
  title: string
  value: string | number
  subtitle?: string
  icon?: ReactNode
  trend?: {
    value: number
    isPositive: boolean
  }
  color?: 'default' | 'success' | 'warning' | 'danger'
}

const colorClasses = {
  default: 'bg-primary-50 text-primary-600',
  success: 'bg-green-50 text-green-600',
  warning: 'bg-yellow-50 text-yellow-600',
  danger: 'bg-red-50 text-red-600',
}

export default function StatCard({
  title,
  value,
  subtitle,
  icon,
  trend,
  color = 'default',
}: StatCardProps) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">{title}</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
          {subtitle && (
            <p className="text-sm text-gray-500 mt-1">{subtitle}</p>
          )}
          {trend && (
            <p
              className={clsx(
                'text-sm font-medium mt-2',
                trend.isPositive ? 'text-green-600' : 'text-red-600'
              )}
            >
              {trend.isPositive ? '+' : ''}{trend.value}%
            </p>
          )}
        </div>
        {icon && (
          <div className={clsx('p-3 rounded-lg', colorClasses[color])}>
            {icon}
          </div>
        )}
      </div>
    </div>
  )
}
