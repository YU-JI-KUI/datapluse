import { useState, useEffect, useRef } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  LogOut, ChevronDown, KeyRound, Eye, EyeOff, BookOpen,
  PanelLeftClose, PanelLeftOpen, Check,
  LayoutDashboard, Search, Database, Cpu, Tag, AlertTriangle,
  Tags, Download, Settings, Gauge, History, Filter, Zap, FileText,
  FolderOpen, Users, Terminal, ShieldCheck, Lightbulb,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { datasetApi, authApi, evalApi, getCurrentDatasetId, setCurrentDatasetId, getCurrentBu, setCurrentBu } from '@/lib/api'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

// 三个子系统 = 顶栏一级切换。datasetBound / buBound 决定顶栏右侧展示哪个上下文选择器。
// defaultPath 是点击一级 Tab 后的落地页（各子系统第一个页面）。
const subsystems = [
  {
    key: 'annotation',
    label: '标注平台',
    datasetBound: true,
    defaultPath: '/dashboard',
    items: [
      { to: '/dashboard',      label: '首页',       icon: LayoutDashboard },
      { to: '/explorer',       label: '数据管理',   icon: Search },
      { to: '/data',           label: '数据上传',   icon: Database },
      { to: '/pre-annotation', label: '预标注',     icon: Cpu },
      { to: '/annotation',     label: '标注工作台', icon: Tag },
      { to: '/conflicts',      label: '冲突检测',   icon: AlertTriangle },
      { to: '/categories',     label: '业务分类',   icon: Tags },
      { to: '/export',         label: '数据导出',   icon: Download },
      { to: '/config',         label: '配置中心',   icon: Settings },
    ],
  },
  {
    key: 'eval',
    label: 'AI 评测',
    buBound: true,
    defaultPath: '/eval',
    items: [
      { to: '/eval',            label: '评测',       icon: Gauge, end: true },
      { to: '/eval/history',    label: '历史评测',   icon: History },
      { to: '/eval/categories', label: '业务分类',   icon: Tags },
      { to: '/eval/activity',   label: '活动标问',   icon: Filter },
      { to: '/eval/rules',      label: '短路规则',   icon: Zap },
      { to: '/eval/prompts',    label: '提示词管理', icon: FileText },
      { to: '/eval/insights',   label: '问题洞察',   icon: Lightbulb },
    ],
  },
  {
    key: 'admin',
    label: '系统管理',
    adminOnly: true,
    defaultPath: '/datasets',
    items: [
      { to: '/datasets',  label: '数据集管理', icon: FolderOpen },
      { to: '/users',     label: '用户管理',   icon: Users },
      { to: '/roles',     label: '角色权限',   icon: ShieldCheck },
      { to: '/admin-sql', label: 'SQL 工具',   icon: Terminal },
    ],
  },
]

// 当前路径命中哪个子系统。最长前缀匹配，避免 /eval 命中 / 之类的误伤。
function subsystemOfPath(pathname) {
  let best = null
  for (const sys of subsystems) {
    for (const it of sys.items) {
      if (pathname === it.to || pathname.startsWith(it.to + '/')) {
        if (!best || it.to.length > best._to.length) best = { sys, _to: it.to }
      }
    }
  }
  return best?.sys || subsystems[0]
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

// ── 顶栏上下文选择器（数据集 / BU 共用一个槽位，样式统一）────────────────────────

function ContextPicker({ label, current, currentLabel, items, onPick, renderMeta }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    function onClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-2 h-9 pl-3 pr-2 rounded-md border border-gray-200 bg-white hover:bg-gray-50 transition-colors"
      >
        <span className="text-[11px] text-gray-400 hidden sm:inline">{label}</span>
        <span className="text-sm font-medium text-gray-700 max-w-[160px] truncate">
          {currentLabel || current || '—'}
        </span>
        <ChevronDown className={cn('w-4 h-4 text-gray-400 transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1.5 z-50 w-64 max-h-72 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg py-1">
          {items.length === 0 && (
            <div className="px-3 py-6 text-center text-xs text-gray-400">暂无数据</div>
          )}
          {items.map(it => (
            <button
              key={it.value}
              onClick={() => { onPick(it.value); setOpen(false) }}
              className="w-full flex items-start gap-2 px-3 py-2 text-left hover:bg-gray-50 transition-colors"
            >
              <Check className={cn('w-4 h-4 mt-0.5 shrink-0', it.value === current ? 'text-indigo-600' : 'text-transparent')} />
              <div className="min-w-0 flex-1">
                <div className={cn('text-sm truncate', it.value === current ? 'font-medium text-indigo-600' : 'text-gray-700')}>
                  {it.name}
                </div>
                {renderMeta?.(it) && (
                  <div className="text-xs text-gray-400 truncate">{renderMeta(it)}</div>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── 主布局 ─────────────────────────────────────────────────────────────────────

export default function Layout() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const location = useLocation()
  const username = localStorage.getItem('username') || 'admin'
  const roles    = JSON.parse(localStorage.getItem('roles') || '[]')
  const isAdmin  = roles.includes('admin')

  const activeSys = subsystemOfPath(location.pathname)
  const visibleSystems = subsystems.filter(s => !s.adminOnly || isAdmin)

  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem('sidebar-collapsed') === 'true'
  )
  const [changePwdOpen, setChangePwdOpen] = useState(false)
  const [userMenuOpen, setUserMenuOpen]   = useState(false)
  const userMenuRef = useRef(null)

  const [datasets, setDatasets]             = useState([])
  const [currentDataset, setCurrentDataset] = useState(getCurrentDatasetId())

  const [bus, setBus]                  = useState([])
  const [currentBu, setCurrentBuState] = useState(getCurrentBu())

  useEffect(() => {
    evalApi.bus()
      .then(res => {
        const list = res.data?.data?.bus || []
        setBus(list)
        if (list.length && !list.find(b => b.code === currentBu)) switchBu(list[0].code)
      })
      .catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    datasetApi.list()
      .then(res => {
        const list = res.data?.data || []
        setDatasets(list)
        if (list.length === 0) return
        const valid = list.find(d => d.id === currentDataset)
        if (!valid) switchDataset(list[0].id)
        else window.dispatchEvent(new CustomEvent('datasetChanged', { detail: { datasetId: currentDataset } }))
      })
      .catch(() => {})
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    function handleClickOutside(e) {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target)) setUserMenuOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  function switchDataset(id) {
    setCurrentDataset(id)
    setCurrentDatasetId(id)
    window.dispatchEvent(new CustomEvent('datasetChanged', { detail: { datasetId: id } }))
    qc.invalidateQueries()
  }

  function switchBu(code) {
    setCurrentBuState(code)
    setCurrentBu(code)
    window.dispatchEvent(new CustomEvent('buChanged', { detail: { bu: code } }))
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
  const sidebarItems = activeSys.items.filter(it => !it.adminOnly || isAdmin)

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* ── 顶栏（一级）─────────────────────────────────────────────── */}
      <header className="h-14 shrink-0 flex items-center gap-6 pl-4 pr-3 bg-white border-b border-gray-200">
        {/* 品牌 */}
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="w-7 h-7 rounded-md bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center text-white font-bold text-xs">
            D
          </div>
          <span className="font-semibold text-[15px] text-gray-900 tracking-tight">Datapulse</span>
        </div>

        {/* 一级切换 */}
        <nav className="flex items-center gap-1 h-full">
          {visibleSystems.map(sys => {
            const active = sys.key === activeSys.key
            return (
              <button
                key={sys.key}
                onClick={() => navigate(sys.defaultPath)}
                className={cn(
                  'relative h-full px-3.5 text-sm font-medium whitespace-nowrap transition-colors',
                  active ? 'text-gray-900' : 'text-gray-500 hover:text-gray-800'
                )}
              >
                {sys.label}
                {active && (
                  <span className="absolute inset-x-2.5 -bottom-px h-0.5 rounded-full bg-indigo-600" />
                )}
              </button>
            )
          })}
        </nav>

        <div className="flex-1" />

        {/* 上下文选择器（随子系统切换）+ 用户区 */}
        <div className="flex items-center gap-2 shrink-0">
          {activeSys.datasetBound && (
            <ContextPicker
              label="数据集"
              current={currentDataset}
              currentLabel={currentDs?.name}
              items={datasets.map(d => ({ value: d.id, name: d.name, description: d.description }))}
              onPick={switchDataset}
              renderMeta={it => it.description}
            />
          )}
          {activeSys.buBound && (
            <ContextPicker
              label="业务单元"
              current={currentBu}
              currentLabel={bus.find(b => b.code === currentBu)?.name}
              items={bus.map(b => ({ value: b.code, name: b.name, intent_count: b.intent_count }))}
              onPick={switchBu}
              renderMeta={it => `${it.intent_count} 个业务分类`}
            />
          )}

          <a
            href="/docs" target="_blank" rel="noopener noreferrer"
            title="使用文档"
            className="w-9 h-9 flex items-center justify-center rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
          >
            <BookOpen className="w-[18px] h-[18px]" />
          </a>

          {/* 用户菜单 */}
          <div className="relative" ref={userMenuRef}>
            <button
              onClick={() => setUserMenuOpen(v => !v)}
              className="flex items-center gap-2 h-9 pl-1 pr-2 rounded-md hover:bg-gray-100 transition-colors"
            >
              <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-400 to-violet-500 flex items-center justify-center text-xs font-semibold text-white">
                {username[0]?.toUpperCase()}
              </div>
              <span className="text-sm text-gray-700 max-w-[100px] truncate hidden sm:inline">{username}</span>
              <ChevronDown className={cn('w-4 h-4 text-gray-400 transition-transform', userMenuOpen && 'rotate-180')} />
            </button>
            {userMenuOpen && (
              <div className="absolute right-0 top-full mt-1.5 z-50 w-48 rounded-lg border border-gray-200 bg-white shadow-lg overflow-hidden">
                <div className="px-3 py-2.5 border-b border-gray-100">
                  <div className="text-sm font-medium text-gray-900 truncate">{username}</div>
                  <div className="text-xs text-gray-400">{isAdmin ? '管理员' : roles[0] || '用户'}</div>
                </div>
                <button
                  onClick={() => { setUserMenuOpen(false); setChangePwdOpen(true) }}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
                >
                  <KeyRound className="w-4 h-4 text-gray-400" />
                  修改密码
                </button>
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
                >
                  <LogOut className="w-4 h-4 text-gray-400" />
                  退出登录
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* ── 侧栏（当前子系统）+ 内容 ────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">
        <aside
          className={cn(
            'shrink-0 flex flex-col bg-white border-r border-gray-200',
            collapsed ? 'w-14' : 'w-52'
          )}
        >
          {/* 标题行：展开时显子系统名，折叠时仅居中放折叠按钮 */}
          <div className={cn('flex items-center py-2.5', collapsed ? 'justify-center px-0' : 'justify-between pl-3 pr-1.5')}>
            {!collapsed && (
              <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">
                {activeSys.label}
              </span>
            )}
            <button
              onClick={toggleSidebar}
              title={collapsed ? '展开侧栏' : '收起侧栏'}
              className="w-7 h-7 flex items-center justify-center rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
            >
              {collapsed
                ? <PanelLeftOpen className="w-[18px] h-[18px]" />
                : <PanelLeftClose className="w-[18px] h-[18px]" />}
            </button>
          </div>

          {/* 导航：折叠态为图标 rail（保留全部入口 + hover 提示），展开态图标+文字 */}
          <nav className="flex-1 px-2 pb-3 space-y-0.5 overflow-y-auto">
            {sidebarItems.map(({ to, label, end, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                title={collapsed ? label : undefined}
                className={({ isActive }) =>
                  cn(
                    'group relative flex items-center h-9 rounded-md text-sm transition-colors',
                    collapsed ? 'justify-center' : 'px-3 gap-2.5',
                    isActive
                      ? 'bg-indigo-50 text-indigo-700 font-medium'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-indigo-600" />}
                    {Icon && <Icon className="w-[18px] h-[18px] shrink-0" />}
                    {!collapsed && label}
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </aside>

        <main className="flex-1 min-w-0 overflow-y-auto">
          <Outlet />
        </main>
      </div>

      <ChangePasswordDialog open={changePwdOpen} onClose={() => setChangePwdOpen(false)} />
    </div>
  )
}
