/** 优化建议：多专项卡片（每维度一段文本，可折叠）；兼容旧任务的结构化 items。 */
import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { toast } from 'sonner'
import { AlertOctagon, AlertTriangle, Info, Lightbulb, Cpu, FileText, ChevronRight,
         ChevronsDownUp, ChevronsUpDown, RefreshCw, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { EvalBadge, SectionTitle } from './EvalPrimitives'
import { evalApi } from '@/lib/api'

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

/**
 * 清洗模型输出的噪声，保证 markdown 干净可渲染：
 * 模型偶尔吐图片/HTML 徽章（react-markdown 不渲染 → 坏图/原文）、连续感叹号星号等噪声。
 * 提示词已约束，这里是前端兜底。只动新 cards 分支。
 */
function sanitizeAdviceText(text) {
  if (!text) return ''
  return text
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')        // 去图片 ![alt](url)（含 shields.io 徽章）
    .replace(/<\/?[a-zA-Z][^>]*>/g, '')          // 去裸 HTML 标签 <span> </div> 等
    .replace(/[!！]{2,}/g, '')                    // 连续感叹号噪声
    .replace(/\*{3,}/g, '**')                     // 3+ 连星折成加粗
    .replace(/\n{3,}/g, '\n\n')                   // 多余空行收敛
    .trim()
}

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
function AdviceCard({ card, open, onToggle }) {
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
      </summary>
      <div className="border-t px-4 py-3">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>
          {sanitizeAdviceText(card.text) || '_（无内容）_'}
        </ReactMarkdown>
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
        {cards ? <CardsView cards={cards} /> : <LegacyView advice={advice} />}
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

/** 新结构：一行一卡、可折叠（受控）+ 全部展开/折叠。 */
function CardsView({ cards }) {
  // 默认：全局卡展开、逐分类折叠
  const [openIds, setOpenIds] = useState(() =>
    new Set(cards.filter((c) => c.category === '全局').map((c) => c.id)))

  if (!cards.length) {
    return (
      <div className="text-sm text-muted-foreground py-4 text-center">
        暂无明显需优化的点（指标良好或样本不足）。
      </div>
    )
  }

  const allOpen = openIds.size === cards.length
  const toggle = (id) => setOpenIds((prev) => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <Button variant="ghost" size="sm" className="text-xs text-muted-foreground"
          onClick={() => setOpenIds(allOpen ? new Set() : new Set(cards.map((c) => c.id)))}>
          {allOpen
            ? <><ChevronsDownUp className="w-3.5 h-3.5 mr-1" />全部折叠</>
            : <><ChevronsUpDown className="w-3.5 h-3.5 mr-1" />全部展开</>}
        </Button>
      </div>
      {cards.map((c) => (
        <AdviceCard key={c.id} card={c} open={openIds.has(c.id)} onToggle={toggle} />
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
