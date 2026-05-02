import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell
} from 'recharts'
import {
  Database, CheckCircle, AlertTriangle, Cpu,
  ArrowRight, Play, RefreshCw, Tag, Clock, Zap, Timer,
  CheckCheck, ChevronRight, XCircle, BrainCircuit,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { dataApi, pipelineApi, getCurrentDatasetId } from '@/lib/api'
import { toast } from 'sonner'
import { useState, useEffect } from 'react'

// ── 常量 ────────────────────────────────────────────────────────────────────

const STATUS_CONFIG = [
  { key: 'raw',           label: '原始',    color: '#6b7280' },
  { key: 'cleaned',       label: '已清洗',  color: '#3b82f6' },
  { key: 'pre_annotated', label: '预标注',  color: '#8b5cf6' },
  { key: 'annotated',     label: '已标注',  color: '#f97316' },
  { key: 'checked',       label: '已检测',  color: '#22c55e' },
]

const PIPELINE_STEPS = [
  { key: 'process',      label: '数据清洗',   icon: '🧹' },
  { key: 'pre_annotate', label: '预标注',     icon: '🤖' },
  { key: 'check',        label: '冲突检测',   icon: '🔍' },
]

// ── 工具函数 ─────────────────────────────────────────────────────────────────

function fmtDuration(seconds) {
  if (!seconds || seconds <= 0) return '-'
  if (seconds < 60) return `${Math.round(seconds)}秒`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return s > 0 ? `${m}分${s}秒` : `${m}分钟`
}

function fmtNum(n) {
  if (n == null) return '-'
  return Number(n).toLocaleString('zh-CN')
}

// ── 子组件 ───────────────────────────────────────────────────────────────────

function StatCard({ title, value, icon: Icon, color, sub }) {
  return (
    <Card>
      <CardContent className="p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <p className="text-3xl font-bold mt-1">{value ?? '-'}</p>
            {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
          </div>
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${color}`}>
            <Icon className="w-6 h-6 text-white" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// 步骤时间轴（运行中/完成）
function StepTimeline({ currentStep, pipelineStatus, results }) {
  const stepIndex = PIPELINE_STEPS.findIndex(s => s.key === currentStep)

  return (
    <div className="flex items-center gap-1 w-full">
      {PIPELINE_STEPS.map((step, idx) => {
        const isCompleted = pipelineStatus === 'completed'
          || (pipelineStatus === 'running' && idx < stepIndex)
        const isCurrent   = pipelineStatus === 'running' && idx === stepIndex
        const isPending   = !isCompleted && !isCurrent

        return (
          <div key={step.key} className="flex items-center flex-1 min-w-0">
            {/* 步骤圆点 */}
            <div className="flex flex-col items-center gap-1 flex-shrink-0">
              <div className={`
                w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all
                ${isCompleted ? 'bg-green-500 text-white' :
                  isCurrent   ? 'bg-blue-500 text-white ring-4 ring-blue-200 animate-pulse' :
                                'bg-muted text-muted-foreground'}
              `}>
                {isCompleted ? <CheckCircle className="w-4 h-4" /> : step.icon}
              </div>
              <span className={`text-[10px] whitespace-nowrap font-medium
                ${isCompleted ? 'text-green-600' :
                  isCurrent   ? 'text-blue-600' :
                                'text-muted-foreground'}`}>
                {step.label}
              </span>
            </div>
            {/* 连接线 */}
            {idx < PIPELINE_STEPS.length - 1 && (
              <div className={`h-0.5 flex-1 mx-1 rounded transition-all
                ${isCompleted ? 'bg-green-400' : 'bg-muted'}`}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

// 运行中的实时进度详情
function RunningDetail({ pipeline }) {
  const detail = pipeline.detail || {}
  const {
    processed, total, skipped, pct,
    speed_per_sec, eta_seconds, elapsed_seconds,
  } = detail

  const progress = pipeline.progress || 0

  return (
    <div className="space-y-4">
      {/* 进度条 */}
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs font-medium">
          <span className="text-blue-700">
            {PIPELINE_STEPS.find(s => s.key === pipeline.current_step)?.label || pipeline.current_step}
          </span>
          <span className="text-blue-600 tabular-nums">{progress}%</span>
        </div>
        <Progress value={progress} className="h-2" />
      </div>

      {/* 数量进度 */}
      {total > 0 && (
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">进度</span>
          <span className="font-mono font-medium tabular-nums">
            {fmtNum(processed)} / {fmtNum(total)}
            {skipped > 0 && <span className="text-muted-foreground ml-1">({fmtNum(skipped)} 跳过)</span>}
          </span>
        </div>
      )}

      {/* 速度 + 剩余时间 + 已用时 */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-blue-50 rounded-lg p-2 text-center">
          <div className="flex items-center justify-center gap-1 text-blue-500 mb-0.5">
            <Zap className="w-3 h-3" />
            <span className="text-[10px]">速度</span>
          </div>
          <div className="text-xs font-bold tabular-nums text-blue-700">
            {speed_per_sec != null ? `${Math.round(speed_per_sec)}/s` : '-'}
          </div>
        </div>
        <div className="bg-orange-50 rounded-lg p-2 text-center">
          <div className="flex items-center justify-center gap-1 text-orange-500 mb-0.5">
            <Timer className="w-3 h-3" />
            <span className="text-[10px]">剩余</span>
          </div>
          <div className="text-xs font-bold tabular-nums text-orange-700">
            {fmtDuration(eta_seconds)}
          </div>
        </div>
        <div className="bg-gray-50 rounded-lg p-2 text-center">
          <div className="flex items-center justify-center gap-1 text-gray-500 mb-0.5">
            <Clock className="w-3 h-3" />
            <span className="text-[10px]">已用时</span>
          </div>
          <div className="text-xs font-bold tabular-nums text-gray-700">
            {fmtDuration(elapsed_seconds)}
          </div>
        </div>
      </div>
    </div>
  )
}

// 完成后的结果汇总
function CompletedResults({ pipeline }) {
  const results = Array.isArray(pipeline.results) ? pipeline.results : []

  const stepLabel = {
    process:      '数据清洗',
    pre_annotate: 'LLM 预标注',
    check:        '冲突检测',
  }

  function stepSummary(r) {
    if (!r) return '-'
    const step = r.step
    if (step === 'process')
      return `${fmtNum(r.processed)} 条清洗完成${r.skipped > 0 ? `，${fmtNum(r.skipped)} 跳过` : ''}`
    if (step === 'pre_annotate')
      return `${fmtNum(r.annotated)} 条已预标注`
    if (step === 'check') {
      const clean     = r.clean    ?? 0
      const lConflict = r.label_conflicts    ?? 0
      const sConflict = r.semantic_conflicts ?? 0
      return `${fmtNum(clean)} 条通过，${fmtNum(lConflict + sConflict)} 条冲突（标签 ${fmtNum(lConflict)} / 语义 ${fmtNum(sConflict)}）`
    }
    return JSON.stringify(r)
  }

  return (
    <div className="space-y-2">
      {PIPELINE_STEPS.map(step => {
        const r = results.find(x => x.step === step.key)
        return (
          <div key={step.key} className="flex items-start gap-2 text-xs">
            <CheckCheck className="w-3.5 h-3.5 text-green-500 flex-shrink-0 mt-0.5" />
            <div>
              <span className="font-medium text-foreground">{stepLabel[step.key]}</span>
              <span className="text-muted-foreground ml-1.5">{r ? stepSummary(r) : '已完成'}</span>
            </div>
          </div>
        )
      })}

      {pipeline.finished_at && (
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground pt-1 border-t">
          <Clock className="w-3 h-3" />
          完成于 {new Date(pipeline.finished_at).toLocaleString('zh-CN')}
        </div>
      )}
    </div>
  )
}

// 向量化离线任务状态卡
function EmbedJobCard({ embedJob }) {
  if (!embedJob?.status) return null

  const isRunning   = embedJob.status === 'running'
  const isCompleted = embedJob.status === 'completed'
  const isError     = embedJob.status === 'error'

  return (
    <div className={`rounded-lg border p-3 text-xs space-y-2
      ${isRunning   ? 'border-blue-200 bg-blue-50' :
        isCompleted ? 'border-green-200 bg-green-50' :
        isError     ? 'border-red-200 bg-red-50' :
                      'border-muted bg-muted/30'}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <BrainCircuit className={`w-3.5 h-3.5
            ${isRunning   ? 'text-blue-500 animate-pulse' :
              isCompleted ? 'text-green-600' :
              isError     ? 'text-red-500' : 'text-muted-foreground'}`}
          />
          <span className={`font-medium
            ${isRunning   ? 'text-blue-700' :
              isCompleted ? 'text-green-700' :
              isError     ? 'text-red-700' : 'text-muted-foreground'}`}>
            {isRunning   ? '向量化进行中…' :
             isCompleted ? '向量化已完成' :
             isError     ? '向量化失败' : '向量化空闲'}
          </span>
        </div>
        <span className="text-muted-foreground tabular-nums">
          {isRunning && `${embedJob.progress || 0}%`}
          {!isRunning && embedJob.detail?.elapsed_s != null && `耗时 ${embedJob.detail.elapsed_s}s`}
        </span>
      </div>

      {isRunning && (
        <Progress value={embedJob.progress || 0} className="h-1" />
      )}

      {isCompleted && (
        <p className="text-green-600">
          {embedJob.detail?.new_vectors != null && (
            <>新增 {fmtNum(embedJob.detail.new_vectors)} 条向量</>
          )}
          {embedJob.detail?.index_size != null && (
            <>，索引总量 {fmtNum(embedJob.detail.index_size)}</>
          )}
          {embedJob.detail?.skipped > 0 && (
            <span className="text-muted-foreground ml-1">
              （{fmtNum(embedJob.detail.skipped)} 条已有向量，跳过）
            </span>
          )}
        </p>
      )}

      {isError && (
        <p className="text-red-600">{embedJob.detail?.error || '未知错误'}</p>
      )}

      {embedJob.updated_at && (
        <p className="text-muted-foreground">
          更新于 {embedJob.updated_at.slice(0, 16).replace('T', ' ')}
        </p>
      )}
    </div>
  )
}

// ── 主页面 ───────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const navigate  = useNavigate()
  const [runningPipeline, setRunningPipeline] = useState(false)
  const [datasetId, setDatasetId] = useState(() => getCurrentDatasetId())

  useEffect(() => {
    const handler = (e) => setDatasetId(e.detail.datasetId)
    window.addEventListener('datasetChanged', handler)
    if (datasetId === null) {
      const check = () => {
        const cur = getCurrentDatasetId()
        if (cur !== null) setDatasetId(cur)
        else setTimeout(check, 100)
      }
      check()
    }
    return () => window.removeEventListener('datasetChanged', handler)
  }, [])

  // Stats 轮询：固定 15s，状态不影响
  const { data: statsRes, refetch: refetchStats } = useQuery({
    queryKey:              ['stats', datasetId],
    queryFn:               () => dataApi.stats(datasetId),
    refetchInterval:       15_000,
    refetchIntervalInBackground: true,   // 窗口非激活态也继续轮询（修复 Windows 下不更新问题）
    enabled:               datasetId !== null,
  })

  // Pipeline 轮询：
  //   主流程 running → 每 2s 快速刷新
  //   embed_job running → 每 3s 刷新（离线任务，不需要那么频繁）
  //   其他状态 → 停止自动轮询
  const { data: pipelineRes, refetch: refetchPipeline } = useQuery({
    queryKey: ['pipeline-status', datasetId],
    queryFn:  () => pipelineApi.status(datasetId),
    refetchInterval: (query) => {
      const d = query.state.data?.data?.data
      if (d?.status === 'running') return 2_000
      if (d?.embed_job?.status === 'running') return 3_000
      return false
    },
    refetchIntervalInBackground: true,   // 修复 Windows 下后台轮询不工作
    enabled: datasetId !== null,
  })

  const stats    = statsRes?.data?.data    || {}
  const pipeline = pipelineRes?.data?.data || {}
  const embedJob = pipeline.embed_job      || {}

  const chartData = STATUS_CONFIG.map(s => ({
    name:  s.label,
    count: stats[s.key] || 0,
    color: s.color,
  }))

  async function handleRunPipeline() {
    setRunningPipeline(true)
    try {
      await pipelineApi.run(datasetId)
      toast.success('Pipeline 已启动，后台运行中')
      refetchPipeline()
    } catch (err) {
      toast.error(err.response?.data?.detail || '启动失败')
    } finally {
      setRunningPipeline(false)
    }
  }

  const isRunning   = pipeline.status === 'running'
  const isCompleted = pipeline.status === 'completed'
  const isError     = pipeline.status === 'error'

  const statusBadgeVariant = {
    idle:      'secondary',
    running:   'default',
    completed: 'success',
    error:     'destructive',
  }[pipeline.status] || 'secondary'

  const statusLabel = {
    idle:      '空闲',
    running:   '运行中',
    completed: '已完成',
    error:     '出错',
  }[pipeline.status] || (pipeline.status || '空闲')

  return (
    <div className="p-8 space-y-6">

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground text-sm mt-1">数据飞轮全局概览</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => { refetchStats(); refetchPipeline() }}>
            <RefreshCw className="w-4 h-4 mr-2" /> 刷新
          </Button>
          <Button
            size="sm"
            onClick={handleRunPipeline}
            disabled={runningPipeline || isRunning}
          >
            <Play className="w-4 h-4 mr-2" />
            {isRunning ? '运行中...' : '运行 Pipeline'}
          </Button>
        </div>
      </div>

      {/* ── Pipeline 运行横幅（仅 running 时显示）────────────────────────────── */}
      {isRunning && (
        <Card className="border-blue-200 bg-blue-50">
          <CardContent className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                <span className="text-sm font-semibold text-blue-700">Pipeline 运行中</span>
              </div>
              <span className="text-xs text-blue-500 tabular-nums">
                {pipeline.started_at && `开始于 ${new Date(pipeline.started_at).toLocaleTimeString('zh-CN')}`}
              </span>
            </div>

            {/* 步骤时间轴 */}
            <StepTimeline
              currentStep={pipeline.current_step}
              pipelineStatus={pipeline.status}
              results={pipeline.results}
            />

            {/* 当前步骤进度详情 */}
            {pipeline.detail && Object.keys(pipeline.detail).length > 0 && (
              <div className="pt-1">
                <RunningDetail pipeline={pipeline} />
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Stat cards ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard title="总数据量"   value={fmtNum(stats.total)}         icon={Database}     color="bg-gray-700" />
        <StatCard title="待标注"     value={fmtNum(stats.pre_annotated)} icon={Cpu}          color="bg-violet-500" sub="预标注完成" />
        <StatCard title="已标注"     value={fmtNum(stats.annotated)}     icon={Tag}          color="bg-orange-500" sub="人工标注" />
        <StatCard title="高质量数据" value={fmtNum(stats.checked)}       icon={CheckCircle}  color="bg-green-500"  sub="通过冲突检测" />
      </div>

      {/* ── 图表 + Pipeline 状态面板 ─────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* 柱状图 */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">各阶段数据分布</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData} barSize={40}>
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip formatter={(v) => [fmtNum(v), '数量']} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Pipeline 状态面板 */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center justify-between">
              Pipeline 状态
              <Badge variant={statusBadgeVariant} className={isRunning ? 'animate-pulse' : ''}>
                {statusLabel}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">

            {/* 错误信息 */}
            {isError && pipeline.error && (
              <div className="flex items-start gap-2 text-xs text-red-600 bg-red-50 rounded-lg p-3 border border-red-200">
                <XCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                <span>{pipeline.error}</span>
              </div>
            )}

            {/* 运行中：步骤轴 + 简版进度 */}
            {isRunning && (
              <div className="space-y-3">
                <StepTimeline
                  currentStep={pipeline.current_step}
                  pipelineStatus={pipeline.status}
                />
                {pipeline.detail && Object.keys(pipeline.detail).length > 0 && (
                  <RunningDetail pipeline={pipeline} />
                )}
              </div>
            )}

            {/* 完成：结果汇总 */}
            {isCompleted && (
              <CompletedResults pipeline={pipeline} />
            )}

            {/* 空闲 / 未启动 */}
            {!isRunning && !isCompleted && !isError && (
              <p className="text-xs text-muted-foreground">
                点击「运行 Pipeline」开始全量处理。
              </p>
            )}

            {/* 向量化离线任务状态（独立于主 Pipeline，始终显示） */}
            {embedJob.status && (
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1.5">离线任务</p>
                <EmbedJobCard embedJob={embedJob} />
              </div>
            )}

            {/* 时间信息（非运行中时展示） */}
            {!isRunning && (pipeline.started_at || pipeline.finished_at) && (
              <div className="text-xs text-muted-foreground space-y-1 border-t pt-3">
                {pipeline.started_at && (
                  <div className="flex items-center gap-1.5">
                    <Play className="w-3 h-3" />
                    开始：{new Date(pipeline.started_at).toLocaleString('zh-CN')}
                  </div>
                )}
                {pipeline.finished_at && (
                  <div className="flex items-center gap-1.5">
                    <CheckCircle className="w-3 h-3" />
                    结束：{new Date(pipeline.finished_at).toLocaleString('zh-CN')}
                  </div>
                )}
              </div>
            )}

            {/* 快速导航 */}
            <div className="pt-1 space-y-1 border-t">
              <p className="text-xs font-medium text-muted-foreground pb-1">快速操作</p>
              {[
                { path: '/data',       Icon: Database,      label: '上传数据' },
                { path: '/annotation', Icon: Tag,           label: '开始标注' },
                { path: '/conflicts',  Icon: AlertTriangle, label: '冲突检测' },
              ].map(({ path, Icon, label }) => (
                <button
                  key={path}
                  onClick={() => navigate(path)}
                  className="flex items-center justify-between w-full text-sm px-3 py-2 rounded-lg hover:bg-accent transition-colors"
                >
                  <span className="flex items-center gap-2">
                    <Icon className="w-4 h-4" />{label}
                  </span>
                  <ChevronRight className="w-3 h-3 opacity-40" />
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

      </div>
    </div>
  )
}
