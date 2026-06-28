/** 评测上传区：拖拽 Excel + 两个样例按钮（零配置体验）。BU 由左侧全局选择器决定。 */
import { useRef, useState } from 'react'
import { Upload, ShieldCheck, TrendingUp } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

export default function EvalUploader({ onUpload, onSample, busy }) {
  const inputRef = useRef(null)
  const [drag, setDrag] = useState(false)

  function pickFile(file) {
    if (file) onUpload(file)
  }

  return (
    <div className="space-y-6">
      {/* 拖拽上传 */}
      <Card>
        <CardContent className="p-6">
          <div
            onClick={() => !busy && inputRef.current?.click()}
            onDragOver={e => { e.preventDefault(); setDrag(true) }}
            onDragLeave={() => setDrag(false)}
            onDrop={e => {
              e.preventDefault(); setDrag(false)
              if (!busy) pickFile(e.dataTransfer.files?.[0])
            }}
            className={cn(
              'flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed py-12 cursor-pointer transition-colors',
              drag ? 'border-blue-500 bg-blue-50' : 'border-border hover:bg-accent',
              busy && 'opacity-50 cursor-not-allowed',
            )}
          >
            <Upload className="w-8 h-8 text-muted-foreground" />
            <div className="font-medium">拖入或点击上传对话日志 Excel</div>
            <div className="text-xs text-muted-foreground">支持 .xlsx / .xls，需含日志导出列（可含运营人工标注列）</div>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".xlsx,.xls"
            className="hidden"
            onChange={e => { pickFile(e.target.files?.[0]); e.target.value = '' }}
          />
        </CardContent>
      </Card>

      {/* 样例按钮 */}
      <div className="grid sm:grid-cols-2 gap-3">
        <button
          type="button"
          disabled={busy}
          onClick={() => onSample('calib')}
          className="flex items-start gap-3 rounded-lg border border-sky-200 bg-sky-50 p-4 text-left hover:bg-sky-100 transition-colors disabled:opacity-50"
        >
          <ShieldCheck className="w-5 h-5 text-sky-600 shrink-0 mt-0.5" />
          <div>
            <div className="font-medium">校准样例（有人工打标）</div>
            <div className="text-xs text-muted-foreground">算 κ/F1 验证 Judge 可信度</div>
          </div>
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onSample('prod')}
          className="flex items-start gap-3 rounded-lg border border-green-200 bg-green-50 p-4 text-left hover:bg-green-100 transition-colors disabled:opacity-50"
        >
          <TrendingUp className="w-5 h-5 text-green-600 shrink-0 mt-0.5" />
          <div>
            <div className="font-medium">生产样例（无标注）</div>
            <div className="text-xs text-muted-foreground">直接出业务洞察 + 优化建议</div>
          </div>
        </button>
      </div>
    </div>
  )
}
