import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ChevronLeft, ChevronRight, Tag, CheckCircle2, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { annotationApi, dataApi } from '@/lib/api'
import { formatDate } from '@/lib/utils'

// 意图标签颜色
const LABEL_COLORS = [
  'bg-blue-500 hover:bg-blue-600',
  'bg-violet-500 hover:bg-violet-600',
  'bg-green-500 hover:bg-green-600',
  'bg-orange-500 hover:bg-orange-600',
  'bg-rose-500 hover:bg-rose-600',
]

export default function Annotation() {
  const qc = useQueryClient()
  const [currentItem, setCurrentItem] = useState(null)
  const [loadingNext, setLoadingNext] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [labels, setLabels] = useState(['寿险意图', '拒识', '健康险意图', '财险意图', '其他意图'])

  // 已标注列表
  const { data: labeledData, isLoading, refetch } = useQuery({
    queryKey: ['labeled-list'],
    queryFn: () => annotationApi.labeled({ page: 1, page_size: 20 }),
  })

  const { data: queueData } = useQuery({
    queryKey: ['annotation-queue'],
    queryFn: () => annotationApi.queue({ page: 1, page_size: 1 }),
    refetchInterval: 5000,
  })

  const labeled = labeledData?.data?.items || []
  const totalLabeled = labeledData?.data?.total || 0
  const queueTotal = queueData?.data?.total || 0

  async function fetchNext() {
    setLoadingNext(true)
    try {
      const res = await annotationApi.next()
      setCurrentItem(res.data.data)
      if (!res.data.data) toast.info('标注队列已清空！')
    } catch (err) {
      toast.error('获取失败')
    } finally {
      setLoadingNext(false)
    }
  }

  async function handleLabel(label) {
    if (!currentItem) return
    setSubmitting(true)
    try {
      await annotationApi.submit(currentItem.id, label)
      toast.success(`已标注: ${label}`)
      refetch()
      qc.invalidateQueries(['annotation-queue'])
      setCurrentItem(null)
      // 自动获取下一条
      await fetchNext()
    } catch (err) {
      toast.error('提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  async function skipItem() {
    setCurrentItem(null)
    await fetchNext()
  }

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">人工标注</h1>
          <p className="text-muted-foreground text-sm mt-1">对数据进行人工意图标注</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">
            队列: <span className="font-medium text-foreground">{queueTotal}</span> 条待标注
          </span>
          <Button onClick={fetchNext} disabled={loadingNext || queueTotal === 0}>
            {loadingNext
              ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> 加载中</>
              : <><Tag className="w-4 h-4 mr-2" /> 开始标注</>
            }
          </Button>
        </div>
      </div>

      {/* 标注卡片 */}
      {currentItem ? (
        <Card className="border-primary/30 shadow-md">
          <CardHeader className="pb-3">
            <div className="flex items-start justify-between">
              <div>
                <CardTitle className="text-base">待标注文本</CardTitle>
                <p className="text-xs text-muted-foreground mt-1">
                  ID: {currentItem.id.slice(0, 16)}...
                  {currentItem.model_pred && (
                    <span className="ml-2">
                      模型预测: <Badge variant="purple" className="ml-1">{currentItem.model_pred}</Badge>
                      <span className="ml-1">({currentItem.model_score ? `${(currentItem.model_score * 100).toFixed(0)}%` : ''})</span>
                    </span>
                  )}
                </p>
              </div>
              <Button variant="ghost" size="sm" onClick={skipItem}>跳过</Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* 文本展示 */}
            <div className="bg-muted/50 rounded-lg p-4">
              <p className="text-base leading-relaxed">{currentItem.text}</p>
            </div>

            {/* 标签按钮 */}
            <div>
              <p className="text-sm font-medium mb-3">选择意图标签</p>
              <div className="flex flex-wrap gap-2">
                {labels.map((label, i) => (
                  <button
                    key={label}
                    onClick={() => handleLabel(label)}
                    disabled={submitting}
                    className={`px-5 py-2.5 rounded-lg text-sm font-medium text-white transition-all ${LABEL_COLORS[i % LABEL_COLORS.length]} disabled:opacity-50 disabled:cursor-not-allowed`}
                  >
                    {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : label}
                  </button>
                ))}
              </div>
              <p className="text-xs text-muted-foreground mt-2">点击标签即提交，自动加载下一条</p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="border-dashed">
          <CardContent className="p-12 text-center">
            <div className="w-12 h-12 rounded-xl bg-muted flex items-center justify-center mx-auto mb-3">
              <Tag className="w-6 h-6 text-muted-foreground" />
            </div>
            <p className="text-sm font-medium">点击"开始标注"获取待标注数据</p>
            <p className="text-xs text-muted-foreground mt-1">
              {queueTotal > 0 ? `当前队列有 ${queueTotal} 条数据` : '队列为空，请先运行预标注步骤'}
            </p>
          </CardContent>
        </Card>
      )}

      {/* 已标注历史 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-green-500" />
            已标注记录
            <span className="text-sm font-normal text-muted-foreground">({totalLabeled} 条)</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>文本</TableHead>
                <TableHead>人工标签</TableHead>
                <TableHead>模型预测</TableHead>
                <TableHead>标注人</TableHead>
                <TableHead>标注时间</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={5} className="text-center py-8 text-muted-foreground">加载中...</TableCell></TableRow>
              ) : labeled.length === 0 ? (
                <TableRow><TableCell colSpan={5} className="text-center py-8 text-muted-foreground">暂无标注记录</TableCell></TableRow>
              ) : labeled.map(item => (
                <TableRow key={item.id}>
                  <TableCell><p className="text-sm max-w-xs truncate" title={item.text}>{item.text}</p></TableCell>
                  <TableCell><Badge variant="outline">{item.label}</Badge></TableCell>
                  <TableCell>
                    {item.model_pred
                      ? <span className={`text-sm ${item.model_pred === item.label ? 'text-green-600' : 'text-orange-500'}`}>{item.model_pred}</span>
                      : '-'
                    }
                  </TableCell>
                  <TableCell className="text-sm">{item.annotator || '-'}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{formatDate(item.annotated_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
