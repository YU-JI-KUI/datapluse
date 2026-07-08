/** 业务洞察：按业务分类切片的表格（样本量 / 实际分入本BU / 解决率 / 复核率），可排序。
 *  每行可展开，查看该分类的 AI 优化建议（分发提升 + 解决率提升）。 */
import { useState, Fragment } from 'react'
import { ChevronRight } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { RateBar, SectionTitle } from './EvalPrimitives'
import AdviceMarkdown from './AdviceMarkdown'
import AdviceCardActions from './AdviceCardActions'
import { cn } from '@/lib/utils'

const fmtPct = (n, d) => (d > 0 ? `${Math.round((n / d) * 1000) / 10}%` : '—')

/** 把分类卡按 category 分组 → { 分类名: { dispatch, resolved } }。 */
function groupClassificationCards(adviceCards) {
  const map = {}
  for (const c of adviceCards || []) {
    if (!c || c.category === '全局') continue
    const g = map[c.category] || (map[c.category] = {})
    if (c.dimension === '分发') g.dispatch = c
    else if (c.dimension === '解决率') g.resolved = c
  }
  return map
}

export default function InsightsPanel({ insights, adviceCards, taskId, onRefetch }) {
  const [sortKey, setSortKey] = useState('count')
  const [openCats, setOpenCats] = useState(() => new Set())
  const rows = insights?.by_intent || []
  const totalCount = rows.reduce((s, x) => s + (x.count || 0), 0)   // 全部样本数（占比分母）
  const cardsByCat = groupClassificationCards(adviceCards)

  const sorted = [...rows].sort((a, b) => {
    if (sortKey === 'count') return (b.count || 0) - (a.count || 0)
    if (sortKey === 'resolved') return (a.resolved_rate || 0) - (b.resolved_rate || 0)  // 差的在前
    return 0
  })

  const toggle = (name) => setOpenCats((prev) => {
    const next = new Set(prev)
    next.has(name) ? next.delete(name) : next.add(name)
    return next
  })

  function Th({ k, children, className }) {
    const active = sortKey === k
    return (
      <TableHead
        className={cn('cursor-pointer select-none', className)}
        onClick={() => k && setSortKey(k)}
      >
        {children}{active && <span className="ml-1 text-blue-600">↓</span>}
      </TableHead>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <SectionTitle hint="按业务分类切片，点开某分类查看该业务的 AI 优化建议">业务洞察</SectionTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>业务分类</TableHead>
              <Th k="count" className="text-right">样本量（占比）</Th>
              <TableHead className="text-right" title="该分类中，系统日志实际把问题分给了本BU承接的条数（解决率的分母）">
                实际分入本BU（占比）
              </TableHead>
              <Th k="resolved">问题解决率</Th>
              <TableHead>需复核率</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">暂无数据</TableCell>
              </TableRow>
            ) : sorted.map((x, i) => {
              const cards = cardsByCat[x.name]
              const hasAdvice = cards && (cards.dispatch || cards.resolved)
              const open = openCats.has(x.name)
              return (
                <Fragment key={i}>
                  <TableRow
                    className={cn(hasAdvice && 'cursor-pointer hover:bg-gray-50')}
                    onClick={() => hasAdvice && toggle(x.name)}
                  >
                    <TableCell className="font-medium">
                      <span className="inline-flex items-center gap-1.5">
                        {hasAdvice && (
                          <ChevronRight className={cn('w-4 h-4 text-gray-400 transition-transform', open && 'rotate-90')} />
                        )}
                        {x.name}
                      </span>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {x.count}
                      <span className="ml-1.5 text-xs text-muted-foreground">{fmtPct(x.count, totalCount)}</span>
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {x.in_bu_count ?? '—'}
                      <span className="ml-1.5 text-xs">{fmtPct(x.in_bu_count ?? 0, x.count)}</span>
                    </TableCell>
                    <TableCell><RateBar value={x.resolved_rate} /></TableCell>
                    <TableCell className={cn('tabular-nums', (x.needs_review_rate ?? 0) >= 0.4 && 'text-amber-600')}>
                      {Math.round((x.needs_review_rate ?? 0) * 100)}%
                    </TableCell>
                  </TableRow>
                  {open && hasAdvice && (
                    <TableRow className="bg-gray-50/60">
                      <TableCell colSpan={5} className="px-6 py-4">
                        <div className="space-y-4">
                          {cards.dispatch && (
                            <div>
                              <div className="flex items-center gap-2 mb-1">
                                <h4 className="text-sm font-semibold text-gray-800">分发提升</h4>
                                <AdviceCardActions card={cards.dispatch} taskId={taskId} onRefetch={onRefetch} />
                              </div>
                              <AdviceMarkdown text={cards.dispatch.text} />
                            </div>
                          )}
                          {cards.resolved && (
                            <div>
                              <div className="flex items-center gap-2 mb-1">
                                <h4 className="text-sm font-semibold text-gray-800">解决率提升</h4>
                                <AdviceCardActions card={cards.resolved} taskId={taskId} onRefetch={onRefetch} />
                              </div>
                              <AdviceMarkdown text={cards.resolved.text} />
                            </div>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </Fragment>
              )
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
