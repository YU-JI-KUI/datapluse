/** 单行详情：会话上下文 / AI 回答 / Judge 判断 / 人工打标对比。用 Dialog 承载。 */
import { MessageSquare, Bot, Scale, ShieldCheck } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
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

export default function DetailDrawer({ row, open, onClose }) {
  if (!row) return null
  const j = row.judge && typeof row.judge === 'object' ? row.judge : {}
  const gold = row.gold || {}

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose() }}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">{row.session}</span>
            <EvalBadge tone="slate">第 {row.turn} 轮</EvalBadge>
            {row.j_intent && <EvalBadge tone="brand">{row.j_intent}</EvalBadge>}
            {row.is_disagreement && <EvalBadge tone="bad">与打标不一致</EvalBadge>}
          </div>
          <DialogTitle className="text-left mt-1">{row.question}</DialogTitle>
        </DialogHeader>

        <div className="space-y-6 mt-2">
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
        </div>
      </DialogContent>
    </Dialog>
  )
}
