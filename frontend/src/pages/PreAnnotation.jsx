import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Cpu, RefreshCw, Loader2, BrainCircuit } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { pipelineApi, dataApi, getCurrentDatasetId } from '@/lib/api'
import { formatDate } from '@/lib/utils'
import TablePagination from '@/components/TablePagination'
import SearchBar from '@/components/SearchBar'

export default function PreAnnotation() {
  const qc = useQueryClient()
  const [running, setRunning]         = useState(false)
  const [embedRunning, setEmbedRunning] = useState(false)
  const [datasetId]                   = useState(() => getCurrentDatasetId())

  // 列表搜索/分页状态
  const [page, setPage]         = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [filters, setFilters]   = useState({})

  // 待预标注数量（已清洗）
  const { data: processedData } = useQuery({
    queryKey: ['cleaned-count', datasetId],
    queryFn:  () => dataApi.list({ status: 'cleaned', page: 1, page_size: 1 }),
    enabled:  !!datasetId,
  })

  // 预标注结果列表（带分页/搜索）
  const queryParams = {
    status: 'pre_annotated',
    page,
    page_size: pageSize,
    ...(filters.keyword    ? { keyword:    filters.keyword    } : {}),
    ...(filters.start_date ? { start_date: filters.start_date } : {}),
    ...(filters.end_date   ? { end_date:   filters.end_date   } : {}),
  }

  const { data: preAnnotatedData, isLoading, refetch } = useQuery({
    queryKey: ['pre-annotated-list', datasetId, queryParams],
    queryFn:  () => dataApi.list(queryParams),
    enabled:  !!datasetId,
    refetchInterval: 8000,
  })

  // Pipeline 状态
  const { data: pipelineData } = useQuery({
    queryKey: ['pipeline-status', datasetId],
    queryFn:  () => pipelineApi.status(datasetId),
    enabled:  !!datasetId,
    refetchInterval: 10000,
  })

  const processedResult    = processedData?.data?.data ?? {}
  const preAnnotatedResult = preAnnotatedData?.data?.data ?? {}
  const pipeline           = pipelineData?.data?.data ?? pipelineData?.data ?? {}
  const embedJob           = pipeline.embed_job ?? {}

  const processedCount    = processedResult.pagination?.total || 0
  const preAnnotatedTotal = preAnnotatedResult.pagination?.total || 0
  const preAnnotated      = preAnnotatedResult.list || []

  const embedRunningRemote = embedJob.status === 'running'

  async function handleRunEmbed() {
    setEmbedRunning(true)
    try {
      await pipelineApi.runEmbed(datasetId)
      toast.success('向量化任务已启动（后台运行，可继续操作）')
      qc.invalidateQueries(['pipeline-status'])
    } catch (err) {
      const msg = err.response?.data?.detail || '向量化启动失败'
      toast.error(msg)
    } finally {
      setEmbedRunning(false)
    }
  }

  async function handleRunPreAnnotate() {
    setRunning(true)
    try {
      await pipelineApi.runStep('pre_annotate')
      toast.success('预标注已启动（异步执行）')
      refetch()
      qc.invalidateQueries(['pipeline-status'])
    } catch (err) {
      toast.error(err.response?.data?.detail || '预标注失败')
    } finally {
      setRunning(false)
    }
  }

  function handleSearch(f) {
    setFilters(f)
    setPage(1)
  }

  const scoreColor = (score) => {
    if (!score) return 'text-muted-foreground'
    if (score >= 0.9) return 'text-green-600'
    if (score >= 0.7) return 'text-orange-500'
    return 'text-red-500'
  }

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">预标注</h1>
          <p className="text-muted-foreground text-sm mt-1">调用大模型自动预测标签</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="w-4 h-4 mr-2" /> 刷新
          </Button>
          <Button size="sm" onClick={handleRunPreAnnotate}
            disabled={running || processedCount === 0 || pipeline.status === 'running'}>
            {running
              ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> 预标注中</>
              : <><Cpu className="w-4 h-4 mr-2" /> 运行预标注</>
            }
          </Button>
          <Button
            variant="outline" size="sm"
            onClick={handleRunEmbed}
            disabled={embedRunning || embedRunningRemote}
            title="向量化 + 重建 FAISS 索引（离线任务，不影响主流程）"
          >
            {(embedRunning || embedRunningRemote)
              ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> 向量化中</>
              : <><BrainCircuit className="w-4 h-4 mr-2" /> 触发向量化</>
            }
          </Button>
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-5">
            <p className="text-sm text-muted-foreground">待预标注</p>
            <p className="text-3xl font-bold mt-1">{processedCount}</p>
            <p className="text-xs text-muted-foreground mt-1">已清洗数据</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-sm text-muted-foreground">预标注完成</p>
            <p className="text-3xl font-bold mt-1">{preAnnotatedTotal}</p>
            <p className="text-xs text-muted-foreground mt-1">待人工标注</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-sm text-muted-foreground">模型配置</p>
            <Badge variant={pipeline.status === 'running' ? 'info' : 'secondary'} className="mt-2">
              {pipeline.status === 'running' ? '运行中' : 'Mock 模式'}
            </Badge>
            <p className="text-xs text-muted-foreground mt-1">在配置中心切换</p>
          </CardContent>
        </Card>
      </div>

      {/* 预标注进度条 */}
      {(running || pipeline.current_step === 'pre_annotate') && (
        <Card className="border-purple-200 bg-purple-50">
          <CardContent className="p-4">
            <div className="flex justify-between text-sm mb-2">
              <span className="font-medium text-purple-700">预标注中...</span>
              <span className="text-purple-600">{pipeline.progress || 0}%</span>
            </div>
            <Progress value={pipeline.progress || 0} className="h-1.5" />
          </CardContent>
        </Card>
      )}

      {/* Embed Job 状态卡（有状态时才显示） */}
      {embedJob.status && (
        <Card className={
          embedJob.status === 'running'   ? 'border-blue-200 bg-blue-50' :
          embedJob.status === 'completed' ? 'border-green-200 bg-green-50' :
          embedJob.status === 'error'     ? 'border-red-200 bg-red-50' : ''
        }>
          <CardContent className="p-4">
            <div className="flex items-center justify-between text-sm mb-1">
              <div className="flex items-center gap-2">
                <BrainCircuit className={`w-4 h-4 ${
                  embedJob.status === 'running'   ? 'text-blue-600 animate-pulse' :
                  embedJob.status === 'completed' ? 'text-green-600' : 'text-red-600'
                }`} />
                <span className={`font-medium ${
                  embedJob.status === 'running'   ? 'text-blue-700' :
                  embedJob.status === 'completed' ? 'text-green-700' : 'text-red-700'
                }`}>
                  {embedJob.status === 'running'   ? '向量化进行中...' :
                   embedJob.status === 'completed' ? `向量化完成（索引已重建）` :
                   `向量化失败：${embedJob.detail?.error || '未知错误'}`}
                </span>
              </div>
              <span className="text-muted-foreground text-xs">
                {embedJob.status === 'running'
                  ? `${embedJob.progress || 0}%`
                  : embedJob.detail?.elapsed_s != null
                    ? `耗时 ${embedJob.detail.elapsed_s}s`
                    : ''}
              </span>
            </div>
            {embedJob.status === 'running' && (
              <Progress value={embedJob.progress || 0} className="h-1.5 mt-2" />
            )}
            {embedJob.status === 'completed' && embedJob.detail?.index_size != null && (
              <p className="text-xs text-green-600 mt-1">
                索引向量数：{embedJob.detail.index_size.toLocaleString()}，
                嵌入条数：{embedJob.detail.embedded?.toLocaleString() ?? '-'}
              </p>
            )}
            {embedJob.updated_at && (
              <p className="text-xs text-muted-foreground mt-1">
                更新于 {embedJob.updated_at.slice(0, 16).replace('T', ' ')}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* 预标注结果列表 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <CardTitle className="text-base">预标注结果</CardTitle>
            <SearchBar
              placeholder="搜索文本内容…"
              onSearch={handleSearch}
              className="flex-1 max-w-2xl"
            />
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>文本</TableHead>
                <TableHead className="w-32">预测标签</TableHead>
                <TableHead className="w-24">置信度</TableHead>
                <TableHead className="w-40 whitespace-nowrap">更新时间</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={4} className="text-center py-10 text-muted-foreground">
                    加载中…
                  </TableCell>
                </TableRow>
              ) : preAnnotated.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="text-center py-10 text-muted-foreground">
                    {Object.values(filters).some(Boolean)
                      ? '没有符合条件的预标注数据'
                      : '暂无预标注数据，请先清洗数据再运行预标注'}
                  </TableCell>
                </TableRow>
              ) : preAnnotated.map(item => (
                <TableRow key={item.id}>
                  <TableCell>
                    <p className="text-sm max-w-sm truncate" title={item.content}>{item.content}</p>
                  </TableCell>
                  <TableCell>
                    <Badge variant="purple">{item.pre_annotation?.label || '-'}</Badge>
                  </TableCell>
                  <TableCell>
                    <span className={`text-sm font-medium ${scoreColor(item.pre_annotation?.score)}`}>
                      {item.pre_annotation?.score != null
                        ? `${(item.pre_annotation.score * 100).toFixed(1)}%`
                        : '-'}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                    {formatDate(item.updated_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePagination
            page={page}
            pageSize={pageSize}
            total={preAnnotatedTotal}
            onPageChange={setPage}
            onSizeChange={size => { setPageSize(size); setPage(1) }}
          />
        </CardContent>
      </Card>
    </div>
  )
}
