import { useState, useEffect } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Database, Search, Tag, CheckSquare, AlertTriangle,
  Settings, Download, LogOut, Cpu, ChevronLeft, ChevronRight,
  Users, ChevronDown,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { datasetApi, getCurrentDatasetId, setCurrentDatasetId } from '@/lib/api'

const navItems = [
  { to: '/dashboard',      label: 'Dashboard',    icon: LayoutDashboard },
  { to: '/explorer',       label: 'Data Explorer', icon: Search },
  { to: '/data',           label: '数据上传',      icon: Database },
  { to: '/pre-annotation', label: '预标注',        icon: Cpu },
  { to: '/annotation',     label: '标注工作台',    icon: Tag },
  { to: '/conflicts',      label: '冲突检测',      icon: AlertTriangle },
  { to: '/config',         label: '配置中心',      icon: Settings },
  { to: '/export',         label: '数据导出',      icon: Download },
  { to: '/users',          label: '用户管理',      icon: Users },
]

export default function Layout() {
  const navigate = useNavigate()
  const username = localStorage.getItem('username') || 'admin'
  const roles    = JSON.parse(localStorage.getItem('roles') || '[]')
  const isAdmin  = roles.includes('admin')

  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem('sidebar-collapsed') === 'true'
  )
  const [datasets, setDatasets]           = useState([])
  const [currentDataset, setCurrentDataset] = useState(getCurrentDatasetId())
  const [dsOpen, setDsOpen]               = useState(false)

  useEffect(() => {
    datasetApi.list()
      .then(res => {
        const list = res.data?.data || []
        setDatasets(list)
        if (list.length === 0) return
        // 当前 dataset_id 不在列表中（或尚未设置）时，自动切换到第一个
        const valid = list.find(d => d.id === currentDataset)
        if (!valid) {
          // 复用 switchDataset 确保同时更新 state + localStorage + 广播事件
          // 子页面监听 datasetChanged 后会重新发起正确的 API 请求
          switchDataset(list[0].id)
        } else {
          // 即使是有效的，也要触发事件让Dashboard知道
          window.dispatchEvent(new CustomEvent('datasetChanged', { detail: { datasetId: currentDataset } }))
        }
      })
      .catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  function switchDataset(id) {
    setCurrentDataset(id)
    setCurrentDatasetId(id)
    setDsOpen(false)
    // 刷新当前页面数据（通知子组件）
    window.dispatchEvent(new CustomEvent('datasetChanged', { detail: { datasetId: id } }))
  }

  function toggleSidebar() {
    const next = !collapsed
    setCollapsed(next)
    localStorage.setItem('sidebar-collapsed', String(next))
  }

  function handleLogout() {
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    localStorage.removeItem('roles')
    navigate('/login')
  }

  const currentDs = datasets.find(d => d.id === currentDataset)

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside
        className={cn(
          'flex flex-col bg-gray-900 text-gray-100 shrink-0 transition-all duration-200',
          collapsed ? 'w-16' : 'w-60'
        )}
      >
        {/* Logo */}
        <div className={cn('border-b border-gray-700', collapsed ? 'px-3 py-5' : 'px-6 py-5')}>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center text-white font-bold text-sm shrink-0">
              D
            </div>
            {!collapsed && (
              <div>
                <div className="font-semibold text-sm">Datapulse</div>
                <div className="text-xs text-gray-400">数据飞轮</div>
              </div>
            )}
          </div>
        </div>

        {/* Dataset Selector */}
        {!collapsed && (
          <div className="px-3 py-3 border-b border-gray-700">
            <div className="text-xs text-gray-500 mb-1 px-1">当前数据集</div>
            <div className="relative">
              <button
                onClick={() => setDsOpen(v => !v)}
                className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-sm transition-colors"
              >
                <span className="truncate text-gray-200">
                  {currentDs?.name || currentDataset}
                </span>
                <ChevronDown className={cn('w-4 h-4 shrink-0 text-gray-400 transition-transform', dsOpen && 'rotate-180')} />
              </button>
              {dsOpen && (
                <div className="absolute left-0 right-0 top-full mt-1 z-50 bg-gray-800 border border-gray-700 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                  {datasets.length === 0 && (
                    <div className="px-3 py-2 text-xs text-gray-500">暂无数据集</div>
                  )}
                  {datasets.map(ds => (
                    <button
                      key={ds.id}
                      onClick={() => switchDataset(ds.id)}
                      className={cn(
                        'w-full text-left px-3 py-2 text-sm transition-colors hover:bg-gray-700',
                        ds.id === currentDataset ? 'text-blue-400 bg-gray-700' : 'text-gray-300'
                      )}
                    >
                      <div className="font-medium truncate">{ds.name}</div>
                      {ds.description && (
                        <div className="text-xs text-gray-500 truncate">{ds.description}</div>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Navigation */}
        <nav className="flex-1 px-2 py-4 space-y-1 overflow-y-auto">
          {navItems
            .filter(item => item.to !== '/users' || isAdmin)
            .map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                title={collapsed ? label : undefined}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
                    collapsed ? 'justify-center' : '',
                    isActive
                      ? 'bg-gray-700 text-white'
                      : 'text-gray-400 hover:bg-gray-800 hover:text-gray-100'
                  )
                }
              >
                <Icon className="w-4 h-4 shrink-0" />
                {!collapsed && label}
              </NavLink>
            ))}
        </nav>

        {/* User + Toggle */}
        <div className="px-2 py-3 border-t border-gray-700 space-y-1">
          {/* User info */}
          <div className={cn(
            'flex items-center gap-3 px-3 py-2 rounded-lg',
            collapsed ? 'justify-center' : ''
          )}>
            <div
              className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-400 to-violet-500 flex items-center justify-center text-xs font-semibold text-white shrink-0"
              title={collapsed ? username : undefined}
            >
              {username[0]?.toUpperCase()}
            </div>
            {!collapsed && (
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{username}</div>
                <div className="text-xs text-gray-400">
                  {isAdmin ? '管理员' : roles[0] || '用户'}
                </div>
              </div>
            )}
            {!collapsed && (
              <button
                onClick={handleLogout}
                className="text-gray-400 hover:text-white transition-colors"
                title="退出"
              >
                <LogOut className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Collapse toggle */}
          <button
            onClick={toggleSidebar}
            className={cn(
              'w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-400 hover:bg-gray-800 hover:text-gray-100 transition-colors',
              collapsed ? 'justify-center' : ''
            )}
            title={collapsed ? '展开侧边栏' : '收起侧边栏'}
          >
            {collapsed ? <ChevronRight className="w-4 h-4" /> : (
              <>
                <ChevronLeft className="w-4 h-4" />
                <span>收起</span>
              </>
            )}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
