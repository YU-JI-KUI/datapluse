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
import { createPortal } from 'react-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  MessageSquare, RefreshCw,
  X, Send, Eye, Clock, User, Tag, Cpu, Trash2, GitBranch, Pencil, Tags, MoreHorizontal,
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
import { dataApi, commentApi, annotationApi, categoryApi, configApi, getCurrentDatasetId } from '@/lib/api'
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

  // 是否有任何推理链数据（结构化字段 or 旧 COT 文本）
  const hasCot = preAnn?.cot || annotations.some(a => a.cot || a.category || a.keywords || a.keywords_desc) || resultCot

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

              {/* 2. 各标注员结构化字段 */}
              {annotations.filter(a => a.is_active).map(a => {
                const parts = [
                  a.category    || '',
                  a.keywords    || '',
                  a.keywords_desc || '',
                  a.label       || '',
                ].filter(Boolean)
                const cotText = parts.join('｜')
                return (
                  <div key={a.id} className="border rounded-lg p-3 bg-blue-50/30 border-blue-100">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-blue-700 mb-2">
                      <User className="w-3.5 h-3.5" />
                      <span>{a.username}</span>
                      <span className="ml-auto bg-blue-100 text-blue-700 border border-blue-200 rounded px-1.5 py-0.5 font-medium">
                        {a.label}
                      </span>
                    </div>
                    {cotText ? (
                      <p className="text-sm text-gray-700 leading-relaxed font-mono">{cotText}</p>
                    ) : (
                      <p className="text-xs text-muted-foreground italic">未填写补充信息</p>
                    )}
                  </div>
                )
              })}

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
  const [label,        setLabel]        = useState('')
  const [category,     setCategory]     = useState('none')
  const [keywords,     setKeywords]     = useState('')
  const [keywordsDesc, setKeywordsDesc] = useState('')
  const [submitting,   setSubmitting]   = useState(false)

  // 从配置拿标签列表和 requireCot 设置
  const { data: cfgRes } = useQuery({
    queryKey: ['config'],
    queryFn:  () => configApi.get(),
    enabled:  open,
  })
  const labels     = cfgRes?.data?.data?.labels || []
  const requireCot = cfgRes?.data?.data?.pipeline?.require_cot ?? false

  // 业务分类列表
  const { data: catRes } = useQuery({
    queryKey: ['categories-all'],
    queryFn:  () => categoryApi.list({ page: 1, page_size: 100 }),
    enabled:  open,
  })
  const categoryOptions = catRes?.data?.data?.list ?? []

  // 打开时重置，并回填当前数据的已有值
  useEffect(() => {
    if (open) {
      setLabel('')
      setCategory('none')
      setKeywords('')
      setKeywordsDesc('')
      // 回填当前条目第一个有效标注的值（方便修改时保留旧内容）
      const firstAnn = item?.annotations?.[0]
      if (firstAnn) {
        if (firstAnn.label)         setLabel(firstAnn.label)
        if (firstAnn.category)      setCategory(firstAnn.category)
        if (firstAnn.keywords)      setKeywords(firstAnn.keywords)
        if (firstAnn.keywords_desc) setKeywordsDesc(firstAnn.keywords_desc)
      }
    }
  }, [open, item])

  async function handleSubmit() {
    if (!label) { toast.error('请选择标注标签'); return }
    setSubmitting(true)

    // 从结构化字段自动生成 COT 字符串
    const kw   = keywords.trim()
    const desc = keywordsDesc.trim()
    const cat  = category !== 'none' ? category : ''
    const finalCot = (kw || desc || cat) ? `${kw}｜${desc}｜${label}｜${cat}` : null

    try {
      await annotationApi.submit(
        item.id, label,
        finalCot,
        category !== 'none' ? category : null,
        keywords.trim() || null,
        keywordsDesc.trim() || null,
      )
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
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>修改标注 · #{item?.id}</DialogTitle>
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

          {/* 结构化标注字段（由配置中心 展示COT 开关控制）*/}
          {requireCot && (
            <div className="space-y-3 border border-blue-100 rounded-xl p-4 bg-blue-50/40">
              <p className="text-xs font-medium text-blue-700 flex items-center gap-1.5">
                标注补充信息
                <span className="text-muted-foreground font-normal">（均为选填）</span>
              </p>

              {/* 业务分类 */}
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">业务分类</label>
                <Select value={category} onValueChange={setCategory}>
                  <SelectTrigger className="h-8 text-sm bg-white">
                    <SelectValue placeholder="选择业务分类（可选）" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none" className="text-sm text-muted-foreground">不填写</SelectItem>
                    {categoryOptions.map(c => (
                      <SelectItem key={c.id} value={c.name} className="text-sm">{c.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* 关键词 */}
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">关键词</label>
                <Input
                  value={keywords}
                  onChange={e => setKeywords(e.target.value)}
                  placeholder="输入关键词（可选）"
                  className="h-8 text-sm bg-white"
                />
              </div>

              {/* 关键词说明 */}
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">关键词说明</label>
                <textarea
                  value={keywordsDesc}
                  onChange={e => setKeywordsDesc(e.target.value)}
                  placeholder="对关键词的详细说明（可选）"
                  rows={2}
                  className="w-full text-sm border rounded-lg px-3 py-2 resize-y focus:outline-none focus:ring-2 focus:ring-blue-200 border-gray-200 bg-white placeholder:text-muted-foreground/60"
                />
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={handleSubmit} disabled={submitting || !label}>
            {submitting ? '提交中…' : '确认修改'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── 批量修改标签对话框 ──────────────────────────────────────────────────────────

function BatchEditDialog({ open, onOpenChange, selectedCount, onConfirm, submitting }) {
  const [label,        setLabel]        = useState('')
  const [category,     setCategory]     = useState('none')
  const [keywords,     setKeywords]     = useState('')
  const [keywordsDesc, setKeywordsDesc] = useState('')

  // 从配置拿标签列表和 requireCot 设置
  const { data: cfgRes } = useQuery({
    queryKey: ['config'],
    queryFn:  () => configApi.get(),
    enabled:  open,
  })
  const labels     = cfgRes?.data?.data?.labels || []
  const requireCot = cfgRes?.data?.data?.pipeline?.require_cot ?? false

  // 业务分类列表
  const { data: catRes } = useQuery({
    queryKey: ['categories-all'],
    queryFn:  () => categoryApi.list({ page: 1, page_size: 100 }),
    enabled:  open,
  })
  const categoryOptions = catRes?.data?.data?.list ?? []

  // 打开时重置
  useEffect(() => {
    if (open) { setLabel(''); setCategory('none'); setKeywords(''); setKeywordsDesc('') }
  }, [open])

  function handleConfirm() {
    if (!label) { toast.error('请选择标注标签'); return }
    const kw   = keywords.trim()
    const desc = keywordsDesc.trim()
    const cat  = category !== 'none' ? category : ''
    const cot  = (kw || desc || cat) ? `${kw}｜${desc}｜${label}｜${cat}` : null
    onConfirm(label, cot, category !== 'none' ? category : null, kw || null, desc || null)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Tags className="w-4 h-4 text-primary" />
            批量修改标签
          </DialogTitle>
        </DialogHeader>

        <div className="py-2 space-y-4">
          <p className="text-sm text-muted-foreground">
            将为已选中的 <span className="font-semibold text-foreground">{selectedCount}</span> 条数据统一设置标注标签。
            <br />
            <span className="text-xs">该操作会覆盖这些条目的当前标注结果。</span>
          </p>

          {/* 标签选择 */}
          <div>
            <label className="block text-sm font-medium mb-1.5">
              目标标签 <span className="text-destructive">*</span>
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

          {/* 结构化标注字段（由配置中心 展示COT 开关控制）*/}
          {requireCot && (
            <div className="space-y-3 border border-blue-100 rounded-xl p-4 bg-blue-50/40">
              <p className="text-xs font-medium text-blue-700">
                标注补充信息
                <span className="text-muted-foreground font-normal ml-1">（均为选填，批量操作时所有条目将使用相同的值）</span>
              </p>

              {/* 业务分类 */}
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">业务分类</label>
                <Select value={category} onValueChange={setCategory}>
                  <SelectTrigger className="h-8 text-sm bg-white">
                    <SelectValue placeholder="选择业务分类（可选）" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none" className="text-sm text-muted-foreground">不填写</SelectItem>
                    {categoryOptions.map(c => (
                      <SelectItem key={c.id} value={c.name} className="text-sm">{c.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* 关键词 */}
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">关键词</label>
                <Input
                  value={keywords}
                  onChange={e => setKeywords(e.target.value)}
                  placeholder="输入关键词（可选）"
                  className="h-8 text-sm bg-white"
                />
              </div>

              {/* 关键词说明 */}
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">关键词说明</label>
                <textarea
                  value={keywordsDesc}
                  onChange={e => setKeywordsDesc(e.target.value)}
                  placeholder="对关键词的详细说明（可选）"
                  rows={2}
                  className="w-full text-sm border rounded-lg px-3 py-2 resize-y focus:outline-none focus:ring-2 focus:ring-blue-200 border-gray-200 bg-white placeholder:text-muted-foreground/60"
                />
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>取消</Button>
          <Button onClick={handleConfirm} disabled={submitting || !label}>
            {submitting ? '提交中…' : `确认修改 ${selectedCount} 条`}
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
  const [filters, setFilters]               = useState({})
  const [labelFilter, setLabelFilter]       = useState('all')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [sourceFilter, setSourceFilter]     = useState('all')   // 按上传文件（source_ref）筛选
  const [sourceDeleteOpen, setSourceDeleteOpen] = useState(false)
  const [page, setPage]                     = useState(1)
  const [pageSize, setPageSize]             = useState(10)
  const [sideItem, setSideItem]             = useState(null)
  const [sideMode, setSideMode]             = useState('detail')
  const [datasetId, setDatasetId]           = useState(() => getCurrentDatasetId())
  // 3-dot 菜单（portal 渲染，避免被 Table overflow-auto 裁剪）
  const [menuState, setMenuState] = useState(null) // { item, top, left } | null

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
      setCategoryFilter('all')
      setSourceFilter('all')
      setPage(1)
    }
    window.addEventListener('datasetChanged', handler)
    return () => window.removeEventListener('datasetChanged', handler)
  }, [])

  // 点击页面其他区域关闭 3-dot 菜单
  useEffect(() => {
    if (!menuState) return
    const handler = () => setMenuState(null)
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [menuState])

  // 打开 3-dot 菜单：用 getBoundingClientRect 计算 fixed 坐标，避开 table overflow
  function openMenu(e, item) {
    e.stopPropagation()
    if (menuState?.item?.id === item.id) { setMenuState(null); return }
    const rect       = e.currentTarget.getBoundingClientRect()
    const menuWidth  = 144 // w-36
    const menuHeight = 170 // 大概高度
    const spaceBelow = window.innerHeight - rect.bottom
    const top  = spaceBelow < menuHeight ? rect.top - menuHeight - 4 : rect.bottom + 4
    const left = rect.right - menuWidth
    setMenuState({ item, top, left })
  }

  const { data: labelOptionsRes } = useQuery({
    queryKey: ['label-options', datasetId],
    queryFn:  () => dataApi.labelOptions(datasetId),
    enabled:  !!datasetId,
    staleTime: 30_000,
  })
  const labelOptions = labelOptionsRes?.data?.data || []

  // 配置（用于判断 requireCot）
  const { data: configData } = useQuery({
    queryKey: ['config', datasetId],
    queryFn:  () => configApi.get(datasetId),
    enabled:  !!datasetId,
    staleTime: 60_000,
  })
  const requireCot = configData?.data?.data?.pipeline?.require_cot ?? false

  // 业务分类列表（仅 requireCot 时加载）
  const { data: categoriesData } = useQuery({
    queryKey: ['categories-all', datasetId],
    queryFn:  () => categoryApi.list({ page: 1, page_size: 100 }, datasetId),
    enabled:  !!datasetId && requireCot,
    staleTime: 60_000,
  })
  const categoryOptions = categoriesData?.data?.data?.list ?? []

  // 上传来源文件列表（含各自条数），供「删除该文件全部」用
  const { data: sourcesRes, refetch: refetchSources } = useQuery({
    queryKey: ['data-sources', datasetId],
    queryFn:  () => dataApi.listSources(datasetId),
    enabled:  !!datasetId,
    staleTime: 30_000,
  })
  const sourceOptions = sourcesRes?.data?.data?.sources ?? []
  const selectedSource = sourceOptions.find(s => s.source_ref === sourceFilter)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['explorer', datasetId, filters, labelFilter, categoryFilter, sourceFilter, page, pageSize],
    queryFn: () => dataApi.list({
      status:     filters.status     || undefined,
      keyword:    filters.keyword    || undefined,
      label:      labelFilter !== 'all' ? labelFilter : undefined,
      category:   (requireCot && categoryFilter !== 'all') ? categoryFilter : undefined,
      source_ref: sourceFilter !== 'all' ? sourceFilter : undefined,
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

  const qc = useQueryClient()

  async function handleEditSuccess() {
    // 失效所有 explorer 缓存（含其他过滤/分页参数组合），并强制立即重拉当前页
    await qc.invalidateQueries({ queryKey: ['explorer'] })
    await refetch()
    // 侧边栏正在显示该条 → 同步拉最新条目数据回填，让用户立刻看到新标签
    if (sideItem?.id === editItem?.id) {
      try {
        const res  = await dataApi.getItem(editItem.id)
        const next = res?.data?.data
        if (next) setSideItem(next)
        else closeSide()
      } catch {
        closeSide()
      }
    }
  }

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

  // ── 按上传文件删除（误传整个文件时一键清除）──────────────────────────────────
  const [sourceDeleting, setSourceDeleting] = useState(false)

  async function handleDeleteBySource() {
    if (sourceFilter === 'all') return
    setSourceDeleting(true)
    try {
      const res = await dataApi.deleteBySource(datasetId, sourceFilter)
      const n = res?.data?.data?.deleted_count ?? 0
      toast.success(`已删除来自「${sourceFilter}」的 ${n} 条数据`)
      setSourceFilter('all')
      setSelectedIds(new Set())
      setPage(1)
      qc.invalidateQueries(['explorer'])
      refetchSources()
    } catch {
      toast.error('删除失败')
    } finally {
      setSourceDeleting(false)
    }
  }

  // ── 批量修改标签 ──────────────────────────────────────────────────────────────
  const [batchEditOpen,    setBatchEditOpen]    = useState(false)
  const [batchEditing,     setBatchEditing]     = useState(false)

  async function handleBatchEdit(label, cot, category, keywords, keywordsDesc) {
    const ids = [...selectedIds]
    setBatchEditing(true)
    try {
      const payload = ids.map(id => ({
        data_id: id, label,
        cot: cot || null,
        category: category || null,
        keywords: keywords || null,
        keywords_desc: keywordsDesc || null,
      }))
      const res = await annotationApi.batchSubmit(payload)
      const errors = res?.data?.data?.errors || []
      if (errors.length > 0) {
        toast.warning(`已修改 ${ids.length - errors.length} 条，${errors.length} 条失败`)
      } else {
        toast.success(`已将 ${ids.length} 条数据标注为「${label}」`)
      }
      setBatchEditOpen(false)
      setSelectedIds(new Set())
      qc.invalidateQueries(['explorer'])
      if (sideItem && ids.includes(sideItem.id)) closeSide()
    } catch {
      toast.error('批量修改失败')
    } finally {
      setBatchEditing(false)
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
              <h1 className="text-2xl font-bold">数据管理</h1>
              <p className="text-muted-foreground text-sm mt-1">浏览所有数据，查看标注详情，添加评论</p>
            </div>
            <div className="flex items-center gap-2">
              {selectedIds.size > 0 && (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setBatchEditOpen(true)}
                    disabled={batchEditing}
                    className="border-primary/50 text-primary hover:bg-primary/10"
                  >
                    <Tags className="w-4 h-4 mr-1.5" />
                    改标签 ({selectedIds.size})
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => setBatchConfirmOpen(true)}
                    disabled={batchDeleting}
                  >
                    <Trash2 className="w-4 h-4 mr-1.5" />
                    删除选中 ({selectedIds.size})
                  </Button>
                </>
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
              {/* 标注标签 + 业务分类过滤 */}
              <div className="flex items-center gap-4 flex-wrap">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground whitespace-nowrap">标注标签：</span>
                  <Select
                    value={labelFilter}
                    onValueChange={v => { setLabelFilter(v); setPage(1); setSelectedIds(new Set()) }}
                  >
                    <SelectTrigger className="w-40 h-8 text-xs">
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

                {/* 业务分类过滤（仅 requireCot 时显示）*/}
                {requireCot && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground whitespace-nowrap">业务分类：</span>
                    <Select
                      value={categoryFilter}
                      onValueChange={v => { setCategoryFilter(v); setPage(1); setSelectedIds(new Set()) }}
                    >
                      <SelectTrigger className="w-40 h-8 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">全部分类</SelectItem>
                        {categoryOptions.map(c => (
                          <SelectItem key={c.id} value={c.name}>{c.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {categoryFilter !== 'all' && (
                      <button
                        onClick={() => { setCategoryFilter('all'); setPage(1) }}
                        className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-0.5"
                      >
                        <X className="w-3 h-3" /> 清除
                      </button>
                    )}
                  </div>
                )}

                {/* 来源文件：选中后列表即按该来源筛选（先查看再决定），也可一键删除其全部数据 */}
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground whitespace-nowrap">来源文件：</span>
                  <Select
                    value={sourceFilter}
                    onValueChange={v => { setSourceFilter(v); setPage(1) }}
                  >
                    <SelectTrigger className="w-56 h-8 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部来源</SelectItem>
                      {sourceOptions.map(s => (
                        <SelectItem key={s.source_ref} value={s.source_ref}>
                          {(s.source_ref || '（空）')}（{s.count} 条）
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {sourceFilter !== 'all' && (
                    <Button
                      variant="destructive"
                      size="sm"
                      className="h-8"
                      onClick={() => setSourceDeleteOpen(true)}
                      disabled={sourceDeleting}
                    >
                      <Trash2 className="w-3.5 h-3.5 mr-1.5" />
                      删除该文件全部{selectedSource ? ` ${selectedSource.count} 条` : ''}
                    </Button>
                  )}
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
                    <TableHead className="w-24">状态</TableHead>
                    <TableHead className="w-32">预测标签</TableHead>
                    <TableHead className="w-32">标注标签</TableHead>
                    {requireCot && <TableHead className="w-28">业务分类</TableHead>}
                    {requireCot && <TableHead className="w-44">关键词</TableHead>}
                    <TableHead className="w-40 whitespace-nowrap">更新时间</TableHead>
                    <TableHead className="w-14 text-center">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {isLoading ? (
                    <TableRow>
                      <TableCell colSpan={requireCot ? 11 : 9} className="text-center py-12 text-muted-foreground">
                        <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2" />加载中...
                      </TableCell>
                    </TableRow>
                  ) : items.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={requireCot ? 11 : 9} className="text-center py-12 text-muted-foreground">
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
                    const firstAnn    = item.annotations?.[0]

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
                        {/* 业务分类列 */}
                        {requireCot && (
                          <TableCell className="text-xs">
                            {firstAnn?.category
                              ? <span className="px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded border border-blue-200 whitespace-nowrap">{firstAnn.category}</span>
                              : <span className="text-muted-foreground">—</span>
                            }
                          </TableCell>
                        )}
                        {/* 关键词列 */}
                        {requireCot && (
                          <TableCell className="text-xs max-w-[11rem]">
                            {firstAnn?.keywords ? (
                              <div>
                                <p className="font-medium text-foreground truncate">{firstAnn.keywords}</p>
                                {firstAnn.keywords_desc && (
                                  <p
                                    className="text-muted-foreground line-clamp-1 leading-snug mt-0.5"
                                    title={firstAnn.keywords_desc}
                                  >
                                    {firstAnn.keywords_desc}
                                  </p>
                                )}
                              </div>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </TableCell>
                        )}
                        <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                          {formatDate(item.updated_at)}
                        </TableCell>
                        {/* 3-dot 操作菜单 */}
                        <TableCell onClick={e => e.stopPropagation()}>
                          <div className="flex justify-center">
                            <button
                              onClick={e => openMenu(e, item)}
                              className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                            >
                              <MoreHorizontal className="w-4 h-4" />
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

      <ConfirmDialog
        open={sourceDeleteOpen}
        onOpenChange={setSourceDeleteOpen}
        title="删除该文件的全部数据"
        description={`将永久删除来自「${sourceFilter}」的${selectedSource ? ` ${selectedSource.count} 条` : ''}数据及其标注结果，此操作无法撤销。`}
        confirmLabel={sourceDeleting ? '删除中…' : '确认删除'}
        onConfirm={handleDeleteBySource}
      />

      {/* 单条修改标注标签对话框 */}
      {editItem && (
        <EditAnnotationDialog
          open={editOpen}
          onOpenChange={setEditOpen}
          item={editItem}
          onSuccess={handleEditSuccess}
        />
      )}

      {/* 批量修改标签对话框 */}
      <BatchEditDialog
        open={batchEditOpen}
        onOpenChange={setBatchEditOpen}
        selectedCount={selectedIds.size}
        onConfirm={handleBatchEdit}
        submitting={batchEditing}
      />

      {/* 3-dot 操作菜单 — 用 portal 渲染到 body，position: fixed 避开 table overflow-auto */}
      {menuState && createPortal(
        <div
          style={{ position: 'fixed', top: menuState.top, left: menuState.left, zIndex: 9999 }}
          className="bg-white border rounded-lg shadow-lg py-1 w-36 text-sm"
          onClick={e => e.stopPropagation()}
        >
          <button
            onClick={() => { openDetail(menuState.item); setMenuState(null) }}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-muted transition-colors"
          >
            <Eye className="w-3.5 h-3.5 text-muted-foreground" />查看详情
          </button>
          <button
            onClick={e => { openEdit(menuState.item, e); setMenuState(null) }}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-muted transition-colors"
          >
            <Pencil className="w-3.5 h-3.5 text-muted-foreground" />修改标注
          </button>
          <button
            onClick={() => { openComment(menuState.item); setMenuState(null) }}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-muted transition-colors"
          >
            <MessageSquare className="w-3.5 h-3.5 text-muted-foreground" />添加评论
          </button>
          <div className="border-t my-1" />
          <button
            onClick={() => { requestDelete(menuState.item.id); setMenuState(null) }}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-destructive hover:bg-red-50 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />删除
          </button>
        </div>,
        document.body
      )}
    </div>
  )
}
