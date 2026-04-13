/**
 * DataUpload — 数据上传页
 *
 * 两种录入方式：
 *   ① 文件上传：支持 Excel / JSON / CSV，拖拽或点击上传
 *   ② 手动录入：文本框逐条输入，支持批量粘贴（每行一条）
 *
 * 下方列表实时显示已上传数据，支持状态过滤和分页。
 */

import { useState, useRef, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Upload, Trash2, RefreshCw, FileText, PenLine,
  Plus, Loader2, CheckCircle2,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import TablePagination from '@/components/TablePagination'
import { dataApi } from '@/lib/api'
import { formatDate, getStatusLabel, getStatusColor, getActiveLabel, getPreLabel, getPreScore } from '@/lib/utils'

// ── 状态筛选选项 ───────────────────────────────────────────────────────────────

const STATUS_OPTIONS = [
  { value: 'all',           label: '全部状态' },
  { value: 'raw',           label: '原始' },
  { value: 'cleaned',       label: '已清洗' },
  { value: 'pre_annotated', label: '已预标注' },
  { value: 'annotated',     label: '已标注' },
  { value: 'checked',       label: '已检测' },
]

// ── 文件上传区 ─────────────────────────────────────────────────────────────────

function FileUploadZone({ onSuccess }) {
  const fileRef = useRef()
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging]   = useState(false)

  async function uploadFile(file) {
    setUploading(true)
    try {
      const res = await dataApi.upload(file)
      const d = res.data?.data ?? res.data ?? {}
      toast.success(`上传成功：新增 ${d.created ?? 0} 条，跳过 ${d.skipped ?? 0} 条，去重 ${d.dup_skipped ?? 0} 条`)
      onSuccess?.()
    } catch (err) {
      toast.error(err.response?.data?.detail || '上传失败')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) uploadFile(file)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-3">
      <Card
        className={`border-2 border-dashed transition-colors cursor-pointer ${
          dragging ? 'border-primary bg-primary/5' : 'border-muted-foreground/25 hover:border-primary/50'
        }`}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => !uploading && fileRef.current?.click()}
      >
        <CardContent className="p-8 text-center">
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xls,.json,.csv"
            hidden
            onChange={e => { const f = e.target.files?.[0]; if (f) uploadFile(f) }}
          />
          <div className="mx-auto w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
            {uploading
              ? <Loader2 className="w-7 h-7 text-primary animate-spin" />
              : <Upload className="w-7 h-7 text-primary" />
            }
          </div>
          {uploading ? (
            <p className="text-sm font-medium text-primary">上传中，请稍候...</p>
          ) : (
            <>
              <p className="text-sm font-semibold">点击选择文件，或拖拽到此处</p>
              <p className="text-xs text-muted-foreground mt-1.5">
                支持 <span className="font-medium">Excel (.xlsx)</span> · <span className="font-medium">JSON</span> · <span className="font-medium">CSV</span>
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Excel/CSV 需包含 <code className="bg-muted px-1 rounded">text</code> 列；JSON 为字符串数组或含 text 字段的对象数组
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ── 手动录入区 ─────────────────────────────────────────────────────────────────

function ManualInputZone({ onSuccess }) {
  const [lines, setLines]       = useState('')   // textarea content
  const [submitting, setSubmitting] = useState(false)
  const [preview, setPreview]   = useState([])   // parsed lines

  // 实时解析行数
  function handleChange(e) {
    const val = e.target.value
    setLines(val)
    const parsed = val.split('\n').map(l => l.trim()).filter(Boolean)
    setPreview(parsed)
  }

  async function handleSubmit() {
    const items = lines.split('\n').map(l => l.trim()).filter(Boolean)
    if (items.length === 0) { toast.error('请输入至少一条内容'); return }
    setSubmitting(true)

    let created = 0, dup = 0, failed = 0
    for (const content of items) {
      try {
        await dataApi.create(content)
        created++
      } catch (err) {
        const detail = err.response?.data?.detail || ''
        if (detail.includes('重复')) dup++
        else failed++
      }
    }

    setSubmitting(false)
    const parts = []
    if (created)  parts.push(`新增 ${created} 条`)
    if (dup)      parts.push(`重复跳过 ${dup} 条`)
    if (failed)   parts.push(`失败 ${failed} 条`)
    toast[failed > 0 ? 'error' : 'success'](parts.join('，'))

    if (created > 0) {
      setLines('')
      setPreview([])
      onSuccess?.()
    }
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium">输入文本内容</label>
          {preview.length > 0 && (
            <span className="text-xs text-muted-foreground">
              共 <span className="font-semibold text-foreground">{preview.length}</span> 条待录入
            </span>
          )}
        </div>
        <textarea
          className="w-full min-h-40 border rounded-lg p-3 text-sm resize-y focus:outline-none focus:ring-2 focus:ring-primary/30 font-mono leading-relaxed"
          placeholder={"每行一条文本，例如：\n我想了解寿险产品\n帮我查一下理赔流程\n推荐一款健康险"}
          value={lines}
          onChange={handleChange}
        />
        <p className="text-xs text-muted-foreground">每行视为一条独立数据，空行自动忽略，重复内容自动去重</p>
      </div>

      {/* 预览 */}
      {preview.length > 0 && (
        <div className="border rounded-lg overflow-hidden">
          <div className="bg-muted/50 px-3 py-2 text-xs font-medium text-muted-foreground">
            预览（前 5 条）
          </div>
          <div className="divide-y">
            {preview.slice(0, 5).map((line, i) => (
              <div key={i} className="px-3 py-2 text-sm flex items-start gap-2">
                <span className="text-xs text-muted-foreground font-mono mt-0.5 w-4 shrink-0">{i + 1}</span>
                <span className="line-clamp-1">{line}</span>
              </div>
            ))}
            {preview.length > 5 && (
              <div className="px-3 py-2 text-xs text-muted-foreground text-center">
                ... 还有 {preview.length - 5} 条
              </div>
            )}
          </div>
        </div>
      )}

      <div className="flex justify-end">
        <Button
          onClick={handleSubmit}
          disabled={submitting || preview.length === 0}
          className="min-w-28"
        >
          {submitting
            ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />提交中</>
            : <><Plus className="w-4 h-4 mr-2" />提交录入</>
          }
        </Button>
      </div>
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

export default function DataUpload() {
  const qc = useQueryClient()
  const [uploadTab, setUploadTab] = useState('file')  // 'file' | 'manual'
  const [statusFilter, setStatusFilter] = useState('all')
  const [page, setPage]         = useState(1)
  const [pageSize, setPageSize] = useState(10)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['data-list', statusFilter, page, pageSize],
    queryFn: () => dataApi.list({
      status: statusFilter === 'all' ? undefined : statusFilter,
      page,
      page_size: pageSize,
    }),
    staleTime: 0,
  })

  // 按后端 page_data 格式解析：{ list, pagination: { total } }
  const result = data?.data?.data ?? {}
  const items  = result.list || []
  const total  = result.pagination?.total || 0

  function handleUploadSuccess() {
    qc.invalidateQueries(['data-list'])
    refetch()
  }

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
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">数据上传</h1>
          <p className="text-muted-foreground text-sm mt-1">文件批量导入或手动逐条录入原始数据</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          <RefreshCw className="w-4 h-4 mr-2" /> 刷新
        </Button>
      </div>

      {/* 上传方式 Tab */}
      <Card>
        <CardHeader className="pb-0">
          <div className="flex gap-1 bg-muted/50 p-1 rounded-lg w-fit">
            <button
              onClick={() => setUploadTab('file')}
              className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                uploadTab === 'file'
                  ? 'bg-white text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <FileText className="w-4 h-4" />
              文件上传
            </button>
            <button
              onClick={() => setUploadTab('manual')}
              className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                uploadTab === 'manual'
                  ? 'bg-white text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <PenLine className="w-4 h-4" />
              手动录入
            </button>
          </div>
        </CardHeader>
        <CardContent className="pt-4">
          {uploadTab === 'file'
            ? <FileUploadZone onSuccess={handleUploadSuccess} />
            : <ManualInputZone onSuccess={handleUploadSuccess} />
          }
        </CardContent>
      </Card>

      {/* 数据列表 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-3">
            <CardTitle className="text-base flex-1">已上传数据</CardTitle>
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
                <TableHead className="w-12">ID</TableHead>
                <TableHead>文本内容</TableHead>
                <TableHead className="w-28">状态</TableHead>
                <TableHead className="w-36">预测标签</TableHead>
                <TableHead className="w-36">人工标签</TableHead>
                <TableHead className="w-32">来源</TableHead>
                <TableHead className="w-40 whitespace-nowrap">创建时间</TableHead>
                <TableHead className="w-12"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-10 text-muted-foreground">
                    <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />加载中...
                  </TableCell>
                </TableRow>
              ) : items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-10 text-muted-foreground">
                    <CheckCircle2 className="w-8 h-8 mx-auto mb-2 opacity-20" />
                    暂无数据，请使用上方上传区添加数据
                  </TableCell>
                </TableRow>
              ) : items.map(item => {
                const preLabel   = getPreLabel(item)
                const preScore   = getPreScore(item)
                const activeLabel = getActiveLabel(item)
                return (
                  <TableRow key={item.id} className="hover:bg-muted/30">
                    <TableCell className="font-mono text-xs text-muted-foreground">{item.id}</TableCell>
                    <TableCell className="max-w-xs">
                      <p className="truncate text-sm" title={item.content}>{item.content}</p>
                    </TableCell>
                    <TableCell>
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${getStatusColor(item.status)}`}>
                        {getStatusLabel(item.status)}
                      </span>
                    </TableCell>
                    <TableCell>
                      {preLabel ? (
                        <>
                          <span className="text-sm">{preLabel}</span>
                          {preScore != null && (
                            <span className="ml-1 text-xs text-muted-foreground">
                              ({(preScore * 100).toFixed(0)}%)
                            </span>
                          )}
                        </>
                      ) : (
                        <span className="text-muted-foreground text-sm">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {activeLabel
                        ? <Badge variant="outline">{activeLabel}</Badge>
                        : <span className="text-muted-foreground text-sm">—</span>
                      }
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{item.source_ref || '—'}</TableCell>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{formatDate(item.created_at)}</TableCell>
                    <TableCell>
                      <button
                        onClick={() => requestDelete(item.id)}
                        className="text-muted-foreground hover:text-destructive transition-colors"
                        title="删除"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>

          {/* 分页 */}
          <TablePagination
            page={page}
            pageSize={pageSize}
            total={total}
            onPageChange={setPage}
            onSizeChange={size => { setPageSize(size); setPage(1) }}
          />
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
