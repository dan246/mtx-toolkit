import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Streams from './pages/Streams'
import Fleet from './pages/Fleet'
import Config from './pages/Config'
import Recordings from './pages/Recordings'
import Testing from './pages/Testing'

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/streams" element={<Streams />} />
        <Route path="/fleet" element={<Fleet />} />
        <Route path="/config" element={<Config />} />
        <Route path="/recordings" element={<Recordings />} />
        <Route path="/testing" element={<Testing />} />
      </Routes>
    </Layout>
  )
}

export default App
