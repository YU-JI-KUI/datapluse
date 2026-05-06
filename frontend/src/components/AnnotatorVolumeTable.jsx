import { useQuery } from '@tanstack/react-query'
import { useState, useMemo } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/table'
import { dashboardApi } from '@/lib/api'

// 7 列：用户名 + 今日标注/裁决 + 本周标注/裁决 + 本月标注/裁决
const COLUMNS = [
  { key: 'username',         label: '标注员',     align: 'left'  },
  { key: 'today_annotation', label: '今日标注',   align: 'right' },
  { key: 'today_resolve',    label: '今日裁决',   align: 'right' },
  { key: 'week_annotation',  label: '本周标注',   align: 'right' },
  { key: 'week_resolve',     label: '本周裁决',   align: 'right' },
  { key: 'month_annotation', label: '本月标注',   align: 'right' },
  { key: 'month_resolve',    label: '本月裁决',   align: 'right' },
]

const fmt = (n) => (n == null ? 0 : n).toLocaleString('zh-CN')

export default function AnnotatorVolumeTable({ datasetId }) {
  // 默认排序：今日总量（标注 + 裁决）降序，并列按 username 升序
  const [sortKey, setSortKey] = useState('today_total')
  const [sortDir, setSortDir] = useState('desc')

  const { data: res, isLoading } = useQuery({
    queryKey:                    ['dashboard', 'annotator-stats', datasetId],
    queryFn:                     () => dashboardApi.annotatorStats(datasetId),
    refetchInterval:             15_000,
    refetchIntervalInBackground: true,
    enabled:                     datasetId !== null && datasetId !== undefined,
  })

  const rows = res?.data?.data || []

  const sorted = useMemo(() => {
    const arr = [...rows]
    const dir = sortDir === 'asc' ? 1 : -1
    arr.sort((a, b) => {
      let av, bv
      if (sortKey === 'today_total') {
        av = (a.today_annotation || 0) + (a.today_resolve || 0)
        bv = (b.today_annotation || 0) + (b.today_resolve || 0)
      } else if (sortKey === 'username') {
        return a.username.localeCompare(b.username) * dir
      } else {
        av = a[sortKey] || 0
        bv = b[sortKey] || 0
      }
      if (av !== bv) return (av - bv) * dir
      return a.username.localeCompare(b.username)
    })
    return arr
  }, [rows, sortKey, sortDir])

  function toggleSort(key) {
    if (sortKey === key) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(key === 'username' ? 'asc' : 'desc')
    }
  }

  function SortIcon({ active, dir }) {
    if (!active) return <ArrowUpDown className="w-3 h-3 opacity-40 inline ml-1" />
    return dir === 'asc'
      ? <ArrowUp   className="w-3 h-3 inline ml-1" />
      : <ArrowDown className="w-3 h-3 inline ml-1" />
  }

  if (isLoading) {
    return <p className="text-sm text-muted-foreground py-4">加载中…</p>
  }
  if (!sorted.length) {
    return <p className="text-sm text-muted-foreground py-4">暂无标注记录。完成第一次标注或冲突裁决后将出现在这里。</p>
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          {COLUMNS.map(c => {
            const active = sortKey === c.key
            return (
              <TableHead
                key={c.key}
                onClick={() => toggleSort(c.key)}
                className={`whitespace-nowrap cursor-pointer select-none ${c.align === 'right' ? 'text-right' : ''}`}
              >
                {c.label}
                <SortIcon active={active} dir={sortDir} />
              </TableHead>
            )
          })}
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map(row => (
          <TableRow key={row.username}>
            <TableCell className="py-2 font-medium">{row.username}</TableCell>
            <TableCell className="py-2 text-right tabular-nums">{fmt(row.today_annotation)}</TableCell>
            <TableCell className="py-2 text-right tabular-nums">{fmt(row.today_resolve)}</TableCell>
            <TableCell className="py-2 text-right tabular-nums text-muted-foreground">{fmt(row.week_annotation)}</TableCell>
            <TableCell className="py-2 text-right tabular-nums text-muted-foreground">{fmt(row.week_resolve)}</TableCell>
            <TableCell className="py-2 text-right tabular-nums text-muted-foreground">{fmt(row.month_annotation)}</TableCell>
            <TableCell className="py-2 text-right tabular-nums text-muted-foreground">{fmt(row.month_resolve)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
