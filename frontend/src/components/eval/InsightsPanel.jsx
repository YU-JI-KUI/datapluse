/** 业务洞察：按业务分类切片的表格（样本量 / 进漏斗 / 解决率 / 复核率），可排序。 */
import { useState } from 'react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { RateBar, SectionTitle } from './EvalPrimitives'
import { cn } from '@/lib/utils'

export default function InsightsPanel({ insights }) {
  const [sortKey, setSortKey] = useState('count')
  const rows = insights?.by_intent || []

  const sorted = [...rows].sort((a, b) => {
    if (sortKey === 'count') return (b.count || 0) - (a.count || 0)
    if (sortKey === 'resolved') return (a.resolved_rate || 0) - (b.resolved_rate || 0)  // 差的在前
    return 0
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
        <SectionTitle hint="按业务分类切片，定位问题集中的环节">业务洞察</SectionTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>业务分类</TableHead>
              <Th k="count" className="text-right">样本量</Th>
              <TableHead className="text-right">进漏斗</TableHead>
              <Th k="resolved">端到端解决率</Th>
              <TableHead>需复核率</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">暂无数据</TableCell>
              </TableRow>
            ) : sorted.map((x, i) => (
              <TableRow key={i}>
                <TableCell className="font-medium">{x.name}</TableCell>
                <TableCell className="text-right tabular-nums">{x.count}</TableCell>
                <TableCell className="text-right tabular-nums text-muted-foreground">
                  {x.in_bu_count ?? '—'}
                </TableCell>
                <TableCell><RateBar value={x.resolved_rate} /></TableCell>
                <TableCell className={cn('tabular-nums', (x.needs_review_rate ?? 0) >= 0.4 && 'text-amber-600')}>
                  {Math.round((x.needs_review_rate ?? 0) * 100)}%
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
