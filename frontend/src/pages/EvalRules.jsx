/**
 * AI 评测 · 短路规则管理（规则集）：按当前 BU 维护「规则集 → 写死评测结果」。
 * 一个规则 = 名字 + 触发问题集合 + 期望答案集合 + 一份写死 judge。
 * 评测时客户问题 ∈ 触发集合 且 答案 ∈ 答案集合（独立组合）→ 直接用写死的 judge 结果，
 * 不调 LLM（省调用），结果照常计入指标、落盘。报告按规则名聚合。
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Loader2, Plus, Pencil, Trash2 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import TablePagination from '@/components/TablePagination'
import { evalApi, getCurrentBu } from '@/lib/api'
import { formatDate, scopeName } from '@/lib/utils'

const RESP = (r) => r?.data?.data ?? {}
const splitLines = (s) => (s || '').split(/\r\n|\r|\n/).map(x => x.trim()).filter(Boolean)

// judge 的 11 个字段（结构同 AI 输出）；布尔用是/否切换，answer_resolved 用枚举，其余文本。
const BOOL_FIELDS = [
  { k: 'should_dispatch_to_bu', label: '该本BU承接' },
  { k: 'answer_relevant',       label: '答案相关' },
  { k: 'answer_complete',       label: '答案完整' },
  { k: 'needs_human_review',    label: '需人工复核' },
]
const RESOLVED_OPTS = ['yes', 'partial', 'no', 'unknown']
const TEXT_FIELDS = [
  { k: 'business_type',        label: '业务分类（可选）', ph: '选填；规则命中行不计入业务分类维度，留空即可' },
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
  const [editing, setEditing] = useState(null)   // { id?, name, questions(多行), answers(多行), note, judge }
  const [delTarget, setDelTarget] = useState(null)
  const [saving, setSaving]   = useState(false)
  const [page, setPage]         = useState(1)
  const [pageSize, setPageSize] = useState(10)

  const pageList = list.slice((page - 1) * pageSize, page * pageSize)

  function load() {
    setLoading(true)
    evalApi.listRules()
      .then(res => { setList(RESP(res).rules || []); setPage(1) })
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
    setEditing({ name: '', questions: '', answers: '', note: '', judge: { ...EMPTY_JUDGE } })
  }
  function openEdit(r) {
    setEditing({
      id: r.id, name: r.name || '',
      questions: (r.questions || []).join('\n'),
      answers: (r.answers || []).join('\n'),
      note: r.note || '',
      judge: { ...EMPTY_JUDGE, ...(r.judge_json || {}) },
    })
  }

  function setJudge(k, v) {
    setEditing(e => ({ ...e, judge: { ...e.judge, [k]: v } }))
  }

  async function handleSave() {
    if (!editing?.name?.trim()) { toast.error('规则名不能为空'); return }
    const questions = splitLines(editing.questions)
    const answers = splitLines(editing.answers)
    if (questions.length === 0) { toast.error('至少填写一个触发问题'); return }
    setSaving(true)
    try {
      await evalApi.upsertRule({
        name: editing.name.trim(),
        questions,
        answers,
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
          <h1 className="text-2xl font-bold">短路规则管理</h1>
          <p className="text-muted-foreground text-sm mt-1">
            维护当前业务单元（<span className="font-medium">{scopeName(bu)}</span>）的短路规则集。
            一个规则含多个触发问题和多个期望答案：评测时客户问题<span className="font-medium">∈ 触发问题集合</span>
            且答案<span className="font-medium">∈ 期望答案集合</span> → 直接用写死的评测结果，
            <span className="font-medium">不调 LLM</span>（省调用），结果照常计入指标、按规则名聚合。改后下次评测即生效。
          </p>
        </div>
        <Button size="sm" onClick={openNew}><Plus className="w-4 h-4 mr-1.5" />新增规则</Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-40">规则名</TableHead>
                <TableHead>触发问题（∈ 即满足问题条件）</TableHead>
                <TableHead>期望答案（∈ 即满足答案条件）</TableHead>
                <TableHead className="w-28">业务分类</TableHead>
                <TableHead className="w-28">修改人</TableHead>
                <TableHead className="w-40 whitespace-nowrap">更新时间</TableHead>
                <TableHead className="w-24 text-center">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow><TableCell colSpan={7} className="text-center py-10 text-muted-foreground">
                  <Loader2 className="w-5 h-5 animate-spin inline mr-2" />加载中…
                </TableCell></TableRow>
              ) : list.length === 0 ? (
                <TableRow><TableCell colSpan={7} className="text-center py-10 text-muted-foreground">
                  当前 BU 暂无规则，点右上角「新增规则」开始维护。
                </TableCell></TableRow>
              ) : pageList.map(r => (
                <TableRow key={r.id}>
                  <TableCell>
                    <span className="inline-block px-2 py-0.5 rounded text-xs bg-blue-50 text-blue-600 font-medium">
                      {r.name}
                    </span>
                  </TableCell>
                  <TableCell><ChipList items={r.questions} /></TableCell>
                  <TableCell><ChipList items={r.answers} muted /></TableCell>
                  <TableCell className="text-sm">{r.judge_json?.business_type || '—'}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{r.updated_by || '—'}</TableCell>
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
          <TablePagination
            page={page}
            pageSize={pageSize}
            total={list.length}
            onPageChange={setPage}
            onSizeChange={size => { setPageSize(size); setPage(1) }}
          />
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
                <label className="font-medium">规则名（报告按此聚合）</label>
                <Input value={editing.name}
                  onChange={e => setEditing({ ...editing, name: e.target.value })}
                  placeholder="如：转人工" />
              </div>
              <div className="space-y-1.5">
                <label className="font-medium">触发问题集合（一行一条，支持通配 / LIKE，匹配任一即满足）</label>
                <textarea value={editing.questions} rows={4}
                  onChange={e => setEditing({ ...editing, questions: e.target.value })}
                  placeholder={'一行一条，例如：\n转人工          （精确相等）\n*               （任意问题）\n%注销%          （包含“注销”）\n注销%            （以“注销”开头）'}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 resize-y focus:outline-none focus:ring-2 focus:ring-ring" />
                <p className="text-xs text-muted-foreground">
                  匹配语法（类 SQL LIKE）：<code>转人工</code> 精确相等；<code>*</code> 任意问题；
                  <code>%注销%</code> 包含；<code>注销%</code> 前缀；<code>%注销</code> 后缀。
                  规则命中行不计入业务分类维度（不进分类分布、不进按分类的优化建议），「业务分类」留空即可。
                </p>
              </div>
              <div className="space-y-1.5">
                <label className="font-medium">期望答案集合（一行一条，样本答案精确等于其中任一即满足）</label>
                <textarea value={editing.answers} rows={4}
                  onChange={e => setEditing({ ...editing, answers: e.target.value })}
                  placeholder={'一行一条，例如：\n你好\n你好呀'}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 resize-y focus:outline-none focus:ring-2 focus:ring-ring" />
                <p className="text-xs text-muted-foreground">
                  问题与答案是独立集合：任一触发问题 × 任一期望答案的组合都算命中。留空答案集合表示不限答案（仅按问题命中，慎用）。
                </p>
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
        description={`将删除规则「${delTarget?.name || ''}」，评测时相关问题恢复走正常 AI 评测。`}
        confirmLabel="删除"
        onConfirm={handleDelete}
      />
    </div>
  )
}

/** 集合以 chips 横排展示；空则显示 —。 */
function ChipList({ items, muted }) {
  const arr = items || []
  if (arr.length === 0) return <span className="text-muted-foreground">—</span>
  return (
    <div className="flex flex-wrap gap-1">
      {arr.map((t, i) => (
        <span key={i}
          className={`inline-block rounded border px-1.5 py-0.5 text-xs ${muted ? 'bg-gray-50 text-muted-foreground max-w-[16rem] truncate' : 'bg-white'}`}
          title={t}>
          {t}
        </span>
      ))}
    </div>
  )
}
