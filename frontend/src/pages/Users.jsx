import { useState, useEffect } from 'react'
import { toast } from 'sonner'
import { Plus, Pencil, Trash2, KeyRound, Shield, User, Eye, EyeOff } from 'lucide-react'
import { userApi } from '@/lib/api'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Dialog, DialogContent } from '@/components/ui/dialog'

// ── 角色徽章样式 ──────────────────────────────────────────────────────────────

function RoleBadge({ role }) {
  const map = {
    admin:     'bg-red-100 text-red-700',
    annotator: 'bg-blue-100 text-blue-700',
    viewer:    'bg-gray-100 text-gray-600',
  }
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${map[role] || 'bg-gray-100 text-gray-600'}`}>
      {role === 'admin' && <Shield className="w-3 h-3" />}
      {role}
    </span>
  )
}

// ── 状态徽章 ──────────────────────────────────────────────────────────────────

function StatusBadge({ active }) {
  return active
    ? <Badge className="bg-green-100 text-green-700 border-0">启用</Badge>
    : <Badge className="bg-gray-100 text-gray-500 border-0">禁用</Badge>
}

// ── 用户表单弹窗 ───────────────────────────────────────────────────────────────

function UserFormDialog({ open, onClose, onSave, user, roles }) {
  const isEdit = !!user
  const [form, setForm] = useState({
    username: '',
    display_name: '',
    password: '',
    role_name: 'annotator',
    is_active: true,
  })
  const [showPwd, setShowPwd] = useState(false)

  useEffect(() => {
    if (user) {
      setForm({
        username:     user.username,
        display_name: user.display_name || '',
        password:     '',
        role_name:    user.roles?.[0] || 'annotator',
        is_active:    user.is_active !== false,
      })
    } else {
      setForm({ username: '', display_name: '', password: '', role_name: 'annotator', is_active: true })
    }
    setShowPwd(false)
  }, [user, open])

  function set(k, v) { setForm(f => ({ ...f, [k]: v })) }

  async function handleSave() {
    if (!form.username.trim()) { toast.error('用户名不能为空'); return }
    if (!isEdit && !form.password.trim()) { toast.error('新建用户必须设置密码'); return }
    await onSave(form, user?.id)
  }

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-md">
        <h2 className="text-lg font-semibold mb-4">{isEdit ? '编辑用户' : '新建用户'}</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">用户名</label>
            <Input
              value={form.username}
              onChange={e => set('username', e.target.value)}
              disabled={isEdit}
              placeholder="仅字母、数字、下划线"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">显示名称</label>
            <Input
              value={form.display_name}
              onChange={e => set('display_name', e.target.value)}
              placeholder="可选"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {isEdit ? '新密码（留空不修改）' : '密码'}
            </label>
            <div className="relative">
              <Input
                type={showPwd ? 'text' : 'password'}
                value={form.password}
                onChange={e => set('password', e.target.value)}
                placeholder={isEdit ? '留空则不修改密码' : '请输入密码'}
              />
              <button
                type="button"
                onClick={() => setShowPwd(v => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">角色</label>
            <select
              value={form.role_name}
              onChange={e => set('role_name', e.target.value)}
              className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
            >
              {roles.map(r => (
                <option key={r.name} value={r.name}>{r.name} — {r.description || ''}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium text-gray-700">账号状态</label>
            <button
              type="button"
              onClick={() => set('is_active', !form.is_active)}
              className={`relative inline-flex h-5 w-9 rounded-full transition-colors ${form.is_active ? 'bg-blue-500' : 'bg-gray-300'}`}
            >
              <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform mt-0.5 ${form.is_active ? 'translate-x-4' : 'translate-x-0.5'}`} />
            </button>
            <span className="text-sm text-gray-500">{form.is_active ? '启用' : '禁用'}</span>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button onClick={handleSave}>{isEdit ? '保存' : '创建'}</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ── 重置密码弹窗 ───────────────────────────────────────────────────────────────

function ResetPasswordDialog({ open, onClose, onSave, user }) {
  const [password, setPassword] = useState('')
  const [showPwd, setShowPwd]   = useState(false)

  useEffect(() => { setPassword(''); setShowPwd(false) }, [open])

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-sm">
        <h2 className="text-lg font-semibold mb-1">重置密码</h2>
        <p className="text-sm text-gray-500 mb-4">用户：<strong>{user?.username}</strong></p>
        <div className="relative">
          <Input
            type={showPwd ? 'text' : 'password'}
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="输入新密码"
          />
          <button
            type="button"
            onClick={() => setShowPwd(v => !v)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          >
            {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button
            onClick={() => { if (!password.trim()) { toast.error('密码不能为空'); return } onSave(user.id, password) }}
          >
            确认重置
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ── 主页面 ─────────────────────────────────────────────────────────────────────

export default function Users() {
  const [users, setUsers]         = useState([])
  const [roles, setRoles]         = useState([])
  const [loading, setLoading]     = useState(true)
  const [formOpen, setFormOpen]   = useState(false)
  const [editUser, setEditUser]   = useState(null)
  const [resetOpen, setResetOpen] = useState(false)
  const [resetUser, setResetUser] = useState(null)

  async function load() {
    try {
      const [ur, rr] = await Promise.all([userApi.list(), userApi.listRoles()])
      setUsers(ur.data || [])
      setRoles(rr.data || [])
    } catch {
      toast.error('加载用户列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function handleSave(form, userId) {
    try {
      const payload = {
        username:     form.username,
        display_name: form.display_name,
        role_name:    form.role_name,
        is_active:    form.is_active,
      }
      if (form.password) payload.password = form.password

      if (userId) {
        await userApi.update(userId, payload)
        toast.success('用户已更新')
      } else {
        await userApi.create(payload)
        toast.success('用户已创建')
      }
      setFormOpen(false)
      setEditUser(null)
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || '操作失败')
    }
  }

  async function handleDelete(user) {
    if (!confirm(`确认删除用户 "${user.username}"？此操作不可恢复。`)) return
    try {
      await userApi.delete(user.id)
      toast.success('已删除')
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || '删除失败')
    }
  }

  async function handleResetPassword(userId, password) {
    try {
      await userApi.resetPassword(userId, { new_password: password })
      toast.success('密码已重置')
      setResetOpen(false)
      setResetUser(null)
    } catch (err) {
      toast.error(err.response?.data?.detail || '重置失败')
    }
  }

  function openEdit(user) { setEditUser(user); setFormOpen(true) }
  function openReset(user) { setResetUser(user); setResetOpen(true) }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">用户管理</h1>
          <p className="text-sm text-gray-500 mt-0.5">管理系统账号与角色权限</p>
        </div>
        <Button onClick={() => { setEditUser(null); setFormOpen(true) }}>
          <Plus className="w-4 h-4 mr-2" />
          新建用户
        </Button>
      </div>

      {/* 角色说明卡片 */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        {roles.map(r => (
          <div key={r.name} className="bg-white border rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              <RoleBadge role={r.name} />
            </div>
            <div className="text-xs text-gray-500">{r.description || '—'}</div>
            <div className="text-xs text-gray-400 mt-1 truncate">
              权限：{Array.isArray(r.permissions) ? r.permissions.join(', ') : '—'}
            </div>
          </div>
        ))}
      </div>

      {/* 用户表格 */}
      <div className="bg-white border rounded-lg overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16 text-gray-400 text-sm">加载中…</div>
        ) : users.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <User className="w-10 h-10 mb-2 opacity-30" />
            <div className="text-sm">暂无用户</div>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>用户名</TableHead>
                <TableHead>显示名称</TableHead>
                <TableHead>角色</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>最后登录</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map(user => (
                <TableRow key={user.id}>
                  <TableCell className="font-medium">{user.username}</TableCell>
                  <TableCell className="text-gray-500">{user.display_name || '—'}</TableCell>
                  <TableCell>
                    <div className="flex gap-1 flex-wrap">
                      {(user.roles || []).map(r => <RoleBadge key={r} role={r} />)}
                    </div>
                  </TableCell>
                  <TableCell><StatusBadge active={user.is_active} /></TableCell>
                  <TableCell className="text-gray-400 text-sm">
                    {user.last_login ? new Date(user.last_login).toLocaleString('zh-CN') : '从未'}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => openReset(user)}
                        className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-700 transition-colors"
                        title="重置密码"
                      >
                        <KeyRound className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => openEdit(user)}
                        className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-700 transition-colors"
                        title="编辑"
                      >
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(user)}
                        className="p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-600 transition-colors"
                        title="删除"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      {/* 弹窗 */}
      <UserFormDialog
        open={formOpen}
        onClose={() => { setFormOpen(false); setEditUser(null) }}
        onSave={handleSave}
        user={editUser}
        roles={roles}
      />
      <ResetPasswordDialog
        open={resetOpen}
        onClose={() => { setResetOpen(false); setResetUser(null) }}
        onSave={handleResetPassword}
        user={resetUser}
      />
    </div>
  )
}
