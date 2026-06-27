/** 逐条明细表：服务端分页（百万级不再全量加载）。
 *
 * 三种视图：
 *  - 全部   ：走 /rows 分页接口，按 row_index 翻页
 *  - 不一致 ：用 result.disagreements（后端代表样本，≤上限），前端翻页 + 搜索
 *  - 需复核 ：走 /rows?flag=review（有限子集），前端翻页 + 搜索
 * 「全部」视图数据量可达百万，不提供前端全量搜索（搜索仅在不一致/需复核子集内生效）。
 */
import { useEffect, useMemo, useState } from 'react'
import { ChevronRight, AlertTriangle, Search } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Input } from '@/components/ui/input'
import TablePagination from '@/components/TablePagination'
import { EvalBadge, YesNo, SectionTitle } from './EvalPrimitives'
import DetailDrawer from './DetailDrawer'
import { evalApi } from '@/lib/api'
import { cn } from '@/lib/utils'

const RESP = (r) => r?.data?.data ?? {}   // datapulse 统一响应：res.data.data
const SCENE_TONE = { 正常: 'good', 该拒未拒: 'bad', 该分未分: 'warn' }

export default function RowsTable({ taskId, disagreements = [], totalSamples = 0, reviewCount = 0 }) {
  const [filter, setFilter] = useState('all')
  const [kw, setKw] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [active, setActive] = useState(null)

  // 全部：服务端分页结果；needs_review：一次拉回有限子集
  const [pageRows, setPageRows] = useState([])
  const [serverTotal, setServerTotal] = useState(0)
  const [reviewRows, setReviewRows] = useState([])
  const [loading, setLoading] = useState(false)

  const FILTERS = [
    { key: 'all',      label: '全部',   count: totalSamples },
    { key: 'disagree', label: '不一致', count: disagreements.length },
    { key: 'review',   label: '需复核', count: reviewCount },
  ]

  // 「全部」视图：随页码/页大小拉服务端分页
  useEffect(() => {
    if (filter !== 'all' || !taskId) return
    let cancelled = false
    setLoading(true)
    evalApi.getRows(taskId, page, pageSize, 'all')
      .then(res => {
        if (cancelled) return
        const d = RESP(res)
        setPageRows(d.list || [])
        setServerTotal(d.pagination?.total || 0)
      })
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [filter, taskId, page, pageSize])

  // 「需复核」视图：首次切入时拉回有限子集（之后前端翻页/搜索）
  useEffect(() => {
    if (filter !== 'review' || !taskId || reviewRows.length) return
    let cancelled = false
    setLoading(true)
    evalApi.getRows(taskId, 1, 500, 'review')
      .then(res => { if (!cancelled) setReviewRows(RESP(res).list || []) })
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [filter, taskId])

  // 子集视图（不一致/需复核）在前端做搜索 + 分页
  const subsetAll = filter === 'disagree' ? disagreements : filter === 'review' ? reviewRows : []
  const subsetFiltered = useMemo(() => {
    if (filter === 'all') return []
    const q = kw.trim().toLowerCase()
    if (!q) return subsetAll
    return subsetAll.filter(x =>
      (x.question || '').toLowerCase().includes(q) ||
      (x.j_intent || '').toLowerCase().includes(q) ||
      (x.session || '').toLowerCase().includes(q))
  }, [filter, subsetAll, kw])

  // 当前页数据 + 总数：全部走服务端，子集走前端切片
  const isAll = filter === 'all'
  const total = isAll ? serverTotal : subsetFiltered.length
  const display = isAll ? pageRows : subsetFiltered.slice((page - 1) * pageSize, page * pageSize)

  function changeFilter(k) { setFilter(k); setPage(1); setKw('') }

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
          <div className="relative w-48">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <Input
              value={kw}
              onChange={e => { setKw(e.target.value); setPage(1) }}
              disabled={isAll}
              placeholder={isAll ? '搜索仅限子集视图' : '搜索问题 / 分类 / 会话'}
              className="pl-7 h-8 text-sm"
            />
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-40">会话 / 轮次</TableHead>
              <TableHead>客户问题</TableHead>
              <TableHead>业务分类</TableHead>
              <TableHead>分发场景</TableHead>
              <TableHead>解决（AI / 人工）</TableHead>
              <TableHead className="w-12"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">加载中…</TableCell>
              </TableRow>
            ) : display.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">暂无数据</TableCell>
              </TableRow>
            ) : display.map((r, i) => (
              <TableRow
                key={r.row_index ?? i}
                onClick={() => setActive(r)}
                className={cn('cursor-pointer', r.is_disagreement && 'bg-red-50/40')}
              >
                <TableCell>
                  <div className="font-mono text-xs truncate max-w-[140px]">{r.session}</div>
                  <span className="inline-block mt-0.5 rounded bg-gray-100 px-1.5 text-[11px]">第 {r.turn} 轮</span>
                </TableCell>
                <TableCell className="max-w-xs truncate">{r.question}</TableCell>
                <TableCell>{r.j_intent ? <EvalBadge tone="brand">{r.j_intent}</EvalBadge> : '—'}</TableCell>
                <TableCell>
                  {r.dispatch_scene
                    ? <EvalBadge tone={SCENE_TONE[r.dispatch_scene] || 'slate'}>{r.dispatch_scene}</EvalBadge>
                    : '—'}
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

      <DetailDrawer row={active} open={!!active} onClose={() => setActive(null)} />
    </Card>
  )
}
