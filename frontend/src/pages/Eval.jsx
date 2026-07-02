/**
 * AI 评测：上传对话日志 Excel / 选样例 → 后台评测 → 轮询进度 → 结果报告。
 * 三态：upload（上传）/ running（评测中）/ result（结果）。
 */
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle, RotateCcw, ArrowLeft, History, Loader2, BookOpen,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { evalApi } from '@/lib/api'
import { EvalBadge } from '@/components/eval/EvalPrimitives'
import EvalUploader from '@/components/eval/EvalUploader'
import EvalProgress from '@/components/eval/EvalProgress'
import EvalResult from '@/components/eval/EvalResult'

// 使用说明是独立 HTML（public/eval-guide.html，fetch docs 的 md 渲染，md 唯一维护源）
const GUIDE_URL = '/eval-guide.html'
const _GUIDE_SEEN_KEY = 'eval_guide_seen'
function openGuide() { window.open(GUIDE_URL, '_blank', 'noopener') }

const RESP = (r) => r?.data?.data ?? {}   // datapulse 统一响应：res.data.data

// 进度轮询间隔。后端每 50 条一批上报进度，按并发 10 × 单条约 2 秒算，一批约 10 秒
// 才推进一次——轮询比这更快只会反复查到同一个进度值，白给 t_eval_task 加查询压力
// （5万条任务跑几小时 × 多用户同时看进度，压力线性叠加）。10 秒刚好匹配进度变化节奏。
const _POLL_INTERVAL_MS = 10000

export default function Eval() {
  const [backend, setBackend]   = useState('')
  const [view, setView]         = useState('upload')   // upload | running | result
  const [task, setTask]         = useState(null)
  const [result, setResult]     = useState(null)
  const [error, setError]       = useState(null)
  const [resumable, setResumable] = useState(null)
  const [busy, setBusy]         = useState(false)
  const [uploadPct, setUploadPct] = useState(0)   // 上传进度 0-100
  // 首次进页面显示醒目的「新人必读」提示条（新标签打开说明，浏览器可能拦截自动弹窗，
  // 故用提示条让用户主动点，比强开新标签体验好）；看过后不再显示。
  const [showGuideTip, setShowGuideTip] = useState(() => !localStorage.getItem(_GUIDE_SEEN_KEY))
  function dismissGuideTip() { localStorage.setItem(_GUIDE_SEEN_KEY, '1'); setShowGuideTip(false) }
  const pollRef = useRef(null)

  // 初始化：后端配置（BU 由左侧全局选择器决定，上传时 evalApi 自动带当前 BU）
  useEffect(() => {
    evalApi.config().then(r => setBackend(RESP(r).active_backend || '')).catch(() => {})
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  function startPolling(taskId) {
    setView('running')
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const t = RESP(await evalApi.getTask(taskId))
        setTask(t)
        if (t.status === 'done') {
          clearInterval(pollRef.current)
          const r = RESP(await evalApi.getResult(taskId))
          setResult(r)
          setView('result')
        } else if (t.status === 'failed') {
          clearInterval(pollRef.current)
          setError(t.error || '评测失败')
          if (t.can_resume) setResumable(taskId)
          setView('upload')
        }
      } catch (e) {
        clearInterval(pollRef.current)
        setError(e.response?.data?.message || '轮询任务状态失败')
        setView('upload')
      }
    }, _POLL_INTERVAL_MS)
  }

  async function handleUpload(file) {
    setError(null); setResumable(null); setBusy(true); setUploadPct(0)
    try {
      const onProgress = (e) => {
        if (e.total) setUploadPct(Math.round(e.loaded * 100 / e.total))
      }
      const t = RESP(await evalApi.upload(file, undefined, onProgress))   // bu 走全局当前 BU
      setTask(t)
      startPolling(t.task_id)
    } catch (e) {
      setError(e.response?.data?.message || '上传失败')
    } finally {
      setBusy(false); setUploadPct(0)
    }
  }

  async function handleSample(kind) {
    setError(null); setResumable(null); setBusy(true)
    try {
      const t = RESP(await evalApi.runSample(undefined, kind))   // bu 走全局当前 BU
      setTask(t)
      startPolling(t.task_id)
    } catch (e) {
      setError(e.response?.data?.message || '样例评测启动失败')
    } finally {
      setBusy(false)
    }
  }

  async function handleResume() {
    if (!resumable) return
    setError(null)
    try {
      await evalApi.resume(resumable)
      startPolling(resumable)
      setResumable(null)
    } catch (e) {
      setError(e.response?.data?.message || '续跑失败')
    }
  }

  function reset() {
    if (pollRef.current) clearInterval(pollRef.current)
    setTask(null); setResult(null); setError(null); setResumable(null); setView('upload')
  }

  return (
    <div className="p-8 space-y-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">AI 评测</h1>
          <p className="text-muted-foreground text-sm mt-1">
            上传对话日志 Excel，自动评测 BU 分发准确率、问题解决率，产出业务洞察与优化建议
            {backend && <EvalBadge tone={backend === 'pingan' ? 'good' : 'slate'} className="ml-2">
              {backend === 'pingan' ? '平安大模型' : 'Mock 后端'}
            </EvalBadge>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {view === 'result' && (
            <Button variant="outline" size="sm" onClick={reset}>
              <ArrowLeft className="w-4 h-4 mr-1.5" />新评测
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={openGuide}>
            <BookOpen className="w-4 h-4 mr-1.5" />使用说明
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link to="/eval/history"><History className="w-4 h-4 mr-1.5" />历史评测</Link>
          </Button>
        </div>
      </div>

      {/* 首次访问：醒目的新人必读提示条 */}
      {showGuideTip && (
        <div className="flex items-center gap-3 rounded-lg border border-indigo-200 bg-gradient-to-r from-indigo-50 to-blue-50 px-4 py-3 text-sm">
          <BookOpen className="w-5 h-5 text-indigo-600 shrink-0" />
          <span className="flex-1">
            <b>新人必读</b>：先花 2 分钟看《AI 评测使用说明》，了解每个指标怎么算、改哪里影响什么、改完要不要重跑。
          </span>
          <Button size="sm" onClick={() => { openGuide(); dismissGuideTip() }}>打开说明</Button>
          <Button variant="ghost" size="sm" onClick={dismissGuideTip}>知道了</Button>
        </div>
      )}

      {/* 错误条 */}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span className="flex-1">{error}</span>
          {resumable && (
            <Button variant="outline" size="sm" onClick={handleResume}>
              <RotateCcw className="w-4 h-4 mr-1.5" />断点续跑
            </Button>
          )}
        </div>
      )}

      {/* 主体 */}
      {view === 'upload' && (
        <EvalUploader onUpload={handleUpload} onSample={handleSample} busy={busy} uploadPct={uploadPct} />
      )}
      {view === 'running' && <EvalProgress task={task} />}
      {view === 'result' && <EvalResult taskId={task?.task_id} result={result} />}

      {busy && view !== 'running' && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />处理中…
        </div>
      )}
    </div>
  )
}
