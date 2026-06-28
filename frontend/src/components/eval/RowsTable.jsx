/** 逐条明细表：服务端分页（默认每页 10）+ 关键字/业务分类查询 + 不一致/需复核过滤。
 *
 *  - 全部   ：/rows 服务端分页，支持 q(客户问题) / intent(业务分类) 过滤
 *  - 不一致 ：用 result.disagreements（代表样本），前端翻页 + 关键字
 *  - 需复核 ：/rows?flag=review（有限子集），前端翻页 + 关键字
 *  分发场景（正常/该拒未拒…）只在详情页展示，此处分发判定列只看 AI/人工 是否一致。
 */
import { useEffect, useMemo, useState } from 'react'
import { ChevronRight, AlertTriangle, Search } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Input } from '@/components/ui/input'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import TablePagination from '@/components/TablePagination'
import { EvalBadge, YesNo, SectionTitle } from './EvalPrimitives'
import DetailDrawer from './DetailDrawer'
import { evalApi } from '@/lib/api'
import { cn } from '@/lib/utils'

const RESP = (r) => r?.data?.data ?? {}

export default function RowsTable({ taskId, disagreements = [], totalSamples = 0, reviewCount = 0, intentOptions = [] }) {
  const [filter, setFilter] = useState('all')
  const [kw, setKw] = useState('')
  const [intent, setIntent] = useState('all')   // 'all' = 不过滤
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)   // 默认每页 10
  const [active, setActive] = useState(null)

  const [pageRows, setPageRows] = useState([])
  const [serverTotal, setServerTotal] = useState(0)
  const [reviewRows, setReviewRows] = useState([])
  const [loading, setLoading] = useState(false)

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
    evalApi.getRows(taskId, page, pageSize, 'all', q, it)
      .then(res => {
        if (cancelled) return
        const d = RESP(res)
        setPageRows(d.list || [])
        setServerTotal(d.pagination?.total || 0)
      })
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [isAll, taskId, page, pageSize, kw, intent])

  // 「需复核」视图：首次切入拉回有限子集
  useEffect(() => {
    if (filter !== 'review' || !taskId || reviewRows.length) return
    let cancelled = false
    setLoading(true)
    evalApi.getRows(taskId, 1, 500, 'review')
      .then(res => { if (!cancelled) setReviewRows(RESP(res).list || []) })
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [filter, taskId])

  // 子集视图（不一致/需复核）前端搜索 + 分页
  const subsetAll = filter === 'disagree' ? disagreements : filter === 'review' ? reviewRows : []
  const subsetFiltered = useMemo(() => {
    if (isAll) return []
    const q = kw.trim().toLowerCase()
    if (!q) return subsetAll
    return subsetAll.filter(x =>
      (x.question || '').toLowerCase().includes(q) ||
      (x.j_intent || '').toLowerCase().includes(q) ||
      (x.session || '').toLowerCase().includes(q))
  }, [isAll, subsetAll, kw])

  const total = isAll ? serverTotal : subsetFiltered.length
  const display = isAll ? pageRows : subsetFiltered.slice((page - 1) * pageSize, page * pageSize)

  function changeFilter(k) { setFilter(k); setPage(1); setKw(''); setIntent('all') }

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
          {isAll && (
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
          )}
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
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
                <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">加载中…</TableCell>
              </TableRow>
            ) : display.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">暂无数据</TableCell>
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

      <DetailDrawer row={active} open={!!active} onClose={() => setActive(null)} />
    </Card>
  )
}
