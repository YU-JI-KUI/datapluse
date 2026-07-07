/** 优化建议：多专项卡片（每维度一段文本，可折叠）；兼容旧任务的结构化 items。 */
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { AlertOctagon, AlertTriangle, Info, Lightbulb, Cpu, FileText, ChevronRight } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { EvalBadge, SectionTitle } from './EvalPrimitives'

// markdown 渲染样式（与 EvalPrompts 保持一致）
const MD = {
  h1: (p) => <h1 className="text-base font-bold mt-3 mb-2" {...p} />,
  h2: (p) => <h2 className="text-sm font-bold mt-3 mb-1.5" {...p} />,
  h3: (p) => <h3 className="text-sm font-semibold mt-2 mb-1" {...p} />,
  p:  (p) => <p className="my-1.5 leading-relaxed text-sm text-gray-700" {...p} />,
  ul: (p) => <ul className="list-disc pl-5 my-1.5 space-y-0.5 text-sm text-gray-700" {...p} />,
  ol: (p) => <ol className="list-decimal pl-5 my-1.5 space-y-0.5 text-sm text-gray-700" {...p} />,
  li: (p) => <li className="leading-relaxed" {...p} />,
  code: (p) => <code className="rounded bg-gray-200 px-1 py-0.5 text-[0.85em] font-mono" {...p} />,
  pre: (p) => <pre className="rounded bg-gray-100 p-2 my-2 overflow-x-auto text-xs" {...p} />,
  blockquote: (p) => <blockquote className="border-l-2 border-gray-300 pl-3 italic text-muted-foreground my-2 text-sm" {...p} />,
  table: (p) => <table className="border-collapse my-2 text-xs" {...p} />,
  th: (p) => <th className="border border-gray-300 px-2 py-1 bg-gray-100 text-left" {...p} />,
  td: (p) => <td className="border border-gray-300 px-2 py-1" {...p} />,
  a:  (p) => <a className="text-blue-600 underline" {...p} />,
}

// 维度徽章色
const DIM_TONE = { 分发: 'bad', 解决率: 'warn', 新分类: 'brand' }

// ── 旧任务用：结构化 items ──────────────────────────────────────────────────
const SEVERITY = {
  high:   { tone: 'bad',  icon: AlertOctagon,  label: '高' },
  medium: { tone: 'warn', icon: AlertTriangle, label: '中' },
  low:    { tone: 'info', icon: Info,          label: '低' },
}
const SEV_ORDER = { high: 0, medium: 1, low: 2 }
const ROOT_CAUSE_TONE = { 分发问题: 'bad', 答案问题: 'warn', 数据问题: 'info', 需人工: 'brand' }

function SourceBadge({ source }) {
  if (!source) return null
  return (
    <EvalBadge tone={source === 'model' ? 'good' : 'slate'}>
      {source === 'model'
        ? <span className="inline-flex items-center gap-1"><Cpu className="w-3 h-3" />大模型生成</span>
        : <span className="inline-flex items-center gap-1"><FileText className="w-3 h-3" />规则生成</span>}
    </EvalBadge>
  )
}

/** 单张可折叠建议卡：一行一卡，全局默认展开、逐分类默认折叠。 */
function AdviceCard({ card }) {
  const defaultOpen = card.category === '全局'
  return (
    <details open={defaultOpen} className="group rounded-lg border">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 hover:bg-gray-50">
        <ChevronRight className="w-4 h-4 shrink-0 text-gray-400 transition-transform group-open:rotate-90" />
        <span className="font-medium text-sm">{card.title}</span>
        {card.dimension && <EvalBadge tone={DIM_TONE[card.dimension] || 'slate'}>{card.dimension}</EvalBadge>}
        {card.category && card.category !== '全局' && (
          <EvalBadge tone="slate">{card.category}</EvalBadge>
        )}
      </summary>
      <div className="border-t px-4 py-3">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>{card.text || '_（无内容）_'}</ReactMarkdown>
      </div>
    </details>
  )
}

export default function AdvicePanel({ advice }) {
  const cards = advice?.cards
  const source = advice?.source

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <SectionTitle hint="按业务维度分专项生成，可展开查看详情">优化建议</SectionTitle>
          <SourceBadge source={source} />
        </div>
      </CardHeader>
      <CardContent>
        {cards ? <CardsView cards={cards} /> : <LegacyView advice={advice} />}
      </CardContent>
    </Card>
  )
}

/** 新结构：一行一卡、可折叠。 */
function CardsView({ cards }) {
  if (!cards.length) {
    return (
      <div className="text-sm text-muted-foreground py-4 text-center">
        暂无明显需优化的点（指标良好或样本不足）。
      </div>
    )
  }
  return (
    <div className="space-y-2">
      {cards.map((c) => <AdviceCard key={c.id} card={c} />)}
    </div>
  )
}

/** 旧结构：结构化 severity/root_cause 卡片（历史任务兼容）。 */
function LegacyView({ advice }) {
  const items = advice?.items || []
  const sorted = [...items].sort((a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9))
  if (!sorted.length) {
    return (
      <div className="text-sm text-muted-foreground py-4 text-center">
        暂无明显需优化的点（指标良好或样本不足）。
      </div>
    )
  }
  return (
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
  )
}
