/**
 * AI 评测 · 问题洞察：基于评测明细，跨任务聚合当前 BU 的客户问题。
 * 四视图：① 高频问榜单 ② 每日提问频率 ③ 趋势对比（解决率/分发准确率随提问日期变化）
 *          ④ 关键词提炼（TF-IDF，纯展示）。
 * BU 跟随左侧全局选择器（buChanged），页面内不设 BU 下拉，只留业务分类 + 提问日期区间。
 * 关键：日期区间基于「数据里实际的提问日期范围」（options.date_min/max），默认落在有数据的
 * 窗口，进页面不查全量；分类下拉走独立 DISTINCT 接口，不依赖榜单结果。
 */
import { useEffect, useState, useCallback } from 'react'
import { toast } from 'sonner'
import { Loader2, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { evalApi, getCurrentBu } from '@/lib/api'
import { cn } from '@/lib/utils'

const RESP = (r) => r?.data?.data ?? {}

const TABS = [
  { key: 'top',      label: '高频问' },
  { key: 'daily',    label: '每日频率' },
  { key: 'trend',    label: '趋势对比' },
  { key: 'keywords', label: '关键词提炼' },
]

const pct = (v) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)

export default function EvalInsights() {
  const [bu, setBu]         = useState(getCurrentBu())
  const [tab, setTab]       = useState('top')
  const [intent, setIntent] = useState('all')
  const [start, setStart]   = useState('')     // 提问日期区间（真日期，来自 options 边界）
  const [end, setEnd]       = useState('')
  const [bounds, setBounds] = useState({ min: '', max: '' })  // 数据实际日期边界
  const [intents, setIntents] = useState([])   // 独立 DISTINCT 分类列表
  const [loading, setLoading] = useState(false)
  const [qData, setQData]   = useState(null)   // { total, distinct, top_questions, daily }
  const [tData, setTData]   = useState(null)   // { series }
  const [kwData, setKwData] = useState(null)   // { groups }

  // 切 BU：拉筛选器元数据，默认区间落到「数据实际范围」，不查全量、不用系统时间
  const loadOptions = useCallback((targetBu) => {
    evalApi.insightsOptions(targetBu)
      .then(r => {
        const d = RESP(r)
        setIntents(d.intents || [])
        setBounds({ min: d.date_min || '', max: d.date_max || '' })
        setStart(d.date_min || '')
        setEnd(d.date_max || '')
      })
      .catch(() => { setIntents([]); setBounds({ min: '', max: '' }) })
  }, [])

  useEffect(() => { loadOptions(bu) }, [bu, loadOptions])

  const loadQuestions = useCallback(() => {
    const it = intent === 'all' ? '' : intent
    setLoading(true)
    evalApi.insightsQuestions(bu, { intent: it, start, end })
      .then(r => setQData(RESP(r)))
      .catch(e => toast.error(e.response?.data?.message || '加载失败'))
      .finally(() => setLoading(false))
  }, [bu, intent, start, end])

  const loadTimeline = useCallback(() => {
    const it = intent === 'all' ? '' : intent
    setLoading(true)
    evalApi.insightsTimeline(bu, { intent: it, start, end })
      .then(r => setTData(RESP(r)))
      .catch(e => toast.error(e.response?.data?.message || '加载失败'))
      .finally(() => setLoading(false))
  }, [bu, intent, start, end])

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
    else if (tab === 'trend') loadTimeline()
    else loadQuestions()
  }, [tab, loadQuestions, loadTimeline, loadKeywords])

  useEffect(() => {
    const onBuChange = (e) => { setBu(e.detail?.bu || getCurrentBu()); setIntent('all') }
    window.addEventListener('buChanged', onBuChange)
    return () => window.removeEventListener('buChanged', onBuChange)
  }, [])

  const maxCnt = Math.max(1, ...(qData?.top_questions || []).map(x => x.count))
  const showDateRange = tab !== 'keywords'

  return (
    <div className="p-6 max-w-5xl">
      <div className="flex items-baseline gap-2 mb-1">
        <h1 className="text-xl font-semibold">问题洞察</h1>
        {tab !== 'keywords' && qData && (
          <span className="text-xs text-muted-foreground">
            共 {qData.total?.toLocaleString?.() ?? qData.total} 条评测明细
          </span>
        )}
      </div>
      <p className="text-sm text-muted-foreground mb-4">
        基于评测明细跨任务聚合，按当前业务单元统计。
      </p>

      {/* 页面内筛选：业务分类（独立 DISTINCT）+ 提问日期区间（数据实际范围） */}
      <div className="flex flex-wrap gap-2 mb-4 items-center">
        <Select value={intent} onValueChange={v => setIntent(v)}>
          <SelectTrigger className="w-auto min-w-[140px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">业务分类：全部</SelectItem>
            {intents.map(i => <SelectItem key={i} value={i}>{i}</SelectItem>)}
          </SelectContent>
        </Select>
        {showDateRange && (
          <div className="flex items-center gap-1.5 text-sm">
            <Input type="date" value={start} min={bounds.min} max={end || bounds.max}
                   onChange={e => setStart(e.target.value)}
                   className="w-auto h-9" />
            <span className="text-muted-foreground">至</span>
            <Input type="date" value={end} min={start || bounds.min} max={bounds.max}
                   onChange={e => setEnd(e.target.value)}
                   className="w-auto h-9" />
            {bounds.min && (
              <button
                onClick={() => { setStart(bounds.min); setEnd(bounds.max) }}
                className="text-xs text-blue-600 hover:underline ml-1 whitespace-nowrap">
                全部范围
              </button>
            )}
          </div>
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
      {!loading && tab === 'trend' && (
        <TrendCompare series={tData?.series || []} />
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
    return <Empty text="暂无带时间的问题数据（仅含「时间」列的评测有每日频率）" />
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

/** 趋势对比：解决率 / 分发准确率随提问日期变化，两条折线 + 首尾环比摘要。 */
function TrendCompare({ series }) {
  if (!series.length) {
    return <Empty text="暂无带时间的评测数据（仅含「时间」列的评测有趋势）" />
  }
  // recharts 折线数据：率转成百分比数值（null 断线）
  const chart = series.map(s => ({
    date: s.date,
    resolved: s.resolved_rate == null ? null : +(s.resolved_rate * 100).toFixed(1),
    dispatch: s.dispatch_accuracy == null ? null : +(s.dispatch_accuracy * 100).toFixed(1),
  }))
  const first = series[0]
  const last = series[series.length - 1]
  const deltaOf = (a, b) => (a == null || b == null ? null : b - a)
  const rDelta = deltaOf(first.resolved_rate, last.resolved_rate)
  const dDelta = deltaOf(first.dispatch_accuracy, last.dispatch_accuracy)

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <MetricCard label="解决率" first={first.resolved_rate} last={last.resolved_rate}
                    delta={rDelta} />
        <MetricCard label="分发准确率" first={first.dispatch_accuracy} last={last.dispatch_accuracy}
                    delta={dDelta} />
      </div>
      <Card>
        <CardContent className="pt-6">
          <div style={{ width: '100%', height: 340 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chart} margin={{ top: 8, right: 24, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} domain={[0, 100]} unit="%" />
                <Tooltip formatter={(v) => (v == null ? '—' : `${v}%`)} />
                <Legend />
                <Line type="monotone" dataKey="resolved" name="解决率" connectNulls
                      stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                <Line type="monotone" dataKey="dispatch" name="分发准确率" connectNulls
                      stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

/** 单个指标卡：首日率 → 末日率 + 区间环比（pp）。 */
function MetricCard({ label, first, last, delta }) {
  const up = delta != null && delta > 0
  const down = delta != null && delta < 0
  const Icon = up ? TrendingUp : down ? TrendingDown : Minus
  const color = up ? 'text-emerald-600' : down ? 'text-red-600' : 'text-muted-foreground'
  return (
    <Card>
      <CardContent className="py-4">
        <div className="text-xs text-muted-foreground mb-1">{label}</div>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-semibold">{pct(last)}</span>
          <span className={cn('flex items-center gap-0.5 text-sm', color)}>
            <Icon className="w-4 h-4" />
            {delta == null ? '—' : `${delta > 0 ? '+' : ''}${(delta * 100).toFixed(1)}pp`}
          </span>
        </div>
        <div className="text-xs text-muted-foreground mt-1">
          区间起点 {pct(first)} → 终点 {pct(last)}
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
