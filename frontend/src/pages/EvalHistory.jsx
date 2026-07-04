/**
 * AI 评测 · 历史评测：表格展示当前 BU 的评测记录，支持查看报告 / 重测 / 删除。
 * 每行展示「文件、模式、状态(评测中显示进度%)、样本数、评测人、开始/完成时间」。
 * 列表按左侧全局 BU 过滤，故不再单列业务单元。
 */
import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { toast } from 'sonner'
import { ArrowLeft, Loader2, User, Eye, RotateCcw, Trash2, Search, X } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import TablePagination from '@/components/TablePagination'
import { EvalBadge } from '@/components/eval/EvalPrimitives'
import { evalApi } from '@/lib/api'
import { formatDate, cn } from '@/lib/utils'

const RESP = (r) => r?.data?.data ?? {}

const STATUS = {
  pending:     { label: '待执行',   tone: 'slate' },
  running:     { label: '评测中',   tone: 'info' },
  paused:      { label: '限流暂停', tone: 'warn' },
  interrupted: { label: '恢复中',   tone: 'warn' },
  done:        { label: '已完成',   tone: 'good' },
  failed:      { label: '失败',     tone: 'bad' },
}

export default function EvalHistory() {
  const navigate = useNavigate()
  const [list, setList]         = useState([])
  const [total, setTotal]       = useState(0)
  const [page, setPage]         = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [loading, setLoading]   = useState(false)
  const [delTarget, setDelTarget] = useState(null)   // 待删除的任务
  const [rerunTarget, setRerunTarget] = useState(null)   // 待重测的任务
  const [keyword, setKeyword]   = useState('')       // 文件名搜索框实时值（受控）
  const [debKeyword, setDebKeyword] = useState('')   // 防抖后的关键字，真正参与查询
  const [mode, setMode]         = useState('all')    // 模式过滤：all/calibration/production

  // 输入防抖 300ms：停止输入后才更新 debKeyword，触发查询并回到第 1 页
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebKeyword(keyword.trim())
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [keyword])

  // silent=true：轮询静默刷新，不显示「加载中」遮罩，只更新数据（状态列随之变化）
  function load(silent = false) {
    if (!silent) setLoading(true)
    evalApi.listTasks(page, pageSize, { keyword: debKeyword, mode: mode === 'all' ? '' : mode })
      .then(res => {
        const d = RESP(res)
        setList(d.list || [])
        setTotal(d.pagination?.total || 0)
      })
      .catch(e => { if (!silent) toast.error(e.response?.data?.message || '加载历史评测失败') })
      .finally(() => { if (!silent) setLoading(false) })
  }

  useEffect(() => { load() }, [page, pageSize, debKeyword, mode])  // eslint-disable-line react-hooks/exhaustive-deps

  // 全局 BU 切换时刷新（列表已按当前 BU 过滤）
  useEffect(() => {
    const onBuChange = () => { setPage(1); load() }
    window.addEventListener('buChanged', onBuChange)
    return () => window.removeEventListener('buChanged', onBuChange)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 有进行中/暂停/恢复中的任务时每 10 秒静默刷新（这些状态会自动流转）
  useEffect(() => {
    const active = new Set(['running', 'paused', 'interrupted'])
    if (!list.some(t => active.has(t.status))) return
    const timer = setInterval(() => load(true), 10000)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list])

  async function handleRerun() {
    if (!rerunTarget) return
    try {
      await evalApi.rerun(rerunTarget.task_id)
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

      {/* 搜索筛选栏：文件名关键字（防抖）+ 模式 */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative w-72">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
            placeholder="按文件名搜索…"
            className="pl-8 pr-8 h-9"
          />
          {keyword && (
            <button
              title="清空"
              onClick={() => setKeyword('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded hover:bg-accent text-muted-foreground"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
        <Select value={mode} onValueChange={v => { setMode(v); setPage(1) }}>
          <SelectTrigger className="h-9 w-32">
            <SelectValue placeholder="全部模式" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部模式</SelectItem>
            <SelectItem value="calibration">校准</SelectItem>
            <SelectItem value="production">生产</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>文件</TableHead>
                <TableHead>模式</TableHead>
                <TableHead className="w-44">状态</TableHead>
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
                const canView = t.status === 'done'
                return (
                  <TableRow key={t.task_id}>
                    <TableCell className="max-w-xs truncate font-medium">{t.filename}</TableCell>
                    <TableCell>
                      {t.mode
                        ? <EvalBadge tone={t.mode === 'calibration' ? 'info' : 'good'}>
                            {t.mode === 'calibration' ? '校准' : '生产'}
                          </EvalBadge>
                        : <span className="text-muted-foreground text-xs">—</span>}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <EvalBadge tone={st.tone}>{st.label}</EvalBadge>
                        {['running', 'paused', 'interrupted'].includes(t.status) && (
                          <div className="flex items-center gap-1.5 flex-1 min-w-0">
                            <div className="h-1.5 flex-1 rounded-full bg-gray-200 overflow-hidden min-w-[40px]">
                              <div className={cn('h-full transition-all', t.status === 'paused' ? 'bg-amber-500' : 'bg-blue-500')}
                                   style={{ width: `${t.progress_pct || 0}%` }} />
                            </div>
                            <span className="text-xs text-muted-foreground tabular-nums shrink-0">
                              {t.progress_pct ?? 0}%
                            </span>
                          </div>
                        )}
                      </div>
                    </TableCell>
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
                          onClick={() => setRerunTarget(t)}
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

      <ConfirmDialog
        open={!!rerunTarget}
        onOpenChange={v => { if (!v) setRerunTarget(null) }}
        title="重新评测"
        description={`将清空「${rerunTarget?.filename || ''}」已有结果，用当前提示词与业务分类从头重跑。重测会调用大模型，数据量大时较耗时，确认继续？`}
        confirmLabel="开始重测"
        confirmVariant="default"
        onConfirm={handleRerun}
      />
    </div>
  )
}
