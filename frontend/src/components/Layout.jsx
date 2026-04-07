import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Database, Tag, CheckSquare, AlertTriangle,
  Settings, Download, LogOut, Cpu, ChevronRight,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  { to: '/dashboard',      label: 'Dashboard',  icon: LayoutDashboard },
  { to: '/data',           label: '数据管理',    icon: Database },
  { to: '/pre-annotation', label: '预标注',      icon: Cpu },
  { to: '/annotation',     label: '标注',        icon: Tag },
  { to: '/conflicts',      label: '冲突检测',    icon: AlertTriangle },
  { to: '/config',         label: '配置中心',    icon: Settings },
  { to: '/export',         label: '数据导出',    icon: Download },
]

export default function Layout() {
  const navigate = useNavigate()
  const username = localStorage.getItem('username') || 'admin'

  function handleLogout() {
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    navigate('/login')
  }

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-60 flex flex-col bg-gray-900 text-gray-100 shrink-0">
        {/* Logo */}
        <div className="px-6 py-5 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center text-white font-bold text-sm">
              D
            </div>
            <div>
              <div className="font-semibold text-sm">Datapluse</div>
              <div className="text-xs text-gray-400">数据飞轮</div>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
                  isActive
                    ? 'bg-gray-700 text-white'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-gray-100'
                )
              }
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* User */}
        <div className="px-3 py-4 border-t border-gray-700">
          <div className="flex items-center gap-3 px-3 py-2 rounded-lg">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-400 to-violet-500 flex items-center justify-center text-xs font-semibold text-white shrink-0">
              {username[0]?.toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate">{username}</div>
              <div className="text-xs text-gray-400">超级管理员</div>
            </div>
            <button onClick={handleLogout} className="text-gray-400 hover:text-white transition-colors" title="退出">
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
