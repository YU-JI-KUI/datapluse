/**
 * AI 评测页专用原子组件（datapulse 浅色风格）。
 * 把 ark 深色金融风的 tone（good/warn/bad/info/brand/slate）映射到 datapulse 配色。
 */
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

// tone → 浅色徽章配色
const TONE = {
  good:  'bg-green-100 text-green-700 border-green-200',
  brand: 'bg-blue-100 text-blue-700 border-blue-200',
  info:  'bg-sky-100 text-sky-700 border-sky-200',
  warn:  'bg-amber-100 text-amber-700 border-amber-200',
  bad:   'bg-red-100 text-red-700 border-red-200',
  slate: 'bg-gray-100 text-gray-600 border-gray-200',
}

// tone → 数值/图标前景色
const TONE_FG = {
  good:  'text-green-600',
  brand: 'text-blue-600',
  info:  'text-sky-600',
  warn:  'text-amber-600',
  bad:   'text-red-600',
  slate: 'text-gray-600',
}

export function EvalBadge({ children, tone = 'slate', className }) {
  return (
    <span className={cn(
      'inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap',
      TONE[tone] || TONE.slate, className,
    )}>
      {children}
    </span>
  )
}

export function StatCard({ label, value, sub, tone = 'brand', icon: Icon }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">{label}</span>
          {Icon && <Icon className={cn('w-4 h-4', TONE_FG[tone] || TONE_FG.brand)} />}
        </div>
        <div className={cn('mt-2 text-2xl font-bold', TONE_FG[tone] || TONE_FG.brand)}>
          {value}
        </div>
        {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
      </CardContent>
    </Card>
  )
}

// 是/否徽章：value 为 "是"/"否"，goodWhenYes 决定"是"是绿是红
export function YesNo({ value, goodWhenYes = true }) {
  if (value !== '是' && value !== '否') return <span className="text-muted-foreground">—</span>
  const isYes = value === '是'
  const good = goodWhenYes ? isYes : !isYes
  return <EvalBadge tone={good ? 'good' : 'bad'}>{value}</EvalBadge>
}

// 比率进度条 + 百分比。dangerLow=true 时低值标红（解决率类）
export function RateBar({ value, dangerLow = true, width = 'w-24' }) {
  const v = value == null ? 0 : value
  const pct = Math.round(v * 100)
  let color = 'bg-blue-500'
  if (dangerLow) {
    color = v >= 0.8 ? 'bg-green-500' : v >= 0.6 ? 'bg-amber-500' : 'bg-red-500'
  }
  return (
    <div className="flex items-center gap-2">
      <div className={cn('h-1.5 rounded-full bg-gray-200 overflow-hidden', width)}>
        <div className={cn('h-full rounded-full', color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums text-muted-foreground w-10">{pct}%</span>
    </div>
  )
}

export function SectionTitle({ children, hint }) {
  return (
    <div className="flex items-baseline gap-2">
      <h2 className="text-base font-semibold">{children}</h2>
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </div>
  )
}

// κ / F1 分数 → tone
export function metricTone(v) {
  if (v == null) return 'slate'
  if (v >= 0.8) return 'good'
  if (v >= 0.6) return 'brand'
  if (v >= 0.4) return 'warn'
  return 'bad'
}

export function pct(v) {
  return `${Math.round((v ?? 0) * 1000) / 10}%`
}
