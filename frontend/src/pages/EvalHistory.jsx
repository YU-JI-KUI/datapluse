/**
 * AI 评测 · 历史评测：表格展示全部评测任务，点击行查看该任务的评测报告。
 * 每行展示「谁、何时、评测了哪个 BU、什么文件、什么模式、多少样本、当前状态」。
 */
import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { toast } from 'sonner'
import { ArrowLeft, ChevronRight, Loader2, User, Clock } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import TablePagination from '@/components/TablePagination'
import { EvalBadge } from '@/components/eval/EvalPrimitives'
import { evalApi } from '@/lib/api'
import { formatDate } from '@/lib/utils'

const RESP = (r) => r?.data?.data ?? {}

// 任务状态 → 展示文案 + 配色
const STATUS = {
  pending: { label: '待执行', tone: 'slate' },
  running: { label: '评测中', tone: 'info' },
  done:    { label: '已完成', tone: 'good' },
  failed:  { label: '失败',   tone: 'bad' },
}

export default function EvalHistory() {
  const navigate = useNavigate()
  const [list, setList]         = useState([])
  const [total, setTotal]       = useState(0)
  const [page, setPage]         = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [loading, setLoading]   = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    evalApi.listTasks(page, pageSize)
      .then(res => {
        if (cancelled) return
        const d = RESP(res)
        setList(d.list || [])
        setTotal(d.pagination?.total || 0)
      })
      .catch(e => !cancelled && toast.error(e.response?.data?.message || '加载历史评测失败'))
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [page, pageSize])

  // 点击行跳评测页加载该任务报告（评测页按任务状态自行处理）
  function openTask(t) {
    navigate(`/eval?task=${t.task_id}`)
  }

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">历史评测</h1>
          <p className="text-muted-foreground text-sm mt-1">
            全部评测任务记录，点击任意一行查看评测报告。
          </p>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link to="/eval"><ArrowLeft className="w-4 h-4 mr-1.5" />返回评测</Link>
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>文件</TableHead>
                <TableHead>业务单元</TableHead>
                <TableHead>模式</TableHead>
                <TableHead>状态</TableHead>
                <TableHead className="text-right">样本数</TableHead>
                <TableHead>评测人</TableHead>
                <TableHead className="w-40 whitespace-nowrap">完成时间</TableHead>
                <TableHead className="w-10"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-10 text-muted-foreground">
                    <Loader2 className="w-5 h-5 animate-spin inline mr-2" />加载中…
                  </TableCell>
                </TableRow>
              ) : list.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-10 text-muted-foreground">暂无评测记录</TableCell>
                </TableRow>
              ) : list.map(t => {
                const st = STATUS[t.status] || STATUS.pending
                return (
                  <TableRow key={t.task_id} onClick={() => openTask(t)} className="cursor-pointer">
                    <TableCell className="max-w-xs truncate font-medium">{t.filename}</TableCell>
                    <TableCell><EvalBadge tone="brand">{t.bu_name}</EvalBadge></TableCell>
                    <TableCell>
                      {t.mode
                        ? <EvalBadge tone={t.mode === 'calibration' ? 'info' : 'good'}>
                            {t.mode === 'calibration' ? '校准' : '生产'}
                          </EvalBadge>
                        : <span className="text-muted-foreground text-xs">—</span>}
                    </TableCell>
                    <TableCell><EvalBadge tone={st.tone}>{st.label}</EvalBadge></TableCell>
                    <TableCell className="text-right tabular-nums">{t.progress_total || 0}</TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-1 text-sm">
                        <User className="w-3.5 h-3.5 text-muted-foreground" />{t.created_by || '—'}
                      </span>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      <span className="inline-flex items-center gap-1">
                        <Clock className="w-3 h-3" />{formatDate(t.finished_at || t.created_at)}
                      </span>
                    </TableCell>
                    <TableCell><ChevronRight className="w-4 h-4 text-muted-foreground" /></TableCell>
                  </TableRow>
                )
              })}
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
      </Card>
    </div>
  )
}
