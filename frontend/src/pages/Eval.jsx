/**
 * AI 对话评测：上传 Excel / 选样例 → 后台评测 → 轮询进度 → 结果报告。
 * 三态：upload（上传）/ running（评测中）/ result（结果）。
 */
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  AlertTriangle, RotateCcw, ArrowLeft, History, Clock, FileSpreadsheet, Loader2,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { evalApi } from '@/lib/api'
import { formatDate } from '@/lib/utils'
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
  const [history, setHistory]   = useState([])
  const [historyOpen, setHistoryOpen] = useState(false)
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

  async function openHistory() {
    setHistoryOpen(true)
    try {
      const data = RESP(await evalApi.listTasks(1, 100))
      setHistory((data.list || []).filter(t => t.status === 'done'))
    } catch {
      setHistory([])
    }
  }

  async function loadHistory(taskId) {
    setHistoryOpen(false); setBusy(true)
    try {
      const t = RESP(await evalApi.getTask(taskId))
      const r = RESP(await evalApi.getResult(taskId))
      setTask(t); setResult(r); setView('result')
    } catch (e) {
      toast.error(e.response?.data?.message || '加载历史评测失败')
    } finally {
      setBusy(false)
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
          <h1 className="text-2xl font-bold">AI 对话评测</h1>
          <p className="text-muted-foreground text-sm mt-1">
            上传对话日志 Excel，自动评测 BU 分发准确率、端到端解决率，产出业务洞察与优化建议
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
          <Button variant="outline" size="sm" onClick={openHistory}>
            <History className="w-4 h-4 mr-1.5" />历史
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

      {/* 历史面板 */}
      {historyOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={() => setHistoryOpen(false)}>
          <div className="w-96 max-w-full h-full bg-background shadow-xl p-5 overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold">历史评测</h2>
              <EvalBadge tone="slate">{history.length} 条</EvalBadge>
            </div>
            {history.length === 0 ? (
              <div className="text-sm text-muted-foreground py-8 text-center">暂无已完成的评测记录</div>
            ) : (
              <div className="space-y-2">
                {history.map(t => (
                  <button
                    key={t.task_id}
                    onClick={() => loadHistory(t.task_id)}
                    className="w-full rounded-lg border p-3 text-left hover:bg-accent transition-colors"
                  >
                    <div className="flex items-center gap-2 font-medium text-sm truncate">
                      <FileSpreadsheet className="w-4 h-4 text-green-600 shrink-0" />
                      <span className="truncate">{t.filename}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-1.5 text-xs text-muted-foreground">
                      <EvalBadge tone={t.mode === 'calibration' ? 'info' : 'good'}>
                        {t.mode === 'calibration' ? '校准' : '生产'}
                      </EvalBadge>
                      <span>{t.bu_name}</span>
                      <span className="ml-auto flex items-center gap-1">
                        <Clock className="w-3 h-3" />{formatDate(t.finished_at || t.created_at)}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {busy && view !== 'running' && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />处理中…
        </div>
      )}
    </div>
  )
}
