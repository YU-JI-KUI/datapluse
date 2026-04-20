import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  AlertTriangle, Play, RefreshCw, CheckCircle, Loader2,
  ShieldAlert, GitMerge, Users, Check, SearchCheck,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { conflictApi, dataApi, configApi, getCurrentDatasetId } from '@/lib/api'
import { formatDate } from '@/lib/utils'

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
  // 语义相似冲突：文本 + 标注并排展示，清晰对照
  return (
    <div className="text-xs space-y-1.5">
      <span className="text-muted-foreground">相似度: <span className="font-semibold text-foreground">{((detail.similarity || 0) * 100).toFixed(1)}%</span></span>
      <div className="space-y-1 mt-1">
        {/* 本条 */}
        <div className="flex items-start gap-1.5">
          <span className="shrink-0 text-muted-foreground w-8 pt-0.5">本条</span>
          <span className="text-foreground truncate max-w-[160px]" title={conflict.data_content}>
            {conflict.data_content || '—'}
          </span>
          {detail.self_label && (
            <span className="shrink-0 px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 font-semibold whitespace-nowrap">{detail.self_label}</span>
          )}
        </div>
        {/* 相似条 */}
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

// ── 解决冲突弹窗 ───────────────────────────────────────────────────────────────
function ResolveDialog({ conflict, labels, open, onOpenChange, onResolved, requireCot = false }) {
  const [selectedLabel, setSelectedLabel] = useState('')
  const [cot, setCot]                      = useState('')
  const [submitting, setSubmitting]        = useState(false)

  if (!conflict) return null

  const detail      = conflict.detail || {}
  const annotators  = detail.annotators || []

  async function handleSubmit() {
    if (!selectedLabel) { toast.error('请选择最终标注标签'); return }
    setSubmitting(true)
    try {
      await conflictApi.resolve(conflict.id, selectedLabel, cot.trim())
      toast.success(`冲突已裁决：「${selectedLabel}」`)
      onOpenChange(false)
      setSelectedLabel('')
      setCot('')
      onResolved()
    } catch (err) {
      toast.error(err.response?.data?.detail || '裁决失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-orange-500" />
            解决冲突 · 数据 #{conflict.data_id}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* 文本内容 */}
          <div>
            <p className="text-xs font-medium text-muted-foreground mb-1.5">待裁决文本</p>
            <div className="bg-muted/50 rounded-lg p-3 text-sm leading-relaxed border">
              {conflict.data_content || '（文本内容不可用）'}
            </div>
          </div>

          {/* 当前各方标注（仅标注分歧时显示）*/}
          {conflict.conflict_type === 'label_conflict' && annotators.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1.5">各方标注意见</p>
              <div className="flex flex-wrap gap-2">
                {annotators.map((a, i) => (
                  <div key={i} className="flex items-center gap-1.5 bg-white border rounded-lg px-3 py-1.5 text-sm">
                    <span className="text-muted-foreground text-xs">{a.username}</span>
                    <span className="font-semibold">{a.label}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 裁决标签选择 */}
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

          {/* 裁决理由（COT，由配置中心控制是否显示，不强制填写）*/}
          {requireCot && (
            <div>
              <p className="text-xs font-medium mb-1.5 flex items-center gap-1">
                裁决理由
                <span className="font-normal text-muted-foreground ml-0.5">（Chain of Thought，选填）</span>
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

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={!selectedLabel || submitting}>
            {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            确认裁决
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ── 主页面 ─────────────────────────────────────────────────────────────────────
export default function ConflictDetection() {
  const qc          = useQueryClient()
  const datasetId   = getCurrentDatasetId()
  const [running, setRunning]           = useState(false)
  const [selfChecking, setSelfChecking] = useState(false)
  const [statusFilter, setStatusFilter] = useState('open')
  const [typeFilter, setTypeFilter]   = useState('all')
  const [resolveTarget, setResolveTarget] = useState(null)   // 当前要解决的 conflict
  const [resolveOpen, setResolveOpen]     = useState(false)

  const { data: annotatedData } = useQuery({
    queryKey: ['annotated-count'],
    queryFn: () => dataApi.list({ status: 'annotated', page: 1, page_size: 1 }),
  })

  const { data: conflictRes, isLoading, refetch } = useQuery({
    queryKey: ['conflicts', statusFilter],
    queryFn: () => conflictApi.list({ status: statusFilter === 'all' ? undefined : statusFilter }),
    refetchInterval: 8000,
  })

  // 从配置中心读取标签列表
  const { data: configData } = useQuery({
    queryKey: ['config', datasetId],
    queryFn: () => configApi.get(datasetId),
    enabled: !!datasetId,
  })
  const configLabels = configData?.data?.data?.labels ?? configData?.data?.labels
  const labels = configLabels || ['寿险意图', '拒识', '健康险意图', '财险意图', '其他意图']
  // requireCot 仅控制是否显示 COT 输入框，不强制填写
  const requireCot = configData?.data?.data?.pipeline?.require_cot ?? false

  const annotatedResult = annotatedData?.data?.data ?? {}
  const annotatedCount  = annotatedResult.pagination?.total || 0

  const allConflicts = conflictRes?.data?.data ?? conflictRes?.data ?? []
  const conflicts    = Array.isArray(allConflicts) ? allConflicts : []

  const displayConflicts = typeFilter === 'all'
    ? conflicts
    : conflicts.filter(c => c.conflict_type === typeFilter)

  const labelConflictCount = conflicts.filter(c => c.conflict_type === 'label_conflict').length
  const resolvedCount      = conflicts.filter(c => c.status === 'resolved').length

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

  function openResolve(conflict) {
    setResolveTarget(conflict)
    setResolveOpen(true)
  }

  return (
    <div className="p-8 space-y-6">
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
          <div><p className="text-xs text-muted-foreground">开放冲突</p><p className="text-2xl font-bold text-red-500">{conflicts.filter(c => c.status === 'open').length}</p></div>
          <ShieldAlert className="w-8 h-8 text-red-400 opacity-80" />
        </CardContent></Card>
        <Card><CardContent className="p-5 flex items-center justify-between">
          <div><p className="text-xs text-muted-foreground">标注分歧</p><p className="text-2xl font-bold text-orange-500">{labelConflictCount}</p></div>
          <Users className="w-8 h-8 text-orange-400 opacity-80" />
        </CardContent></Card>
        <Card><CardContent className="p-5 flex items-center justify-between">
          <div><p className="text-xs text-muted-foreground">已解决</p><p className="text-2xl font-bold text-green-600">{resolvedCount}</p></div>
          <CheckCircle className="w-8 h-8 text-green-500 opacity-80" />
        </CardContent></Card>
      </div>

      {/* Conflict list */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-3">
            <CardTitle className="text-base flex-1 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-orange-500" />冲突列表
            </CardTitle>
            <Select value={typeFilter} onValueChange={setTypeFilter}>
              <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部类型</SelectItem>
                <SelectItem value="label_conflict">标注分歧</SelectItem>
                <SelectItem value="semantic_conflict">语义相似</SelectItem>
              </SelectContent>
            </Select>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部状态</SelectItem>
                <SelectItem value="open">待解决</SelectItem>
                <SelectItem value="resolved">已解决</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-20">数据 ID</TableHead>
                <TableHead>文本内容</TableHead>
                <TableHead className="w-28">冲突类型</TableHead>
                <TableHead>冲突详情</TableHead>
                <TableHead className="w-40 whitespace-nowrap">检测时间</TableHead>
                <TableHead className="w-24 whitespace-nowrap">状态</TableHead>
                <TableHead className="w-28 text-center">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={7} className="text-center py-10 text-muted-foreground">
                  <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />加载中...
                </TableCell></TableRow>
              ) : displayConflicts.length === 0 ? (
                <TableRow><TableCell colSpan={7} className="text-center py-10 text-muted-foreground">
                  {annotatedCount === 0 ? '请先完成人工标注，再运行冲突检测' : '暂无冲突记录，数据质量良好 ✓'}
                </TableCell></TableRow>
              ) : displayConflicts.map(c => (
                <TableRow key={c.id} className={c.status === 'resolved' ? 'opacity-60' : ''}>
                  <TableCell className="font-mono text-xs">#{c.data_id}</TableCell>
                  <TableCell className="max-w-xs">
                    <p className="truncate text-sm" title={c.data_content}>
                      {c.data_content || <span className="text-muted-foreground italic text-xs">加载中…</span>}
                    </p>
                  </TableCell>
                  <TableCell><ConflictTypeBadge type={c.conflict_type} /></TableCell>
                  <TableCell className="max-w-sm"><ConflictDetail conflict={c} /></TableCell>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{formatDate(c.created_at)}</TableCell>
                  <TableCell className="whitespace-nowrap">
                    {c.status === 'resolved'
                      ? <Badge className="bg-green-100 text-green-700 border-0 text-xs whitespace-nowrap">已解决</Badge>
                      : <Badge className="bg-red-100 text-red-700 border-0 text-xs whitespace-nowrap">待解决</Badge>
                    }
                  </TableCell>
                  <TableCell className="text-center">
                    {c.status === 'open' && (
                      <Button
                        size="sm"
                        className="h-7 text-xs"
                        onClick={() => openResolve(c)}
                      >
                        解决冲突
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* 解决冲突弹窗 */}
      <ResolveDialog
        conflict={resolveTarget}
        labels={labels}
        open={resolveOpen}
        onOpenChange={setResolveOpen}
        requireCot={requireCot}
        onResolved={() => {
          refetch()
          qc.invalidateQueries(['annotated-count'])
        }}
      />
    </div>
  )
}
