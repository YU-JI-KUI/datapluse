/** 单行详情：会话上下文 / AI 回答 / Judge 判断 / 人工打标对比 / 人工复核。用 Dialog 承载。 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { MessageSquare, Bot, Scale, ShieldCheck, UserCheck, Loader2, RotateCcw } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { evalApi } from '@/lib/api'
import { EvalBadge, YesNo } from './EvalPrimitives'

function Block({ icon: Icon, title, children }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Icon className="w-4 h-4 text-muted-foreground" />{title}
      </div>
      {children}
    </div>
  )
}

function JField({ label, value, highlight }) {
  return (
    <div className={`rounded-md px-3 py-2 ${highlight ? 'bg-blue-50' : 'bg-gray-50'}`}>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="text-sm font-medium">{value ?? '—'}</div>
    </div>
  )
}

function JFieldBool({ label, value, warnTrue }) {
  let node = <span className="text-muted-foreground">—</span>
  if (value === true) node = <EvalBadge tone={warnTrue ? 'warn' : 'good'}>是</EvalBadge>
  else if (value === false) node = <EvalBadge tone={warnTrue ? 'good' : 'bad'}>否</EvalBadge>
  return (
    <div className="rounded-md bg-gray-50 px-3 py-2">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5">{node}</div>
    </div>
  )
}

function GoldCompare({ label, pred, gold }) {
  const has = gold === '是' || gold === '否'
  const disagree = has && pred !== gold
  return (
    <div className={`rounded-md border px-3 py-2 ${disagree ? 'border-red-300 bg-red-50' : 'border-border'}`}>
      <div className="text-[11px] text-muted-foreground mb-1">{label}</div>
      <div className="flex items-center gap-3 text-sm">
        <span>Judge：<YesNo value={pred} /></span>
        <span className={disagree ? 'text-red-500 font-bold' : 'text-green-600 font-bold'}>{disagree ? '≠' : '='}</span>
        <span>打标：{has ? <YesNo value={gold} /> : <span className="text-muted-foreground">—</span>}</span>
      </div>
    </div>
  )
}

// 三态选择：维持 AI（''）/ 是 / 否
function TriSelect({ label, aiValue, value, onChange }) {
  const opts = [
    { v: '', label: `维持AI（${aiValue || '—'}）` },
    { v: '是', label: '是' },
    { v: '否', label: '否' },
  ]
  return (
    <div className="space-y-1.5">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="flex gap-1.5">
        {opts.map(o => (
          <button
            key={o.v}
            type="button"
            onClick={() => onChange(o.v)}
            className={`px-2.5 py-1 rounded-md text-xs border transition-colors ${
              value === o.v ? 'border-blue-500 bg-blue-50 text-blue-700 font-medium' : 'border-border hover:bg-accent'
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}

export default function DetailDrawer({ row, open, onClose, taskId, intentOptions = [], onReviewed }) {
  const rv = row?.review || null
  const [dispatch, setDispatch] = useState('')
  const [resolved, setResolved] = useState('')
  const [intent, setIntent]     = useState('')
  const [comment, setComment]   = useState('')
  const [saving, setSaving]     = useState(false)

  // 切换到不同行时，用该行已有的复核值回填表单
  useEffect(() => {
    setDispatch(rv?.reviewed_dispatch || '')
    setResolved(rv?.reviewed_resolved || '')
    setIntent(rv?.reviewed_intent || '')
    setComment(rv?.comment || '')
  }, [row?.row_index, rv?.reviewed_dispatch, rv?.reviewed_resolved, rv?.reviewed_intent, rv?.comment])

  if (!row) return null
  const j = row.judge && typeof row.judge === 'object' ? row.judge : {}
  const gold = row.gold || {}
  const canReview = !!taskId && row.row_index != null

  async function handleSubmitReview() {
    setSaving(true)
    try {
      await evalApi.submitReview(taskId, row.row_index, {
        reviewed_dispatch: dispatch, reviewed_resolved: resolved,
        reviewed_intent: intent, comment,
      })
      toast.success('复核已提交（结果页指标重进生效）')
      onReviewed?.()
      onClose()
    } catch (e) {
      toast.error(e.response?.data?.message || '复核提交失败')
    } finally {
      setSaving(false)
    }
  }

  async function handleRevokeReview() {
    setSaving(true)
    try {
      await evalApi.deleteReview(taskId, row.row_index)
      toast.success('已撤销复核（该条恢复 AI 判定）')
      onReviewed?.()
      onClose()
    } catch (e) {
      toast.error(e.response?.data?.message || '撤销失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose() }}>
      {/* 右侧抽屉 + 三段式：固定头 / 滚动体 / 固定脚。长内容不憋屈，关闭键与复核操作始终可见。 */}
      <DialogContent position="right" className="p-0 gap-0 flex flex-col overflow-hidden">
        <DialogHeader className="shrink-0 px-6 pt-6 pb-3 border-b">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">{row.session}</span>
            <EvalBadge tone="slate">第 {row.turn} 轮</EvalBadge>
            {row.j_intent && <EvalBadge tone="brand">{row.j_intent}</EvalBadge>}
            {row.is_disagreement && <EvalBadge tone="bad">与打标不一致</EvalBadge>}
            {j.needs_human_review && <EvalBadge tone="warn">需复核</EvalBadge>}
            {rv && <EvalBadge tone="good">已复核</EvalBadge>}
          </div>
          <DialogTitle className="text-left mt-1 pr-8">{row.question}</DialogTitle>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
          {/* 会话上下文 */}
          {Array.isArray(row.context) && row.context.length > 0 && (
            <Block icon={MessageSquare} title="会话上下文（前文）">
              <div className="space-y-2">
                {row.context.map((c, i) => (
                  <div key={i} className="text-sm">
                    <div className="text-xs text-muted-foreground">第 {c.turn} 轮 · 用户</div>
                    <div>{c.user ?? (typeof c === 'string' ? c : '')}</div>
                    {c.ai && (
                      <div className="mt-1 border-l-2 border-blue-200 pl-2 text-muted-foreground italic">{c.ai}</div>
                    )}
                  </div>
                ))}
              </div>
            </Block>
          )}

          {/* AI 回答 */}
          <Block icon={Bot} title="AI 回答（原始内容）">
            <pre className="whitespace-pre-wrap break-words rounded-md bg-gray-50 p-3 text-sm">{row.answer_text || '—'}</pre>
            {row.next_user_turn && (
              <div className="border-l-2 border-amber-300 pl-2 text-xs text-amber-700">
                下一轮用户：{row.next_user_turn}
              </div>
            )}
          </Block>

          {/* Judge 判断 */}
          <Block icon={Scale} title="Judge 判断">
            <div className="grid grid-cols-2 gap-2.5">
              <JField label="业务分类" value={j.business_type} />
              <JField label="分发场景" value={row.dispatch_scene} highlight />
              <JFieldBool label="该不该本BU接" value={j.should_dispatch_to_bu} />
              <JFieldBool label="答案相关" value={j.answer_relevant} />
              <JFieldBool label="答案完整" value={j.answer_complete} />
              <JField label="是否解决" value={j.answer_resolved} highlight />
              <JFieldBool label="需人工复核" value={j.needs_human_review} warnTrue />
            </div>
            {j.dispatch_reason && (
              <div className="rounded-md bg-gray-50 px-3 py-2 text-xs">分发理由：{j.dispatch_reason}</div>
            )}
            {j.resolved_reason && (
              <div className="rounded-md bg-gray-50 px-3 py-2 text-xs">解决度依据：{j.resolved_reason}</div>
            )}
            {j.unresolved_cause && (
              <div className="rounded-md bg-gray-50 px-3 py-2 text-xs">未解决原因：{j.unresolved_cause}</div>
            )}
            {j.review_reason && (
              <div className="rounded-md bg-gray-50 px-3 py-2 text-xs">复核原因：{j.review_reason}</div>
            )}
          </Block>

          {/* 人工打标对比 */}
          {(gold.dispatch || gold.resolved) && (
            <Block icon={ShieldCheck} title="人工打标对比">
              <div className="space-y-2">
                <GoldCompare label="分发是否正确" pred={row.j_dispatch} gold={gold.dispatch} />
                <GoldCompare label="答案是否解决" pred={row.j_resolved} gold={gold.resolved} />
              </div>
              {gold.unresolved_reason && (
                <div className="text-xs text-muted-foreground">打标未解决原因：{gold.unresolved_reason}</div>
              )}
              {gold.qtype && (
                <div className="text-xs text-muted-foreground">打标问题类型：{gold.qtype}</div>
              )}
            </Block>
          )}

          {/* 人工复核：覆盖 AI 判定，指标按最终值重算（重进结果页生效）*/}
          {canReview && (
            <Block icon={UserCheck} title="人工复核">
              <p className="text-xs text-muted-foreground">
                复核结论将覆盖 AI 判定，并计入 BU 分发准确率 / 问题解决率（最终值口径）。
                「维持AI」表示该维度不改、沿用 AI 结论。
              </p>
              <div className="grid sm:grid-cols-2 gap-3 rounded-md border p-3">
                <TriSelect label="分发是否正确" aiValue={row.j_dispatch} value={dispatch} onChange={setDispatch} />
                <TriSelect label="答案是否解决" aiValue={row.j_resolved} value={resolved} onChange={setResolved} />
                <div className="space-y-1.5 sm:col-span-2">
                  <div className="text-[11px] text-muted-foreground">业务分类（可选，留空=维持 AI「{row.j_intent || '—'}」）</div>
                  <Input value={intent} onChange={e => setIntent(e.target.value)}
                    placeholder="如需修正业务分类，填入正确分类名" list="eval-intent-options" />
                  <datalist id="eval-intent-options">
                    {intentOptions.map(o => <option key={o} value={o} />)}
                  </datalist>
                </div>
                <div className="space-y-1.5 sm:col-span-2">
                  <div className="text-[11px] text-muted-foreground">复核评论（可选）</div>
                  <textarea value={comment} onChange={e => setComment(e.target.value)} rows={2}
                    placeholder="记录复核判断的依据或备注…"
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-y focus:outline-none focus:ring-2 focus:ring-ring" />
                </div>
              </div>
            </Block>
          )}
        </div>

        {/* 固定脚：复核操作始终可见，不必滚到底 */}
        {canReview && (
          <div className="shrink-0 flex items-center justify-between gap-2 px-6 py-3 border-t bg-background">
            <div className="text-xs text-muted-foreground">
              {rv ? `已由 ${rv.reviewer || '—'} 复核` : '尚未复核'}
            </div>
            <div className="flex gap-2">
              {rv && (
                <Button variant="secondary" size="sm" onClick={handleRevokeReview} disabled={saving}>
                  <RotateCcw className="w-4 h-4 mr-1.5" />撤销复核
                </Button>
              )}
              <Button size="sm" onClick={handleSubmitReview} disabled={saving}>
                {saving && <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />}提交复核
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
