/** 评测上传区：拖拽 Excel + 两个样例按钮（零配置体验）。BU 由左侧全局选择器决定。 */
import { useRef, useState } from 'react'
import { Upload, ShieldCheck, TrendingUp, ChevronRight, ChevronDown } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

// 与后端 pipeline.COLS 的列映射保持一致：列名用「包含匹配」解析（先精确、再包含），
// 故实际列名只要含下面的关键字即可（如「答案是否解决客户问题」精确命中金标列）。
// 必需列缺失会直接报错；金标列决定是否进「校准模式」并参与 κ/F1 计算。
const REQUIRED_COLS = [
  { name: '应用会话ID', use: '会话分组：同一 ID 的多行按轮次重组为一通对话' },
  { name: '客户咨询轮次', use: '轮次排序 + 还原多轮上下文（前文用户问 + AI 答）' },
  { name: '客户问题', use: '本轮要评测的客户问题，喂给 Judge' },
  { name: '答案', use: 'AI 回答原文（可含 JSON 卡 / HTML，程序自动净化提取正文）' },
  { name: '分发BU', use: '日志实际分发的 BU——分发准确率、解决率漏斗都以「实际是否分给本 BU」为事实侧，缺此列会让这些指标全部失真，故为必需' },
]
const GOLD_COLS = [
  { name: '分发是否正确', val: '是 / 否', use: 'BU 分发金标，与模型分发判定比对算准确率 / κ / F1' },
  { name: '答案是否解决客户问题', val: '是 / 否', use: '解决度金标，与模型解决判定比对算 κ / F1' },
]
const OPTIONAL_COLS = [
  { name: '模型意图', use: '模型给出的意图，作为分发场景参考' },
  { name: '分发BU理由 / 分发理由', use: '分发理由文本，展示在明细详情里' },
  { name: '未解决原因', use: '运营备注的未解决原因，仅透传展示，不参与计算' },
  { name: '问题类型 / 常规意图识别模块', use: '透传展示，不参与指标计算' },
]

export default function EvalUploader({ onUpload, onSample, busy, uploadPct = 0 }) {
  const inputRef = useRef(null)
  const [drag, setDrag] = useState(false)
  const [showCols, setShowCols] = useState(false)

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
            {busy ? (
              <div className="w-64 text-center">
                <div className="font-medium">
                  {uploadPct < 100 ? `上传中… ${uploadPct}%` : '已上传，正在创建任务…'}
                </div>
                <div className="mt-2 h-1.5 w-full rounded-full bg-muted overflow-hidden">
                  <div className="h-full bg-blue-500 transition-all" style={{ width: `${uploadPct}%` }} />
                </div>
                <div className="mt-1 text-xs text-muted-foreground">大文件传输较慢，请勿关闭页面</div>
              </div>
            ) : (
              <>
                <div className="font-medium">拖入或点击上传对话日志 Excel</div>
                <div className="text-xs text-muted-foreground">支持 .xlsx / .xls，需含日志导出列（可含运营人工标注列）</div>
              </>
            )}
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

      {/* 需要哪些列：默认折叠，点开看完整说明 */}
      <Card>
        <CardContent className="p-0">
          <button
            type="button"
            onClick={() => setShowCols(v => !v)}
            className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm font-medium hover:bg-accent transition-colors"
          >
            {showCols ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            上传的 Excel 需要哪些列？（程序解析 / 处理 / 展示的列）
          </button>

          {showCols && (
            <div className="space-y-5 px-4 pb-5 pt-1 text-sm">
              <p className="text-xs text-muted-foreground">
                列名按「包含匹配」解析，实际列名只要含下方关键字即可。
                <span className="text-foreground font-medium">必需列</span>缺失会直接报错；
                带有<span className="text-sky-700 font-medium">金标列</span>（填「是 / 否」）才会进入
                <span className="text-sky-700 font-medium">校准模式</span>，计算 κ / F1 验证 Judge 可信度；
                金标列全空则按生产模式只出业务洞察。
              </p>

              <ColGroup
                title="① 必需列（缺任一列直接报错）"
                tone="rose"
                rows={REQUIRED_COLS}
              />
              <ColGroup
                title="② 人工打标金标列（决定校准模式，取值必须是「是 / 否」）"
                tone="sky"
                rows={GOLD_COLS}
                showVal
              />
              <ColGroup
                title="③ 可选辅助列（有则展示 / 增强判断，缺失不影响评测）"
                tone="slate"
                rows={OPTIONAL_COLS}
              />

              <p className="text-xs text-muted-foreground border-t pt-3">
                提示：做校准评测时，至少填写一个金标列的「是 / 否」；两个金标列填得越全，
                可校准的维度越多。「智能体名称」「智能体分类」「问题识别类型」等列程序不读取，可不提供。
              </p>
            </div>
          )}
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
            <div className="text-xs text-muted-foreground">含「是/否」金标列，算 κ/F1 验证 Judge 可信度</div>
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

// 一组列说明（列名 + 取值 + 程序怎么用）。tone 控制左侧色条与列名颜色。
function ColGroup({ title, rows, tone, showVal = false }) {
  const tones = {
    rose:  { bar: 'bg-rose-400',  name: 'text-rose-700' },
    sky:   { bar: 'bg-sky-400',   name: 'text-sky-700' },
    slate: { bar: 'bg-slate-400', name: 'text-slate-600' },
  }
  const c = tones[tone] || tones.slate
  return (
    <div>
      <div className="mb-2 font-medium">{title}</div>
      <div className="space-y-1.5">
        {rows.map(r => (
          <div key={r.name} className="flex items-start gap-2 rounded-md bg-muted/40 px-3 py-2">
            <span className={cn('mt-1 h-3 w-1 shrink-0 rounded', c.bar)} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <code className={cn('font-medium', c.name)}>{r.name}</code>
                {showVal && r.val && (
                  <span className="rounded bg-sky-100 px-1.5 py-0.5 text-xs text-sky-700">
                    取值：{r.val}
                  </span>
                )}
              </div>
              <div className="text-xs text-muted-foreground">{r.use}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
