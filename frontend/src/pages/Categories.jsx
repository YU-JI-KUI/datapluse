/**
 * 业务分类管理页
 *
 * - 分页列表 + keyword 搜索
 * - 多选 checkbox + 批量删除工具栏
 * - 单条新建 / 编辑 / 删除
 * - Excel 上传弹窗（拖拽 / 点击，格式说明）
 */

import { useState, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Plus, Pencil, Trash2, Upload, Search, Tags,
  FileSpreadsheet, X, CheckCircle2, AlertCircle,
} from 'lucide-react'

import { categoryApi, getCurrentDatasetId } from '@/lib/api'
import { Button }        from '@/components/ui/button'
import { Input }         from '@/components/ui/input'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import TablePagination from '@/components/TablePagination'

// ── 编辑 / 新建 对话框 ────────────────────────────────────────────────────────

function CategoryDialog({ open, onOpenChange, initial, onSave }) {
  const [name, setName]     = useState(initial?.name        ?? '')
  const [desc, setDesc]     = useState(initial?.description ?? '')
  const [saving, setSaving] = useState(false)

  const handleOpen = (v) => {
    if (v) {
      setName(initial?.name        ?? '')
      setDesc(initial?.description ?? '')
    }
    onOpenChange(v)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!name.trim()) { toast.error('分类名称不能为空'); return }
    setSaving(true)
    try {
      await onSave({ name: name.trim(), description: desc.trim() })
      onOpenChange(false)
    } catch {
      // error handled upstream
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpen}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{initial ? '编辑业务分类' : '新建业务分类'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">
              分类名称 <span className="text-destructive">*</span>
            </label>
            <Input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="请输入分类名称"
              autoFocus
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">业务介绍</label>
            <textarea
              value={desc}
              onChange={e => setDesc(e.target.value)}
              placeholder="请输入业务介绍（可多行）"
              rows={6}
              className={[
                'w-full rounded-md border border-input bg-background px-3 py-2',
                'text-sm ring-offset-background resize-y',
                'placeholder:text-muted-foreground',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
              ].join(' ')}
            />
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <Button type="button" variant="secondary" size="sm"
              onClick={() => onOpenChange(false)} disabled={saving}>
              取消
            </Button>
            <Button type="submit" size="sm" disabled={saving}>
              {saving ? '保存中…' : '保存'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ── Excel 上传弹窗 ─────────────────────────────────────────────────────────────

function UploadDialog({ open, onOpenChange, onUpload }) {
  const fileRef                   = useRef(null)
  const [dragging,  setDragging]  = useState(false)
  const [file,      setFile]      = useState(null)
  const [result,    setResult]    = useState(null)
  const [error,     setError]     = useState(null)
  const [loading,   setLoading]   = useState(false)

  const reset = () => { setFile(null); setResult(null); setError(null) }

  const handleClose = (v) => { if (!v) reset(); onOpenChange(v) }

  const pickFile = (f) => {
    if (!f) return
    if (!/\.(xlsx|xls)$/i.test(f.name)) { toast.error('仅支持 .xlsx / .xls 格式'); return }
    setFile(f); setResult(null); setError(null)
  }

  const handleInputChange = (e) => { pickFile(e.target.files?.[0]); e.target.value = '' }

  const handleDrop = useCallback((e) => {
    e.preventDefault(); setDragging(false); pickFile(e.dataTransfer.files?.[0])
  }, [])

  const handleDragOver  = (e) => { e.preventDefault(); setDragging(true) }
  const handleDragLeave = ()  => setDragging(false)

  const handleUpload = async () => {
    if (!file) return
    setLoading(true); setError(null)
    try {
      const res  = await onUpload(file)
      setResult(res.data?.data ?? {}); setFile(null)
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Excel 导入失败，请检查文件格式')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Excel 批量导入业务分类</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 pt-1">
          {/* 格式说明 */}
          <div className="rounded-lg bg-muted/50 border border-border px-4 py-3 space-y-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">文件格式要求</p>
            <p className="text-sm text-foreground">
              Excel 文件（<code className="text-xs bg-muted rounded px-1">.xlsx</code> 或{' '}
              <code className="text-xs bg-muted rounded px-1">.xls</code>），
              第一行为表头，支持以下列名：
            </p>
            <div className="grid grid-cols-2 gap-2 pt-0.5">
              <div className="rounded-md border border-border bg-background px-3 py-2">
                <p className="text-xs text-muted-foreground mb-0.5">分类名称（必填）</p>
                <p className="text-sm font-mono font-medium">业务名</p>
                <p className="text-xs text-muted-foreground mt-0.5">也可写 <span className="font-mono">name</span></p>
              </div>
              <div className="rounded-md border border-border bg-background px-3 py-2">
                <p className="text-xs text-muted-foreground mb-0.5">业务介绍（可选）</p>
                <p className="text-sm font-mono font-medium">业务介绍</p>
                <p className="text-xs text-muted-foreground mt-0.5">也可写 <span className="font-mono">description</span></p>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">同名分类自动跳过，不会重复写入。</p>
          </div>

          {/* 拖拽 / 点击区 */}
          {!result && (
            <div
              onClick={() => fileRef.current?.click()}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              className={[
                'relative flex flex-col items-center justify-center gap-3',
                'rounded-lg border-2 border-dashed px-6 py-10 cursor-pointer',
                'transition-colors select-none',
                dragging
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/50 hover:bg-muted/30',
              ].join(' ')}
            >
              <input ref={fileRef} type="file" accept=".xlsx,.xls"
                className="hidden" onChange={handleInputChange} />
              <FileSpreadsheet className={`w-10 h-10 ${dragging ? 'text-primary' : 'text-muted-foreground/50'}`} />
              {file ? (
                <div className="flex items-center gap-2 text-sm font-medium">
                  <span className="max-w-[260px] truncate">{file.name}</span>
                  <button type="button"
                    className="text-muted-foreground hover:text-foreground"
                    onClick={(e) => { e.stopPropagation(); reset() }}>
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <>
                  <p className="text-sm font-medium">
                    {dragging ? '松开以选择文件' : '拖拽文件到此处，或点击选择'}
                  </p>
                  <p className="text-xs text-muted-foreground">支持 .xlsx / .xls 格式</p>
                </>
              )}
            </div>
          )}

          {/* 导入结果 */}
          {result && (
            <div className="rounded-lg border border-green-200 bg-green-50 dark:bg-green-950/30 dark:border-green-800 px-4 py-4 space-y-2">
              <div className="flex items-center gap-2 text-green-700 dark:text-green-400">
                <CheckCircle2 className="w-5 h-5 shrink-0" />
                <span className="text-sm font-medium">导入成功</span>
              </div>
              <div className="grid grid-cols-3 gap-3 pt-1">
                {[
                  { label: '总行数', value: result.total_rows ?? 0 },
                  { label: '新增',   value: result.created   ?? 0, accent: true },
                  { label: '跳过',   value: result.skipped   ?? 0 },
                ].map(({ label, value, accent }) => (
                  <div key={label} className="rounded-md bg-white dark:bg-background border border-border px-3 py-2 text-center">
                    <p className={`text-lg font-semibold ${accent ? 'text-green-600 dark:text-green-400' : ''}`}>{value}</p>
                    <p className="text-xs text-muted-foreground">{label}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 错误提示 */}
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* 操作按钮 */}
          <div className="flex justify-end gap-3 pt-1">
            {result ? (
              <>
                <Button variant="outline" size="sm" onClick={reset}>继续导入</Button>
                <Button size="sm" onClick={() => handleClose(false)}>完成</Button>
              </>
            ) : (
              <>
                <Button variant="secondary" size="sm" onClick={() => handleClose(false)}>取消</Button>
                <Button size="sm" disabled={!file || loading} onClick={handleUpload}>
                  <Upload className="w-4 h-4 mr-1.5" />
                  {loading ? '导入中…' : '开始导入'}
                </Button>
              </>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

export default function Categories() {
  const qc        = useQueryClient()
  const datasetId = getCurrentDatasetId()

  // 列表 & 分页
  const [page,     setPage]     = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [keyword,  setKeyword]  = useState('')
  const [search,   setSearch]   = useState('')

  // 多选
  const [selected,  setSelected]  = useState(new Set())   // Set<id>

  // 对话框
  const [dialogOpen,    setDialogOpen]    = useState(false)
  const [editTarget,    setEditTarget]    = useState(null)
  const [deleteTarget,  setDeleteTarget]  = useState(null)   // { id, name } 单条删除
  const [bulkDelOpen,   setBulkDelOpen]   = useState(false)
  const [uploadOpen,    setUploadOpen]    = useState(false)

  // ── 查询 ──────────────────────────────────────────────────────────────────

  const { data, isLoading } = useQuery({
    queryKey: ['categories', datasetId, page, pageSize, search],
    queryFn: async () => {
      const res = await categoryApi.list(
        { page, page_size: pageSize, ...(search ? { keyword: search } : {}) },
        datasetId,
      )
      return res.data?.data ?? { list: [], pagination: { total: 0 } }
    },
    enabled: !!datasetId,
  })

  const list  = data?.list              ?? []
  const total = data?.pagination?.total ?? 0

  // ── 写操作 ────────────────────────────────────────────────────────────────

  const invalidate = () => { qc.invalidateQueries({ queryKey: ['categories'] }); setSelected(new Set()) }

  const createMut = useMutation({
    mutationFn: (body) => categoryApi.create(body, datasetId),
    onSuccess: () => { toast.success('创建成功'); invalidate() },
    onError:   (e)  => toast.error(e.response?.data?.detail ?? '创建失败'),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, body }) => categoryApi.update(id, body),
    onSuccess: () => { toast.success('更新成功'); invalidate() },
    onError:   (e)  => toast.error(e.response?.data?.detail ?? '更新失败'),
  })

  const deleteMut = useMutation({
    mutationFn: (id)  => categoryApi.delete(id),
    onSuccess: () => { toast.success('删除成功'); invalidate() },
    onError:   (e)    => toast.error(e.response?.data?.detail ?? '删除失败'),
  })

  const bulkDeleteMut = useMutation({
    mutationFn: (ids) => categoryApi.bulkDelete(ids),
    onSuccess: (res) => {
      const cnt = res.data?.data?.deleted ?? selected.size
      toast.success(`已删除 ${cnt} 条`)
      invalidate()
    },
    onError: (e) => toast.error(e.response?.data?.detail ?? '批量删除失败'),
  })

  // ── 操作处理 ──────────────────────────────────────────────────────────────

  const handleSave = async (body) => {
    if (editTarget) await updateMut.mutateAsync({ id: editTarget.id, body })
    else            await createMut.mutateAsync(body)
  }

  const openCreate = () => { setEditTarget(null); setDialogOpen(true) }
  const openEdit   = (row) => { setEditTarget(row); setDialogOpen(true) }

  const handleSearch = () => { setSearch(keyword); setPage(1) }
  const handleKeyDown = (e) => { if (e.key === 'Enter') handleSearch() }

  const handleUpload = (file) => {
    const res = categoryApi.upload(file, datasetId)
    res.then(() => invalidate())
    return res
  }

  // ── 多选逻辑 ──────────────────────────────────────────────────────────────

  const allIds      = list.map(r => r.id)
  const allChecked  = allIds.length > 0 && allIds.every(id => selected.has(id))
  const someChecked = allIds.some(id => selected.has(id)) && !allChecked

  const toggleAll = () => {
    if (allChecked) {
      setSelected(prev => { const s = new Set(prev); allIds.forEach(id => s.delete(id)); return s })
    } else {
      setSelected(prev => new Set([...prev, ...allIds]))
    }
  }

  const toggleOne = (id) => {
    setSelected(prev => {
      const s = new Set(prev)
      s.has(id) ? s.delete(id) : s.add(id)
      return s
    })
  }

  // ── 渲染 ──────────────────────────────────────────────────────────────────

  if (!datasetId) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-muted-foreground gap-3">
        <Tags className="w-10 h-10 opacity-30" />
        <p>请先在顶部选择一个数据集</p>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-5">
      {/* 页面标题 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">业务分类</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            管理当前数据集的业务分类，用于意图识别标签体系
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setUploadOpen(true)}>
            <Upload className="w-4 h-4 mr-1.5" />
            Excel 导入
          </Button>
          <Button size="sm" onClick={openCreate}>
            <Plus className="w-4 h-4 mr-1.5" />
            新建分类
          </Button>
        </div>
      </div>

      {/* 搜索栏 */}
      <div className="flex items-center gap-2 max-w-sm">
        <Input
          placeholder="搜索分类名称…"
          value={keyword}
          onChange={e => setKeyword(e.target.value)}
          onKeyDown={handleKeyDown}
          className="h-8 text-sm"
        />
        <Button variant="outline" size="sm" className="h-8 px-3" onClick={handleSearch}>
          <Search className="w-3.5 h-3.5" />
        </Button>
      </div>

      {/* 批量操作工具栏 */}
      {selected.size > 0 && (
        <div className="flex items-center gap-3 px-4 py-2.5 rounded-lg border border-primary/30 bg-primary/5 text-sm">
          <span className="text-primary font-medium">已选 {selected.size} 条</span>
          <div className="flex-1" />
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs"
            onClick={() => setSelected(new Set())}
          >
            取消选择
          </Button>
          <Button
            variant="destructive"
            size="sm"
            className="h-7 text-xs"
            onClick={() => setBulkDelOpen(true)}
          >
            <Trash2 className="w-3.5 h-3.5 mr-1" />
            批量删除
          </Button>
        </div>
      )}

      {/* 表格 */}
      <div className="border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10 text-center px-2">
                <input
                  type="checkbox"
                  checked={allChecked}
                  ref={el => { if (el) el.indeterminate = someChecked }}
                  onChange={toggleAll}
                  className="cursor-pointer rounded"
                />
              </TableHead>
              <TableHead className="w-10 text-center text-xs text-muted-foreground">#</TableHead>
              <TableHead className="w-48">分类名称</TableHead>
              <TableHead>业务介绍</TableHead>
              <TableHead className="w-32 whitespace-nowrap">创建人</TableHead>
              <TableHead className="w-40 whitespace-nowrap">创建时间</TableHead>
              <TableHead className="w-20 text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-muted-foreground py-12">
                  加载中…
                </TableCell>
              </TableRow>
            ) : list.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-muted-foreground py-12">
                  暂无业务分类，点击右上角「新建分类」或「Excel 导入」添加
                </TableCell>
              </TableRow>
            ) : (
              list.map((row, idx) => {
                const checked = selected.has(row.id)
                return (
                  <TableRow
                    key={row.id}
                    className={checked ? 'bg-primary/5' : undefined}
                  >
                    <TableCell className="text-center px-2">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleOne(row.id)}
                        className="cursor-pointer rounded"
                      />
                    </TableCell>
                    <TableCell className="text-center text-xs text-muted-foreground">
                      {(page - 1) * pageSize + idx + 1}
                    </TableCell>
                    <TableCell className="font-medium">{row.name}</TableCell>
                    <TableCell>
                      {row.description ? (
                        <p className="text-sm text-muted-foreground whitespace-pre-wrap line-clamp-3 max-w-xl">
                          {row.description}
                        </p>
                      ) : (
                        <span className="text-xs text-muted-foreground/50">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
                      {row.created_by || '—'}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      {row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '—'}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0"
                          title="编辑" onClick={() => openEdit(row)}>
                          <Pencil className="w-3.5 h-3.5" />
                        </Button>
                        <Button variant="ghost" size="sm"
                          className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                          title="删除"
                          onClick={() => setDeleteTarget({ id: row.id, name: row.name })}>
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>

        <TablePagination
          page={page}
          pageSize={pageSize}
          total={total}
          onPageChange={setPage}
          onSizeChange={size => { setPageSize(size); setPage(1) }}
        />
      </div>

      {/* 新建 / 编辑对话框 */}
      <CategoryDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        initial={editTarget}
        onSave={handleSave}
      />

      {/* Excel 上传弹窗 */}
      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        onUpload={handleUpload}
      />

      {/* 单条删除确认 */}
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => { if (!v) setDeleteTarget(null) }}
        title="删除业务分类"
        description={`确认删除「${deleteTarget?.name}」？此操作不可撤销。`}
        confirmLabel="删除"
        onConfirm={() => deleteMut.mutateAsync(deleteTarget.id)}
      />

      {/* 批量删除确认 */}
      <ConfirmDialog
        open={bulkDelOpen}
        onOpenChange={setBulkDelOpen}
        title="批量删除业务分类"
        description={`确认删除已选的 ${selected.size} 条分类？此操作不可撤销。`}
        confirmLabel={`删除 ${selected.size} 条`}
        onConfirm={() => bulkDeleteMut.mutateAsync([...selected])}
      />
    </div>
  )
}
