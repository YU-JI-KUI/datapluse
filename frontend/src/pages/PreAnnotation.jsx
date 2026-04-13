import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Cpu, Play, RefreshCw, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { pipelineApi, dataApi } from '@/lib/api'
import { formatDate } from '@/lib/utils'

export default function PreAnnotation() {
  const qc = useQueryClient()
  const [running, setRunning] = useState(false)

  const { data: processedData } = useQuery({
    queryKey: ['cleaned-count'],
    queryFn: () => dataApi.list({ status: 'cleaned', page: 1, page_size: 1 }),
  })

  const { data: preAnnotatedData, isLoading, refetch } = useQuery({
    queryKey: ['pre-annotated-list'],
    queryFn: () => dataApi.list({ status: 'pre_annotated', page: 1, page_size: 50 }),
    refetchInterval: 5000,
  })

  const { data: pipelineData } = useQuery({
    queryKey: ['pipeline-status'],
    queryFn: () => pipelineApi.status(),
    refetchInterval: 10000,
  })

  const processedResult = processedData?.data?.data ?? {}
  const preAnnotatedResult = preAnnotatedData?.data?.data ?? {}
  const pipeline = pipelineData?.data?.data ?? pipelineData?.data ?? {}
  const processedCount = processedResult.pagination?.total || 0
  const preAnnotatedCount = preAnnotatedResult.pagination?.total || 0
  const preAnnotated = preAnnotatedResult.list || []

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
        </div>
      </div>

      {/* Status cards */}
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
            <p className="text-3xl font-bold mt-1">{preAnnotatedCount}</p>
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

      {/* Running progress */}
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

      {/* Results table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">预标注结果</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>文本</TableHead>
                <TableHead>预测标签</TableHead>
                <TableHead>置信度</TableHead>
                <TableHead className="w-40 whitespace-nowrap">创建时间</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={4} className="text-center py-8 text-muted-foreground">加载中...</TableCell></TableRow>
              ) : preAnnotated.length === 0 ? (
                <TableRow><TableCell colSpan={4} className="text-center py-8 text-muted-foreground">暂无预标注数据，请先清洗数据再运行预标注</TableCell></TableRow>
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
                      {item.pre_annotation?.score != null ? `${(item.pre_annotation.score * 100).toFixed(1)}%` : '-'}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                    {formatDate(item.created_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
