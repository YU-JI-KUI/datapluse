/** 业务分类分布：横向柱状图（recharts）。 */
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { SectionTitle } from './EvalPrimitives'

export default function IntentCharts({ insights }) {
  const data = (insights?.by_intent || [])
    .map(x => ({ name: x.name, count: x.count }))
    .sort((a, b) => b.count - a.count)

  if (data.length === 0) return null
  const height = Math.max(220, data.length * 30)

  return (
    <Card>
      <CardHeader className="pb-3">
        <SectionTitle hint="各业务分类的样本量分布">业务分类分布</SectionTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 4 }}>
            <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12, fill: '#6b7280' }} />
            <YAxis
              type="category"
              dataKey="name"
              width={130}
              tick={{ fontSize: 12, fill: '#374151' }}
            />
            <Tooltip
              cursor={{ fill: 'rgba(59,130,246,0.06)' }}
              formatter={(v) => [`${v} 条`, '样本量']}
              contentStyle={{ fontSize: 12, borderRadius: 8 }}
            />
            <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={16}>
              {data.map((_, i) => <Cell key={i} fill="#3b82f6" />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
