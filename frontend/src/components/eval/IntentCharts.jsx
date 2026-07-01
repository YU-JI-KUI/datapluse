/** 业务分类分布：横向柱状图（recharts）。柱尾显示「数量（百分比）」。 */
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LabelList,
} from 'recharts'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { SectionTitle } from './EvalPrimitives'

export default function IntentCharts({ insights }) {
  const raw = (insights?.by_intent || []).map(x => ({ name: x.name, count: x.count }))
  const total = raw.reduce((s, x) => s + x.count, 0)
  const data = raw
    .map(x => ({ ...x, pct: total ? x.count / total : 0 }))
    .sort((a, b) => b.count - a.count)

  if (data.length === 0) return null
  const height = Math.max(220, data.length * 34)
  const fmtPct = p => `${(p * 100).toFixed(1)}%`

  return (
    <Card>
      <CardHeader className="pb-3">
        <SectionTitle hint="各业务分类的样本量分布（占比 = 该分类 / 全部样本）">
          业务分类分布 <span className="text-xs text-muted-foreground font-normal">（共 {total} 条）</span>
        </SectionTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 64, top: 4, bottom: 4 }}>
            <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12, fill: '#6b7280' }} />
            <YAxis
              type="category"
              dataKey="name"
              width={130}
              tick={{ fontSize: 12, fill: '#374151' }}
            />
            <Tooltip
              cursor={{ fill: 'rgba(59,130,246,0.06)' }}
              formatter={(v, _n, p) => [`${v} 条（${fmtPct(p.payload.pct)}）`, '样本量']}
              contentStyle={{ fontSize: 12, borderRadius: 8 }}
            />
            <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={16}>
              {data.map((_, i) => <Cell key={i} fill="#3b82f6" />)}
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
