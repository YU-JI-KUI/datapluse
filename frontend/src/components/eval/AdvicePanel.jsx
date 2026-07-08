/** 优化建议：多专项卡片（每维度一段文本，可折叠）；兼容旧任务的结构化 items。 */
import { useState, useRef, useEffect } from 'react'
import { toast } from 'sonner'
import { AlertOctagon, AlertTriangle, Info, Lightbulb, Cpu, FileText, ChevronRight,
         ChevronsDownUp, ChevronsUpDown, RefreshCw, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { EvalBadge, SectionTitle } from './EvalPrimitives'
import AdviceMarkdown from './AdviceMarkdown'
import AdviceCardActions from './AdviceCardActions'
import { evalApi } from '@/lib/api'

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

/** 单张可折叠建议卡（受控）：open 由父的 openIds 决定。 */
function AdviceCard({ card, open, onToggle, taskId, onRefetch }) {
  return (
    <details open={open} className="group rounded-lg border">
      <summary
        className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 hover:bg-gray-50"
        onClick={(e) => { e.preventDefault(); onToggle(card.id) }}
      >
        <ChevronRight className={`w-4 h-4 shrink-0 text-gray-400 transition-transform ${open ? 'rotate-90' : ''}`} />
        <span className="font-medium text-sm">{card.title}</span>
        {card.dimension && <EvalBadge tone={DIM_TONE[card.dimension] || 'slate'}>{card.dimension}</EvalBadge>}
        {card.category && card.category !== '全局' && (
          <EvalBadge tone="slate">{card.category}</EvalBadge>
        )}
        <span className="ml-auto">
          <AdviceCardActions card={card} taskId={taskId} onRefetch={onRefetch} />
        </span>
      </summary>
      <div className="border-t px-4 py-3">
        <AdviceMarkdown text={card.text} />
      </div>
    </details>
  )
}

export default function AdvicePanel({ advice, taskId, onRefetch }) {
  const cards = advice?.cards
  const source = advice?.source

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <SectionTitle hint="按业务维度分专项生成，可展开查看详情">优化建议</SectionTitle>
          <div className="flex items-center gap-2">
            <SourceBadge source={source} />
            {taskId && <RegenerateButton taskId={taskId} onRefetch={onRefetch} />}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {cards ? <CardsView cards={cards} taskId={taskId} onRefetch={onRefetch} /> : <LegacyView advice={advice} />}
      </CardContent>
    </Card>
  )
}

/** 「重新生成建议」按钮：只重算 advice（不重 judge），轮询任务到 done 再刷新。 */
function RegenerateButton({ taskId, onRefetch }) {
  const [running, setRunning] = useState(false)
  const timer = useRef(null)

  useEffect(() => () => clearInterval(timer.current), [])

  async function handleClick() {
    if (running) return
    setRunning(true)
    const tip = toast.loading('正在重新生成优化建议…')
    try {
      await evalApi.rerunAdvice(taskId)
      // 轮询任务状态：rerunning → done 后刷新报告
      timer.current = setInterval(async () => {
        try {
          const res = await evalApi.getTask(taskId)
          const st = res?.data?.data?.status
          if (st && st !== 'rerunning') {
            clearInterval(timer.current)
            setRunning(false)
            const err = res?.data?.data?.error
            if (err) { toast.error(err, { id: tip }) }
            else { toast.success('优化建议已更新', { id: tip }); onRefetch?.() }
          }
        } catch { /* 轮询失败下次再试 */ }
      }, 2000)
    } catch (e) {
      setRunning(false)
      toast.error(e.response?.data?.message || '重新生成失败', { id: tip })
    }
  }

  return (
    <Button variant="outline" size="sm" disabled={running} onClick={handleClick}>
      {running
        ? <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" />生成中…</>
        : <><RefreshCw className="w-4 h-4 mr-1.5" />重新生成建议</>}
    </Button>
  )
}

/** 新结构：只展示 3 张全局卡（分类卡移到「业务洞察」对应分类下）。可折叠 + 全部展开/折叠。 */
function CardsView({ cards, taskId, onRefetch }) {
  // 只保留全局卡（分发诊断/解决率诊断/新分类发现）；分类卡在业务洞察里展示
  const globalCards = cards.filter((c) => c.category === '全局')
  // 全局卡默认全展开
  const [openIds, setOpenIds] = useState(() => new Set(globalCards.map((c) => c.id)))

  if (!globalCards.length) {
    return (
      <div className="text-sm text-muted-foreground py-4 text-center">
        暂无明显需优化的点（指标良好或样本不足）。
      </div>
    )
  }

  const allOpen = openIds.size === globalCards.length
  const toggle = (id) => setOpenIds((prev) => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">各业务分类的分发/解决率优化建议已移至「业务洞察」，点开对应分类查看。</span>
        <Button variant="ghost" size="sm" className="text-xs text-muted-foreground"
          onClick={() => setOpenIds(allOpen ? new Set() : new Set(globalCards.map((c) => c.id)))}>
          {allOpen
            ? <><ChevronsDownUp className="w-3.5 h-3.5 mr-1" />全部折叠</>
            : <><ChevronsUpDown className="w-3.5 h-3.5 mr-1" />全部展开</>}
        </Button>
      </div>
      {globalCards.map((c) => (
        <AdviceCard key={c.id} card={c} open={openIds.has(c.id)} onToggle={toggle}
          taskId={taskId} onRefetch={onRefetch} />
      ))}
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
