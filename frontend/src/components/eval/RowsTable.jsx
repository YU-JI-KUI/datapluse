/** 逐条明细表：过滤（全部/不一致/需复核）+ 搜索 + 分页 + 点击查看详情。 */
import { useMemo, useState } from 'react'
import { ChevronRight, AlertTriangle, Search } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Input } from '@/components/ui/input'
import TablePagination from '@/components/TablePagination'
import { EvalBadge, YesNo, SectionTitle } from './EvalPrimitives'
import DetailDrawer from './DetailDrawer'
import { cn } from '@/lib/utils'

const SCENE_TONE = { 正常: 'good', 该拒未拒: 'bad', 该分未分: 'warn' }

const FILTERS = [
  { key: 'all',      label: '全部' },
  { key: 'disagree', label: '不一致' },
  { key: 'review',   label: '需复核' },
]

export default function RowsTable({ rows = [] }) {
  const [filter, setFilter] = useState('all')
  const [kw, setKw] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [active, setActive] = useState(null)

  const counts = useMemo(() => ({
    all: rows.length,
    disagree: rows.filter(r => r.is_disagreement).length,
    review: rows.filter(r => r.judge?.needs_human_review).length,
  }), [rows])

  const filtered = useMemo(() => {
    let r = rows
    if (filter === 'disagree') r = r.filter(x => x.is_disagreement)
    else if (filter === 'review') r = r.filter(x => x.judge?.needs_human_review)
    if (kw.trim()) {
      const q = kw.trim().toLowerCase()
      r = r.filter(x =>
        (x.question || '').toLowerCase().includes(q) ||
        (x.j_intent || '').toLowerCase().includes(q) ||
        (x.session || '').toLowerCase().includes(q))
    }
    return r
  }, [rows, filter, kw])

  const total = filtered.length
  const pageRows = filtered.slice((page - 1) * pageSize, page * pageSize)

  function changeFilter(k) { setFilter(k); setPage(1) }

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
                {f.label} <span className="tabular-nums">{counts[f.key]}</span>
              </button>
            ))}
          </div>
          <div className="relative w-48">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <Input
              value={kw}
              onChange={e => { setKw(e.target.value); setPage(1) }}
              placeholder="搜索问题 / 分类 / 会话"
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
            {pageRows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">暂无数据</TableCell>
              </TableRow>
            ) : pageRows.map((r, i) => (
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
