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
  Search, MessageSquare, ChevronDown, ChevronUp, RefreshCw,
  X, Send, Eye, Clock, User, Tag, Cpu, Trash2,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { dataApi, commentApi, getCurrentDatasetId } from '@/lib/api'
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
  const [tab, setTab] = useState('info') // 'info' | 'comments'
  const annotations  = item?.annotations || []
  const preAnn       = item?.pre_annotation
  // final_label 来自 t_annotation_result，label_source: 'auto' | 'manual'
  const finalLabel   = item?.label
  const labelSource  = item?.label_source
  const resolver     = item?.resolver

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
        {[['info', '详情'], ['comments', '评论']].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 transition-colors ${tab === key ? 'border-b-2 border-primary font-medium' : 'text-muted-foreground hover:text-foreground'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'info' ? (
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

// ── 主页面 ────────────────────────────────────────────────────────────────────

const STATUS_OPTIONS = [
  { value: 'all',           label: '全部状态' },
  { value: 'raw',           label: '原始' },
  { value: 'cleaned',       label: '已清洗' },
  { value: 'pre_annotated', label: '已预标注' },
  { value: 'annotated',     label: '已标注' },
  { value: 'checked',       label: '已检测' },
]

export default function DataExplorer() {
  const [keyword, setKeyword]         = useState('')
  const [debouncedKw, setDebouncedKw] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [page, setPage]               = useState(1)
  const [sideItem, setSideItem]       = useState(null)   // 当前侧边栏展示的 item
  const [sideMode, setSideMode]       = useState('detail') // 'detail' | 'comment'
  const [datasetId, setDatasetId]     = useState(() => getCurrentDatasetId())

  // 数据集切换监听
  useEffect(() => {
    const handler = (e) => setDatasetId(e.detail.datasetId)
    window.addEventListener('datasetChanged', handler)
    return () => window.removeEventListener('datasetChanged', handler)
  }, [])

  // 关键词防抖 300ms
  useEffect(() => {
    const t = setTimeout(() => { setDebouncedKw(keyword); setPage(1) }, 300)
    return () => clearTimeout(t)
  }, [keyword])

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['explorer', datasetId, statusFilter, debouncedKw, page],
    queryFn: () => dataApi.list({
      status:   statusFilter === 'all' ? undefined : statusFilter || undefined,
      keyword:  debouncedKw || undefined,
      page,
      page_size: 25,
    }, datasetId),
    enabled: !!datasetId,
    staleTime: 0,
  })

  const result     = data?.data?.data ?? {}
  const items      = result.list || []
  const total      = result.pagination?.total || 0
  const totalPages = Math.ceil(total / 25)

  function openDetail(item) {
    setSideItem(item)
    setSideMode('detail')
  }

  function openComment(item) {
    setSideItem(item)
    setSideMode('comment')
  }

  function closeSide() { setSideItem(null) }

  const qc = useQueryClient()
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)
  const [confirmOpen, setConfirmOpen]         = useState(false)

  function requestDelete(id) {
    setConfirmDeleteId(id)
    setConfirmOpen(true)
  }

  async function handleDelete() {
    if (confirmDeleteId === null) return
    try {
      await dataApi.deleteItem(confirmDeleteId)
      toast.success('已删除')
      if (sideItem?.id === confirmDeleteId) closeSide()
      qc.invalidateQueries(['explorer'])
    } catch {
      toast.error('删除失败')
    }
  }

  return (
    <div className="flex h-full">
      {/* ── 主区域 ── */}
      <div className={`flex-1 flex flex-col min-w-0 transition-all ${sideItem ? 'mr-0' : ''}`}>
        <div className="p-8 space-y-5 flex-1 overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">Data Explorer</h1>
              <p className="text-muted-foreground text-sm mt-1">浏览所有数据，查看标注详情，添加评论</p>
            </div>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw className="w-4 h-4 mr-2" />刷新
            </Button>
          </div>

          {/* Search bar */}
          <Card>
            <CardContent className="p-4">
              <div className="flex gap-3">
                {/* Keyword */}
                <div className="flex-1 relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    placeholder="搜索文本内容..."
                    value={keyword}
                    onChange={e => setKeyword(e.target.value)}
                    className="pl-9"
                  />
                  {keyword && (
                    <button
                      onClick={() => setKeyword('')}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>

                {/* Status filter */}
                <Select value={statusFilter} onValueChange={v => { setStatusFilter(v); setPage(1) }}>
                  <SelectTrigger className="w-36">
                    <SelectValue placeholder="全部状态" />
                  </SelectTrigger>
                  <SelectContent>
                    {STATUS_OPTIONS.map(o => (
                      <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {/* Result count */}
                <div className="flex items-center text-sm text-muted-foreground whitespace-nowrap">
                  共 <span className="font-semibold text-foreground mx-1">{total}</span> 条
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Table */}
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-12">ID</TableHead>
                    <TableHead>文本内容</TableHead>
                    <TableHead className="w-28">状态</TableHead>
                    <TableHead className="w-36">预测标签</TableHead>
                    <TableHead className="w-36">标注标签</TableHead>
                    <TableHead className="w-40 whitespace-nowrap">创建时间</TableHead>
                    <TableHead className="w-32 text-center">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isLoading ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center py-12 text-muted-foreground">
                        <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2" />加载中...
                      </TableCell>
                    </TableRow>
                  ) : items.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center py-12 text-muted-foreground">
                        {debouncedKw ? `未找到包含"${debouncedKw}"的数据` : '暂无数据'}
                      </TableCell>
                    </TableRow>
                  ) : items.map(item => {
                    const preLabel   = getPreLabel(item)
                    const preScore   = getPreScore(item)
                    const activeLabel = getActiveLabel(item)
                    const isActive   = sideItem?.id === item.id

                    return (
                      <TableRow
                        key={item.id}
                        className={`cursor-pointer transition-colors ${isActive ? 'bg-blue-50' : 'hover:bg-muted/50'}`}
                        onClick={() => openDetail(item)}
                      >
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

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-center gap-2 p-4 border-t">
                  <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</Button>
                  <span className="text-sm text-muted-foreground">第 {page} / {totalPages} 页</span>
                  <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>下一页</Button>
                </div>
              )}
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

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="确认删除"
        description="删除后无法恢复，确定要删除这条数据吗？"
        confirmLabel="删除"
        onConfirm={handleDelete}
      />
    </div>
  )
}
