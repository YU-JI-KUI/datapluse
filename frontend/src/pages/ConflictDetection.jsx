import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { AlertTriangle, Play, RefreshCw, CheckCircle, Loader2, ShieldAlert } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { pipelineApi, dataApi, annotationApi } from '@/lib/api'
import { formatDate } from '@/lib/utils'

export default function ConflictDetection() {
  const qc = useQueryClient()
  const [running, setRunning] = useState(false)
  const [conflictFilter, setConflictFilter] = useState('all')

  const { data: labeledData } = useQuery({
    queryKey: ['labeled-count'],
    queryFn: () => dataApi.list({ status: 'labeled', page: 1, page_size: 1 }),
  })

  const { data: checkedData } = useQuery({
    queryKey: ['checked-count'],
    queryFn: () => dataApi.list({ status: 'checked', page: 1, page_size: 1 }),
  })

  // 已标注数据（包含冲突标记）
  const { data: conflictData, isLoading, refetch } = useQuery({
    queryKey: ['conflict-list', conflictFilter],
    queryFn: async () => {
      const res = await dataApi.list({ status: 'labeled', page: 1, page_size: 100 })
      return res
    },
    refetchInterval: 8000,
  })

  const labeledResult = labeledData?.data?.data ?? labeledData?.data ?? {}
  const checkedResult = checkedData?.data?.data ?? checkedData?.data ?? {}
  const conflictResult = conflictData?.data?.data ?? conflictData?.data ?? {}
  const labeledCount = labeledResult.total || 0
  const checkedCount = checkedResult.total || 0
  const allLabeled = conflictResult.items || []
  const conflicts = allLabeled.filter(i => i.conflict_flag)
  const labelConflicts = conflicts.filter(i => i.conflict_type === 'label_conflict')
  const semanticConflicts = conflicts.filter(i => i.conflict_type === 'semantic_conflict')

  const displayItems = conflictFilter === 'label'
    ? labelConflicts
    : conflictFilter === 'semantic'
    ? semanticConflicts
    : conflicts

  async function handleRunCheck() {
    setRunning(true)
    try {
      await pipelineApi.runStep('check')
      toast.success('冲突检测完成')
      refetch()
      qc.invalidateQueries(['checked-count'])
      qc.invalidateQueries(['labeled-count'])
    } catch (err) {
      toast.error(err.response?.data?.detail || '检测失败')
    } finally {
      setRunning(false)
    }
  }

  // 强制设置为 checked（人工审核通过）
  async function handleApprove(item) {
    try {
      const updated = { ...item, status: 'checked', conflict_flag: false, conflict_type: null, conflict_detail: null }
      await annotationApi.submit(item.id, item.label)
      toast.success('已标记为通过')
      refetch()
    } catch {
      toast.error('操作失败')
    }
  }

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">冲突检测</h1>
          <p className="text-muted-foreground text-sm mt-1">检测标注冲突与语义冲突，保障数据质量</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="w-4 h-4 mr-2" /> 刷新
          </Button>
          <Button size="sm" onClick={handleRunCheck} disabled={running || labeledCount === 0}>
            {running
              ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> 检测中</>
              : <><Play className="w-4 h-4 mr-2" /> 运行检测</>
            }
          </Button>
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-5">
            <p className="text-sm text-muted-foreground">已标注</p>
            <p className="text-3xl font-bold mt-1">{labeledCount}</p>
          </CardContent>
        </Card>
        <Card className="border-red-200">
          <CardContent className="p-5">
            <p className="text-sm text-muted-foreground">标注冲突</p>
            <p className="text-3xl font-bold mt-1 text-red-600">{labelConflicts.length}</p>
          </CardContent>
        </Card>
        <Card className="border-orange-200">
          <CardContent className="p-5">
            <p className="text-sm text-muted-foreground">语义冲突</p>
            <p className="text-3xl font-bold mt-1 text-orange-600">{semanticConflicts.length}</p>
          </CardContent>
        </Card>
        <Card className="border-green-200">
          <CardContent className="p-5">
            <p className="text-sm text-muted-foreground">通过检测</p>
            <p className="text-3xl font-bold mt-1 text-green-600">{checkedCount}</p>
          </CardContent>
        </Card>
      </div>

      {/* 冲突列表 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-3">
            <CardTitle className="text-base flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-orange-500" />
              冲突数据列表
            </CardTitle>
            <Select value={conflictFilter} onValueChange={setConflictFilter}>
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部冲突</SelectItem>
                <SelectItem value="label">标注冲突</SelectItem>
                <SelectItem value="semantic">语义冲突</SelectItem>
              </SelectContent>
            </Select>
            <span className="text-sm text-muted-foreground">{displayItems.length} 条</span>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>文本</TableHead>
                <TableHead>标签</TableHead>
                <TableHead>冲突类型</TableHead>
                <TableHead>冲突详情</TableHead>
                <TableHead>标注时间</TableHead>
                <TableHead className="w-20">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">加载中...</TableCell></TableRow>
              ) : displayItems.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-12">
                    <div className="flex flex-col items-center gap-2">
                      <CheckCircle className="w-8 h-8 text-green-400" />
                      <p className="text-sm text-muted-foreground">
                        {labeledCount > 0 ? '暂无冲突，数据质量良好！' : '请先完成人工标注再运行检测'}
                      </p>
                    </div>
                  </TableCell>
                </TableRow>
              ) : displayItems.map(item => (
                <TableRow key={item.id} className="hover:bg-orange-50/50">
                  <TableCell>
                    <p className="text-sm max-w-xs truncate" title={item.text}>{item.text}</p>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{item.label}</Badge>
                  </TableCell>
                  <TableCell>
                    {item.conflict_type === 'label_conflict'
                      ? <Badge variant="destructive">标注冲突</Badge>
                      : <Badge variant="warning">语义冲突</Badge>
                    }
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground max-w-xs">
                    {item.conflict_type === 'semantic_conflict' && item.conflict_detail ? (
                      <div>
                        <p>相似度: <span className="font-medium text-orange-600">{item.conflict_detail.similarity}</span></p>
                        <p className="truncate" title={item.conflict_detail.paired_text}>
                          对比: {item.conflict_detail.paired_text?.slice(0, 30)}...
                          (<span className="text-red-500">{item.conflict_detail.paired_label}</span>)
                        </p>
                      </div>
                    ) : item.conflict_detail ? (
                      <p>涉及标签: {item.conflict_detail.conflicting_labels?.join(', ')}</p>
                    ) : '-'}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{formatDate(item.annotated_at)}</TableCell>
                  <TableCell>
                    <Button variant="ghost" size="sm" onClick={() => handleApprove(item)}
                      className="text-green-600 hover:text-green-700 hover:bg-green-50 text-xs">
                      通过
                    </Button>
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
