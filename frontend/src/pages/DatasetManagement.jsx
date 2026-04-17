/**
 * DatasetManagement — 数据集管理页（仅 admin）
 *
 * 功能：
 *   - 数据集 CRUD + 分页
 *   - 为每个数据集分配可访问的用户（多选）
 */

import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Plus, Pencil, Trash2, Users, FolderOpen, Search, X } from 'lucide-react'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import TablePagination from '@/components/TablePagination'
import { datasetApi, userApi } from '@/lib/api'
import { formatDate } from '@/lib/utils'

// ── 新建/编辑数据集弹窗 ────────────────────────────────────────────────────────

function DatasetFormDialog({ open, onClose, onSave, dataset }) {
  const isEdit = !!dataset
  const [name, setName]         = useState(dataset?.name || '')
  const [desc, setDesc]         = useState(dataset?.description || '')
  const [active, setActive]     = useState(dataset?.status !== 'inactive')
  const [loading, setLoading]   = useState(false)

  useEffect(() => {
    if (open) {
      setName(dataset?.name || '')
      setDesc(dataset?.description || '')
      setActive(dataset?.status !== 'inactive')
    }
  }, [open, dataset])

  async function handleSave() {
    if (!name.trim()) { toast.error('数据集名称不能为空'); return }
    setLoading(true)
    try {
      await onSave({ name: name.trim(), description: desc.trim(), is_active: active }, dataset?.id)
      onClose()
    } catch (err) {
      toast.error(err.response?.data?.detail || '操作失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-md">
        <h2 className="text-lg font-semibold mb-4">{isEdit ? '编辑数据集' : '新建数据集'}</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">名称</label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="数据集名称" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">描述</label>
            <Input value={desc} onChange={e => setDesc(e.target.value)} placeholder="可选，简要说明" />
          </div>
          {isEdit && (
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-gray-700">状态</label>
              <button
                type="button"
                onClick={() => setActive(v => !v)}
                className={`relative inline-flex h-5 w-9 rounded-full transition-colors ${active ? 'bg-blue-500' : 'bg-gray-300'}`}
              >
                <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform mt-0.5 ${active ? 'translate-x-4' : 'translate-x-0.5'}`} />
              </button>
              <span className="text-sm text-gray-500">{active ? '活跃' : '停用'}</span>
            </div>
          )}
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="outline" onClick={onClose} disabled={loading}>取消</Button>
          <Button onClick={handleSave} disabled={loading}>{isEdit ? '保存' : '创建'}</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ── 用户分配弹窗 ───────────────────────────────────────────────────────────────

function AssignUsersDialog({ open, onClose, dataset, allUsers }) {
  const qc = useQueryClient()

  // 获取当前已分配的用户
  const { data: assignedData } = useQuery({
    queryKey: ['dataset-users', dataset?.id],
    queryFn: () => datasetApi.getUsers(dataset.id),
    enabled: open && !!dataset?.id,
  })
  const assigned = assignedData?.data?.data || []

  const [selected, setSelected] = useState([])
  const [loading, setLoading]   = useState(false)

  // 每次弹窗打开或已分配列表加载完成后同步
  useEffect(() => {
    if (open) setSelected(assigned)
  }, [open, assigned.join(',')]) // eslint-disable-line react-hooks/exhaustive-deps

  function toggle(username) {
    setSelected(prev =>
      prev.includes(username)
        ? prev.filter(u => u !== username)
        : [...prev, username]
    )
  }

  async function handleSave() {
    setLoading(true)
    try {
      await datasetApi.assignUsers(dataset.id, selected)
      toast.success('分配成功')
      qc.invalidateQueries(['dataset-users', dataset.id])
      onClose()
    } catch (err) {
      toast.error(err.response?.data?.detail || '分配失败')
    } finally {
      setLoading(false)
    }
  }

  // non-admin users
  const eligibleUsers = allUsers.filter(u => !u.roles?.includes('admin'))

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="max-w-sm">
        <h2 className="text-base font-semibold mb-1">分配用户</h2>
        <p className="text-xs text-gray-500 mb-3">数据集：<strong>{dataset?.name}</strong>（admin 无需分配，可访问全部）</p>
        <div className="border rounded-lg max-h-52 overflow-y-auto divide-y">
          {eligibleUsers.length === 0 && (
            <div className="px-3 py-4 text-xs text-gray-400 text-center">暂无普通用户</div>
          )}
          {eligibleUsers.map(u => (
            <label key={u.id} className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-gray-50">
              <input
                type="checkbox"
                checked={selected.includes(u.username)}
                onChange={() => toggle(u.username)}
                className="w-4 h-4 rounded"
              />
              <div>
                <div className="text-sm font-medium">{u.username}</div>
                <div className="text-xs text-gray-400">{u.roles?.join(', ')}</div>
              </div>
            </label>
          ))}
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="outline" onClick={onClose} disabled={loading}>取消</Button>
          <Button onClick={handleSave} disabled={loading}>保存分配</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ── 主页面 ─────────────────────────────────────────────────────────────────────

export default function DatasetManagement() {
  const qc = useQueryClient()
  const [page, setPage]     = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [keyword, setKeyword]   = useState('')
  const [keywordInput, setKeywordInput] = useState('')

  const [formOpen, setFormOpen]     = useState(false)
  const [editDs, setEditDs]         = useState(null)
  const [assignOpen, setAssignOpen] = useState(false)
  const [assignDs, setAssignDs]     = useState(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [deleteDs, setDeleteDs]     = useState(null)

  // 获取全部数据集（含 inactive），admin only
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['all-datasets'],
    queryFn: () => datasetApi.listAll(),
  })
  const allDatasets = data?.data?.data || []

  // 客户端搜索 + 分页
  const filtered   = keyword
    ? allDatasets.filter(ds =>
        ds.name.toLowerCase().includes(keyword.toLowerCase()) ||
        (ds.description || '').toLowerCase().includes(keyword.toLowerCase())
      )
    : allDatasets
  const total      = filtered.length
  const paginated  = filtered.slice((page - 1) * pageSize, page * pageSize)

  // 获取全部用户（用于分配弹窗）
  const { data: usersData } = useQuery({
    queryKey: ['all-users'],
    queryFn: () => userApi.list(),
  })
  const allUsers = usersData?.data?.data?.list || []

  async function handleSave(form, dsId) {
    if (dsId) {
      await datasetApi.update(dsId, { name: form.name, description: form.description, is_active: form.is_active })
      toast.success('数据集已更新')
    } else {
      await datasetApi.create({ name: form.name, description: form.description })
      toast.success('数据集已创建')
    }
    setFormOpen(false)
    setEditDs(null)
    await refetch()
    qc.invalidateQueries(['all-datasets'])
  }

  async function handleDelete() {
    if (!deleteDs) return
    try {
      await datasetApi.delete(deleteDs.id)
      toast.success('已删除')
      // 立即刷新 + invalidate 双保险
      await refetch()
      qc.invalidateQueries(['all-datasets'])
    } catch (err) {
      toast.error(err.response?.data?.detail || '删除失败')
    } finally {
      setDeleteDs(null)
      setConfirmOpen(false)
    }
  }

  function openEdit(ds) { setEditDs(ds); setFormOpen(true) }
  function openAssign(ds) { setAssignDs(ds); setAssignOpen(true) }
  function requestDelete(ds) { setDeleteDs(ds); setConfirmOpen(true) }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">数据集管理</h1>
          <p className="text-sm text-gray-500 mt-0.5">创建和管理数据集，并为用户分配访问权限</p>
        </div>
        <Button onClick={() => { setEditDs(null); setFormOpen(true) }}>
          <Plus className="w-4 h-4 mr-2" />
          新建数据集
        </Button>
      </div>

      {/* Search bar */}
      <div className="mb-4">
        <form
          onSubmit={e => { e.preventDefault(); setKeyword(keywordInput); setPage(1) }}
          className="flex gap-2 max-w-sm"
        >
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
            <Input
              value={keywordInput}
              onChange={e => {
                setKeywordInput(e.target.value)
                if (e.target.value === '') { setKeyword(''); setPage(1) }
              }}
              placeholder="搜索数据集名称或描述..."
              className="pl-8 pr-8 h-9 text-sm"
            />
            {keywordInput && (
              <button
                type="button"
                onClick={() => { setKeywordInput(''); setKeyword(''); setPage(1) }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
          <Button type="submit" variant="outline" size="sm" className="h-9">搜索</Button>
        </form>
      </div>

      {/* 表格 */}
      <div className="bg-white border rounded-lg overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-16 text-gray-400 text-sm">加载中…</div>
        ) : allDatasets.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <FolderOpen className="w-10 h-10 mb-2 opacity-30" />
            <div className="text-sm">暂无数据集</div>
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">ID</TableHead>
                  <TableHead>名称</TableHead>
                  <TableHead>描述</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead className="w-40 whitespace-nowrap">创建时间</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paginated.map(ds => (
                  <TableRow key={ds.id}>
                    <TableCell className="text-xs text-muted-foreground">{ds.id}</TableCell>
                    <TableCell className="font-medium">{ds.name}</TableCell>
                    <TableCell className="text-sm text-gray-500 max-w-xs truncate">
                      {ds.description || '—'}
                    </TableCell>
                    <TableCell>
                      {ds.status === 'active'
                        ? <Badge className="bg-green-100 text-green-700 border-0">活跃</Badge>
                        : <Badge className="bg-gray-100 text-gray-500 border-0">停用</Badge>
                      }
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      {formatDate(ds.created_at)}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={() => openAssign(ds)}
                          className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-blue-600 transition-colors"
                          title="分配用户"
                        >
                          <Users className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => openEdit(ds)}
                          className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-700 transition-colors"
                          title="编辑"
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => requestDelete(ds)}
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
            <TablePagination
              page={page}
              pageSize={pageSize}
              total={total}
              onPageChange={setPage}
              onSizeChange={size => { setPageSize(size); setPage(1) }}
            />
          </>
        )}
      </div>

      {/* 弹窗 */}
      <DatasetFormDialog
        open={formOpen}
        onClose={() => { setFormOpen(false); setEditDs(null) }}
        onSave={handleSave}
        dataset={editDs}
      />
      <AssignUsersDialog
        open={assignOpen}
        onClose={() => { setAssignOpen(false); setAssignDs(null) }}
        dataset={assignDs}
        allUsers={allUsers}
      />
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="确认删除"
        description={`确认删除数据集 "${deleteDs?.name}"？此操作将级联删除所有关联数据，不可恢复。`}
        confirmLabel="删除"
        cancelLabel="取消"
        onConfirm={handleDelete}
      />
    </div>
  )
}
