import { useState, useRef, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Upload, Trash2, RefreshCw } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { dataApi } from '@/lib/api'
import { formatDate, getStatusLabel, getStatusColor, getActiveLabel, getPreLabel, getPreScore } from '@/lib/utils'

const STATUS_OPTIONS = [
  { value: 'all',           label: '全部状态' },
  { value: 'raw',           label: '原始' },
  { value: 'cleaned',       label: '已清洗' },
  { value: 'pre_annotated', label: '已预标注' },
  { value: 'annotated',     label: '已标注' },
  { value: 'checked',       label: '已检测' },
]

export default function DataManagement() {
  const qc = useQueryClient()
  const fileRef = useRef()
  const [statusFilter, setStatusFilter] = useState('all')
  const [page, setPage] = useState(1)
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['data-list', statusFilter, page],
    queryFn: () => dataApi.list({ status: statusFilter === 'all' ? undefined : statusFilter, page, page_size: 20 }),
    staleTime: 0,
  })

  const result = data?.data?.data ?? {}
  const items = result.list || []
  const total = result.pagination?.total || 0
  const totalPages = Math.ceil(total / 20)

  async function uploadFile(file) {
    setUploading(true)
    try {
      const res = await dataApi.upload(file)
      const d = res.data?.data ?? res.data ?? {}
      toast.success(`上传成功：新增 ${d.created ?? 0} 条，跳过 ${d.skipped ?? 0} 条，去重 ${d.dup_skipped ?? 0} 条`)
      qc.invalidateQueries(['data-list'])
    } catch (err) {
      toast.error(err.response?.data?.detail || '上传失败')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  function handleFileChange(e) {
    const file = e.target.files?.[0]
    if (file) uploadFile(file)
  }

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) uploadFile(file)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const [confirmDeleteId, setConfirmDeleteId] = useState(null)
  const [confirmOpen, setConfirmOpen] = useState(false)

  function requestDelete(id) {
    setConfirmDeleteId(id)
    setConfirmOpen(true)
  }

  async function handleDelete() {
    if (confirmDeleteId === null) return
    try {
      await dataApi.deleteItem(confirmDeleteId)
      toast.success('已删除')
      refetch()
    } catch {
      toast.error('删除失败')
    } finally {
      setConfirmDeleteId(null)
      setConfirmOpen(false)
    }
  }

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">数据管理</h1>
          <p className="text-muted-foreground text-sm mt-1">上传、查看和管理原始数据</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          <RefreshCw className="w-4 h-4 mr-2" /> 刷新
        </Button>
      </div>

      {/* Upload zone */}
      <Card
        className={`border-2 border-dashed transition-colors cursor-pointer ${dragging ? 'border-primary bg-primary/5' : 'border-muted-foreground/25 hover:border-primary/50'}`}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileRef.current?.click()}
      >
        <CardContent className="p-8 text-center">
          <input ref={fileRef} type="file" accept=".xlsx,.xls,.json,.csv" hidden onChange={handleFileChange} />
          <div className="mx-auto w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center mb-3">
            <Upload className="w-6 h-6 text-primary" />
          </div>
          {uploading
            ? <p className="text-sm font-medium">上传中...</p>
            : <>
                <p className="text-sm font-medium">点击或拖拽文件上传</p>
                <p className="text-xs text-muted-foreground mt-1">支持 Excel (.xlsx) · JSON · CSV</p>
              </>
          }
        </CardContent>
      </Card>

      {/* Filter + table */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-3">
            <CardTitle className="text-base flex-1">数据列表</CardTitle>
            <Select value={statusFilter} onValueChange={v => { setStatusFilter(v); setPage(1) }}>
              <SelectTrigger className="w-36">
                <SelectValue placeholder="全部状态" />
              </SelectTrigger>
              <SelectContent>
                {STATUS_OPTIONS.map(o => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-sm text-muted-foreground">共 {total} 条</span>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-64">文本</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>预测标签</TableHead>
                <TableHead>人工标签</TableHead>
                <TableHead>来源文件</TableHead>
                <TableHead className="w-40 whitespace-nowrap">创建时间</TableHead>
                <TableHead className="w-16"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground">加载中...</TableCell></TableRow>
              ) : items.length === 0 ? (
                <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground">暂无数据，请上传文件</TableCell></TableRow>
              ) : items.map(item => {
                const preLabel = getPreLabel(item)
                const preScore = getPreScore(item)
                const activeLabel = getActiveLabel(item)
                return (
                  <TableRow key={item.id}>
                    <TableCell className="max-w-xs">
                      <p className="truncate text-sm" title={item.content}>{item.content}</p>
                      <p className="text-xs text-muted-foreground font-mono">#{item.id}</p>
                    </TableCell>
                    <TableCell>
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${getStatusColor(item.status)}`}>
                        {getStatusLabel(item.status)}
                      </span>
                    </TableCell>
                    <TableCell>
                      {preLabel
                        ? <><span className="text-sm">{preLabel}</span><span className="ml-1 text-xs text-muted-foreground">{preScore != null ? `(${(preScore * 100).toFixed(0)}%)` : ''}</span></>
                        : <span className="text-muted-foreground text-sm">-</span>
                      }
                    </TableCell>
                    <TableCell>
                      {activeLabel
                        ? <Badge variant="outline">{activeLabel}</Badge>
                        : <span className="text-muted-foreground text-sm">-</span>
                      }
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{item.source_ref || '-'}</TableCell>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{formatDate(item.created_at)}</TableCell>
                    <TableCell>
                      <button onClick={() => requestDelete(item.id)} className="text-muted-foreground hover:text-destructive transition-colors">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 p-4 border-t">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</Button>
              <span className="text-sm text-muted-foreground">{page} / {totalPages}</span>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>下一页</Button>
            </div>
          )}
        </CardContent>
      </Card>
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="确认删除"
        description="确定要删除这条数据吗？此操作无法撤销。"
        confirmLabel="删除"
        cancelLabel="取消"
        onConfirm={handleDelete}
      />
    </div>
  )
}
