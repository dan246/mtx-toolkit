import { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Radio,
  Server,
  Settings,
  Film,
  FlaskConical,
  Activity,
} from 'lucide-react'
import clsx from 'clsx'

interface LayoutProps {
  children: ReactNode
}

const navItems = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/streams', label: 'Streams', icon: Radio },
  { path: '/fleet', label: 'Fleet', icon: Server },
  { path: '/config', label: 'Config', icon: Settings },
  { path: '/recordings', label: 'Recordings', icon: Film },
  { path: '/testing', label: 'Testing', icon: FlaskConical },
]

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-64 bg-slate-900 text-white flex flex-col">
        {/* Logo */}
        <div className="p-4 border-b border-slate-700">
          <div className="flex items-center gap-3">
            <Activity className="w-8 h-8 text-primary-400" />
            <div>
              <h1 className="font-bold text-lg">MTX Toolkit</h1>
              <p className="text-xs text-slate-400">Stream Reliability</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4">
          <ul className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.path
              return (
                <li key={item.path}>
                  <Link
                    to={item.path}
                    className={clsx(
                      'flex items-center gap-3 px-3 py-2 rounded-lg transition-colors',
                      isActive
                        ? 'bg-primary-600 text-white'
                        : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                    )}
                  >
                    <Icon className="w-5 h-5" />
                    <span>{item.label}</span>
                  </Link>
                </li>
              )
            })}
          </ul>
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-slate-700 text-xs text-slate-400">
          <p>v0.1.0</p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="p-6">{children}</div>
      </main>
    </div>
  )
}
