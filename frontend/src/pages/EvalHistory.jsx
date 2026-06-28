/**
 * AI 评测 · 历史评测：表格展示全部评测记录，支持查看报告 / 重测 / 删除。
 * 每行展示「谁、何时开始/完成、评测了哪个 BU、什么文件、什么模式、多少样本、状态」。
 */
import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { toast } from 'sonner'
import { ArrowLeft, Loader2, User, Eye, RotateCcw, Trash2 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import TablePagination from '@/components/TablePagination'
import { EvalBadge } from '@/components/eval/EvalPrimitives'
import { evalApi } from '@/lib/api'
import { formatDate } from '@/lib/utils'

const RESP = (r) => r?.data?.data ?? {}

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
  const [delTarget, setDelTarget] = useState(null)   // 待删除的任务

  function load() {
    setLoading(true)
    evalApi.listTasks(page, pageSize)
      .then(res => {
        const d = RESP(res)
        setList(d.list || [])
        setTotal(d.pagination?.total || 0)
      })
      .catch(e => toast.error(e.response?.data?.message || '加载历史评测失败'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [page, pageSize])

  // 全局 BU 切换时刷新（列表已按当前 BU 过滤）
  useEffect(() => {
    const onBuChange = () => { setPage(1); load() }
    window.addEventListener('buChanged', onBuChange)
    return () => window.removeEventListener('buChanged', onBuChange)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleRerun(t) {
    try {
      await evalApi.rerun(t.task_id)
      toast.success('已重新发起评测')
      load()
    } catch (e) {
      toast.error(e.response?.data?.message || '重测失败')
    }
  }

  async function handleDelete() {
    if (!delTarget) return
    try {
      await evalApi.remove(delTarget.task_id)
      toast.success('已删除')
      load()
    } catch (e) {
      toast.error(e.response?.data?.message || '删除失败')
    }
  }

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">历史评测</h1>
          <p className="text-muted-foreground text-sm mt-1">
            全部评测记录，可查看报告、重新评测或删除。
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
                <TableHead className="w-40 whitespace-nowrap">开始时间</TableHead>
                <TableHead className="w-40 whitespace-nowrap">完成时间</TableHead>
                <TableHead className="w-28 text-center">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-10 text-muted-foreground">
                    <Loader2 className="w-5 h-5 animate-spin inline mr-2" />加载中…
                  </TableCell>
                </TableRow>
              ) : list.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-10 text-muted-foreground">暂无评测记录</TableCell>
                </TableRow>
              ) : list.map(t => {
                const st = STATUS[t.status] || STATUS.pending
                const canView = t.status === 'done'
                return (
                  <TableRow key={t.task_id}>
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
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{formatDate(t.created_at)}</TableCell>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{t.finished_at ? formatDate(t.finished_at) : '—'}</TableCell>
                    <TableCell>
                      <div className="flex items-center justify-center gap-1">
                        <button
                          title="查看报告"
                          disabled={!canView}
                          onClick={() => navigate(`/eval/report/${t.task_id}`)}
                          className="p-1.5 rounded hover:bg-accent disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <button
                          title="重新评测"
                          onClick={() => handleRerun(t)}
                          className="p-1.5 rounded hover:bg-accent"
                        >
                          <RotateCcw className="w-4 h-4" />
                        </button>
                        <button
                          title="删除"
                          onClick={() => setDelTarget(t)}
                          className="p-1.5 rounded hover:bg-red-50 text-red-500"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </TableCell>
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

      <ConfirmDialog
        open={!!delTarget}
        onOpenChange={v => { if (!v) setDelTarget(null) }}
        title="删除评测记录"
        description={`将删除「${delTarget?.filename || ''}」的评测任务及全部逐条结果，不可恢复。`}
        confirmLabel="删除"
        onConfirm={handleDelete}
      />
    </div>
  )
}
