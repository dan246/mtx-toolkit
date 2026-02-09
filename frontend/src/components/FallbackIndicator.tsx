import { useLanguage } from '../i18n/LanguageContext'

interface FallbackIndicatorProps {
  fallbackType?: string
  className?: string
}

export default function FallbackIndicator({ fallbackType, className = '' }: FallbackIndicatorProps) {
  const { t } = useLanguage()

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-full bg-yellow-100 text-yellow-800 border border-yellow-300 ${className}`}
    >
      {t.liveness.fallback}
      {fallbackType && fallbackType !== 'none' && (
        <span className="text-yellow-600">({fallbackType.replace('_', ' ')})</span>
      )}
    </span>
  )
}
