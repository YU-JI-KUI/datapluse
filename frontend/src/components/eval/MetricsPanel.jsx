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

// 指标口径说明（hover 显示），与 metrics.py 计算口径一致
const HINT = {
  kappa: 'Cohen\'s κ：Judge 与人工打标的一致性，且扣除了「瞎猜也会蒙对」的部分，比准确率更可信。'
       + '>0.8 几乎完全一致 / 0.6~0.8 较强 / 0.4~0.6 中等 / <0.4 弱（Judge 不可信，建议改提示词）。'
       + 'κ=0 等于瞎猜。',
  accuracy: '准确率 = Judge 判定与人工打标一致的条数 / 总条数。样本不均衡时会虚高，故同时看 κ。',
  macro_f1: '宏平均 F1 = 「是」「否」两类 F1 的简单平均。类别不均衡时比准确率更能反映真实表现。',
  confusion: '混淆矩阵：行=人工打标真值，列=Judge 预测。对角线（蓝）为判对，非对角线（红）为判错，'
           + '可看出 Judge 偏乐观（真否判成是）还是偏保守（真是判成否）。',
  precision: 'P 精确率 = Judge 判为该类的里面真的是该类的比例。低=爱误报（乱判成这类）→ 提示词收紧定义、补反例。',
  recall: 'R 召回率 = 真正属于该类的里面 Judge 抓到的比例。低=爱漏判 → 提示词放宽定义、补正例。',
  f1: 'F1 = P 与 R 的调和平均，综合分。高=既不爱误报也不爱漏判。',
}

function Hint({ text }) {
  return (
    <span title={text}
          className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full border border-muted-foreground/40 text-[9px] text-muted-foreground cursor-help align-middle">
      ?
    </span>
  )
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

function MiniBar({ label, v, hint }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-6 text-[11px] text-muted-foreground" title={hint}>{label}</span>
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
          <div className="text-xs text-muted-foreground">Cohen's κ <Hint text={HINT.kappa} /></div>
        </div>
        <div className="grid grid-cols-2 gap-2 flex-1">
          <div className="rounded-md bg-gray-50 px-3 py-2">
            <div className="text-sm font-semibold tabular-nums">{Math.round((m.accuracy ?? 0) * 100)}%</div>
            <div className="text-[11px] text-muted-foreground">准确率 <Hint text={HINT.accuracy} /></div>
          </div>
          <div className="rounded-md bg-gray-50 px-3 py-2">
            <div className="text-sm font-semibold tabular-nums">{(m.macro_f1 ?? 0).toFixed(2)}</div>
            <div className="text-[11px] text-muted-foreground">宏平均 F1 <Hint text={HINT.macro_f1} /></div>
          </div>
        </div>
      </div>

      {/* 混淆矩阵 2x2 */}
      <div>
        <div className="text-xs text-muted-foreground mb-1.5">混淆矩阵 <Hint text={HINT.confusion} /></div>
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
              <MiniBar label="P" v={v.precision} hint={HINT.precision} />
              <MiniBar label="R" v={v.recall} hint={HINT.recall} />
              <MiniBar label="F1" v={v.f1} hint={HINT.f1} />
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
