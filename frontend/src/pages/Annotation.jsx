/**
 * Annotation — 专业标注工作台（v2）
 *
 * 布局：
 *   ┌─────────────────────────────────────────────────────────┐
 *   │ 顶部状态条：全部 N / 未标注 M / 我的标注 K / 进度条        │
 *   ├─────────────────────────┬───────────────────────────────┤
 *   │ 左侧：数据列表           │ 右侧：标注工作区               │
 *   │ [全部][未标注][我的标注]  │  文本内容 → 预标注建议         │
 *   │ ● item (active)          │  当前我的标注（可改 / 撤销）   │
 *   │ ○ item (已标注)          │  标签选择区                   │
 *   └─────────────────────────┴───────────────────────────────┘
 *
 * 关键设计：
 *  - 统一列表：已标注和未标注条目都在侧边栏中显示，不再有底部历史面板
 *  - 过滤 Tab：全部 / 未标注 / 我的标注
 *  - 撤销/修改：只能操作自己的标注（my_annotation 字段由后端按当前用户过滤）
 */

import { useState, useEffect, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  CheckCircle2, Loader2,
  Tag, Cpu, Clock, RotateCcw,
  AlertCircle, Inbox, ChevronLeft, ChevronRight, Search,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Input } from '@/components/ui/input'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { annotationApi, configApi, getCurrentDatasetId } from '@/lib/api'
import { formatDate, scoreColor } from '@/lib/utils'

// ── 标签颜色 ──────────────────────────────────────────────────────────────────

const LABEL_PALETTE = [
  { bg: 'bg-blue-500 hover:bg-blue-600',     ring: 'ring-blue-400',   text: 'text-white', light: 'bg-blue-50 text-blue-700 border-blue-200' },
  { bg: 'bg-violet-500 hover:bg-violet-600', ring: 'ring-violet-400', text: 'text-white', light: 'bg-violet-50 text-violet-700 border-violet-200' },
  { bg: 'bg-green-500 hover:bg-green-600',   ring: 'ring-green-400',  text: 'text-white', light: 'bg-green-50 text-green-700 border-green-200' },
  { bg: 'bg-orange-500 hover:bg-orange-600', ring: 'ring-orange-400', text: 'text-white', light: 'bg-orange-50 text-orange-700 border-orange-200' },
  { bg: 'bg-rose-500 hover:bg-rose-600',     ring: 'ring-rose-400',   text: 'text-white', light: 'bg-rose-50 text-rose-700 border-rose-200' },
  { bg: 'bg-teal-500 hover:bg-teal-600',     ring: 'ring-teal-400',   text: 'text-white', light: 'bg-teal-50 text-teal-700 border-teal-200' },
]

// 默认色：当 label 不在当前 labels 列表里（indexOf 返回 -1）时使用，防止 undefined 崩溃
const LABEL_COLOR_FALLBACK = {
  bg: 'bg-gray-400 hover:bg-gray-500', ring: 'ring-gray-400',
  text: 'text-white', light: 'bg-gray-50 text-gray-700 border-gray-200',
}

function getLabelColor(index) {
  if (index < 0) return LABEL_COLOR_FALLBACK
  return LABEL_PALETTE[index % LABEL_PALETTE.length]
}

// ── 预标注建议卡片 ────────────────────────────────────────────────────────────

function PreAnnotationHint({ preAnn, labels, onAccept }) {
  if (!preAnn) return null
  const idx   = labels.indexOf(preAnn.label)
  const color = idx >= 0 ? getLabelColor(idx).light : 'bg-gray-50 text-gray-700 border-gray-200'
  const score = preAnn.score

  return (
    <div className="border rounded-xl p-3 bg-gradient-to-r from-purple-50 to-violet-50 border-purple-200">
      <div className="flex items-center gap-2 text-xs font-medium text-purple-600 mb-2">
        <Cpu className="w-3.5 h-3.5" /> 模型预标注建议
      </div>
      <div className="flex items-center gap-3">
        <span className={`inline-flex items-center px-3 py-1 rounded-lg border text-sm font-semibold ${color}`}>
          {preAnn.label}
        </span>
        <div className="flex-1">
          <div className="flex justify-between text-xs mb-1">
            <span className="text-muted-foreground">置信度</span>
            <span className={`font-medium ${scoreColor(score)}`}>
              {score != null ? `${(score * 100).toFixed(1)}%` : '-'}
            </span>
          </div>
          {score != null && (
            <div className="h-1.5 rounded-full bg-purple-100 overflow-hidden">
              <div
                className="h-full rounded-full bg-purple-500 transition-all"
                style={{ width: `${(score * 100).toFixed(0)}%` }}
              />
            </div>
          )}
        </div>
        <Button
          size="sm" variant="outline"
          className="text-xs h-8 border-purple-300 text-purple-700 hover:bg-purple-50"
          onClick={() => onAccept(preAnn.label)}
        >
          采纳建议
        </Button>
      </div>
    </div>
  )
}

// ── 过滤 Tab ──────────────────────────────────────────────────────────────────

const VIEWS = [
  { key: 'all',          label: '全部' },
  { key: 'unannotated',  label: '未标注' },
  { key: 'my_annotated', label: '我的标注' },
]

function ViewTabs({ view, onChange, counts }) {
  return (
    <div className="flex border-b shrink-0">
      {VIEWS.map(v => (
        <button
          key={v.key}
          onClick={() => onChange(v.key)}
          className={`flex-1 py-2 text-xs font-medium transition-colors ${
            view === v.key
              ? 'border-b-2 border-blue-500 text-blue-600'
              : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          {v.label}
          {counts[v.key] != null && (
            <span className={`ml-1 text-xs ${view === v.key ? 'text-blue-500' : 'text-muted-foreground'}`}>
              {counts[v.key]}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

// ── 数据侧边栏 ────────────────────────────────────────────────────────────────

function ItemSidebar({ items, currentId, onSelect, loadingId, labels }) {
  return (
    <div className="flex-1 overflow-y-auto">
      {items.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          <Inbox className="w-8 h-8 mx-auto mb-2 opacity-30" />
          <p className="text-sm">暂无数据</p>
        </div>
      ) : items.map(item => {
        const isActive  = item.id === currentId
        const myAnn     = item.my_annotation
        const preAnn    = item.pre_annotation
        const otherCnt  = (item.annotations || []).filter(a => a.is_active).length

        return (
          <button
            key={item.id}
            onClick={() => onSelect(item)}
            disabled={loadingId === item.id}
            className={`w-full text-left px-3 py-2.5 border-b transition-colors ${
              isActive
                ? 'bg-blue-50 border-l-2 border-l-blue-500'
                : 'hover:bg-muted/50'
            }`}
          >
            <div className="flex items-start gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 mb-0.5">
                  <span className="text-xs font-mono text-muted-foreground">#{item.id}</span>
                  {myAnn && (
                    <span className={`inline-flex items-center px-1.5 py-0 rounded text-xs font-medium border ${
                      getLabelColor(labels.indexOf(myAnn.label)).light
                    }`}>
                      {myAnn.label}
                    </span>
                  )}
                </div>
                <p className="text-xs line-clamp-2 leading-snug text-foreground">{item.content}</p>
                {preAnn && !myAnn && (
                  <p className="text-xs text-purple-500 mt-0.5 truncate">
                    <Cpu className="w-2.5 h-2.5 inline mr-0.5" />
                    {preAnn.label}
                  </p>
                )}
                {otherCnt > 0 && (
                  <p className="text-xs text-emerald-600 mt-0.5">
                    共 {otherCnt} 人标注
                  </p>
                )}
              </div>
              {loadingId === item.id && <Loader2 className="w-3 h-3 animate-spin shrink-0 mt-1" />}
            </div>
          </button>
        )
      })}
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

export default function Annotation() {
  const qc = useQueryClient()
  const [datasetId, setDatasetId] = useState(() => getCurrentDatasetId())
  const [currentItem, setCurrentItem] = useState(null)
  const [submitting, setSubmitting]   = useState(false)
  const [revoking, setRevoking]       = useState(false)
  const [cot, setCot]                 = useState('')
  const [view, setView]               = useState('unannotated')
  const [keyword, setKeyword]         = useState('')
  const [keywordInput, setKeywordInput] = useState('')
  const [labelFilter, setLabelFilter] = useState('all')
  const [page, setPage]               = useState(1)
  const [pageSize, setPageSize]       = useState(10)

  const myUsername = localStorage.getItem('username') || ''

  // 数据集切换监听
  useEffect(() => {
    const handler = (e) => {
      setDatasetId(e.detail.datasetId)
      setCurrentItem(null)
      setPage(1)
    }
    window.addEventListener('datasetChanged', handler)
    return () => window.removeEventListener('datasetChanged', handler)
  }, [])

  // 切换 view 时回到第一页，清空当前选中，重置标签过滤
  const handleViewChange = (v) => {
    setView(v)
    setPage(1)
    setLabelFilter('all')
    setCurrentItem(null)
    setCot('')
  }

  // ── 主列表查询 ────────────────────────────────────────────────────────────
  const listKey = ['annotation-items', datasetId, view, page, pageSize, keyword, labelFilter]
  const { data: itemsData, isLoading: listLoading, refetch: refetchList } = useQuery({
    queryKey: listKey,
    queryFn: () => annotationApi.myItems({
      view,
      page,
      page_size: pageSize,
      keyword: keyword || undefined,
      label: (view === 'my_annotated' && labelFilter !== 'all') ? labelFilter : undefined,
    }),
    enabled: !!datasetId,
    refetchInterval: 20000,
  })

  // ── 各 view 的数量（只拉 page_size=1 获取 total）────────────────────────
  const { data: cntAll } = useQuery({
    queryKey: ['ann-cnt-all', datasetId],
    queryFn: () => annotationApi.myItems({ view: 'all', page: 1, page_size: 1 }),
    enabled: !!datasetId,
  })
  const { data: cntUnannotated } = useQuery({
    queryKey: ['ann-cnt-unannotated', datasetId],
    queryFn: () => annotationApi.myItems({ view: 'unannotated', page: 1, page_size: 1 }),
    enabled: !!datasetId,
  })
  const { data: cntMy } = useQuery({
    queryKey: ['ann-cnt-my', datasetId],
    queryFn: () => annotationApi.myItems({ view: 'my_annotated', page: 1, page_size: 1 }),
    enabled: !!datasetId,
  })

  // 标签列表
  const { data: configData } = useQuery({
    queryKey: ['config', datasetId],
    queryFn: () => configApi.get(datasetId),
    enabled: !!datasetId,
  })

  const result    = itemsData?.data?.data  ?? {}
  const items     = result.list            ?? []
  const total     = result.pagination?.total ?? 0
  const totalPages = Math.ceil(total / pageSize) || 1

  const countAll         = cntAll?.data?.data?.pagination?.total          ?? 0
  const countUnannotated = cntUnannotated?.data?.data?.pagination?.total  ?? 0
  const countMy          = cntMy?.data?.data?.pagination?.total           ?? 0
  const progress         = countAll > 0 ? Math.round((countMy / countAll) * 100) : 0

  const configLabels = configData?.data?.data?.labels ?? configData?.data?.labels
  const labels = configLabels || ['寿险意图', '拒识', '健康险意图', '财险意图', '其他意图']

  // requireCot 仅控制是否显示 COT 输入框，不强制填写
  const requireCot = configData?.data?.data?.pipeline?.require_cot ?? false

  // 自动选中第一条（切换 view / 页 时）
  useEffect(() => {
    if (!currentItem && items.length > 0) {
      setCurrentItem(items[0])
    }
  }, [items]) // eslint-disable-line react-hooks/exhaustive-deps

  // 刷新当前 item 数据（从列表中同步最新状态）
  const syncCurrentItem = useCallback((updatedId) => {
    refetchList().then(res => {
      const freshItems = res.data?.data?.data?.list ?? []
      const found = freshItems.find(i => i.id === updatedId)
      if (found) setCurrentItem(found)
    })
  }, [refetchList])

  // 提交标注
  const handleLabel = useCallback(async (label) => {
    if (!currentItem || submitting) return
    setSubmitting(true)
    try {
      await annotationApi.submit(currentItem.id, label, cot.trim() || null)
      toast.success(`已标注：${label}`, { duration: 1500 })
      setCot('')  // 标注后清空 COT

      // 刷新各计数 + 列表
      qc.invalidateQueries(['ann-cnt-all', datasetId])
      qc.invalidateQueries(['ann-cnt-unannotated', datasetId])
      qc.invalidateQueries(['ann-cnt-my', datasetId])

      if (view === 'unannotated') {
        // 未标注模式：标注后自动跳到下一条
        const idx  = items.findIndex(i => i.id === currentItem.id)
        const next = items[idx + 1] ?? items[idx - 1] ?? null
        setCurrentItem(next)
        refetchList()
      } else {
        // 其他模式：留在当前条目，刷新其标注状态
        syncCurrentItem(currentItem.id)
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || '提交失败')
    } finally {
      setSubmitting(false)
    }
  }, [currentItem, submitting, cot, items, view, datasetId, qc, refetchList, syncCurrentItem])

  // 撤销标注（仅自己的）
  const handleRevoke = useCallback(async () => {
    if (!currentItem || revoking) return
    setRevoking(true)
    try {
      await annotationApi.revoke(currentItem.id)
      toast.success('标注已撤销')

      qc.invalidateQueries(['ann-cnt-all', datasetId])
      qc.invalidateQueries(['ann-cnt-unannotated', datasetId])
      qc.invalidateQueries(['ann-cnt-my', datasetId])

      if (view === 'my_annotated') {
        // 我的标注模式：撤销后当前条目消失，跳到下一条
        const idx  = items.findIndex(i => i.id === currentItem.id)
        const next = items[idx + 1] ?? items[idx - 1] ?? null
        setCurrentItem(next)
        refetchList()
      } else {
        syncCurrentItem(currentItem.id)
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || '撤销失败')
    } finally {
      setRevoking(false)
    }
  }, [currentItem, revoking, items, view, datasetId, qc, refetchList, syncCurrentItem])

  // 键盘快捷键（数字键 1-9）：直接提交，COT 不影响快捷键
  useEffect(() => {
    const handler = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
      const n = parseInt(e.key, 10)
      if (n >= 1 && n <= labels.length) {
        handleLabel(labels[n - 1])
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [labels, handleLabel])

  // 当前 item 的预标注 & 当前用户自己的标注
  const preAnn = currentItem?.pre_annotation ?? null
  const myAnn  = currentItem?.my_annotation  ?? null   // 后端已按 my_username 过滤

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      {/* ── 顶部状态条 ── */}
      <div className="border-b bg-white px-6 py-3 shrink-0">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-5 text-sm">
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full bg-gray-400" />
              <span className="text-muted-foreground">全部</span>
              <span className="font-bold text-lg leading-none ml-1">{countAll}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full bg-orange-400" />
              <span className="text-muted-foreground">未标注</span>
              <span className="font-bold text-lg leading-none ml-1">{countUnannotated}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full bg-green-500" />
              <span className="text-muted-foreground">我的标注</span>
              <span className="font-bold text-lg leading-none ml-1">{countMy}</span>
            </div>
          </div>
          <div className="flex-1 max-w-xs">
            <div className="flex justify-between text-xs text-muted-foreground mb-1">
              <span>我的进度</span>
              <span>{progress}%</span>
            </div>
            <Progress value={progress} className="h-1.5" />
          </div>
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-muted-foreground">快捷键：数字 1-{Math.min(labels.length, 9)}</span>
            <Button variant="outline" size="sm" onClick={() => {
              qc.invalidateQueries(['ann-cnt-all', datasetId])
              qc.invalidateQueries(['ann-cnt-unannotated', datasetId])
              qc.invalidateQueries(['ann-cnt-my', datasetId])
              refetchList()
            }}>
              <RotateCcw className="w-3.5 h-3.5 mr-1.5" />刷新
            </Button>
          </div>
        </div>
      </div>

      {/* ── 主体区域 ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── 左侧数据列表 ── */}
        <div className="w-72 border-r bg-gray-50/50 flex flex-col overflow-hidden shrink-0">
          {/* 过滤 Tab */}
          <ViewTabs
            view={view}
            onChange={handleViewChange}
            counts={{ all: countAll, unannotated: countUnannotated, my_annotated: countMy }}
          />

          {/* 关键词搜索 */}
          <div className="px-3 py-2 border-b">
            <form onSubmit={e => { e.preventDefault(); setKeyword(keywordInput); setPage(1); setCurrentItem(null) }}
              className="flex gap-1">
              <Input
                value={keywordInput}
                onChange={e => setKeywordInput(e.target.value)}
                placeholder="搜索文本..."
                className="h-7 text-xs"
              />
              <Button type="submit" size="sm" variant="ghost" className="h-7 px-2">
                <Search className="w-3.5 h-3.5" />
              </Button>
            </form>
          </div>

          {/* 我的标注：按标签过滤 */}
          {view === 'my_annotated' && (
            <div className="px-3 py-2 border-b">
              <Select
                value={labelFilter}
                onValueChange={v => { setLabelFilter(v); setPage(1); setCurrentItem(null) }}
              >
                <SelectTrigger className="h-7 text-xs">
                  <SelectValue placeholder="按标签筛选" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all" className="text-xs">全部标签</SelectItem>
                  {labels.map(l => (
                    <SelectItem key={l} value={l} className="text-xs">{l}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* 数据列表 */}
          {listLoading ? (
            <div className="flex-1 flex items-center justify-center text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin" />
            </div>
          ) : (
            <ItemSidebar
              items={items}
              currentId={currentItem?.id}
              onSelect={setCurrentItem}
              loadingId={submitting ? currentItem?.id : null}
              labels={labels}
            />
          )}

          {/* 分页 */}
          <div className="flex items-center justify-end gap-1.5 px-2 py-2 border-t text-xs text-muted-foreground shrink-0">
            <Select
              value={String(pageSize)}
              onValueChange={v => { setPageSize(Number(v)); setPage(1); setCurrentItem(null) }}
            >
              <SelectTrigger className="h-6 w-[58px] text-xs px-1.5">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {['10','25','50','100'].map(opt => (
                  <SelectItem key={opt} value={opt} className="text-xs">{opt}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="whitespace-nowrap">{page}/{totalPages}</span>
            <button
              disabled={page <= 1}
              onClick={() => { setPage(p => p - 1); setCurrentItem(null) }}
              className="disabled:opacity-40 hover:text-foreground p-0.5"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <button
              disabled={page >= totalPages}
              onClick={() => { setPage(p => p + 1); setCurrentItem(null) }}
              className="disabled:opacity-40 hover:text-foreground p-0.5"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* ── 右侧工作区 ── */}
        <div className="flex-1 overflow-y-auto bg-white">
          {!currentItem ? (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
              {items.length === 0 && !listLoading ? (
                <>
                  <CheckCircle2 className="w-16 h-16 text-green-400 mb-4" />
                  <h3 className="text-lg font-semibold text-foreground mb-1">
                    {view === 'unannotated' ? '没有待标注的数据了！' : '暂无数据'}
                  </h3>
                  {view === 'unannotated' && (
                    <p className="text-sm">已完成本批次所有标注，切换"全部"查看历史记录</p>
                  )}
                </>
              ) : (
                <p className="text-sm">从左侧选择一条数据开始标注</p>
              )}
            </div>
          ) : (
            <div className="max-w-2xl mx-auto p-8 space-y-6">
              {/* 题目标题 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-muted-foreground text-sm">
                  <Tag className="w-4 h-4" />
                  <span>标注任务</span>
                  <span className="font-mono bg-muted px-1.5 py-0.5 rounded text-xs">#{currentItem.id}</span>
                  {/* 最终标注标签（来自 t_annotation_result）*/}
                  {currentItem.label && (
                    <span className={`inline-flex items-center px-2 py-0.5 rounded border text-xs font-medium ${
                      getLabelColor(labels.indexOf(currentItem.label)).light
                    }`}>
                      最终：{currentItem.label}
                      {currentItem.label_source === 'manual' && (
                        <span className="ml-1 text-xs opacity-70">（裁决）</span>
                      )}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Clock className="w-3.5 h-3.5" />
                  {formatDate(currentItem.created_at)}
                </div>
              </div>

              {/* 文本内容卡片 */}
              <Card className="border-2 border-gray-200 shadow-sm">
                <CardContent className="p-6">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3">
                    待标注文本
                  </p>
                  <p className="text-xl leading-relaxed font-medium text-gray-900 break-words">
                    {currentItem.content}
                  </p>
                </CardContent>
              </Card>

              {/* 其他标注人的意见（排除自己）*/}
              {(() => {
                const others = (currentItem.annotations || []).filter(
                  a => a.is_active && a.username !== myUsername
                )
                if (others.length === 0) return null
                return (
                  <div className="border rounded-lg p-3 bg-emerald-50 border-emerald-200">
                    <p className="text-xs font-medium text-emerald-700 mb-2">其他标注人的意见</p>
                    <div className="flex flex-wrap gap-2">
                      {others.map(a => {
                        const idx = labels.indexOf(a.label)
                        const c = idx >= 0 ? getLabelColor(idx).light : 'bg-gray-100 text-gray-700 border-gray-200'
                        return (
                          <div key={a.id} className="bg-white border rounded px-2 py-1.5 text-xs space-y-1">
                            <div className="flex items-center gap-1.5">
                              <span className="text-muted-foreground">{a.username}</span>
                              <span className={`inline-flex items-center px-1.5 py-0.5 rounded border font-medium ${c}`}>
                                {a.label}
                              </span>
                            </div>
                            {a.cot && (
                              <p className="text-muted-foreground leading-snug pl-1 border-l-2 border-emerald-200">
                                {a.cot}
                              </p>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })()}

              {/* 预标注建议 */}
              <PreAnnotationHint
                preAnn={preAnn}
                labels={labels}
                onAccept={(label) => {
                  handleLabel(label)
                }}
              />

              {/* 我的标注状态（修改 / 撤销区域）*/}
              {myAnn && (
                <div className="space-y-1">
                  <div className="flex items-center gap-2 text-sm bg-orange-50 border border-orange-200 rounded-lg px-3 py-2">
                    <AlertCircle className="w-4 h-4 text-orange-500 shrink-0" />
                    <span className="text-orange-700">我的标注</span>
                    <Badge className="bg-orange-100 text-orange-800 border-orange-200 border">{myAnn.label}</Badge>
                    <span className="text-orange-600 text-xs flex-1">点击标签可修改</span>
                    <Button
                      variant="ghost" size="sm"
                      onClick={handleRevoke}
                      disabled={revoking}
                      className="h-7 text-xs text-orange-600 hover:text-destructive hover:bg-red-50 shrink-0"
                    >
                      {revoking
                        ? <Loader2 className="w-3 h-3 animate-spin mr-1" />
                        : <RotateCcw className="w-3 h-3 mr-1" />
                      }
                      撤销标注
                    </Button>
                  </div>
                  {myAnn.cot && (
                    <div className="text-xs text-orange-700 bg-orange-50 border border-orange-100 rounded px-3 py-2">
                      <span className="font-medium">我的理由：</span>{myAnn.cot}
                    </div>
                  )}
                </div>
              )}

              {/* COT 推理过程输入框（由配置中心控制是否显示）*/}
              {requireCot && (
                <div>
                  <p className="text-sm font-medium mb-2 flex items-center gap-1.5">
                    <Tag className="w-4 h-4 text-primary" />
                    标注理由
                    <span className="text-xs text-muted-foreground font-normal ml-1">（Chain of Thought，选填）</span>
                  </p>
                  <textarea
                    value={cot}
                    onChange={e => setCot(e.target.value)}
                    placeholder="可填写标注理由或推理依据，说明为什么选择该标签（选填）"
                    rows={3}
                    className="w-full text-sm border rounded-lg px-3 py-2 resize-y focus:outline-none focus:ring-2 focus:ring-blue-200 border-gray-200 bg-white placeholder:text-muted-foreground/60 transition-colors"
                  />
                </div>
              )}

              {/* 标签选择区 */}
              <div>
                <p className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-1.5">
                  <Tag className="w-4 h-4" />
                  {myAnn ? '修改标签' : '选择标签'}
                  <span className="text-xs text-muted-foreground font-normal ml-1">（或按数字快捷键）</span>
                </p>
                <div className="flex flex-wrap gap-3">
                  {labels.map((label, i) => {
                    const color   = getLabelColor(i)
                    const isMyAnn = myAnn?.label === label
                    return (
                      <button
                        key={label}
                        onClick={() => handleLabel(label)}
                        disabled={submitting}
                        title={`标注为「${label}」`}
                        className={`
                          relative flex items-center gap-2 px-5 py-3 rounded-xl text-sm font-semibold
                          transition-all duration-150 active:scale-95
                          ${isMyAnn
                            ? `${color.bg} ${color.text} ring-2 ${color.ring} ring-offset-2 shadow-md`
                            : `${color.bg} ${color.text} shadow hover:shadow-md cursor-pointer`
                          }
                        `}
                      >
                        <span className="w-5 h-5 rounded-full bg-white/30 flex items-center justify-center text-xs font-bold">
                          {i + 1}
                        </span>
                        {label}
                        {isMyAnn && <CheckCircle2 className="w-4 h-4" />}
                        {submitting && <Loader2 className="w-3 h-3 animate-spin absolute right-2 top-2" />}
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* 导航按钮 */}
              <div className="flex items-center justify-between pt-2 border-t">
                <Button
                  variant="outline" size="sm"
                  disabled={items.findIndex(i => i.id === currentItem.id) <= 0}
                  onClick={() => {
                    const idx = items.findIndex(i => i.id === currentItem.id)
                    if (idx > 0) setCurrentItem(items[idx - 1])
                  }}
                >
                  <ChevronLeft className="w-4 h-4 mr-1" />上一条
                </Button>
                <span className="text-xs text-muted-foreground">
                  {items.findIndex(i => i.id === currentItem.id) + 1} / {items.length} 条（第 {page} 页）
                </span>
                <Button
                  variant="outline" size="sm"
                  disabled={items.findIndex(i => i.id === currentItem.id) >= items.length - 1}
                  onClick={() => {
                    const idx = items.findIndex(i => i.id === currentItem.id)
                    if (idx < items.length - 1) setCurrentItem(items[idx + 1])
                  }}
                >
                  下一条<ChevronRight className="w-4 h-4 ml-1" />
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
