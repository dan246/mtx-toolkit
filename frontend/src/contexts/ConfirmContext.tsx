import { createContext, useContext, useState, useCallback, useRef, ReactNode } from 'react'
import { useLanguage } from '../i18n/LanguageContext'

interface ConfirmOptions {
  title?: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
}

interface PromptOptions extends ConfirmOptions {
  defaultValue?: string
  inputType?: 'text' | 'number'
}

interface ConfirmContextType {
  confirm: (options: ConfirmOptions) => Promise<boolean>
  prompt: (options: PromptOptions) => Promise<string | null>
}

const ConfirmContext = createContext<ConfirmContextType | undefined>(undefined)

interface DialogState {
  options: PromptOptions
  isPrompt: boolean
  inputValue: string
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const { t } = useLanguage()
  const [state, setState] = useState<DialogState | null>(null)
  const resolver = useRef<((value: boolean | string | null) => void) | null>(null)

  const close = useCallback((result: boolean | string | null) => {
    resolver.current?.(result)
    resolver.current = null
    setState(null)
  }, [])

  const confirm = useCallback((options: ConfirmOptions) => {
    setState({ options, isPrompt: false, inputValue: '' })
    return new Promise<boolean>((resolve) => {
      resolver.current = (v) => resolve(Boolean(v))
    })
  }, [])

  const prompt = useCallback((options: PromptOptions) => {
    setState({ options, isPrompt: true, inputValue: options.defaultValue ?? '' })
    return new Promise<string | null>((resolve) => {
      resolver.current = (v) => resolve(v === false ? null : (v as string))
    })
  }, [])

  return (
    <ConfirmContext.Provider value={{ confirm, prompt }}>
      {children}
      {state && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
            <h3 className="text-lg font-semibold text-gray-900">
              {state.options.title ?? t.common.confirmTitle}
            </h3>
            <p className="mt-2 text-sm text-gray-600">{state.options.message}</p>
            {state.isPrompt && (
              <input
                autoFocus
                type={state.options.inputType ?? 'text'}
                value={state.inputValue}
                onChange={(e) => setState(s => s && { ...s, inputValue: e.target.value })}
                onKeyDown={(e) => { if (e.key === 'Enter') close(state.inputValue) }}
                className="mt-4 w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            )}
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => close(state.isPrompt ? null : false)}
                className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50"
              >
                {state.options.cancelLabel ?? t.common.cancel}
              </button>
              <button
                onClick={() => close(state.isPrompt ? state.inputValue : true)}
                className={`px-4 py-2 text-sm text-white rounded-lg ${
                  state.options.danger
                    ? 'bg-red-600 hover:bg-red-700'
                    : 'bg-primary-600 hover:bg-primary-700'
                }`}
              >
                {state.options.confirmLabel ?? t.common.confirm}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  )
}

export function useConfirm() {
  const ctx = useContext(ConfirmContext)
  if (!ctx) throw new Error('useConfirm must be used within a ConfirmProvider')
  return ctx
}
