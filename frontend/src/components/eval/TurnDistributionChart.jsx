/** 会话轮次分布：按每通对话的总轮次动态分桶（1/2/3 轮单独 + 高轮次分位数归桶）。
 * 横向柱状图，柱尾显示「会话数（百分比）」。 */
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LabelList,
} from 'recharts'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { SectionTitle } from './EvalPrimitives'

export default function TurnDistributionChart({ filterStats }) {
  const raw = filterStats?.turn_distribution
  if (!raw || raw.length === 0) return null

  const total = raw.reduce((s, x) => s + x.count, 0)
  const data = raw.map(x => ({ ...x, pct: total ? x.count / total : 0 }))
  const fmtPct = p => `${(p * 100).toFixed(1)}%`
  const height = Math.max(200, data.length * 34)

  return (
    <Card>
      <CardHeader className="pb-3">
        <SectionTitle hint="按每通对话的总轮次分桶（区间由数据动态决定）；反映客户对话复杂度">
          会话轮次分布 <span className="text-xs text-muted-foreground font-normal">（共 {total} 通会话）</span>
        </SectionTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 72, top: 4, bottom: 4 }}>
            <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12, fill: '#6b7280' }} />
            <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 12, fill: '#374151' }} />
            <Tooltip
              cursor={{ fill: 'rgba(59,130,246,0.06)' }}
              formatter={(v, _n, p) => [`${v} 通（${fmtPct(p.payload.pct)}）`, '会话数']}
              contentStyle={{ fontSize: 12, borderRadius: 8 }}
            />
            <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={16}>
              {data.map((_, i) => <Cell key={i} fill="#6366f1" />)}
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
