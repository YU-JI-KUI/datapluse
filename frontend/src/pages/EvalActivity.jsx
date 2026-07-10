/**
 * AI 评测 · 活动标问管理：按当前 BU 维护「活动标问」清单。
 * 活动标问是前端写死按钮触发的写死回复（如「帮我解锁消费权益」），不经 AI。
 * 评测时客户问题与清单精确相等即整条跳过——不喂模型、不计入分发准确率/解决率，
 * 仅作后续轮上下文保留。改后下次评测即生效。当前 BU 由左侧全局选择器决定。
 *
 * 展示：同一活动名下的多个标问聚合成一行，标问以 chips 横排；每个 chip 可单独删除。
 * 新增：一个活动名 + 多行 textarea（一行一条标问）批量录入。
 * 编辑：打开整个活动的全部标问（多行 textarea），保存做 diff（增/删/改活动名）。
 */
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Loader2, Plus, Trash2, Pencil, X } from 'lucide-react'
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
const splitLines = (s) => (s || '').split(/\r\n|\r|\n/).map(x => x.trim()).filter(Boolean)

export default function EvalActivity() {
  const [bu, setBu]           = useState(getCurrentBu())
  const [list, setList]       = useState([])   // 扁平：[{id, activity_name, question, note, updated_by, updated_at}]
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(null)  // 批量新增 { activity_name, questions(多行), note }
  const [editing, setEditing]   = useState(null)  // 整活动编辑 { key, activity_name, questions(多行), note, origItems }
  const [delTarget, setDelTarget] = useState(null)  // 单标问删除 { id, question }
  const [saving, setSaving]   = useState(false)
  const [page, setPage]         = useState(1)
  const [pageSize, setPageSize] = useState(10)

  // 按活动名聚合成组：同名归一组，活动名空则各自单独一组（用 question 兜底 key）
  const groups = useMemo(() => {
    const map = new Map()
    for (const q of list) {
      const key = q.activity_name || `__q__${q.id}`
      if (!map.has(key)) {
        map.set(key, {
          key,
          activity_name: q.activity_name || '',
          note: q.note || '',
          items: [],
          updated_by: q.updated_by,
          updated_at: q.updated_at,
        })
      }
      const g = map.get(key)
      g.items.push({ id: q.id, question: q.question })
      // 该组的备注/修改人/时间取最新一条（列表已按更新时间倒序则天然最新）
      if (!g.note && q.note) g.note = q.note
    }
    return [...map.values()]
  }, [list])

  const pageGroups = groups.slice((page - 1) * pageSize, page * pageSize)

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

  // 批量新增：textarea 按换行拆多条，去空去重后一次提交
  async function handleCreate() {
    const questions = splitLines(creating?.questions)
    if (questions.length === 0) { toast.error('请至少填写一条活动标问'); return }
    setSaving(true)
    try {
      const res = await evalApi.createActivityQuestion({
        questions,
        activity_name: (creating.activity_name || '').trim(),
        note: creating.note || '',
      })
      toast.success(`已新增 ${RESP(res).created ?? questions.length} 条`)
      setCreating(null)
      load()
    } catch (e) {
      toast.error(e.response?.data?.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  // 编辑整个活动：对比新旧标问集，删掉移除的、加新增的、活动名改则更新保留项
  async function handleUpdateActivity() {
    const newName = (editing.activity_name || '').trim()
    const newQs = splitLines(editing.questions)
    if (newQs.length === 0) { toast.error('该活动至少保留一条标问'); return }
    const orig = editing.origItems  // [{id, question}]
    const origQs = orig.map(o => o.question)
    const added = newQs.filter(q => !origQs.includes(q))
    const removed = orig.filter(o => !newQs.includes(o.question))
    const kept = orig.filter(o => newQs.includes(o.question))

    setSaving(true)
    try {
      // 1. 删除移除的标问
      for (const o of removed) await evalApi.deleteActivityQuestion(o.id)
      // 2. 活动名变化 → 更新保留项的活动名
      if (newName !== editing.origName) {
        for (const o of kept) {
          await evalApi.updateActivityQuestion(o.id, { question: o.question, activity_name: newName })
        }
      }
      // 3. 新增的标问（归到该活动名下）
      if (added.length > 0) {
        await evalApi.createActivityQuestion({
          questions: added, activity_name: newName, note: editing.note || '',
        })
      }
      toast.success('已更新该活动')
      setEditing(null)
      load()
    } catch (e) {
      toast.error(e.response?.data?.message || '保存失败')
      load()  // 多步操作可能半成品，重新拉取保持一致
    } finally {
      setSaving(false)
    }
  }

  // 删单条标问（chip 上的小删除号，或最后一条走确认框）
  async function deleteOne(id) {
    try {
      await evalApi.deleteActivityQuestion(id)
      load()
    } catch (e) {
      toast.error(e.response?.data?.message || '删除失败')
    }
  }

  function openEdit(g) {
    setEditing({
      key: g.key,
      activity_name: g.activity_name,
      origName: g.activity_name,
      questions: g.items.map(i => i.question).join('\n'),
      note: g.note,
      origItems: g.items,
    })
  }

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">活动标问管理</h1>
          <p className="text-muted-foreground text-sm mt-1">
            维护当前业务单元（<span className="font-medium">{scopeName(bu)}</span>）的活动标问清单。
            同一活动的多个标问聚合成一行展示。活动标问是前端写死按钮触发的写死回复，不经 AI；评测时客户问题与清单
            <span className="font-medium">精确相等</span>即整条跳过，不计入分发准确率与解决率。改后下次评测即生效。
          </p>
        </div>
        <Button size="sm" onClick={() => setCreating({ activity_name: '', questions: '', note: '' })}>
          <Plus className="w-4 h-4 mr-1.5" />新增活动标问
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-44">活动</TableHead>
                <TableHead>活动标问（与客户问题精确相等即跳过）</TableHead>
                <TableHead className="w-56">备注</TableHead>
                <TableHead className="w-28">修改人</TableHead>
                <TableHead className="w-40 whitespace-nowrap">更新时间</TableHead>
                <TableHead className="w-24 text-center">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-10 text-muted-foreground">
                    <Loader2 className="w-5 h-5 animate-spin inline mr-2" />加载中…
                  </TableCell>
                </TableRow>
              ) : groups.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-10 text-muted-foreground">
                    当前 BU 暂无活动标问，点右上角「新增活动标问」开始维护。
                  </TableCell>
                </TableRow>
              ) : pageGroups.map(g => (
                <TableRow key={g.key}>
                  <TableCell>
                    <span className="inline-block px-2 py-0.5 rounded text-xs bg-blue-50 text-blue-600">
                      {g.activity_name || g.items[0]?.question}
                    </span>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1.5">
                      {g.items.map(it => (
                        <span key={it.id}
                          className="group inline-flex items-center gap-1 rounded-md border bg-gray-50 px-2 py-0.5 text-sm">
                          {it.question}
                          <button title="删除该标问"
                            onClick={() => (g.items.length > 1
                              ? deleteOne(it.id)
                              : setDelTarget({ id: it.id, question: it.question }))}
                            className="text-gray-300 hover:text-red-500">
                            <X className="w-3 h-3" />
                          </button>
                        </span>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{g.note}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{g.updated_by || '—'}</TableCell>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{formatDate(g.updated_at)}</TableCell>
                  <TableCell>
                    <div className="flex items-center justify-center">
                      <button title="编辑整个活动" onClick={() => openEdit(g)}
                        className="p-1.5 rounded hover:bg-blue-50 text-blue-500">
                        <Pencil className="w-4 h-4" />
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
            total={groups.length}
            onPageChange={setPage}
            onSizeChange={size => { setPageSize(size); setPage(1) }}
          />
        </CardContent>
      </Card>

      {/* 批量新增对话框：一个活动名 + 多行标问（一行一条） */}
      <Dialog open={!!creating} onOpenChange={v => { if (!v) setCreating(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新增活动标问</DialogTitle>
          </DialogHeader>
          {creating && (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">活动名称</label>
                <Input
                  value={creating.activity_name}
                  onChange={e => setCreating({ ...creating, activity_name: e.target.value })}
                  placeholder="如：双十一消费券（下方多条标问都归到这个活动）"
                />
                <p className="text-xs text-muted-foreground">
                  下方每一条标问都归属该活动名，聚合成一行、评测报告按活动聚合成一根柱。留空则每条各自用标问全文。
                </p>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">活动标问（一行一条，可填多条）</label>
                <textarea
                  value={creating.questions}
                  onChange={e => setCreating({ ...creating, questions: e.target.value })}
                  rows={6}
                  placeholder={'一行一条，例如：\n帮我解锁消费权益\n我要领取消费券\n消费券怎么用'}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <p className="text-xs text-muted-foreground">
                  每行一条标问，采用精确相等匹配（去首尾空格）。请与日志「客户问题」列完全一致，避免误伤真实问题；空行自动忽略，重复自动去重。
                </p>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">备注（可选）</label>
                <textarea
                  value={creating.note}
                  onChange={e => setCreating({ ...creating, note: e.target.value })}
                  rows={3}
                  placeholder="如：双十一活动，2026-11-01 ~ 11-11，会员中心解锁权益按钮"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="secondary" size="sm" onClick={() => setCreating(null)}>取消</Button>
            <Button size="sm" onClick={handleCreate} disabled={saving}>
              {saving && <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />}保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 编辑整个活动对话框：活动名 + 该活动全部标问（多行，可增删改） */}
      <Dialog open={!!editing} onOpenChange={v => { if (!v) setEditing(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>编辑活动</DialogTitle>
          </DialogHeader>
          {editing && (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">活动名称</label>
                <Input
                  value={editing.activity_name}
                  onChange={e => setEditing({ ...editing, activity_name: e.target.value })}
                  placeholder="留空则每条各自用标问全文"
                />
                <p className="text-xs text-muted-foreground">
                  改活动名会同步更新该活动下保留的全部标问。留空则每条各自用标问全文。
                </p>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">该活动的全部标问（一行一条，增删改后保存）</label>
                <textarea
                  value={editing.questions}
                  onChange={e => setEditing({ ...editing, questions: e.target.value })}
                  rows={8}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <p className="text-xs text-muted-foreground">
                  一行一条。删掉某行即删除该标问，新增一行即新增标问。精确相等匹配（去首尾空格），空行忽略、重复去重。
                </p>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="secondary" size="sm" onClick={() => setEditing(null)}>取消</Button>
            <Button size="sm" onClick={handleUpdateActivity} disabled={saving}>
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
        onConfirm={() => { if (delTarget) deleteOne(delTarget.id) }}
      />
    </div>
  )
}
