/** 单张建议卡的操作：重新生成（只重跑这张）、查看真实 prompt。挂在 AdvicePanel/InsightsPanel 每张卡。 */
import { useState, useRef, useEffect } from 'react'
import { toast } from 'sonner'
import { RefreshCw, Loader2, Eye } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog'
import { evalApi } from '@/lib/api'

const RESP = (r) => r?.data?.data ?? {}

export default function AdviceCardActions({ card, taskId, onRefetch, size = 'sm' }) {
  if (!taskId || !card?.id) return null
  return (
    <span className="inline-flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
      <RegenerateOne cardId={card.id} taskId={taskId} onRefetch={onRefetch} size={size} />
      <ViewPrompt cardId={card.id} title={card.title} taskId={taskId} size={size} />
    </span>
  )
}

/** 重新生成这一张卡（只重跑该卡，轮询到完成再刷新）。 */
function RegenerateOne({ cardId, taskId, onRefetch, size }) {
  const [running, setRunning] = useState(false)
  const timer = useRef(null)
  useEffect(() => () => clearInterval(timer.current), [])

  async function handleClick(e) {
    e.stopPropagation()
    if (running) return
    setRunning(true)
    const tip = toast.loading('正在重新生成这条建议…')
    try {
      await evalApi.rerunAdvice(taskId, [cardId])
      timer.current = setInterval(async () => {
        try {
          const res = await evalApi.getTask(taskId)
          const st = RESP(res).status
          if (st && st !== 'rerunning') {
            clearInterval(timer.current)
            setRunning(false)
            const err = RESP(res).error
            if (err) toast.error(err, { id: tip })
            else { toast.success('已更新', { id: tip }); onRefetch?.() }
          }
        } catch { /* 轮询失败下次再试 */ }
      }, 2000)
    } catch (e2) {
      setRunning(false)
      toast.error(e2.response?.data?.message || '重新生成失败', { id: tip })
    }
  }

  return (
    <Button variant="ghost" size={size} className="h-7 px-2 text-xs text-muted-foreground"
      disabled={running} onClick={handleClick} title="只重新生成这一条建议">
      {running
        ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
        : <RefreshCw className="w-3.5 h-3.5" />}
      <span className="ml-1">重新生成</span>
    </Button>
  )
}

/** 查看这张卡真实喂给模型的 prompt（system + user，含填满的 payload）。 */
function ViewPrompt({ cardId, title, taskId, size }) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [messages, setMessages] = useState(null)

  async function handleOpen(e) {
    e.stopPropagation()
    setOpen(true); setLoading(true); setMessages(null)
    try {
      const res = await evalApi.getAdvicePrompt(taskId, cardId)
      setMessages(RESP(res).messages || [])
    } catch (e2) {
      toast.error(e2.response?.data?.message || '获取提示词失败')
      setOpen(false)
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <Button variant="ghost" size={size} className="h-7 px-2 text-xs text-muted-foreground"
        onClick={handleOpen} title="查看真实喂给模型的完整提示词">
        <Eye className="w-3.5 h-3.5" />
        <span className="ml-1">查看提示词</span>
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>提示词预览 · {title}</DialogTitle>
            <DialogDescription>实时用库中最新提示词组装，含填满的真实 payload。</DialogDescription>
          </DialogHeader>
          {loading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />组装中…
            </div>
          ) : (
            <div className="max-h-[65vh] overflow-y-auto space-y-4">
              {(messages || []).map((m, i) => (
                <div key={i}>
                  <div className="text-xs font-semibold text-gray-500 mb-1 uppercase">{m.role}</div>
                  <pre className="whitespace-pre-wrap break-words rounded bg-gray-50 border p-3 text-xs leading-relaxed font-mono">
                    {m.content}
                  </pre>
                </div>
              ))}
              {(!messages || messages.length === 0) && (
                <div className="text-sm text-muted-foreground text-center py-8">无内容</div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
