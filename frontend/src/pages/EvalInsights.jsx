/**
 * AI 评测 · 问题洞察：基于评测明细，跨任务聚合当前 BU 的客户问题。
 * 三视图：① 高频问榜单（按原文聚合）② 每日提问频率 ③ 关键词提炼（TF-IDF，纯展示）。
 * BU 跟随左侧全局选择器（buChanged），故页面内不设 BU 下拉，只留业务分类 + 时间筛选。
 */
import { useEffect, useState, useCallback } from 'react'
import { toast } from 'sonner'
import { Loader2 } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { Card, CardContent } from '@/components/ui/card'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { evalApi, getCurrentBu } from '@/lib/api'
import { cn } from '@/lib/utils'

const RESP = (r) => r?.data?.data ?? {}

const TABS = [
  { key: 'top',      label: '高频问' },
  { key: 'daily',    label: '每日频率' },
  { key: 'keywords', label: '关键词提炼' },
]

const RANGES = [
  { value: 'all', label: '全部时间', days: 0 },
  { value: '7',   label: '近 7 天',  days: 7 },
  { value: '30',  label: '近 30 天', days: 30 },
]

function rangeToDates(value) {
  const r = RANGES.find(x => x.value === value)
  if (!r || !r.days) return { start: '', end: '' }
  const end = new Date()
  const start = new Date(end.getTime() - r.days * 86400000)
  const fmt = d => d.toISOString().slice(0, 10)
  return { start: fmt(start), end: fmt(end) }
}

export default function EvalInsights() {
  const [bu, setBu]         = useState(getCurrentBu())
  const [tab, setTab]       = useState('top')
  const [intent, setIntent] = useState('all')
  const [range, setRange]   = useState('all')
  const [loading, setLoading] = useState(false)
  const [qData, setQData]   = useState(null)   // { total, distinct, top_questions, daily }
  const [kwData, setKwData] = useState(null)   // { groups }

  const loadQuestions = useCallback(() => {
    const { start, end } = rangeToDates(range)
    const it = intent === 'all' ? '' : intent
    setLoading(true)
    evalApi.insightsQuestions(bu, { intent: it, start, end })
      .then(r => setQData(RESP(r)))
      .catch(e => toast.error(e.response?.data?.message || '加载失败'))
      .finally(() => setLoading(false))
  }, [bu, intent, range])

  const loadKeywords = useCallback(() => {
    const it = intent === 'all' ? '' : intent
    setLoading(true)
    evalApi.insightsKeywords(bu, it)
      .then(r => setKwData(RESP(r)))
      .catch(e => toast.error(e.response?.data?.message || '加载失败'))
      .finally(() => setLoading(false))
  }, [bu, intent])

  useEffect(() => {
    if (tab === 'keywords') loadKeywords()
    else loadQuestions()
  }, [tab, loadQuestions, loadKeywords])

  useEffect(() => {
    const onBuChange = (e) => { setBu(e.detail?.bu || getCurrentBu()); setIntent('all') }
    window.addEventListener('buChanged', onBuChange)
    return () => window.removeEventListener('buChanged', onBuChange)
  }, [])

  // 业务分类下拉选项：从高频问结果里的 intent 去重（复用评测已打的 j_intent）
  const intentOptions = Array.from(
    new Set((qData?.top_questions || []).map(x => x.intent).filter(Boolean))
  )

  const maxCnt = Math.max(1, ...(qData?.top_questions || []).map(x => x.count))

  return (
    <div className="p-6 max-w-5xl">
      <div className="flex items-baseline gap-2 mb-1">
        <h1 className="text-xl font-semibold">问题洞察</h1>
        {qData && (
          <span className="text-xs text-muted-foreground">
            共 {qData.total?.toLocaleString?.() ?? qData.total} 条评测明细
          </span>
        )}
      </div>
      <p className="text-sm text-muted-foreground mb-4">
        基于评测明细跨任务聚合，按当前业务单元统计。
      </p>

      {/* 页面内筛选：业务分类 + 时间 */}
      <div className="flex flex-wrap gap-2 mb-4 items-center">
        <Select value={intent} onValueChange={v => setIntent(v)}>
          <SelectTrigger className="w-auto min-w-[140px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">业务分类：全部</SelectItem>
            {intentOptions.map(i => <SelectItem key={i} value={i}>{i}</SelectItem>)}
          </SelectContent>
        </Select>
        {tab !== 'keywords' && (
          <Select value={range} onValueChange={v => setRange(v)}>
            <SelectTrigger className="w-auto min-w-[120px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              {RANGES.map(r => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
      </div>

      {/* tab 切换 */}
      <div className="flex gap-1 border-b mb-4">
        {TABS.map(t => {
          const on = tab === t.key
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                'px-4 py-2 text-sm border-b-2 -mb-px transition-colors',
                on ? 'border-blue-500 text-blue-600 font-medium'
                   : 'border-transparent text-muted-foreground hover:text-foreground'
              )}
            >
              {t.label}
            </button>
          )
        })}
      </div>

      {loading && (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="w-5 h-5 animate-spin mr-2" />加载中…
        </div>
      )}

      {!loading && tab === 'top' && (
        <TopQuestions data={qData} maxCnt={maxCnt} />
      )}
      {!loading && tab === 'daily' && (
        <DailyChart daily={qData?.daily || []} />
      )}
      {!loading && tab === 'keywords' && (
        <Keywords data={kwData} />
      )}
    </div>
  )
}

function TopQuestions({ data, maxCnt }) {
  const rows = data?.top_questions || []
  if (!rows.length) return <Empty text="当前筛选下暂无问题数据" />
  return (
    <div className="border rounded-lg divide-y">
      {rows.map((r, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-2.5">
          <span className="w-6 text-sm text-muted-foreground text-center">{i + 1}</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 text-sm">
              <span className="truncate">{r.question || '(空)'}</span>
              {r.intent && (
                <span className="text-xs px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 whitespace-nowrap">
                  {r.intent}
                </span>
              )}
            </div>
            <div className="mt-1 h-1.5 bg-gray-100 rounded overflow-hidden">
              <div className="h-full bg-blue-500 rounded"
                   style={{ width: `${Math.round(r.count / maxCnt * 100)}%` }} />
            </div>
          </div>
          <div className="text-right min-w-[72px]">
            <div className="text-sm font-medium">{r.count?.toLocaleString?.() ?? r.count}</div>
            <div className="text-xs text-muted-foreground">
              {r.ratio != null ? `${(r.ratio * 100).toFixed(1)}%` : ''}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function DailyChart({ daily }) {
  if (!daily.length) {
    return <Empty text="暂无带时间的问题数据（仅新上传、含「时间」列的评测有每日频率）" />
  }
  return (
    <Card>
      <CardContent className="pt-6">
        <div style={{ width: '100%', height: 320 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={daily} margin={{ top: 8, right: 24, bottom: 8, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} allowDecimals={false} domain={[0, 'dataMax + 1']} />
              <Tooltip />
              <Line type="monotone" dataKey="count" name="提问量"
                    stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}

function Keywords({ data }) {
  const groups = data?.groups || []
  if (!groups.length) return <Empty text="样本不足，暂无法提炼关键词" />
  const maxW = Math.max(1, ...groups.flatMap(g => g.keywords.map(k => k.weight)))
  return (
    <div className="space-y-4">
      {data?.sampled && (
        <p className="text-xs text-amber-600">
          数据量大，已按前 {data.sample_size?.toLocaleString?.()} 条问题采样提炼。
        </p>
      )}
      {groups.map(g => (
        <div key={g.intent}>
          <div className="flex items-center gap-2 mb-2 text-sm">
            <span className="font-medium">{g.intent}</span>
            <span className="text-xs text-muted-foreground">{g.doc_count} 条问题</span>
          </div>
          <div className="flex flex-wrap gap-2 items-baseline">
            {g.keywords.map(k => (
              <span key={k.word}
                    className="px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-700"
                    style={{ fontSize: `${Math.round(12 + k.weight / maxW * 10)}px` }}>
                {k.word}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function Empty({ text }) {
  return <div className="py-16 text-center text-sm text-muted-foreground">{text}</div>
}
