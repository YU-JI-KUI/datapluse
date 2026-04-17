/**
 * DataExplorer — 数据浏览页
 *
 * 布局：
 *   ┌──────────────────────────────────────────┐
 *   │  搜索条件栏（关键词 + 状态 + 来源）         │
 *   ├──────────────────────────────────────────┤
 *   │  数据列表（分页表格）                       │
 *   │  Action 列：查看详情 / 添加评论             │
 *   └──────────────────────────────────────────┘
 *
 * 功能：
 * - 全文关键词搜索
 * - 按 status 过滤
 * - 查看数据详情（含标注历史 + 评论）
 * - 添加评论（comment）
 */

import { useState, useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  MessageSquare, RefreshCw,
  X, Send, Eye, Clock, User, Tag, Cpu, Trash2, GitBranch, Pencil,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import TablePagination from '@/components/TablePagination'
import SearchBar from '@/components/SearchBar'
import { dataApi, commentApi, annotationApi, configApi, getCurrentDatasetId } from '@/lib/api'
import {
  formatDate, getStatusLabel, getStatusColor,
  getActiveLabel, getPreLabel, getPreScore, scoreColor,
} from '@/lib/utils'

// ── 评论面板 ──────────────────────────────────────────────────────────────────

function CommentPanel({ dataId, onClose }) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const inputRef = useRef()
  const qc = useQueryClient()

  const { data: commentsRes, isLoading, refetch } = useQuery({
    queryKey: ['comments', dataId],
    queryFn: () => commentApi.list(dataId),
    enabled: !!dataId,
  })
  const comments = commentsRes?.data?.data ?? commentsRes?.data ?? []

  async function handleSend() {
    if (!text.trim()) return
    setSending(true)
    try {
      await commentApi.add(dataId, text.trim())
      setText('')
      refetch()
      qc.invalidateQueries(['comments', dataId])
    } catch (err) {
      toast.error(err.response?.data?.detail || '评论失败')
    } finally {
      setSending(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b bg-gray-50">
        <div className="flex items-center gap-2 text-sm font-medium">
          <MessageSquare className="w-4 h-4 text-blue-500" />
          评论 · #{dataId}
        </div>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Comments list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0">
        {isLoading && <p className="text-sm text-muted-foreground text-center py-4">加载中...</p>}
        {!isLoading && comments.length === 0 && (
          <div className="text-center py-8 text-muted-foreground">
            <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-30" />
            <p className="text-sm">暂无评论</p>
          </div>
        )}
        {comments.map(c => (
          <div key={c.id} className="bg-white border rounded-lg p-3 space-y-1">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <User className="w-3 h-3" />
              <span className="font-medium text-foreground">{c.username}</span>
              <Clock className="w-3 h-3 ml-auto" />
              <span>{formatDate(c.created_at)}</span>
            </div>
            <p className="text-sm whitespace-pre-wrap">{c.comment}</p>
          </div>
        ))}
      </div>

      {/* Input */}
      <div className="p-3 border-t bg-white flex gap-2">
        <Input
          ref={inputRef}
          placeholder="添加评论（Enter 发送）"
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          className="flex-1 text-sm"
        />
        <Button size="sm" onClick={handleSend} disabled={sending || !text.trim()}>
          <Send className="w-4 h-4" />
        </Button>
      </div>
    </div>
  )
}

// ── 详情面板 ──────────────────────────────────────────────────────────────────

function DetailPanel({ item, onClose }) {
  const [tab, setTab] = useState('info') // 'info' | 'cot' | 'comments'
  const annotations  = item?.annotations || []
  const preAnn       = item?.pre_annotation
  // final_label 来自 t_annotation_result，label_source: 'auto' | 'manual'
  const finalLabel   = item?.label
  const labelSource  = item?.label_source
  const resolver     = item?.resolver
  const resultCot    = item?.result_cot

  // 是否有任何 COT 数据
  const hasCot = preAnn?.cot || annotations.some(a => a.cot) || resultCot

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b bg-gray-50">
        <span className="text-sm font-medium flex items-center gap-2">
          <Eye className="w-4 h-4 text-gray-500" />
          数据详情 · #{item?.id}
        </span>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b text-sm">
        {[
          ['info', '详情'],
          ['cot', hasCot ? '推理链 ●' : '推理链'],
          ['comments', '评论'],
        ].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-3 py-2 transition-colors text-xs ${tab === key ? 'border-b-2 border-primary font-medium text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'cot' ? (
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {!hasCot ? (
            <div className="text-center py-10 text-muted-foreground">
              <GitBranch className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="text-sm">暂无推理链数据</p>
              <p className="text-xs mt-1">标注员提交时填写理由后可在此查看</p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* 1. 模型预标注 COT */}
              {preAnn?.cot && (
                <div className="border rounded-lg p-3 bg-purple-50/50 border-purple-200">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-purple-700 mb-2">
                    <Cpu className="w-3.5 h-3.5" />
                    <span>模型预标注推理</span>
                    {preAnn.label && (
                      <span className="ml-auto bg-purple-100 text-purple-700 border border-purple-200 rounded px-1.5 py-0.5 font-medium">
                        {preAnn.label}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{preAnn.cot}</p>
                </div>
              )}

              {/* 2. 各标注员 COT */}
              {annotations.filter(a => a.is_active).map(a => (
                a.cot ? (
                  <div key={a.id} className="border rounded-lg p-3 bg-blue-50/30 border-blue-100">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-blue-700 mb-2">
                      <User className="w-3.5 h-3.5" />
                      <span>{a.username} 的标注理由</span>
                      <span className="ml-auto bg-blue-100 text-blue-700 border border-blue-200 rounded px-1.5 py-0.5 font-medium">
                        {a.label}
                      </span>
                    </div>
                    <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{a.cot}</p>
                  </div>
                ) : (
                  <div key={a.id} className="border rounded-lg p-3 bg-gray-50/50 border-gray-100">
                    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <User className="w-3.5 h-3.5" />
                      <span>{a.username}</span>
                      <span className="ml-auto bg-gray-100 text-gray-600 rounded px-1.5 py-0.5">{a.label}</span>
                      <span className="text-xs italic">未填写理由</span>
                    </div>
                  </div>
                )
              ))}

              {/* 3. 裁决 COT（manual 时）*/}
              {labelSource === 'manual' && (
                <div className="border rounded-lg p-3 bg-orange-50/50 border-orange-200">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-orange-700 mb-2">
                    <Tag className="w-3.5 h-3.5" />
                    <span>裁决理由</span>
                    <span className="text-muted-foreground font-normal">by {resolver}</span>
                    {finalLabel && (
                      <span className="ml-auto bg-orange-100 text-orange-700 border border-orange-200 rounded px-1.5 py-0.5 font-medium">
                        最终：{finalLabel}
                      </span>
                    )}
                  </div>
                  {resultCot ? (
                    <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{resultCot}</p>
                  ) : (
                    <p className="text-xs text-muted-foreground italic">裁决时未填写理由</p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      ) : tab === 'info' ? (
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Content */}
          <div>
            <p className="text-xs text-muted-foreground mb-1">文本内容</p>
            <p className="text-sm bg-gray-50 rounded-lg p-3 leading-relaxed">{item?.content}</p>
          </div>

          {/* Status */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-xs text-muted-foreground mb-1">当前状态</p>
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${getStatusColor(item?.status)}`}>
                {getStatusLabel(item?.status)}
              </span>
            </div>
            <div>
              <p className="text-xs text-muted-foreground mb-1">来源文件</p>
              <p className="text-xs truncate">{item?.source_ref || '-'}</p>
            </div>
          </div>

          {/* Pre-annotation */}
          {preAnn && (
            <div className="border rounded-lg p-3 bg-purple-50/50">
              <div className="flex items-center gap-1.5 text-xs font-medium text-purple-700 mb-2">
                <Cpu className="w-3.5 h-3.5" /> 模型预标注
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold">{preAnn.label}</span>
                <span className={`text-xs font-medium ${scoreColor(preAnn.score)}`}>
                  {preAnn.score != null ? `${(preAnn.score * 100).toFixed(1)}%` : ''}
                </span>
              </div>
              {preAnn.model_name && <p className="text-xs text-muted-foreground mt-1">模型: {preAnn.model_name}</p>}
            </div>
          )}

          {/* 最终标注结果（来自 t_annotation_result）*/}
          {finalLabel && (
            <div className="border rounded-lg p-3 bg-green-50/50 border-green-200">
              <div className="flex items-center gap-1.5 text-xs font-medium text-green-700 mb-1.5">
                <Tag className="w-3.5 h-3.5" /> 最终标注结果
              </div>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-sm font-semibold border-green-300 text-green-800">
                  {finalLabel}
                </Badge>
                {labelSource === 'manual' ? (
                  <span className="text-xs text-orange-600 bg-orange-50 border border-orange-200 rounded px-1.5 py-0.5">
                    裁决 · {resolver}
                  </span>
                ) : (
                  <span className="text-xs text-muted-foreground">多数投票</span>
                )}
              </div>
            </div>
          )}

          {/* 各标注员的标注（事实层）*/}
          {annotations.filter(a => a.is_active).length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mb-2">
                <Tag className="w-3.5 h-3.5" /> 各标注员明细
              </div>
              <div className="space-y-1.5">
                {annotations.filter(a => a.is_active).map(a => (
                  <div key={a.id} className="border rounded-lg p-2 bg-gray-50/50 flex items-center justify-between">
                    <Badge variant="outline" className="text-xs">{a.label}</Badge>
                    <span className="text-xs text-muted-foreground">{a.username}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Timestamps */}
          <div className="text-xs text-muted-foreground space-y-1 pt-2 border-t">
            <div>创建时间: {formatDate(item?.created_at)}</div>
            <div>更新时间: {formatDate(item?.updated_at)}</div>
          </div>
        </div>
      ) : (
        <CommentPanel dataId={item?.id} onClose={onClose} />
      )}
    </div>
  )
}

// ── 修改标注标签对话框 ────────────────────────────────────────────────────────

function EditAnnotationDialog({ open, onOpenChange, item, onSuccess }) {
  const [label,      setLabel]      = useState('')
  const [cot,        setCot]        = useState('')
  const [submitting, setSubmitting] = useState(false)

  // 从配置拿标签列表
  const { data: cfgRes } = useQuery({
    queryKey: ['config'],
    queryFn:  () => configApi.get(),
    enabled:  open,
  })
  const labels = cfgRes?.data?.data?.labels || []

  // 打开时重置
  useEffect(() => {
    if (open) { setLabel(''); setCot('') }
  }, [open])

  async function handleSubmit() {
    if (!label)       { toast.error('请选择标注标签'); return }
    if (!cot.trim())  { toast.error('请填写标注理由（COT）'); return }
    setSubmitting(true)
    try {
      await annotationApi.submit(item.id, label, cot.trim())
      toast.success(`已更新标注：${label}`)
      onSuccess?.()
      onOpenChange(false)
    } catch (err) {
      toast.error(err.response?.data?.detail || '提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>修改标注标签 · #{item?.id}</DialogTitle>
        </DialogHeader>

        {item && (
          <div className="text-sm bg-muted/50 rounded-lg p-3 my-1 line-clamp-3 text-muted-foreground leading-relaxed">
            {item.content}
          </div>
        )}

        <div className="space-y-4 py-1">
          {/* 标签选择 */}
          <div>
            <label className="block text-sm font-medium mb-1.5">
              标注标签 <span className="text-destructive">*</span>
            </label>
            <Select value={label} onValueChange={setLabel}>
              <SelectTrigger className={`w-full ${!label ? 'border-orange-300' : 'border-green-400'}`}>
                <SelectValue placeholder="请选择意图标签…" />
              </SelectTrigger>
              <SelectContent>
                {labels.map(l => (
                  <SelectItem key={l} value={l}>{l}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* COT */}
          <div>
            <label className="block text-sm font-medium mb-1.5">
              标注理由（COT）<span className="text-destructive">*</span>
            </label>
            <textarea
              className={`w-full min-h-[100px] rounded-md border px-3 py-2 text-sm bg-background
                         placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-y
                         ${!cot.trim() ? 'border-orange-300' : 'border-green-400'}`}
              placeholder="请说明选择该标签的依据，例如：用户询问了保费金额，符合寿险意图的定义…"
              value={cot}
              onChange={e => setCot(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button
            onClick={handleSubmit}
            disabled={submitting || !label || !cot.trim()}
          >
            {submitting ? '提交中…' : '确认修改'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

const STATUS_OPTIONS = [
  { value: 'raw',           label: '原始' },
  { value: 'cleaned',       label: '已清洗' },
  { value: 'pre_annotated', label: '已预标注' },
  { value: 'annotated',     label: '已标注' },
  { value: 'checked',       label: '已检测' },
]

export default function DataExplorer() {
  const [filters, setFilters]         = useState({})
  const [labelFilter, setLabelFilter] = useState('all')
  const [page, setPage]               = useState(1)
  const [pageSize, setPageSize]       = useState(10)
  const [sideItem, setSideItem]       = useState(null)
  const [sideMode, setSideMode]       = useState('detail')
  const [datasetId, setDatasetId]     = useState(() => getCurrentDatasetId())

  // 修改标注标签对话框
  const [editItem, setEditItem]       = useState(null)
  const [editOpen, setEditOpen]       = useState(false)

  // ── 多选状态 ────────────────────────────────────────────────────────────────
  const [selectedIds, setSelectedIds] = useState(new Set())

  // 数据集切换监听
  useEffect(() => {
    const handler = (e) => {
      setDatasetId(e.detail.datasetId)
      setSelectedIds(new Set())
      setLabelFilter('all')
      setPage(1)
    }
    window.addEventListener('datasetChanged', handler)
    return () => window.removeEventListener('datasetChanged', handler)
  }, [])

  const { data: labelOptionsRes } = useQuery({
    queryKey: ['label-options', datasetId],
    queryFn:  () => dataApi.labelOptions(datasetId),
    enabled:  !!datasetId,
    staleTime: 30_000,
  })
  const labelOptions = labelOptionsRes?.data?.data || []

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['explorer', datasetId, filters, labelFilter, page, pageSize],
    queryFn: () => dataApi.list({
      status:     filters.status     || undefined,
      keyword:    filters.keyword    || undefined,
      label:      labelFilter !== 'all' ? labelFilter : undefined,
      start_date: filters.start_date || undefined,
      end_date:   filters.end_date   || undefined,
      page,
      page_size: pageSize,
    }, datasetId),
    enabled: !!datasetId,
    staleTime: 0,
  })

  const result = data?.data?.data ?? {}
  const items  = result.list || []
  const total  = result.pagination?.total || 0

  // 当前页全选状态
  const pageIds     = items.map(i => i.id)
  const allSelected = pageIds.length > 0 && pageIds.every(id => selectedIds.has(id))
  const someSelected = pageIds.some(id => selectedIds.has(id)) && !allSelected

  function toggleSelectAll() {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (allSelected) {
        pageIds.forEach(id => next.delete(id))
      } else {
        pageIds.forEach(id => next.add(id))
      }
      return next
    })
  }

  function toggleSelect(id) {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function openDetail(item) { setSideItem(item); setSideMode('detail') }
  function openComment(item) { setSideItem(item); setSideMode('comment') }
  function closeSide() { setSideItem(null) }

  function openEdit(item, e) {
    e.stopPropagation()
    setEditItem(item)
    setEditOpen(true)
  }

  function handleEditSuccess() {
    refetch()
    // 如果侧边栏正在显示该条，刷新后关闭（数据已变）
    if (sideItem?.id === editItem?.id) closeSide()
  }

  const qc = useQueryClient()

  // ── 单条删除 ─────────────────────────────────────────────────────────────────
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)
  const [confirmOpen, setConfirmOpen]         = useState(false)

  function requestDelete(id) { setConfirmDeleteId(id); setConfirmOpen(true) }

  async function handleDelete() {
    if (confirmDeleteId === null) return
    try {
      await dataApi.deleteItem(confirmDeleteId)
      toast.success('已删除')
      if (sideItem?.id === confirmDeleteId) closeSide()
      setSelectedIds(prev => { const n = new Set(prev); n.delete(confirmDeleteId); return n })
      qc.invalidateQueries(['explorer'])
    } catch {
      toast.error('删除失败')
    }
  }

  // ── 批量删除 ─────────────────────────────────────────────────────────────────
  const [batchConfirmOpen, setBatchConfirmOpen] = useState(false)
  const [batchDeleting,    setBatchDeleting]    = useState(false)

  async function handleBatchDelete() {
    const ids = [...selectedIds]
    setBatchDeleting(true)
    try {
      await dataApi.deleteBatch(ids)
      toast.success(`已删除 ${ids.length} 条数据`)
      if (sideItem && ids.includes(sideItem.id)) closeSide()
      setSelectedIds(new Set())
      qc.invalidateQueries(['explorer'])
    } catch {
      toast.error('批量删除失败')
    } finally {
      setBatchDeleting(false)
    }
  }

  return (
    <div className="flex h-full">
      {/* ── 主区域 ── */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="p-8 space-y-5 flex-1 overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">Data Explorer</h1>
              <p className="text-muted-foreground text-sm mt-1">浏览所有数据，查看标注详情，添加评论</p>
            </div>
            <div className="flex items-center gap-2">
              {selectedIds.size > 0 && (
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => setBatchConfirmOpen(true)}
                  disabled={batchDeleting}
                >
                  <Trash2 className="w-4 h-4 mr-1.5" />
                  删除选中 ({selectedIds.size})
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={() => refetch()}>
                <RefreshCw className="w-4 h-4 mr-2" />刷新
              </Button>
            </div>
          </div>

          {/* Search bar */}
          <Card>
            <CardContent className="p-4 space-y-3">
              <div className="flex items-center gap-3 flex-wrap">
                <SearchBar
                  placeholder="搜索文本内容…"
                  statusOptions={STATUS_OPTIONS}
                  onSearch={f => { setFilters(f); setPage(1); setSelectedIds(new Set()) }}
                  className="flex-1"
                />
                <div className="text-sm text-muted-foreground whitespace-nowrap">
                  共 <span className="font-semibold text-foreground">{total}</span> 条
                </div>
              </div>
              {/* 标注标签过滤 */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground whitespace-nowrap">标注标签：</span>
                <Select
                  value={labelFilter}
                  onValueChange={v => { setLabelFilter(v); setPage(1); setSelectedIds(new Set()) }}
                >
                  <SelectTrigger className="w-48 h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">全部标签</SelectItem>
                    {labelOptions.map(l => (
                      <SelectItem key={l} value={l}>{l}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {labelFilter !== 'all' && (
                  <button
                    onClick={() => { setLabelFilter('all'); setPage(1) }}
                    className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-0.5"
                  >
                    <X className="w-3 h-3" /> 清除
                  </button>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Table */}
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    {/* 全选 checkbox */}
                    <TableHead className="w-10" onClick={e => e.stopPropagation()}>
                      <button
                        onClick={toggleSelectAll}
                        className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${
                          allSelected
                            ? 'bg-primary border-primary text-white'
                            : someSelected
                              ? 'bg-primary/30 border-primary'
                              : 'border-gray-300 hover:border-primary'
                        }`}
                        title={allSelected ? '取消全选' : '全选本页'}
                      >
                        {allSelected && <span className="text-white text-xs font-bold">✓</span>}
                        {someSelected && <span className="text-primary text-xs font-bold">—</span>}
                      </button>
                    </TableHead>
                    <TableHead className="w-12">ID</TableHead>
                    <TableHead>文本内容</TableHead>
                    <TableHead className="w-28">状态</TableHead>
                    <TableHead className="w-36">预测标签</TableHead>
                    <TableHead className="w-36">标注标签</TableHead>
                    <TableHead className="w-40 whitespace-nowrap">创建时间</TableHead>
                    <TableHead className="w-40 whitespace-nowrap">更新时间</TableHead>
                    <TableHead className="w-32 text-center">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isLoading ? (
                    <TableRow>
                      <TableCell colSpan={9} className="text-center py-12 text-muted-foreground">
                        <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2" />加载中...
                      </TableCell>
                    </TableRow>
                  ) : items.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={9} className="text-center py-12 text-muted-foreground">
                        {Object.values(filters).some(Boolean)
                          ? '没有符合条件的数据'
                          : '暂无数据'}
                      </TableCell>
                    </TableRow>
                  ) : items.map(item => {
                    const preLabel    = getPreLabel(item)
                    const preScore    = getPreScore(item)
                    const activeLabel = getActiveLabel(item)
                    const isActive    = sideItem?.id === item.id
                    const isSelected  = selectedIds.has(item.id)

                    return (
                      <TableRow
                        key={item.id}
                        className={`cursor-pointer transition-colors ${
                          isSelected ? 'bg-blue-50/60' : isActive ? 'bg-blue-50' : 'hover:bg-muted/50'
                        }`}
                        onClick={() => openDetail(item)}
                      >
                        {/* 行 checkbox */}
                        <TableCell onClick={e => e.stopPropagation()}>
                          <button
                            onClick={() => toggleSelect(item.id)}
                            className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${
                              isSelected
                                ? 'bg-primary border-primary text-white'
                                : 'border-gray-300 hover:border-primary'
                            }`}
                          >
                            {isSelected && <span className="text-white text-xs font-bold">✓</span>}
                          </button>
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {item.id}
                        </TableCell>
                        <TableCell>
                          <p className="text-sm line-clamp-2 leading-snug" title={item.content}>
                            {item.content}
                          </p>
                        </TableCell>
                        <TableCell>
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${getStatusColor(item.status)}`}>
                            {getStatusLabel(item.status)}
                          </span>
                        </TableCell>
                        <TableCell>
                          {preLabel ? (
                            <div>
                              <span className="text-xs font-medium">{preLabel}</span>
                              {preScore != null && (
                                <span className={`ml-1 text-xs ${scoreColor(preScore)}`}>
                                  {(preScore * 100).toFixed(0)}%
                                </span>
                              )}
                            </div>
                          ) : (
                            <span className="text-xs text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell>
                          {activeLabel
                            ? <Badge variant="outline" className="text-xs">{activeLabel}</Badge>
                            : <span className="text-xs text-muted-foreground">—</span>
                          }
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                          {formatDate(item.created_at)}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                          {formatDate(item.updated_at)}
                        </TableCell>
                        <TableCell onClick={e => e.stopPropagation()}>
                          <div className="flex items-center justify-center gap-1">
                            <button
                              title="查看详情"
                              onClick={() => openDetail(item)}
                              className={`p-1.5 rounded transition-colors ${isActive && sideMode === 'detail' ? 'bg-blue-100 text-blue-600' : 'text-muted-foreground hover:text-foreground hover:bg-muted'}`}
                            >
                              <Eye className="w-4 h-4" />
                            </button>
                            <button
                              title="修改标注标签"
                              onClick={(e) => openEdit(item, e)}
                              className="p-1.5 rounded transition-colors text-muted-foreground hover:text-primary hover:bg-primary/10"
                            >
                              <Pencil className="w-4 h-4" />
                            </button>
                            <button
                              title="添加评论"
                              onClick={() => openComment(item)}
                              className={`p-1.5 rounded transition-colors ${isActive && sideMode === 'comment' ? 'bg-blue-100 text-blue-600' : 'text-muted-foreground hover:text-foreground hover:bg-muted'}`}
                            >
                              <MessageSquare className="w-4 h-4" />
                            </button>
                            <button
                              title="删除"
                              onClick={() => requestDelete(item.id)}
                              className="p-1.5 rounded transition-colors text-muted-foreground hover:text-destructive hover:bg-red-50"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>

              {/* 分页 */}
              <TablePagination
                page={page}
                pageSize={pageSize}
                total={total}
                onPageChange={p => { setPage(p); setSelectedIds(new Set()) }}
                onSizeChange={size => { setPageSize(size); setPage(1); setSelectedIds(new Set()) }}
              />
            </CardContent>
          </Card>
        </div>
      </div>

      {/* ── 侧边详情/评论面板 ── */}
      {sideItem && (
        <div className="w-96 border-l flex flex-col bg-white shrink-0 overflow-hidden">
          {sideMode === 'comment'
            ? <CommentPanel dataId={sideItem.id} onClose={closeSide} />
            : <DetailPanel item={sideItem} onClose={closeSide} />
          }
        </div>
      )}

      {/* 单条删除确认 */}
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="确认删除"
        description="删除后无法恢复，确定要删除这条数据吗？"
        confirmLabel="删除"
        onConfirm={handleDelete}
      />

      {/* 批量删除确认 */}
      <ConfirmDialog
        open={batchConfirmOpen}
        onOpenChange={setBatchConfirmOpen}
        title={`批量删除 ${selectedIds.size} 条数据`}
        description="选中的数据及其标注结果将被永久删除，此操作无法撤销。"
        confirmLabel={batchDeleting ? '删除中…' : `确认删除 ${selectedIds.size} 条`}
        onConfirm={handleBatchDelete}
      />

      {/* 修改标注标签对话框 */}
      {editItem && (
        <EditAnnotationDialog
          open={editOpen}
          onOpenChange={setEditOpen}
          item={editItem}
          onSuccess={handleEditSuccess}
        />
      )}
    </div>
  )
}
