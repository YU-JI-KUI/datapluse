/** 校准指标（仅 calibration 模式）：κ / 准确率 / 宏F1 / 混淆矩阵 / 分类别 P-R-F1。 */
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { SectionTitle, metricTone } from './EvalPrimitives'
import { cn } from '@/lib/utils'

const TONE_TEXT = {
  good:  'text-green-600',
  brand: 'text-blue-600',
  warn:  'text-amber-600',
  bad:   'text-red-600',
  slate: 'text-gray-500',
}

function ConfCell({ v, diag }) {
  return (
    <div className={cn(
      'rounded-md py-2 text-center text-sm font-medium tabular-nums',
      diag ? 'bg-blue-100 text-blue-700'
        : v > 0 ? 'bg-red-50 text-red-600'
        : 'bg-gray-50 text-gray-400',
    )}>
      {v}
    </div>
  )
}

function MiniBar({ label, v }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-6 text-[11px] text-muted-foreground">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-gray-200 overflow-hidden">
        <div className="h-full rounded-full bg-blue-500/70" style={{ width: `${Math.round((v || 0) * 100)}%` }} />
      </div>
      <span className="w-9 text-right text-[11px] tabular-nums text-muted-foreground">
        {v == null ? '—' : v.toFixed(2)}
      </span>
    </div>
  )
}

function MetricCard({ m }) {
  const cm = m.confusion_matrix || [[0, 0], [0, 0]]
  const kTone = metricTone(m.kappa)
  return (
    <div className="rounded-lg border p-4 space-y-4">
      <div className="flex items-baseline justify-between">
        <span className="font-medium">{m.name}</span>
        <span className="text-xs text-muted-foreground">n={m.n}</span>
      </div>

      {/* κ 大字 + 准确率/宏F1 */}
      <div className="flex items-end gap-4">
        <div>
          <div className={cn('text-3xl font-bold tabular-nums', TONE_TEXT[kTone])}>
            {m.kappa == null ? '—' : m.kappa.toFixed(3)}
          </div>
          <div className="text-xs text-muted-foreground">Cohen's κ</div>
        </div>
        <div className="grid grid-cols-2 gap-2 flex-1">
          <div className="rounded-md bg-gray-50 px-3 py-2">
            <div className="text-sm font-semibold tabular-nums">{Math.round((m.accuracy ?? 0) * 100)}%</div>
            <div className="text-[11px] text-muted-foreground">准确率</div>
          </div>
          <div className="rounded-md bg-gray-50 px-3 py-2">
            <div className="text-sm font-semibold tabular-nums">{(m.macro_f1 ?? 0).toFixed(2)}</div>
            <div className="text-[11px] text-muted-foreground">宏平均 F1</div>
          </div>
        </div>
      </div>

      {/* 混淆矩阵 2x2 */}
      <div>
        <div className="text-xs text-muted-foreground mb-1.5">混淆矩阵</div>
        <div className="grid grid-cols-[auto_1fr_1fr] gap-1.5 items-center">
          <div />
          <div className="text-center text-[11px] text-muted-foreground">预测·是</div>
          <div className="text-center text-[11px] text-muted-foreground">预测·否</div>
          <div className="text-right text-[11px] text-muted-foreground pr-1">真·是</div>
          <ConfCell v={cm[0][0]} diag />
          <ConfCell v={cm[0][1]} />
          <div className="text-right text-[11px] text-muted-foreground pr-1">真·否</div>
          <ConfCell v={cm[1][0]} />
          <ConfCell v={cm[1][1]} diag />
        </div>
      </div>

      {/* per_label */}
      {m.per_label && (
        <div className="space-y-2">
          {Object.entries(m.per_label).map(([label, v]) => (
            <div key={label} className="space-y-1">
              <div className="text-[11px] font-medium">{label}</div>
              <MiniBar label="P" v={v.precision} />
              <MiniBar label="R" v={v.recall} />
              <MiniBar label="F1" v={v.f1} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function MetricsPanel({ metrics }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <SectionTitle hint="人工打标 vs Judge 一致性，证明评测可信">校准指标</SectionTitle>
      </CardHeader>
      <CardContent>
        {!metrics?.length ? (
          <div className="text-sm text-muted-foreground py-4 text-center">
            当前数据没有可用的二值人工打标，无法计算校准指标。
          </div>
        ) : (
          <div className="grid md:grid-cols-2 gap-3">
            {metrics.map((m, i) => <MetricCard key={i} m={m} />)}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
