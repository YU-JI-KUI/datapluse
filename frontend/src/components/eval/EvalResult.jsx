/** 评测结果视图：统计卡 + BU 分发漏斗 + 优化建议 + 业务洞察 + 分布图 + 校准指标 + 明细 + 导出。 */
import { Database, TrendingUp, CheckCircle2, AlertTriangle, Download, FileSpreadsheet, FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { toast } from 'sonner'
import { StatCard, EvalBadge, pct } from './EvalPrimitives'
import AdvicePanel from './AdvicePanel'
import InsightsPanel from './InsightsPanel'
import IntentCharts from './IntentCharts'
import MetricsPanel from './MetricsPanel'
import RowsTable from './RowsTable'
import { evalApi } from '@/lib/api'

export default function EvalResult({ taskId, result }) {
  if (!result) return null
  const s = result.summary || {}
  const f = result.filter_stats || {}
  const isCalib = result.mode === 'calibration'
  const disp = s.bu_dispatch || {}

  async function doExport(fn, name) {
    try {
      await fn(taskId)
    } catch (e) {
      toast.error(e.message || `${name}失败`)
    }
  }

  return (
    <div className="space-y-6">
      {/* 头部：BU + 模式 + 导出 */}
      <div className="flex flex-wrap items-center gap-2">
        <EvalBadge tone="brand">{s.bu_name || result.bu_name || '—'}</EvalBadge>
        <EvalBadge tone={isCalib ? 'info' : 'good'}>{isCalib ? '校准模式（有人工金标）' : '生产模式（无标注）'}</EvalBadge>
        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => doExport(evalApi.exportReport, '导出报告')}>
            <FileText className="w-4 h-4 mr-1.5" />评估报告
          </Button>
          <Button variant="outline" size="sm" onClick={() => doExport(evalApi.exportRows, '导出明细')}>
            <FileSpreadsheet className="w-4 h-4 mr-1.5" />逐条明细
          </Button>
        </div>
      </div>

      {/* 4 张统计卡 */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="评测样本" value={s.total_samples ?? 0}
          sub={`日志共 ${f.total ?? s.total_samples ?? 0} 条`} tone="brand" icon={Database} />
        <StatCard label="BU分发准确率" value={pct(s.dispatch_accuracy)}
          sub="该承接 / 拒识判对占比" tone="info" icon={TrendingUp} />
        <StatCard label="端到端解决率" value={pct(s.end_to_end_resolved_rate ?? s.resolved_rate)}
          sub="仅分发到本BU的问题" tone="good" icon={CheckCircle2} />
        {isCalib
          ? <StatCard label="不一致 case" value={s.disagreement_count ?? 0}
              sub="Judge 与人工金标不一致" tone="bad" icon={AlertTriangle} />
          : <StatCard label="需人工复核" value={s.needs_review ?? 0}
              sub="Judge 标记低置信" tone="warn" icon={AlertTriangle} />}
      </div>

      {/* BU 分发漏斗信息条 */}
      {s.bu_dispatch && (
        <Card>
          <CardContent className="p-4 flex items-center gap-2 text-sm">
            <TrendingUp className="w-4 h-4 text-blue-600 shrink-0" />
            <span>
              BU 分发：对 <b className="text-green-600">{disp.correct ?? 0}/{disp.scored ?? 0}</b> 条
              ·漏收（该承接却拒识）<b className="text-amber-600">{disp.miss_should_accept_but_rejected ?? 0}</b> 条
              ·误收（该拒识却承接）<b className="text-red-600">{disp.over_should_reject_but_accepted ?? 0}</b> 条
            </span>
          </CardContent>
        </Card>
      )}

      {/* 优化建议 */}
      <AdvicePanel advice={result.advice} />

      {/* 业务洞察 + 分布图 */}
      <InsightsPanel insights={result.insights} />
      <IntentCharts insights={result.insights} />

      {/* 校准指标（仅 calibration） */}
      {isCalib && (
        <>
          <MetricsPanel metrics={result.metrics} />
          <Card>
            <CardContent className="p-4 flex items-center justify-between">
              <span className="text-sm text-muted-foreground">导出 Judge 与人工金标不一致的 case，便于人工复核校准 prompt</span>
              <Button variant="outline" size="sm" onClick={() => doExport(evalApi.exportDisagreements, '导出不一致')}>
                <Download className="w-4 h-4 mr-1.5" />导出不一致 case
              </Button>
            </CardContent>
          </Card>
        </>
      )}

      {/* 逐条明细 */}
      <RowsTable rows={result.rows} />
    </div>
  )
}
