import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  AlertTriangle, Play, RefreshCw, CheckCircle, Loader2,
  ShieldAlert, GitMerge, Users, Check, SearchCheck, Undo2, Search, X,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { conflictApi, dataApi, configApi, getCurrentDatasetId } from '@/lib/api'
import { formatDate } from '@/lib/utils'
import TablePagination from '@/components/TablePagination'

// ── 标签颜色（与 Annotation.jsx 保持一致）────────────────────────────────────
const LABEL_PALETTE = [
  'bg-blue-500 text-white', 'bg-violet-500 text-white', 'bg-green-500 text-white',
  'bg-orange-500 text-white', 'bg-rose-500 text-white', 'bg-teal-500 text-white',
]

function ConflictTypeBadge({ type }) {
  if (type === 'label_conflict') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
        <Users className="w-3 h-3" /> 标注分歧
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
      <GitMerge className="w-3 h-3" /> 语义相似
    </span>
  )
}

function ConflictStatusBadge({ status }) {
  if (status === 'resolved') return <Badge className="bg-green-100 text-green-700 border-0 text-xs whitespace-nowrap">已解决</Badge>
  if (status === 'revoked')  return <Badge className="bg-gray-100 text-gray-600 border-0 text-xs whitespace-nowrap">已撤销</Badge>
  return <Badge className="bg-red-100 text-red-700 border-0 text-xs whitespace-nowrap">待解决</Badge>
}

function ConflictDetail({ conflict }) {
  const detail = conflict.detail || {}
  if (conflict.conflict_type === 'label_conflict') {
    return (
      <div className="text-xs space-y-1">
        <div className="text-muted-foreground">标注人意见不一致：</div>
        <div className="flex flex-wrap gap-1">
          {(detail.annotators || []).map((a, i) => (
            <span key={i} className="bg-muted px-1.5 py-0.5 rounded font-mono">
              {a.username}: <span className="font-semibold text-foreground">{a.label}</span>
            </span>
          ))}
        </div>
      </div>
    )
  }
  return (
    <div className="text-xs space-y-1.5">
      <span className="text-muted-foreground">相似度: <span className="font-semibold text-foreground">{((detail.similarity || 0) * 100).toFixed(1)}%</span></span>
      <div className="space-y-1 mt-1">
        <div className="flex items-start gap-1.5">
          <span className="shrink-0 text-muted-foreground w-8 pt-0.5">本条</span>
          <span className="text-foreground truncate max-w-[160px]" title={conflict.data_content}>
            {conflict.data_content || '—'}
          </span>
          {detail.self_label && (
            <span className="shrink-0 px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 font-semibold whitespace-nowrap">{detail.self_label}</span>
          )}
        </div>
        <div className="flex items-start gap-1.5">
          <span className="shrink-0 text-muted-foreground w-8 pt-0.5">相似</span>
          <span className="text-foreground truncate max-w-[160px]" title={detail.paired_content}>
            {detail.paired_content || '—'}
          </span>
          {detail.paired_label && (
            <span className="shrink-0 px-1.5 py-0.5 rounded bg-orange-100 text-orange-700 font-semibold whitespace-nowrap">{detail.paired_label}</span>
          )}
        </div>
      </div>
    </div>
  )
}

// ── 解决冲突弹窗（单条 & 批量共用）─────────────────────────────────────────────
function ResolveDialog({ title, subtext, labels, open, onOpenChange, onSubmit, requireCot = false }) {
  const [selectedLabel, setSelectedLabel] = useState('')
  const [cot, setCot]                     = useState('')
  const [submitting, setSubmitting]       = useState(false)

  function handleClose() {
    setSelectedLabel('')
    setCot('')
    onOpenChange(false)
  }

  async function handleSubmit() {
    if (!selectedLabel) { toast.error('请选择最终标注标签'); return }
    setSubmitting(true)
    try {
      await onSubmit(selectedLabel, cot.trim() || null)
      handleClose()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-orange-500" />
            {title}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {subtext && (
            <div className="bg-muted/50 rounded-lg p-3 text-sm leading-relaxed border">
              {subtext}
            </div>
          )}

          <div>
            <p className="text-xs font-medium text-muted-foreground mb-2">选择最终标注（裁决结果）</p>
            <div className="flex flex-wrap gap-2">
              {labels.map((label, i) => {
                const isSelected = selectedLabel === label
                return (
                  <button
                    key={label}
                    onClick={() => setSelectedLabel(label)}
                    className={`
                      flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-semibold
                      transition-all duration-100 active:scale-95
                      ${isSelected
                        ? `${LABEL_PALETTE[i % LABEL_PALETTE.length]} ring-2 ring-offset-2 ring-current shadow-md`
                        : 'bg-muted text-foreground hover:bg-muted/80 border'
                      }
                    `}
                  >
                    {isSelected && <Check className="w-3.5 h-3.5" />}
                    {label}
                  </button>
                )
              })}
            </div>
            {!selectedLabel && (
              <p className="text-xs text-muted-foreground mt-2">请选择一个标签作为最终裁决结果</p>
            )}
          </div>

          {requireCot && (
            <div>
              <p className="text-xs font-medium mb-1.5">
                裁决理由 <span className="font-normal text-muted-foreground">（选填）</span>
              </p>
              <textarea
                value={cot}
                onChange={e => setCot(e.target.value)}
                placeholder="可填写裁决依据和推理过程（选填）"
                rows={2}
                className="w-full text-sm border rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-blue-200 border-gray-200 bg-white placeholder:text-muted-foreground/60"
              />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={submitting}>取消</Button>
          <Button onClick={handleSubmit} disabled={!selectedLabel || submitting}>
            {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            确认裁决
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── 主页面 ─────────────────────────────────────────────────────────────────────
export default function ConflictDetection() {
  const qc        = useQueryClient()
  const datasetId = getCurrentDatasetId()

  // ── 操作状态 ───────────────────────────────────────────────────────────────
  const [running, setRunning]           = useState(false)
  const [selfChecking, setSelfChecking] = useState(false)

  // ── 过滤 + 分页 ────────────────────────────────────────────────────────────
  const [statusFilter, setStatusFilter]   = useState('open')
  const [typeFilter, setTypeFilter]       = useState('all')
  const [keyword, setKeyword]             = useState('')
  const [keywordInput, setKeywordInput]   = useState('')
  const [page, setPage]                   = useState(1)
  const [pageSize, setPageSize]           = useState(10)

  // ── 多选 ───────────────────────────────────────────────────────────────────
  const [selected, setSelected] = useState(new Set())   // conflict_id Set

  // ── 弹窗 ───────────────────────────────────────────────────────────────────
  const [resolveTarget, setResolveTarget] = useState(null)   // 单条裁决
  const [resolveOpen, setResolveOpen]     = useState(false)
  const [batchResolveOpen, setBatchResolveOpen] = useState(false)

  // ── 数据查询 ───────────────────────────────────────────────────────────────
  const { data: annotatedData } = useQuery({
    queryKey: ['annotated-count'],
    queryFn:  () => dataApi.list({ status: 'annotated', page: 1, page_size: 1 }),
  })

  const { data: conflictRes, isLoading, refetch } = useQuery({
    queryKey: ['conflicts', datasetId, statusFilter, typeFilter, keyword, page, pageSize],
    queryFn:  () => conflictApi.list({
      status:        statusFilter === 'all' ? undefined : statusFilter,
      conflict_type: typeFilter   === 'all' ? undefined : typeFilter,
      keyword:       keyword || undefined,
      page,
      page_size: pageSize,
    }),
    refetchInterval: 8000,
  })

  const { data: configData } = useQuery({
    queryKey: ['config', datasetId],
    queryFn:  () => configApi.get(datasetId),
    enabled:  !!datasetId,
  })
  const configLabels = configData?.data?.data?.labels ?? configData?.data?.labels
  const labels    = configLabels || ['寿险意图', '拒识', '健康险意图', '财险意图', '其他意图']
  const requireCot = configData?.data?.data?.pipeline?.require_cot ?? false

  const annotatedCount = annotatedData?.data?.data?.pagination?.total || 0

  const pageResult = conflictRes?.data?.data ?? { list: [], pagination: { total: 0 } }
  const conflicts  = pageResult.list || []
  const total      = pageResult.pagination?.total || 0

  // ── 多选逻辑 ───────────────────────────────────────────────────────────────
  const openConflicts  = conflicts.filter(c => c.status === 'open')
  const allOpenIds     = openConflicts.map(c => c.id)
  const isAllSelected  = allOpenIds.length > 0 && allOpenIds.every(id => selected.has(id))
  const isPartSelected = allOpenIds.some(id => selected.has(id)) && !isAllSelected

  function toggleSelectAll() {
    if (isAllSelected) {
      setSelected(prev => { const s = new Set(prev); allOpenIds.forEach(id => s.delete(id)); return s })
    } else {
      setSelected(prev => { const s = new Set(prev); allOpenIds.forEach(id => s.add(id)); return s })
    }
  }

  function toggleOne(id) {
    setSelected(prev => {
      const s = new Set(prev)
      s.has(id) ? s.delete(id) : s.add(id)
      return s
    })
  }

  function clearSelection() { setSelected(new Set()) }

  function resetPage() { setPage(1); clearSelection() }

  function handleSearch(e) {
    e.preventDefault()
    setKeyword(keywordInput)
    setPage(1)
    clearSelection()
  }

  function clearSearch() {
    setKeywordInput('')
    setKeyword('')
    setPage(1)
    clearSelection()
  }

  // ── 操作函数 ───────────────────────────────────────────────────────────────
  async function handleDetect() {
    setRunning(true)
    try {
      await conflictApi.detect()
      toast.success('冲突检测已启动（异步执行）')
      setTimeout(() => { refetch(); qc.invalidateQueries(['annotated-count']) }, 2000)
    } catch (err) {
      toast.error(err.response?.data?.detail || '检测失败')
    } finally {
      setRunning(false)
    }
  }

  async function handleSelfCheck() {
    setSelfChecking(true)
    try {
      await conflictApi.selfCheck()
      toast.success('高质量数据自检已启动（异步执行）')
      setTimeout(() => { refetch(); qc.invalidateQueries(['annotated-count']) }, 3000)
    } catch (err) {
      toast.error(err.response?.data?.detail || '自检失败')
    } finally {
      setSelfChecking(false)
    }
  }

  async function handleSingleResolve(label, cot) {
    try {
      await conflictApi.resolve(resolveTarget.id, label, cot)
      toast.success(`冲突已裁决：「${label}」`)
      refetch()
      qc.invalidateQueries(['annotated-count'])
    } catch (err) {
      toast.error(err.response?.data?.detail || '裁决失败')
      throw err
    }
  }

  async function handleBatchResolve(label, cot) {
    const ids = [...selected].filter(id => openConflicts.find(c => c.id === id))
    if (ids.length === 0) { toast.error('未选中任何待解决冲突'); return }
    try {
      const res = await conflictApi.batchResolve(ids, label, cot)
      const n   = res.data?.data?.resolved ?? ids.length
      toast.success(`已批量裁决 ${n} 条冲突，标签：「${label}」`)
      clearSelection()
      refetch()
      qc.invalidateQueries(['annotated-count'])
    } catch (err) {
      toast.error(err.response?.data?.detail || '批量裁决失败')
      throw err
    }
  }

  async function handleRevokeOne(conflict) {
    try {
      await conflictApi.batchRevoke([conflict.id])
      toast.success('已撤销冲突，数据恢复至高质量数据')
      refetch()
      qc.invalidateQueries(['annotated-count'])
    } catch (err) {
      toast.error(err.response?.data?.detail || '撤销失败')
    }
  }

  async function handleBatchRevoke() {
    const ids = [...selected]
    if (ids.length === 0) { toast.error('未选中任何冲突'); return }
    try {
      const res = await conflictApi.batchRevoke(ids)
      const n   = res.data?.data?.revoked ?? ids.length
      toast.success(`已撤销 ${n} 条冲突，数据恢复至高质量数据`)
      clearSelection()
      refetch()
    } catch (err) {
      toast.error(err.response?.data?.detail || '批量撤销失败')
    }
  }

  // ── 是否显示批量撤销（选中项都是语义冲突）────────────────────────────────
  const selectedConflicts = conflicts.filter(c => selected.has(c.id))
  const selectedAllSemantic = selectedConflicts.length > 0
    && selectedConflicts.every(c => c.conflict_type === 'semantic_conflict' && c.status === 'open')

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">冲突检测</h1>
          <p className="text-muted-foreground text-sm mt-1">检测多人标注分歧与语义相似冲突</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="w-4 h-4 mr-2" /> 刷新
          </Button>
          <Button
            variant="outline" size="sm"
            onClick={handleSelfCheck}
            disabled={selfChecking || running}
            title="在所有【通过检查】的数据内部，检测语义相似但标签不同的冲突对"
          >
            {selfChecking
              ? <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              : <SearchCheck className="w-4 h-4 mr-2" />}
            高质量数据自检
          </Button>
          <Button size="sm" onClick={handleDetect} disabled={running || annotatedCount === 0}>
            {running ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
            运行检测
          </Button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card><CardContent className="p-5 flex items-center justify-between">
          <div><p className="text-xs text-muted-foreground">已标注</p><p className="text-2xl font-bold">{annotatedCount}</p></div>
          <CheckCircle className="w-8 h-8 text-green-500 opacity-80" />
        </CardContent></Card>
        <Card><CardContent className="p-5 flex items-center justify-between">
          <div><p className="text-xs text-muted-foreground">本页冲突</p><p className="text-2xl font-bold text-red-500">{conflicts.filter(c => c.status === 'open').length}</p></div>
          <ShieldAlert className="w-8 h-8 text-red-400 opacity-80" />
        </CardContent></Card>
        <Card><CardContent className="p-5 flex items-center justify-between">
          <div><p className="text-xs text-muted-foreground">已选中</p><p className="text-2xl font-bold text-blue-600">{selected.size}</p></div>
          <CheckCircle className="w-8 h-8 text-blue-400 opacity-80" />
        </CardContent></Card>
        <Card><CardContent className="p-5 flex items-center justify-between">
          <div><p className="text-xs text-muted-foreground">共 {total} 条</p><p className="text-2xl font-bold text-green-600">{conflicts.filter(c => c.status === 'resolved').length} 已解</p></div>
          <CheckCircle className="w-8 h-8 text-green-500 opacity-80" />
        </CardContent></Card>
      </div>

      {/* Conflict list */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-3 flex-wrap">
            <CardTitle className="text-base flex-1 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-orange-500" />冲突列表
              {selected.size > 0 && (
                <span className="text-sm font-normal text-blue-600">（已选 {selected.size} 条）</span>
              )}
            </CardTitle>

            {/* 批量操作按钮 */}
            {selected.size > 0 && (
              <div className="flex gap-2">
                {selectedAllSemantic && (
                  <Button
                    variant="outline" size="sm"
                    className="border-amber-300 text-amber-700 hover:bg-amber-50"
                    onClick={handleBatchRevoke}
                  >
                    <Undo2 className="w-3.5 h-3.5 mr-1.5" />
                    批量撤销（{selected.size}）
                  </Button>
                )}
                <Button size="sm" onClick={() => setBatchResolveOpen(true)}>
                  <Check className="w-3.5 h-3.5 mr-1.5" />
                  批量裁决（{selected.size}）
                </Button>
                <Button variant="ghost" size="sm" onClick={clearSelection}>取消选择</Button>
              </div>
            )}

            {/* 搜索框 */}
            <form onSubmit={handleSearch} className="flex items-center gap-1">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
                <Input
                  value={keywordInput}
                  onChange={e => setKeywordInput(e.target.value)}
                  placeholder="搜索文本内容..."
                  className="h-8 pl-8 pr-7 w-52 text-sm"
                />
                {keywordInput && (
                  <button
                    type="button"
                    onClick={clearSearch}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
              <Button type="submit" size="sm" variant="outline" className="h-8 px-2.5">
                搜索
              </Button>
            </form>

            {/* 过滤器 */}
            <Select value={typeFilter} onValueChange={v => { setTypeFilter(v); resetPage() }}>
              <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部类型</SelectItem>
                <SelectItem value="label_conflict">标注分歧</SelectItem>
                <SelectItem value="semantic_conflict">语义相似</SelectItem>
              </SelectContent>
            </Select>
            <Select value={statusFilter} onValueChange={v => { setStatusFilter(v); resetPage() }}>
              <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部状态</SelectItem>
                <SelectItem value="open">待解决</SelectItem>
                <SelectItem value="resolved">已解决</SelectItem>
                <SelectItem value="revoked">已撤销</SelectItem>
              </SelectContent>
            </Select>

            {/* 当前搜索词提示 */}
            {keyword && (
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                搜索：<span className="font-medium text-foreground">"{keyword}"</span>
                <button onClick={clearSearch} className="ml-1 text-muted-foreground hover:text-foreground">
                  <X className="w-3 h-3 inline" />
                </button>
              </span>
            )}
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                {/* 全选 checkbox */}
                <TableHead className="w-10">
                  <input
                    type="checkbox"
                    className="rounded border-gray-300 cursor-pointer"
                    checked={isAllSelected}
                    ref={el => { if (el) el.indeterminate = isPartSelected }}
                    onChange={toggleSelectAll}
                  />
                </TableHead>
                <TableHead className="w-20">数据 ID</TableHead>
                <TableHead>文本内容</TableHead>
                <TableHead className="w-28">冲突类型</TableHead>
                <TableHead>冲突详情</TableHead>
                <TableHead className="w-40 whitespace-nowrap">检测时间</TableHead>
                <TableHead className="w-24 whitespace-nowrap">状态</TableHead>
                <TableHead className="w-36 text-center">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={8} className="text-center py-10 text-muted-foreground">
                  <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />加载中...
                </TableCell></TableRow>
              ) : conflicts.length === 0 ? (
                <TableRow><TableCell colSpan={8} className="text-center py-10 text-muted-foreground">
                  {annotatedCount === 0 ? '请先完成人工标注，再运行冲突检测' : '暂无冲突记录 ✓'}
                </TableCell></TableRow>
              ) : conflicts.map(c => (
                <TableRow
                  key={c.id}
                  className={`${c.status !== 'open' ? 'opacity-60' : ''} ${selected.has(c.id) ? 'bg-blue-50' : ''}`}
                >
                  <TableCell>
                    {c.status === 'open' && (
                      <input
                        type="checkbox"
                        className="rounded border-gray-300 cursor-pointer"
                        checked={selected.has(c.id)}
                        onChange={() => toggleOne(c.id)}
                      />
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-xs">#{c.data_id}</TableCell>
                  <TableCell className="max-w-xs">
                    <p className="truncate text-sm" title={c.data_content}>
                      {c.data_content || <span className="text-muted-foreground italic text-xs">加载中…</span>}
                    </p>
                  </TableCell>
                  <TableCell><ConflictTypeBadge type={c.conflict_type} /></TableCell>
                  <TableCell className="max-w-sm"><ConflictDetail conflict={c} /></TableCell>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{formatDate(c.created_at)}</TableCell>
                  <TableCell className="whitespace-nowrap"><ConflictStatusBadge status={c.status} /></TableCell>
                  <TableCell className="text-center">
                    {c.status === 'open' && (
                      <div className="flex gap-1.5 justify-center">
                        <Button
                          size="sm" className="h-7 text-xs"
                          onClick={() => { setResolveTarget(c); setResolveOpen(true) }}
                        >
                          裁决
                        </Button>
                        {c.conflict_type === 'semantic_conflict' && (
                          <Button
                            size="sm" variant="outline"
                            className="h-7 text-xs border-amber-300 text-amber-700 hover:bg-amber-50"
                            title="撤销冲突，数据恢复到高质量数据（checked）"
                            onClick={() => handleRevokeOne(c)}
                          >
                            <Undo2 className="w-3 h-3" />
                          </Button>
                        )}
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {/* 分页 */}
          <div className="border-t px-4 py-3">
            <TablePagination
              page={page}
              pageSize={pageSize}
              total={total}
              onPageChange={p => { setPage(p); clearSelection() }}
              onSizeChange={s => { setPageSize(s); setPage(1); clearSelection() }}
            />
          </div>
        </CardContent>
      </Card>

      {/* 单条裁决弹窗 */}
      <ResolveDialog
        title={`解决冲突 · 数据 #${resolveTarget?.data_id}`}
        subtext={resolveTarget?.data_content}
        labels={labels}
        open={resolveOpen}
        onOpenChange={setResolveOpen}
        requireCot={requireCot}
        onSubmit={async (label, cot) => {
          await handleSingleResolve(label, cot)
        }}
      />

      {/* 批量裁决弹窗 */}
      <ResolveDialog
        title={`批量裁决 · 已选 ${selected.size} 条冲突`}
        subtext={`将对选中的 ${selected.size} 条冲突统一裁决为同一标签，不支持逐条指定不同标签。`}
        labels={labels}
        open={batchResolveOpen}
        onOpenChange={setBatchResolveOpen}
        requireCot={requireCot}
        onSubmit={handleBatchResolve}
      />
    </div>
  )
}
