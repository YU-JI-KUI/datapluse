/**
 * AI 评测 · 活动标问管理：按当前 BU 维护「活动标问」清单。
 * 活动标问是前端写死按钮触发的写死回复（如「帮我解锁消费权益」），不经 AI。
 * 评测时客户问题与清单精确相等即整条跳过——不喂模型、不计入分发准确率/解决率，
 * 仅作后续轮上下文保留。改后下次评测即生效。当前 BU 由左侧全局选择器决定。
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Loader2, Plus, Trash2 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import TablePagination from '@/components/TablePagination'
import { evalApi, getCurrentBu } from '@/lib/api'
import { formatDate, scopeName } from '@/lib/utils'

const RESP = (r) => r?.data?.data ?? {}

export default function EvalActivity() {
  const [bu, setBu]           = useState(getCurrentBu())
  const [list, setList]       = useState([])
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(null)   // { question, note } 新增中的对象
  const [delTarget, setDelTarget] = useState(null)
  const [saving, setSaving]   = useState(false)
  const [page, setPage]         = useState(1)    // 前端本地分页：全量加载后内存切片
  const [pageSize, setPageSize] = useState(10)

  const pageList = list.slice((page - 1) * pageSize, page * pageSize)

  function load() {
    setLoading(true)
    evalApi.listActivityQuestions()
      .then(res => { setList(RESP(res).questions || []); setPage(1) })
      .catch(e => toast.error(e.response?.data?.message || '加载活动标问失败'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    const onBuChange = (e) => { setBu(e.detail?.bu || getCurrentBu()); load() }
    window.addEventListener('buChanged', onBuChange)
    return () => window.removeEventListener('buChanged', onBuChange)
  }, [])

  async function handleSave() {
    if (!editing?.question?.trim()) { toast.error('活动标问不能为空'); return }
    setSaving(true)
    try {
      await evalApi.createActivityQuestion({ question: editing.question.trim(), note: editing.note || '' })
      toast.success('已新增')
      setEditing(null)
      load()
    } catch (e) {
      toast.error(e.response?.data?.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!delTarget) return
    try {
      await evalApi.deleteActivityQuestion(delTarget.id)
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
          <h1 className="text-2xl font-bold">活动标问管理</h1>
          <p className="text-muted-foreground text-sm mt-1">
            维护当前业务单元（<span className="font-medium">{scopeName(bu)}</span>）的活动标问清单。
            活动标问是前端写死按钮触发的写死回复，不经 AI；评测时客户问题与清单
            <span className="font-medium">精确相等</span>即整条跳过，不计入分发准确率与解决率。改后下次评测即生效。
          </p>
        </div>
        <Button size="sm" onClick={() => setEditing({ question: '', note: '' })}>
          <Plus className="w-4 h-4 mr-1.5" />新增活动标问
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>活动标问（与客户问题精确相等即跳过）</TableHead>
                <TableHead className="w-56">备注</TableHead>
                <TableHead className="w-28">修改人</TableHead>
                <TableHead className="w-40 whitespace-nowrap">更新时间</TableHead>
                <TableHead className="w-20 text-center">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-10 text-muted-foreground">
                    <Loader2 className="w-5 h-5 animate-spin inline mr-2" />加载中…
                  </TableCell>
                </TableRow>
              ) : list.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-10 text-muted-foreground">
                    当前 BU 暂无活动标问，点右上角「新增活动标问」开始维护。
                  </TableCell>
                </TableRow>
              ) : pageList.map(q => (
                <TableRow key={q.id}>
                  <TableCell className="font-medium">{q.question}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{q.note}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{q.updated_by || '—'}</TableCell>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{formatDate(q.updated_at)}</TableCell>
                  <TableCell>
                    <div className="flex items-center justify-center">
                      <button title="删除" onClick={() => setDelTarget(q)} className="p-1.5 rounded hover:bg-red-50 text-red-500">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePagination
            page={page}
            pageSize={pageSize}
            total={list.length}
            onPageChange={setPage}
            onSizeChange={size => { setPageSize(size); setPage(1) }}
          />
        </CardContent>
      </Card>

      {/* 新增对话框 */}
      <Dialog open={!!editing} onOpenChange={v => { if (!v) setEditing(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新增活动标问</DialogTitle>
          </DialogHeader>
          {editing && (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">活动标问全文</label>
                <textarea
                  value={editing.question}
                  onChange={e => setEditing({ ...editing, question: e.target.value })}
                  rows={3}
                  placeholder="如：帮我解锁消费权益（须与日志中客户问题完全一致，含标点）"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <p className="text-xs text-muted-foreground">
                  采用精确相等匹配（去首尾空格）。请填写与日志「客户问题」列完全一致的整句，避免误伤真实问题。
                </p>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">备注（可选）</label>
                <Input
                  value={editing.note}
                  onChange={e => setEditing({ ...editing, note: e.target.value })}
                  placeholder="如：会员中心解锁权益按钮"
                />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="secondary" size="sm" onClick={() => setEditing(null)}>取消</Button>
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving && <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />}保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!delTarget}
        onOpenChange={v => { if (!v) setDelTarget(null) }}
        title="删除活动标问"
        description={`将删除「${delTarget?.question || ''}」，评测时该问题将重新参与评测。`}
        confirmLabel="删除"
        onConfirm={handleDelete}
      />
    </div>
  )
}
