/**
 * AI 评测 · 评测报告：按 task_id 加载并展示某次评测的完整报告。
 * 历史页「查看详情」跳到这里，独立于评测页（评测页只负责上传起评测）。
 */
import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { toast } from 'sonner'
import { ArrowLeft, Loader2, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { EvalBadge } from '@/components/eval/EvalPrimitives'
import EvalResult from '@/components/eval/EvalResult'
import { evalApi } from '@/lib/api'

const RESP = (r) => r?.data?.data ?? {}

export default function EvalReport() {
  const { taskId } = useParams()
  const navigate = useNavigate()
  const [task, setTask]       = useState(null)
  const [result, setResult]   = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(null)
    Promise.all([evalApi.getTask(taskId), evalApi.getResult(taskId)])
      .then(([tRes, rRes]) => {
        if (cancelled) return
        setTask(RESP(tRes)); setResult(RESP(rRes))
      })
      .catch(e => !cancelled && setError(e.response?.data?.message || '加载评测报告失败'))
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [taskId])

  // 供子组件在「重新生成建议」后静默刷新 result（不整页 loading）
  async function refetchResult() {
    try { setResult(RESP(await evalApi.getResult(taskId))) } catch { /* 忽略,下次进入再拉 */ }
  }

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">评测报告</h1>
          {task && (
            <p className="text-muted-foreground text-sm mt-1 flex items-center gap-2">
              <span className="truncate max-w-md">{task.filename}</span>
              {task.bu_name && <EvalBadge tone="brand">{task.bu_name}</EvalBadge>}
            </p>
          )}
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link to="/eval/history"><ArrowLeft className="w-4 h-4 mr-1.5" />返回历史</Link>
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20 text-muted-foreground">
          <Loader2 className="w-5 h-5 animate-spin mr-2" />加载中…
        </div>
      ) : error ? (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span className="flex-1">{error}</span>
          <Button variant="outline" size="sm" onClick={() => navigate('/eval/history')}>返回历史</Button>
        </div>
      ) : (
        <EvalResult taskId={taskId} result={result} onRefetch={refetchResult} />
      )}
    </div>
  )
}
