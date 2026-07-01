/** 评测结果视图：统计卡 + BU 分发漏斗 + 优化建议 + 业务洞察 + 分布图 + 校准指标 + 明细 + 导出。 */
import { useState } from 'react'
import { Database, TrendingUp, CheckCircle2, AlertTriangle, Download, FileSpreadsheet, FileText, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { toast } from 'sonner'
import { StatCard, EvalBadge, pct } from './EvalPrimitives'
import AdvicePanel from './AdvicePanel'
import InsightsPanel from './InsightsPanel'
import IntentCharts from './IntentCharts'
import SourceBreakdownChart from './SourceBreakdownChart'
import MetricsPanel from './MetricsPanel'
import RowsTable from './RowsTable'
import { evalApi } from '@/lib/api'

export default function EvalResult({ taskId, result }) {
  if (!result) return null
  const s = result.summary || {}
  const f = result.filter_stats || {}
  const isCalib = result.mode === 'calibration'
  const disp = s.bu_dispatch || {}

  // 正在导出的类型 key（'report' | 'rows' | 'disagree'），用于禁用对应按钮 + 显示进度
  const [exporting, setExporting] = useState(null)

  async function doExport(key, fn, name) {
    if (exporting) return                     // 有导出在进行中，忽略重复点击（防狂点触发多次大导出）
    setExporting(key)
    const tip = toast.loading(`正在生成${name}，数据量大时需稍候…`)
    try {
      await fn(taskId)
      toast.success(`${name}已开始下载`, { id: tip })
    } catch (e) {
      toast.error(e.message || `${name}失败`, { id: tip })
    } finally {
      setExporting(null)
    }
  }

  return (
    <div className="space-y-6">
      {/* 头部：BU + 模式 + 导出 */}
      <div className="flex flex-wrap items-center gap-2">
        <EvalBadge tone="brand">{s.bu_name || result.bu_name || '—'}</EvalBadge>
        <EvalBadge tone={isCalib ? 'info' : 'good'}>{isCalib ? '校准模式（有人工打标）' : '生产模式（无标注）'}</EvalBadge>
        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" size="sm" disabled={!!exporting}
            onClick={() => doExport('report', evalApi.exportReport, '评估报告')}>
            {exporting === 'report'
              ? <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" />导出中…</>
              : <><FileText className="w-4 h-4 mr-1.5" />评估报告</>}
          </Button>
          <Button variant="outline" size="sm" disabled={!!exporting}
            onClick={() => doExport('rows', evalApi.exportRows, '逐条明细')}>
            {exporting === 'rows'
              ? <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" />导出中…</>
              : <><FileSpreadsheet className="w-4 h-4 mr-1.5" />逐条明细</>}
          </Button>
        </div>
      </div>

      {/* 4 张统计卡 */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="评测样本" value={s.total_samples ?? 0}
          sub={`日志共 ${f.total ?? s.total_samples ?? 0} 条`
            + (f.excluded_activity ? `，排除 ${f.excluded_activity} 条活动标问` : '')
            + (f.rule_hit ? `，规则命中 ${f.rule_hit} 条` : '')}
          hint={
            (f.excluded_activity
              ? `活动标问（写死按钮触发的写死回复）已整条跳过 ${f.excluded_activity} 条：不喂模型、不计入指标。\n` : '')
            + (f.rule_hit
              ? `规则短路命中 ${f.rule_hit} 条：问题+答案匹配预设规则，直接用写死结果、免 LLM 调用，但照常计入指标。\n` : '')
            + '评测样本 = 实际参与评测的条数（已排除活动标问）。'
          }
          tone="brand" icon={Database} />
        <StatCard label="BU分发准确率" value={pct(s.dispatch_accuracy)}
          sub="AI 判该接与实际是否一致"
          hint={
            'BU分发准确率 = 判对数 ÷ 参与评分数。\n' +
            '· 判对：AI 判断「该不该本BU承接」(should_dispatch_to_bu) 与日志事实「实际是否分给本BU」(分发BU 列) 一致——即「该接且接了」或「该拒且拒了」。\n' +
            '· 参与评分数：AI 给出了有效分发判定的样本数（模型调用出错/缺字段的样本不计入分母）。\n' +
            '· 两类判错：漏收 = 该接却被拒（AI 判该接，实际没分到本BU）；误收 = 该拒却收下（AI 判该拒，实际分到了本BU）。\n' +
            '该指标用 AI 判断 vs 日志客观事实比对，不依赖人工金标，故生产模式同样可算。'
          }
          tone="info" icon={TrendingUp} />
        <StatCard label="问题解决率" value={pct(s.end_to_end_resolved_rate ?? s.resolved_rate)}
          sub="仅分发到本BU的问题"
          hint={'问题解决率 = 已解决数 / 实际分发到本BU的样本数。仅统计真正进入本BU的问题（拒识的不计入分母）；Judge 判 answer_resolved=yes 才算已解决，partial/no 不算。'}
          tone="good" icon={CheckCircle2} />
        {isCalib
          ? <StatCard label="不一致 case" value={s.disagreement_count ?? 0}
              sub="Judge 与人工打标不一致"
              hint={'Judge 的判定与人工打标（金标）不一致的条数，用于校准 Judge 可信度。'}
              tone="bad" icon={AlertTriangle} />
          : <StatCard label="需人工复核" value={s.needs_review ?? 0}
              sub={s.reviewed_count ? `已复核 ${s.reviewed_count} 条` : 'Judge 自判需复核'}
              hint={'剩余需人工复核的条数（已被人工复核的不再计入）。Judge 自判需复核的触发：疑似合规风险、信息严重不足无法判定、或明显自相矛盾。指标按复核后的最终值重算，复核后重进本页生效。'}
              tone="warn" icon={AlertTriangle} />}
      </div>

      {/* BU 分发漏斗信息条 */}
      {s.bu_dispatch && (
        <Card>
          <CardContent className="p-4 flex items-center gap-2 text-sm">
            <TrendingUp className="w-4 h-4 text-blue-600 shrink-0" />
            <span>
              BU 分发：对 <b className="text-green-600">{disp.correct ?? 0}/{disp.scored ?? 0}</b> 条
              （{pct(disp.accuracy)}）
              ·漏收（该承接却拒识）<b className="text-amber-600">{disp.miss_should_accept_but_rejected ?? 0}</b> 条
              （{pct((disp.miss_should_accept_but_rejected ?? 0) / (disp.scored || 1))}）
              ·误收（该拒识却承接）<b className="text-red-600">{disp.over_should_reject_but_accepted ?? 0}</b> 条
              （{pct((disp.over_should_reject_but_accepted ?? 0) / (disp.scored || 1))}）
            </span>
          </CardContent>
        </Card>
      )}

      {/* 优化建议 */}
      <AdvicePanel advice={result.advice} />

      {/* 业务洞察 + 分布图 */}
      <InsightsPanel insights={result.insights} />
      <IntentCharts insights={result.insights} />
      <SourceBreakdownChart filterStats={result.filter_stats} />

      {/* 校准指标（仅 calibration） */}
      {isCalib && (
        <>
          <MetricsPanel metrics={result.metrics} />
          <Card>
            <CardContent className="p-4 flex items-center justify-between">
              <span className="text-sm text-muted-foreground">导出 Judge 与人工打标不一致的 case，便于人工复核校准 prompt</span>
              <Button variant="outline" size="sm" disabled={!!exporting}
                onClick={() => doExport('disagree', evalApi.exportDisagreements, '不一致 case')}>
                {exporting === 'disagree'
                  ? <><Loader2 className="w-4 h-4 mr-1.5 animate-spin" />导出中…</>
                  : <><Download className="w-4 h-4 mr-1.5" />导出不一致 case</>}
              </Button>
            </CardContent>
          </Card>
        </>
      )}

      {/* 逐条明细（服务端分页：rows 不再随 result 全量返回） */}
      <RowsTable
        taskId={taskId}
        disagreements={result.disagreements || []}
        totalSamples={s.total_samples || 0}
        reviewCount={s.needs_review || 0}
        intentOptions={(result.intent_distribution?.by_intent || []).map(x => x.name)}
      />
    </div>
  )
}
