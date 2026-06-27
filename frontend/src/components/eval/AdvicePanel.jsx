/** 优化建议：按严重度排序的建议卡片，标注来源（模型/规则）。 */
import { AlertOctagon, AlertTriangle, Info, Lightbulb, Cpu, FileText } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { EvalBadge, SectionTitle } from './EvalPrimitives'

const SEVERITY = {
  high:   { tone: 'bad',  icon: AlertOctagon,  label: '高' },
  medium: { tone: 'warn', icon: AlertTriangle, label: '中' },
  low:    { tone: 'info', icon: Info,          label: '低' },
}
const SEV_ORDER = { high: 0, medium: 1, low: 2 }

const ROOT_CAUSE_TONE = {
  分发问题: 'bad',
  答案问题: 'warn',
  数据问题: 'info',
  需人工:   'brand',
}

export default function AdvicePanel({ advice }) {
  const items = advice?.items || []
  const sorted = [...items].sort(
    (a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9),
  )
  const source = advice?.source

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <SectionTitle hint="基于评测指标自动生成">优化建议</SectionTitle>
          {source && (
            <EvalBadge tone={source === 'model' ? 'good' : 'slate'}>
              {source === 'model'
                ? <span className="inline-flex items-center gap-1"><Cpu className="w-3 h-3" />大模型生成</span>
                : <span className="inline-flex items-center gap-1"><FileText className="w-3 h-3" />规则生成</span>}
            </EvalBadge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {sorted.length === 0 ? (
          <div className="text-sm text-muted-foreground py-4 text-center">
            暂无明显需优化的点（指标良好或样本不足）。
          </div>
        ) : (
          <div className="grid lg:grid-cols-2 gap-3">
            {sorted.map((a, i) => {
              const sev = SEVERITY[a.severity] || SEVERITY.low
              const Icon = sev.icon
              return (
                <div key={i} className="rounded-lg border p-3 space-y-2">
                  <div className="flex items-start gap-2">
                    <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${
                      sev.tone === 'bad' ? 'bg-red-100 text-red-600'
                        : sev.tone === 'warn' ? 'bg-amber-100 text-amber-600'
                        : 'bg-sky-100 text-sky-600'}`}>
                      <Icon className="w-4 h-4" />
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5 min-w-0">
                      {a.scope && <span className="font-medium text-sm">{a.scope}</span>}
                      <EvalBadge tone={sev.tone}>{sev.label}</EvalBadge>
                      {a.root_cause && (
                        <EvalBadge tone={ROOT_CAUSE_TONE[a.root_cause] || 'slate'}>{a.root_cause}</EvalBadge>
                      )}
                    </div>
                  </div>
                  {a.problem && <p className="text-sm text-gray-700">{a.problem}</p>}
                  {a.suggestion && (
                    <div className="flex items-start gap-2 rounded-md bg-gray-50 px-3 py-2">
                      <Lightbulb className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                      <span className="text-xs text-gray-700">{a.suggestion}</span>
                    </div>
                  )}
                  {a.evidence && <p className="text-[11px] text-muted-foreground">依据：{a.evidence}</p>}
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
