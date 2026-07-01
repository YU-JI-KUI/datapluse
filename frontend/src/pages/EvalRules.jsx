/**
 * AI 评测 · 规则短路管理：按当前 BU 维护「问题→写死评测结果」规则。
 * 评测时客户问题精确等于触发问题、且答案等于期望答案 → 直接用写死的 judge 结果，
 * 不调 LLM（省调用），结果照常计入指标、落盘。judge 字段结构与 AI 输出完全一致。
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Link } from 'react-router-dom'
import { ArrowLeft, Loader2, Plus, Pencil, Trash2 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { evalApi, getCurrentBu } from '@/lib/api'
import { formatDate } from '@/lib/utils'

const RESP = (r) => r?.data?.data ?? {}

// judge 的 11 个字段（结构同 AI 输出）；布尔用是/否切换，answer_resolved 用枚举，其余文本。
const BOOL_FIELDS = [
  { k: 'should_dispatch_to_bu', label: '该本BU承接' },
  { k: 'answer_relevant',       label: '答案相关' },
  { k: 'answer_complete',       label: '答案完整' },
  { k: 'needs_human_review',    label: '需人工复核' },
]
const RESOLVED_OPTS = ['yes', 'partial', 'no', 'unknown']
const TEXT_FIELDS = [
  { k: 'business_type',        label: '业务分类', ph: '如：咨询客服' },
  { k: 'dispatch_reason',      label: '分发理由' },
  { k: 'business_type_reason', label: '业务分类理由' },
  { k: 'resolved_reason',      label: '解决度理由' },
  { k: 'unresolved_cause',     label: '未解决原因' },
  { k: 'review_reason',        label: '复核理由' },
]

const EMPTY_JUDGE = {
  should_dispatch_to_bu: false, business_type: '', dispatch_reason: '', business_type_reason: '',
  answer_relevant: true, answer_complete: true, answer_resolved: 'unknown', resolved_reason: '',
  unresolved_cause: '', needs_human_review: false, review_reason: '',
}

export default function EvalRules() {
  const [bu, setBu]           = useState(getCurrentBu())
  const [list, setList]       = useState([])
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(null)   // { id?, question, expected_answer, note, judge }
  const [delTarget, setDelTarget] = useState(null)
  const [saving, setSaving]   = useState(false)

  function load() {
    setLoading(true)
    evalApi.listRules()
      .then(res => setList(RESP(res).rules || []))
      .catch(e => toast.error(e.response?.data?.message || '加载规则失败'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    const onBuChange = (e) => { setBu(e.detail?.bu || getCurrentBu()); load() }
    window.addEventListener('buChanged', onBuChange)
    return () => window.removeEventListener('buChanged', onBuChange)
  }, [])

  function openNew() {
    setEditing({ question: '', expected_answer: '', note: '', judge: { ...EMPTY_JUDGE } })
  }
  function openEdit(r) {
    setEditing({
      id: r.id, question: r.question, expected_answer: r.expected_answer, note: r.note || '',
      judge: { ...EMPTY_JUDGE, ...(r.judge_json || {}) },
    })
  }

  function setJudge(k, v) {
    setEditing(e => ({ ...e, judge: { ...e.judge, [k]: v } }))
  }

  async function handleSave() {
    if (!editing?.question?.trim()) { toast.error('触发问题不能为空'); return }
    setSaving(true)
    try {
      await evalApi.upsertRule({
        question: editing.question.trim(),
        expected_answer: editing.expected_answer,
        judge_json: editing.judge,
        note: editing.note,
      })
      toast.success('已保存')
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
      await evalApi.deleteRule(delTarget.id)
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
          <h1 className="text-2xl font-bold">规则短路管理</h1>
          <p className="text-muted-foreground text-sm mt-1">
            维护当前业务单元（<span className="font-medium">{bu}</span>）的短路规则。
            评测时客户问题<span className="font-medium">精确等于</span>触发问题、且答案等于期望答案 →
            直接用写死的评测结果，<span className="font-medium">不调 LLM</span>（省调用），结果照常计入指标。改后下次评测即生效。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={openNew}><Plus className="w-4 h-4 mr-1.5" />新增规则</Button>
          <Button variant="outline" size="sm" asChild>
            <Link to="/eval"><ArrowLeft className="w-4 h-4 mr-1.5" />返回评测</Link>
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>触发问题（精确匹配）</TableHead>
                <TableHead>期望答案</TableHead>
                <TableHead className="w-32">业务分类</TableHead>
                <TableHead className="w-40 whitespace-nowrap">更新时间</TableHead>
                <TableHead className="w-24 text-center">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow><TableCell colSpan={5} className="text-center py-10 text-muted-foreground">
                  <Loader2 className="w-5 h-5 animate-spin inline mr-2" />加载中…
                </TableCell></TableRow>
              ) : list.length === 0 ? (
                <TableRow><TableCell colSpan={5} className="text-center py-10 text-muted-foreground">
                  当前 BU 暂无规则，点右上角「新增规则」开始维护。
                </TableCell></TableRow>
              ) : list.map(r => (
                <TableRow key={r.id}>
                  <TableCell className="font-medium">{r.question}</TableCell>
                  <TableCell className="text-sm text-muted-foreground max-w-xs truncate">{r.expected_answer}</TableCell>
                  <TableCell className="text-sm">{r.judge_json?.business_type || '—'}</TableCell>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{formatDate(r.updated_at)}</TableCell>
                  <TableCell>
                    <div className="flex items-center justify-center gap-1">
                      <button title="编辑" onClick={() => openEdit(r)} className="p-1.5 rounded hover:bg-accent">
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button title="删除" onClick={() => setDelTarget(r)} className="p-1.5 rounded hover:bg-red-50 text-red-500">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* 新增/编辑对话框（右侧抽屉，字段多） */}
      <Dialog open={!!editing} onOpenChange={v => { if (!v) setEditing(null) }}>
        <DialogContent position="right" className="p-0 gap-0 flex flex-col overflow-hidden">
          <DialogHeader className="shrink-0 px-6 pt-6 pb-3 border-b">
            <DialogTitle className="text-left pr-8">{editing?.id ? '编辑规则' : '新增规则'}</DialogTitle>
          </DialogHeader>
          {editing && (
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4 text-sm">
              <div className="space-y-1.5">
                <label className="font-medium">触发问题（与客户问题精确相等）</label>
                <textarea value={editing.question} rows={2}
                  onChange={e => setEditing({ ...editing, question: e.target.value })}
                  placeholder="如：转人工"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 resize-y focus:outline-none focus:ring-2 focus:ring-ring" />
              </div>
              <div className="space-y-1.5">
                <label className="font-medium">期望答案（须与样本答案一致才命中；留空表示答案也须为空）</label>
                <textarea value={editing.expected_answer} rows={3}
                  onChange={e => setEditing({ ...editing, expected_answer: e.target.value })}
                  placeholder="填入这条问题对应的写死答案原文"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 resize-y focus:outline-none focus:ring-2 focus:ring-ring" />
              </div>

              <div className="rounded-md border p-3 space-y-3">
                <div className="font-medium text-muted-foreground">写死的评测结果（结构同 AI 输出）</div>
                <div className="grid grid-cols-2 gap-2">
                  {BOOL_FIELDS.map(f => (
                    <div key={f.k} className="flex items-center justify-between rounded bg-muted/40 px-2.5 py-1.5">
                      <span className="text-xs">{f.label}</span>
                      <div className="flex gap-1">
                        {[['是', true], ['否', false]].map(([lbl, val]) => (
                          <button key={lbl} type="button" onClick={() => setJudge(f.k, val)}
                            className={`px-2 py-0.5 rounded text-xs border ${editing.judge[f.k] === val ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-border'}`}>
                            {lbl}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs text-muted-foreground">是否解决（answer_resolved）</label>
                  <div className="flex gap-1.5">
                    {RESOLVED_OPTS.map(o => (
                      <button key={o} type="button" onClick={() => setJudge('answer_resolved', o)}
                        className={`px-2.5 py-1 rounded text-xs border ${editing.judge.answer_resolved === o ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-border'}`}>
                        {o}
                      </button>
                    ))}
                  </div>
                </div>
                {TEXT_FIELDS.map(f => (
                  <div key={f.k} className="space-y-1">
                    <label className="text-xs text-muted-foreground">{f.label}</label>
                    <Input value={editing.judge[f.k] || ''} placeholder={f.ph || ''}
                      onChange={e => setJudge(f.k, e.target.value)} />
                  </div>
                ))}
              </div>

              <div className="space-y-1.5">
                <label className="font-medium">备注（可选）</label>
                <Input value={editing.note} onChange={e => setEditing({ ...editing, note: e.target.value })}
                  placeholder="如：转人工按钮固定话术" />
              </div>
            </div>
          )}
          <div className="shrink-0 flex justify-end gap-2 px-6 py-3 border-t bg-background">
            <Button variant="secondary" size="sm" onClick={() => setEditing(null)}>取消</Button>
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving && <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />}保存
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!delTarget}
        onOpenChange={v => { if (!v) setDelTarget(null) }}
        title="删除规则"
        description={`将删除规则「${delTarget?.question || ''}」，评测时该问题恢复走正常 AI 评测。`}
        confirmLabel="删除"
        onConfirm={handleDelete}
      />
    </div>
  )
}
