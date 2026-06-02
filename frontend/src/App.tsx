import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { ReactNode } from 'react'
import { Loader2 } from 'lucide-react'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Streams from './pages/Streams'
import Viewers from './pages/Viewers'
import Preview from './pages/Preview'
import Fleet from './pages/Fleet'
import Config from './pages/Config'
import Recordings from './pages/Recordings'
import Testing from './pages/Testing'
import Login from './pages/Login'
import { useAuth } from './contexts/AuthContext'

function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
      </div>
    )
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <Layout>{children}</Layout>
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="/dashboard" element={<RequireAuth><Dashboard /></RequireAuth>} />
      <Route path="/streams" element={<RequireAuth><Streams /></RequireAuth>} />
      <Route path="/viewers" element={<RequireAuth><Viewers /></RequireAuth>} />
      <Route path="/preview" element={<RequireAuth><Preview /></RequireAuth>} />
      <Route path="/fleet" element={<RequireAuth><Fleet /></RequireAuth>} />
      <Route path="/config" element={<RequireAuth><Config /></RequireAuth>} />
      <Route path="/recordings" element={<RequireAuth><Recordings /></RequireAuth>} />
      <Route path="/testing" element={<RequireAuth><Testing /></RequireAuth>} />
    </Routes>
  )
}

export default App
