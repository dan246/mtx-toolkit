import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react'
import { authApi, AuthUser, TOKEN_KEY } from '../services/api'

interface AuthContextType {
  user: AuthUser | null
  isAuthenticated: boolean
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setUser(null)
    // best-effort server notification; ignore failure
    authApi.logout().catch(() => undefined)
  }, [])

  // Validate an existing token on mount.
  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (!token) {
      setLoading(false)
      return
    }
    authApi.me()
      .then(({ user }) => setUser(user))
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY)
        setUser(null)
      })
      .finally(() => setLoading(false))
  }, [])

  // React to 401s surfaced by the axios interceptor.
  useEffect(() => {
    const onUnauthorized = () => setUser(null)
    window.addEventListener('mtx-unauthorized', onUnauthorized)
    return () => window.removeEventListener('mtx-unauthorized', onUnauthorized)
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const { token, user } = await authApi.login(username, password)
    localStorage.setItem(TOKEN_KEY, token)
    setUser(user)
  }, [])

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated: !!user, loading, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
