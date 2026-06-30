import { useState, useEffect, useRef } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  LayoutDashboard, Database, Search, Tag, AlertTriangle,
  Settings, Download, LogOut, Cpu, ChevronLeft, ChevronRight,
  Users, ChevronDown, KeyRound, Eye, EyeOff, FolderOpen, BookOpen, Tags, Terminal, Gauge, FileText, History, Filter,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { datasetApi, authApi, evalApi, getCurrentDatasetId, setCurrentDatasetId, getCurrentBu, setCurrentBu } from '@/lib/api'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

// 导航按子系统分组：标注平台 / AI 评测（独立子系统）/ 系统管理
// datasetBound=true 的组才与「当前数据集」强绑定，其余子系统不展示数据集下拉框
const navGroups = [
  {
    key: 'annotation',
    group: '标注平台',
    datasetBound: true,
    items: [
      { to: '/dashboard',      label: '首页',          icon: LayoutDashboard },
      { to: '/explorer',       label: '数据管理',      icon: Search },
      { to: '/data',           label: '数据上传',      icon: Database },
      { to: '/pre-annotation', label: '预标注',        icon: Cpu },
      { to: '/annotation',     label: '标注工作台',    icon: Tag },
      { to: '/conflicts',      label: '冲突检测',      icon: AlertTriangle },
      { to: '/categories',     label: '业务分类',      icon: Tags },
      { to: '/export',         label: '数据导出',      icon: Download },
      { to: '/config',         label: '配置中心',      icon: Settings },
    ],
  },
  {
    key: 'eval',
    group: 'AI 评测',
    buBound: true,   // 这些页面基于「当前业务单元(BU)」，侧边栏展示 BU 选择器
    items: [
      { to: '/eval',            label: '评测',          icon: Gauge },
      { to: '/eval/history',    label: '历史评测',      icon: History },
      { to: '/eval/categories', label: '业务分类',      icon: Tags },
      { to: '/eval/activity',   label: '活动标问',      icon: Filter },
      { to: '/eval/prompts',    label: '提示词管理',    icon: FileText },
    ],
  },
  {
    key: 'admin',
    group: '系统管理',
    items: [
      { to: '/datasets',       label: '数据集管理',    icon: FolderOpen, adminOnly: true },
      { to: '/users',          label: '用户管理',      icon: Users,       adminOnly: true },
      { to: '/admin-sql',      label: 'SQL 工具',      icon: Terminal,    adminOnly: true },
    ],
  },
]

// 当前路径属于哪个分组（用于判断数据集下拉框显隐）。最长前缀匹配避免 /eval 命中 /
function groupOfPath(pathname) {
  let best = null
  for (const g of navGroups) {
    for (const it of g.items) {
      if (pathname === it.to || pathname.startsWith(it.to + '/')) {
        if (!best || it.to.length > best.to.length) best = { ...it, _group: g }
      }
    }
  }
  return best?._group || null
}

// ── 修改密码弹窗 ───────────────────────────────────────────────────────────────

function ChangePasswordDialog({ open, onClose }) {
  const [oldPwd, setOldPwd]   = useState('')
  const [newPwd, setNewPwd]   = useState('')
  const [showOld, setShowOld] = useState(false)
  const [showNew, setShowNew] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) { setOldPwd(''); setNewPwd(''); setShowOld(false); setShowNew(false) }
  }, [open])

  async function handleSubmit() {
    if (!oldPwd) { toast.error('请输入旧密码'); return }
    if (newPwd.length < 6) { toast.error('新密码至少 6 位'); return }
    setLoading(true)
    try {
      await authApi.changePassword(oldPwd, newPwd)
      toast.success('密码已更新')
      onClose()
    } catch (err) {
      toast.error(err.response?.data?.detail || '修改失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-sm">
        <h2 className="text-base font-semibold mb-4">修改密码</h2>
        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">旧密码</label>
            <div className="relative">
              <Input
                type={showOld ? 'text' : 'password'}
                value={oldPwd}
                onChange={e => setOldPwd(e.target.value)}
                placeholder="请输入旧密码"
              />
              <button type="button" onClick={() => setShowOld(v => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                {showOld ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">新密码</label>
            <div className="relative">
              <Input
                type={showNew ? 'text' : 'password'}
                value={newPwd}
                onChange={e => setNewPwd(e.target.value)}
                placeholder="至少 6 位"
              />
              <button type="button" onClick={() => setShowNew(v => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                {showNew ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <Button variant="outline" onClick={onClose} disabled={loading}>取消</Button>
          <Button onClick={handleSubmit} disabled={loading}>
            {loading ? '提交中…' : '确认修改'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ── 主布局 ─────────────────────────────────────────────────────────────────────

export default function Layout() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const username = localStorage.getItem('username') || 'admin'
  const roles    = JSON.parse(localStorage.getItem('roles') || '[]')
  const isAdmin  = roles.includes('admin')

  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem('sidebar-collapsed') === 'true'
  )

  // 一级目录折叠状态：存被折叠的 group.key 集合，持久化
  const [collapsedGroups, setCollapsedGroups] = useState(() => {
    try { return new Set(JSON.parse(localStorage.getItem('nav-collapsed-groups') || '[]')) }
    catch { return new Set() }
  })

  const location = useLocation()
  // 标注平台与「当前数据集」绑定；AI 评测与「当前 BU」绑定，各展示各自的选择器
  const activeGroup = groupOfPath(location.pathname)
  const showDatasetSelector = activeGroup?.datasetBound ?? false
  const showBuSelector = activeGroup?.buBound ?? false

  function toggleGroup(key) {
    setCollapsedGroups(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      localStorage.setItem('nav-collapsed-groups', JSON.stringify([...next]))
      return next
    })
  }

  const [datasets, setDatasets]           = useState([])
  const [currentDataset, setCurrentDataset] = useState(getCurrentDatasetId())
  const [dsOpen, setDsOpen]               = useState(false)
  const [changePwdOpen, setChangePwdOpen] = useState(false)
  const [userMenuOpen, setUserMenuOpen]   = useState(false)
  const userMenuRef = useRef(null)

  // AI 评测：当前 BU（业务单元）全局上下文，仿数据集
  const [bus, setBus]             = useState([])
  const [currentBu, setCurrentBuState] = useState(getCurrentBu())
  const [buOpen, setBuOpen]       = useState(false)

  useEffect(() => {
    evalApi.bus()
      .then(res => {
        const list = res.data?.data?.bus || []
        setBus(list)
        if (list.length && !list.find(b => b.code === currentBu)) switchBu(list[0].code)
      })
      .catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  function switchBu(code) {
    setCurrentBuState(code)
    setCurrentBu(code)
    setBuOpen(false)
    window.dispatchEvent(new CustomEvent('buChanged', { detail: { bu: code } }))
    qc.invalidateQueries()
  }

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

  // 点击菜单外部时关闭用户菜单
  useEffect(() => {
    function handleClickOutside(e) {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target)) {
        setUserMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  function switchDataset(id) {
    setCurrentDataset(id)
    setCurrentDatasetId(id)   // 先更新 localStorage
    setDsOpen(false)
    // 通知各页面（监听事件的页面会重置自身的 datasetId state）
    window.dispatchEvent(new CustomEvent('datasetChanged', { detail: { datasetId: id } }))
    // 清除所有 React Query 缓存，确保未监听事件的页面也能获取新数据集数据
    qc.invalidateQueries()
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

        {/* Dataset Selector — 仅标注平台（datasetBound）页面展示 */}
        {!collapsed && showDatasetSelector && (
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

        {/* BU Selector — 仅 AI 评测（buBound）页面展示 */}
        {!collapsed && showBuSelector && (
          <div className="px-3 py-3 border-b border-gray-700">
            <div className="text-xs text-gray-500 mb-1 px-1">当前业务单元（BU）</div>
            <div className="relative">
              <button
                onClick={() => setBuOpen(v => !v)}
                className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-sm transition-colors"
              >
                <span className="truncate text-gray-200">
                  {bus.find(b => b.code === currentBu)?.name || currentBu}
                </span>
                <ChevronDown className={cn('w-4 h-4 shrink-0 text-gray-400 transition-transform', buOpen && 'rotate-180')} />
              </button>
              {buOpen && (
                <div className="absolute left-0 right-0 top-full mt-1 z-50 bg-gray-800 border border-gray-700 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                  {bus.length === 0 && (
                    <div className="px-3 py-2 text-xs text-gray-500">暂无业务单元</div>
                  )}
                  {bus.map(b => (
                    <button
                      key={b.code}
                      onClick={() => switchBu(b.code)}
                      className={cn(
                        'w-full text-left px-3 py-2 text-sm transition-colors hover:bg-gray-700',
                        b.code === currentBu ? 'text-blue-400 bg-gray-700' : 'text-gray-300'
                      )}
                    >
                      <div className="font-medium truncate">{b.name}</div>
                      <div className="text-xs text-gray-500 truncate">{b.intent_count} 个业务分类</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Navigation — 按子系统分组，一级目录可折叠 */}
        <nav className="flex-1 px-2 py-4 space-y-2 overflow-y-auto">
          {navGroups.map(({ key, group, items }) => {
            const visible = items.filter(item => !item.adminOnly || isAdmin)
            if (visible.length === 0) return null
            // 侧边栏整体收窄时不做分组折叠（无标题可点），用分隔线占位并全部展示
            const groupCollapsed = !collapsed && collapsedGroups.has(key)
            return (
              <div key={key} className="space-y-1">
                {collapsed ? (
                  <div className="mx-2 my-2 border-t border-gray-700" />
                ) : (
                  <button
                    onClick={() => toggleGroup(key)}
                    className="w-full flex items-center justify-between px-3 py-1 text-[11px] font-semibold uppercase tracking-wider text-gray-500 hover:text-gray-300 transition-colors"
                  >
                    <span>{group}</span>
                    <ChevronDown className={cn('w-3.5 h-3.5 transition-transform', groupCollapsed && '-rotate-90')} />
                  </button>
                )}
                {!groupCollapsed && visible.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    end={to === '/eval'}
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
              </div>
            )
          })}
        </nav>

        {/* User + Toggle */}
        <div className="px-2 py-3 border-t border-gray-700 space-y-1">
          {/* 用户头像 — 点击弹出菜单 */}
          <div className="relative" ref={userMenuRef}>
            <button
              onClick={() => setUserMenuOpen(v => !v)}
              className={cn(
                'w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-800 transition-colors',
                collapsed ? 'justify-center' : ''
              )}
            >
              <div
                className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-400 to-violet-500 flex items-center justify-center text-xs font-semibold text-white shrink-0"
                title={collapsed ? username : undefined}
              >
                {username[0]?.toUpperCase()}
              </div>
              {!collapsed && (
                <>
                  <div className="flex-1 min-w-0 text-left">
                    <div className="text-sm font-medium truncate text-gray-100">{username}</div>
                    <div className="text-xs text-gray-400">
                      {isAdmin ? '管理员' : roles[0] || '用户'}
                    </div>
                  </div>
                  <ChevronDown className={cn(
                    'w-3.5 h-3.5 text-gray-400 shrink-0 transition-transform',
                    userMenuOpen && 'rotate-180'
                  )} />
                </>
              )}
            </button>

            {/* 下拉菜单 */}
            {userMenuOpen && (
              <div className={cn(
                'absolute bottom-full mb-1 z-50 bg-gray-800 border border-gray-700 rounded-lg shadow-xl overflow-hidden',
                collapsed ? 'left-0 w-36' : 'left-0 right-0'
              )}>
                {/* 用户信息头部 */}
                <div className="px-3 py-2.5 border-b border-gray-700">
                  <div className="text-sm font-medium text-gray-100 truncate">{username}</div>
                  <div className="text-xs text-gray-400">{isAdmin ? '管理员' : roles[0] || '用户'}</div>
                </div>
                {/* 修改密码 */}
                <button
                  onClick={() => { setUserMenuOpen(false); setChangePwdOpen(true) }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white transition-colors"
                >
                  <KeyRound className="w-4 h-4 shrink-0" />
                  修改密码
                </button>
                {/* 退出登录 */}
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white transition-colors"
                >
                  <LogOut className="w-4 h-4 shrink-0" />
                  退出登录
                </button>
              </div>
            )}
          </div>

          {/* 使用文档 + 折叠按钮 */}
          <div className={cn('flex gap-1', collapsed ? 'flex-col' : '')}>
            <a
              href="/docs"
              target="_blank"
              rel="noopener noreferrer"
              className={cn(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-400 hover:bg-gray-800 hover:text-gray-100 transition-colors',
                collapsed ? 'w-full justify-center' : 'flex-1'
              )}
              title="使用文档"
            >
              <BookOpen className="w-4 h-4 shrink-0" />
              {!collapsed && <span>使用文档</span>}
            </a>
            <button
              onClick={toggleSidebar}
              className={cn(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-400 hover:bg-gray-800 hover:text-gray-100 transition-colors',
                collapsed ? 'w-full justify-center' : 'flex-1'
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
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>

      {/* 修改密码弹窗 */}
      <ChangePasswordDialog open={changePwdOpen} onClose={() => setChangePwdOpen(false)} />
    </div>
  )
}
