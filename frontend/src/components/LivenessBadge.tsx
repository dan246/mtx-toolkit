import type { LivenessClassification } from '../types'
import { useLanguage } from '../i18n/LanguageContext'

interface LivenessBadgeProps {
  classification: LivenessClassification
  size?: 'sm' | 'md'
}

const classificationColors: Record<LivenessClassification, string> = {
  live: 'bg-green-100 text-green-800',
  frozen: 'bg-blue-100 text-blue-800',
  black_screen: 'bg-gray-800 text-gray-100',
  stale: 'bg-orange-100 text-orange-800',
  silent: 'bg-gray-100 text-gray-600',
  unknown: 'bg-gray-100 text-gray-500',
}

const classificationKeys: Record<LivenessClassification, keyof typeof import('../i18n/translations').translations.en.liveness> = {
  live: 'live',
  frozen: 'frozen',
  black_screen: 'black',
  stale: 'stale',
  silent: 'silent',
  unknown: 'unknown',
}

export default function LivenessBadge({ classification, size = 'sm' }: LivenessBadgeProps) {
  const { t } = useLanguage()
  const color = classificationColors[classification] || classificationColors.unknown
  const key = classificationKeys[classification] || 'unknown'
  const label = t.liveness[key]
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm'

  return (
    <span className={`inline-flex items-center gap-1 font-medium rounded-full ${color} ${sizeClasses}`}>
      {label}
    </span>
  )
}
