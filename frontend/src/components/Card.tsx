import { ReactNode } from 'react'
import clsx from 'clsx'

interface CardProps {
  title?: string
  subtitle?: string
  children: ReactNode
  className?: string
  padding?: 'none' | 'sm' | 'md' | 'lg'
  action?: ReactNode
}

export default function Card({
  title,
  subtitle,
  children,
  className,
  padding = 'md',
  action,
}: CardProps) {
  return (
    <div
      className={clsx(
        'bg-white rounded-xl shadow-sm border border-gray-200',
        className
      )}
    >
      {(title || action) && (
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            {title && <h3 className="font-semibold text-gray-900">{title}</h3>}
            {subtitle && <p className="text-sm text-gray-500 mt-0.5">{subtitle}</p>}
          </div>
          {action && <div>{action}</div>}
        </div>
      )}
      <div
        className={clsx(
          padding === 'none' && '',
          padding === 'sm' && 'p-4',
          padding === 'md' && 'p-6',
          padding === 'lg' && 'p-8'
        )}
      >
        {children}
      </div>
    </div>
  )
}
