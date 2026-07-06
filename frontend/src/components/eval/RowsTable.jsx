/** 逐条明细表：服务端分页（默认每页 10）+ 关键字/业务分类查询 + 不一致/需复核过滤。
 *
 *  - 全部   ：/rows 服务端分页，支持 q(客户问题) / intent(业务分类) 过滤
 *  - 不一致 ：用 result.disagreements（代表样本），前端翻页 + 关键字
 *  - 需复核 ：/rows?flag=review（有限子集），前端翻页 + 关键字
 *  分发场景（正常/该拒未拒…）只在详情页展示，此处分发判定列只看 AI/人工 是否一致。
 */
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { ChevronRight, AlertTriangle, Search, Zap, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import TablePagination from '@/components/TablePagination'
import { EvalBadge, YesNo, SectionTitle } from './EvalPrimitives'
import DetailDrawer from './DetailDrawer'
import { evalApi } from '@/lib/api'
import { cn } from '@/lib/utils'

const RESP = (r) => r?.data?.data ?? {}

export default function RowsTable({ taskId, disagreements = [], totalSamples = 0, reviewCount = 0, intentOptions = [], buOptions = [] }) {
  const [filter, setFilter] = useState('all')
  const [kw, setKw] = useState('')
  const [intent, setIntent] = useState('all')   // 'all' = 不过滤
  const [buKw, setBuKw] = useState('all')       // 分发BU：'all'=不过滤，否则为具体 BU 值
  const [dispatchF, setDispatchF] = useState('all')  // 分发判定 是/否/all
  const [resolvedF, setResolvedF] = useState('all')  // 是否解决 是/否/all
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)   // 默认每页 10
  const [active, setActive] = useState(null)

  const [pageRows, setPageRows] = useState([])
  const [serverTotal, setServerTotal] = useState(0)
  const [reviewRows, setReviewRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)   // 复核提交/撤销后自增，触发明细重拉

  // 复核成功后：触发当前视图重拉（reloadKey 变会同时驱动「全部」和「需复核」两个 effect）
  function onReviewed() {
    setReloadKey(k => k + 1)
  }

  const [rerunOpen, setRerunOpen] = useState(false)
  const [rerunning, setRerunning] = useState(false)
  const [selected, setSelected] = useState(() => new Set())   // 勾选的 row_index

  function toggleRow(idx) {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(idx) ? next.delete(idx) : next.add(idx)
      return next
    })
  }
  function toggleAllOnPage(rows, checked) {
    setSelected(prev => {
      const next = new Set(prev)
      rows.forEach(r => { if (r.row_index != null) checked ? next.add(r.row_index) : next.delete(r.row_index) })
      return next
    })
  }

  // 勾选行重跑（异步）：提交后立即返回，前端刷新任务状态看进度；完成后指标全量重算
  async function handleRerunSelected() {
    setRerunning(true)
    try {
      const r = await evalApi.rerunRows(taskId, [...selected])
      const n = RESP(r).count ?? selected.size
      toast.success(`已提交重跑 ${n} 条，后台运行中；完成后重进结果页查看新指标`)
      setSelected(new Set())
      setReloadKey(k => k + 1)
    } catch (e) {
      toast.error(e.response?.data?.message || '重跑提交失败')
    } finally {
      setRerunning(false)
      setRerunOpen(false)
    }
  }

  const isAll = filter === 'all'

  const FILTERS = [
    { key: 'all',      label: '全部',   count: totalSamples },
    { key: 'disagree', label: '不一致', count: disagreements.length },
    { key: 'review',   label: '需复核', count: reviewCount },
  ]

  // 「全部」视图：服务端分页 + 关键字/业务分类过滤
  useEffect(() => {
    if (!isAll || !taskId) return
    let cancelled = false
    setLoading(true)
    const q = kw.trim()
    const it = intent === 'all' ? '' : intent
    const extra = {
      dispatched_bu: buKw === 'all' ? '' : buKw,
      j_dispatch: dispatchF === 'all' ? '' : dispatchF,
      j_resolved: resolvedF === 'all' ? '' : resolvedF,
    }
    evalApi.getRows(taskId, page, pageSize, 'all', q, it, extra)
      .then(res => {
        if (cancelled) return
        const d = RESP(res)
        setPageRows(d.list || [])
        setServerTotal(d.pagination?.total || 0)
      })
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [isAll, taskId, page, pageSize, kw, intent, buKw, dispatchF, resolvedF, reloadKey])

  // 「需复核」视图：切入或复核后(reloadKey 变)重拉待复核子集。
  // 不再用 reviewRows.length 做缓存判断——否则复核完清不掉旧数据、也拉不到新的。
  useEffect(() => {
    if (filter !== 'review' || !taskId) return
    let cancelled = false
    setLoading(true)
    evalApi.getRows(taskId, 1, 500, 'review')
      .then(res => { if (!cancelled) setReviewRows(RESP(res).list || []) })
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [filter, taskId, reloadKey])

  // 子集视图（不一致/需复核）前端搜索 + 分页
  const subsetAll = filter === 'disagree' ? disagreements : filter === 'review' ? reviewRows : []
  const subsetFiltered = useMemo(() => {
    if (isAll) return []
    const q = kw.trim().toLowerCase()
    return subsetAll.filter(x => {
      if (q && !(
        (x.question || '').toLowerCase().includes(q) ||
        (x.j_intent || '').toLowerCase().includes(q) ||
        (x.session || '').toLowerCase().includes(q))) return false
      if (intent !== 'all' && (x.j_intent || '') !== intent) return false
      if (buKw !== 'all' && (x.dispatched_bu || '') !== buKw) return false
      if (dispatchF !== 'all' && (x.j_dispatch || '') !== dispatchF) return false
      if (resolvedF !== 'all' && (x.j_resolved || '') !== resolvedF) return false
      return true
    })
  }, [isAll, subsetAll, kw, intent, buKw, dispatchF, resolvedF])

  const total = isAll ? serverTotal : subsetFiltered.length
  const display = isAll ? pageRows : subsetFiltered.slice((page - 1) * pageSize, page * pageSize)

  function changeFilter(k) {
    setFilter(k); setPage(1); setKw(''); setIntent('all')
    setBuKw('all'); setDispatchF('all'); setResolvedF('all')
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center gap-3">
          <SectionTitle hint="逐条评测明细">明细</SectionTitle>
          <div className="flex items-center gap-1 ml-auto">
            {FILTERS.map(f => (
              <button
                key={f.key}
                onClick={() => changeFilter(f.key)}
                className={cn(
                  'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
                  filter === f.key ? 'bg-blue-100 text-blue-700' : 'text-muted-foreground hover:bg-accent',
                )}
              >
                {f.label} <span className="tabular-nums">{f.count}</span>
              </button>
            ))}
          </div>
        </div>

        {/* 查询条件 */}
        <div className="flex flex-wrap items-center gap-2 mt-2">
          <div className="relative w-56">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <Input
              value={kw}
              onChange={e => { setKw(e.target.value); setPage(1) }}
              placeholder="搜索客户问题"
              className="pl-7 h-8 text-sm"
            />
          </div>
          <Select value={intent} onValueChange={v => { setIntent(v); setPage(1) }}>
            <SelectTrigger className="h-8 w-44 text-sm">
              <SelectValue placeholder="业务分类" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部业务分类</SelectItem>
              {intentOptions.map(name => (
                <SelectItem key={name} value={name}>{name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={buKw} onValueChange={v => { setBuKw(v); setPage(1) }}>
            <SelectTrigger className="h-8 w-36 text-sm"><SelectValue placeholder="分发BU" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部分发BU</SelectItem>
              {buOptions.map(name => (
                <SelectItem key={name} value={name}>{name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={dispatchF} onValueChange={v => { setDispatchF(v); setPage(1) }}>
            <SelectTrigger className="h-8 w-32 text-sm"><SelectValue placeholder="分发判定" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">分发判定(全部)</SelectItem>
              <SelectItem value="是">分发·是</SelectItem>
              <SelectItem value="否">分发·否</SelectItem>
            </SelectContent>
          </Select>
          <Select value={resolvedF} onValueChange={v => { setResolvedF(v); setPage(1) }}>
            <SelectTrigger className="h-8 w-32 text-sm"><SelectValue placeholder="是否解决" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">是否解决(全部)</SelectItem>
              <SelectItem value="是">解决·是</SelectItem>
              <SelectItem value="否">解决·否</SelectItem>
            </SelectContent>
          </Select>
          {selected.size > 0 && (
            <Button variant="outline" size="sm" className="ml-auto h-8"
              onClick={() => setRerunOpen(true)} disabled={rerunning}>
              {rerunning ? <><Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />提交中…</>
                : <><Zap className="w-3.5 h-3.5 mr-1.5" />用最新提示词重跑选中（{selected.size}）</>}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <input
                  type="checkbox"
                  className="align-middle cursor-pointer"
                  title="全选本页"
                  checked={display.length > 0 && display.every(r => selected.has(r.row_index))}
                  onChange={e => toggleAllOnPage(display, e.target.checked)}
                />
              </TableHead>
              <TableHead className="w-40">会话 / 轮次</TableHead>
              <TableHead>客户问题</TableHead>
              <TableHead>业务分类</TableHead>
              <TableHead>分发BU</TableHead>
              <TableHead>分发判定（AI / 人工）</TableHead>
              <TableHead>解决（AI / 人工）</TableHead>
              <TableHead className="w-12"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">加载中…</TableCell>
              </TableRow>
            ) : display.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">暂无数据</TableCell>
              </TableRow>
            ) : display.map((r, i) => (
              <TableRow
                key={r.row_index ?? i}
                onClick={() => setActive(r)}
                className={cn('cursor-pointer', r.is_disagreement && 'bg-red-50/40',
                  selected.has(r.row_index) && 'bg-blue-50/60')}
              >
                <TableCell onClick={e => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    className="align-middle cursor-pointer"
                    checked={selected.has(r.row_index)}
                    disabled={r.row_index == null}
                    onChange={() => toggleRow(r.row_index)}
                  />
                </TableCell>
                <TableCell>
                  <div className="font-mono text-xs truncate max-w-[140px]">{r.session}</div>
                  <span className="inline-block mt-0.5 rounded bg-gray-100 px-1.5 text-[11px]">第 {r.turn} 轮</span>
                </TableCell>
                <TableCell className="max-w-xs truncate">{r.question}</TableCell>
                <TableCell>{r.j_intent ? <EvalBadge tone="brand">{r.j_intent}</EvalBadge> : '—'}</TableCell>
                <TableCell className="text-sm">
                  {r.dispatched_bu || <span className="text-muted-foreground text-xs">—</span>}
                </TableCell>
                <TableCell>
                  <div className={cn('inline-flex items-center gap-2 rounded-md px-1.5 py-0.5',
                    r.disagree_dispatch && 'ring-1 ring-red-300')}>
                    {r.j_dispatch === '是' || r.j_dispatch === '否'
                      ? <YesNo value={r.j_dispatch} />
                      : <span className="text-muted-foreground text-xs">—</span>}
                    <span className="text-muted-foreground text-xs">/</span>
                    {r.gold?.dispatch === '是' || r.gold?.dispatch === '否'
                      ? <YesNo value={r.gold.dispatch} />
                      : <span className="text-muted-foreground text-xs">—</span>}
                  </div>
                </TableCell>
                <TableCell>
                  <div className={cn('inline-flex items-center gap-2 rounded-md px-1.5 py-0.5',
                    r.disagree_resolved && 'ring-1 ring-red-300')}>
                    <YesNo value={r.j_resolved} />
                    <span className="text-muted-foreground text-xs">/</span>
                    {r.gold?.resolved === '是' || r.gold?.resolved === '否'
                      ? <YesNo value={r.gold.resolved} />
                      : <span className="text-muted-foreground text-xs">—</span>}
                  </div>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1 text-muted-foreground">
                    {r.judge?.needs_human_review && <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />}
                    <ChevronRight className="w-4 h-4" />
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
      </CardContent>

      <DetailDrawer row={active} open={!!active} onClose={() => setActive(null)}
        taskId={taskId} intentOptions={intentOptions} onReviewed={onReviewed} />

      <ConfirmDialog
        open={rerunOpen}
        onOpenChange={v => { if (!v) setRerunOpen(false) }}
        title="用最新提示词重跑选中"
        description={`将对选中的 ${selected.size} 条用最新提示词（含业务知识）重新评测，`
          + `覆盖它们的 AI 判定并全量重算指标。会调用大模型；已人工复核过的行会自动跳过。`
          + `后台运行，完成后重进结果页查看新指标。`}
        confirmLabel="提交重跑"
        onConfirm={handleRerunSelected}
      />
    </Card>
  )
}
