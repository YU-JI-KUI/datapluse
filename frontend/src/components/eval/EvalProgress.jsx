/** 评测进行中：进度条 + 阶段文字 + 已完成/总数。 */
import { Loader2 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'

const STAGE_LABEL = {
  loading:  '读取与解析 Excel',
  loaded:   '样本构造完成',
  judging:  'LLM Judge 评测中',
  advising: '生成优化建议中',
  done:     '完成',
}

export default function EvalProgress({ task }) {
  if (!task) return null
  const stage = STAGE_LABEL[task.stage] || '准备中'
  const pct = task.progress_pct || 0
  return (
    <Card>
      <CardContent className="p-8">
        <div className="flex items-center gap-3">
          <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
          <div className="flex-1">
            <div className="flex items-baseline justify-between">
              <span className="font-medium">{stage}</span>
              <span className="text-lg font-bold text-blue-600 tabular-nums">{pct}%</span>
            </div>
            <div className="text-xs text-muted-foreground mt-0.5 truncate">{task.filename}</div>
          </div>
        </div>
        <Progress value={pct} className="mt-4" />
        {task.progress_total > 0 && (
          <div className="mt-2 text-xs text-muted-foreground text-right tabular-nums">
            {task.progress_done} / {task.progress_total} 样本
          </div>
        )}
      </CardContent>
    </Card>
  )
}
