/** 评测来源分布：整份日志按「活动标问 / 规则短路 / AI 评测」拆分的横向柱状图。
 * 每个活动标问一根、每条规则一根、其余走 AI 的合并一根，用颜色区分三类。 */
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LabelList,
} from 'recharts'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { SectionTitle } from './EvalPrimitives'

const COLORS = { activity: '#94a3b8', rule: '#22c55e', llm: '#3b82f6' }
const KIND_LABEL = { activity: '活动标问', rule: '规则短路', llm: 'AI 评测' }

export default function SourceBreakdownChart({ filterStats }) {
  const sb = filterStats?.source_breakdown
  if (!sb) return null

  const activityTotal = (sb.activity || []).reduce((s, x) => s + x.count, 0)
  const ruleTotal = (sb.rule || []).reduce((s, x) => s + x.count, 0)
  const grand = activityTotal + ruleTotal + (sb.llm || 0)
  const fmtPct = p => `${(p * 100).toFixed(1)}%`
  const withPct = (x, kind) => ({ ...x, kind, pct: grand ? x.count / grand : 0 })

  const data = [
    ...(sb.activity || []).map(x => withPct(x, 'activity')),
    ...(sb.rule || []).map(x => withPct(x, 'rule')),
    ...(sb.llm ? [withPct({ name: 'AI 评测（其余）', count: sb.llm }, 'llm')] : []),
  ].filter(d => d.count > 0)

  if (data.length === 0) return null

  const height = Math.max(220, data.length * 34)

  return (
    <Card>
      <CardHeader className="pb-3">
        <SectionTitle hint="整份日志按处理来源拆分：活动标问(跳过)、规则短路(免LLM)、AI 评测">
          评测来源分布
        </SectionTitle>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground mt-1">
          <span><i className="inline-block w-2.5 h-2.5 rounded-sm mr-1 align-middle" style={{ background: COLORS.activity }} />活动标问 {activityTotal} 条（{fmtPct(grand ? activityTotal / grand : 0)}，跳过）</span>
          <span><i className="inline-block w-2.5 h-2.5 rounded-sm mr-1 align-middle" style={{ background: COLORS.rule }} />规则短路 {ruleTotal} 条（{fmtPct(grand ? ruleTotal / grand : 0)}，免 LLM）</span>
          <span><i className="inline-block w-2.5 h-2.5 rounded-sm mr-1 align-middle" style={{ background: COLORS.llm }} />AI 评测 {sb.llm || 0} 条（{fmtPct(grand ? (sb.llm || 0) / grand : 0)}）</span>
          <span className="text-foreground font-medium">日志共 {grand} 条</span>
        </div>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 72, top: 4, bottom: 4 }}>
            <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12, fill: '#6b7280' }} />
            <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 12, fill: '#374151' }} />
            <Tooltip
              formatter={(v, _n, p) => [`${v} 条（${fmtPct(p.payload.pct)}）`, KIND_LABEL[p.payload.kind] || '']}
              labelFormatter={l => l}
            />
            <Bar dataKey="count" radius={[0, 4, 4, 0]}>
              {data.map((d, i) => <Cell key={i} fill={COLORS[d.kind]} />)}
              <LabelList dataKey="count" position="right"
                content={({ x, y, width, height: h, value, index }) => (
                  <text x={x + width + 6} y={y + h / 2} dy={4} fontSize={11} fill="#6b7280">
                    {value}（{fmtPct(data[index].pct)}）
                  </text>
                )} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
