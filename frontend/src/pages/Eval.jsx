/**
 * AI 评测：上传对话日志 Excel / 选样例 → 后台评测 → 轮询进度 → 结果报告。
 * 三态：upload（上传）/ running（评测中）/ result（结果）。
 */
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle, RotateCcw, ArrowLeft, History, Loader2,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { evalApi } from '@/lib/api'
import { EvalBadge } from '@/components/eval/EvalPrimitives'
import EvalUploader from '@/components/eval/EvalUploader'
import EvalProgress from '@/components/eval/EvalProgress'
import EvalResult from '@/components/eval/EvalResult'

const RESP = (r) => r?.data?.data ?? {}   // datapulse 统一响应：res.data.data

export default function Eval() {
  const [bus, setBus]           = useState([])
  const [bu, setBu]             = useState('securities')
  const [backend, setBackend]   = useState('')
  const [view, setView]         = useState('upload')   // upload | running | result
  const [task, setTask]         = useState(null)
  const [result, setResult]     = useState(null)
  const [error, setError]       = useState(null)
  const [resumable, setResumable] = useState(null)
  const [busy, setBusy]         = useState(false)
  const pollRef = useRef(null)

  // 初始化：BU 列表 + 后端配置
  useEffect(() => {
    evalApi.bus().then(r => {
      const list = RESP(r).bus || []
      setBus(list)
      if (list[0]) setBu(list[0].code)
    }).catch(() => {})
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
    }, 1000)
  }

  async function handleUpload(file) {
    setError(null); setResumable(null); setBusy(true)
    try {
      const t = RESP(await evalApi.upload(file, bu))
      setTask(t)
      startPolling(t.task_id)
    } catch (e) {
      setError(e.response?.data?.message || '上传失败')
    } finally {
      setBusy(false)
    }
  }

  async function handleSample(buCode, kind) {
    setError(null); setResumable(null); setBusy(true)
    try {
      const t = RESP(await evalApi.runSample(buCode, kind))
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
          <Button variant="outline" size="sm" asChild>
            <Link to="/eval/history"><History className="w-4 h-4 mr-1.5" />历史评测</Link>
          </Button>
        </div>
      </div>

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
        <EvalUploader
          bus={bus} bu={bu} onBuChange={setBu}
          onUpload={handleUpload} onSample={handleSample} busy={busy}
        />
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
