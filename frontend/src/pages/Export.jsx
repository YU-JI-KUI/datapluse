import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Download, FileJson, FileSpreadsheet, RefreshCw, Loader2, Package } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { exportApi, dataApi } from '@/lib/api'
import { formatDate, formatBytes } from '@/lib/utils'

export default function Export() {
  const qc = useQueryClient()
  const [format, setFormat] = useState('json')
  const [creating, setCreating] = useState(false)

  const { data: checkedData } = useQuery({
    queryKey: ['checked-export'],
    queryFn: () => dataApi.list({ status: 'checked', page: 1, page_size: 1 }),
  })

  const { data: exportsData, isLoading, refetch } = useQuery({
    queryKey: ['export-list'],
    queryFn: () => exportApi.list(),
    refetchInterval: 10000,
  })

  const checkedCount = checkedData?.data?.total || 0
  const exports = exportsData?.data?.data || []

  async function handleCreate() {
    if (checkedCount === 0) {
      toast.error('没有通过检测的数据，请先运行冲突检测')
      return
    }
    setCreating(true)
    try {
      const res = await exportApi.create({ format, status_filter: 'checked', include_conflicts: false })
      toast.success(`导出成功：${res.data.count} 条数据，${formatBytes(res.data.size)}`)
      refetch()
    } catch (err) {
      toast.error(err.response?.data?.detail || '导出失败')
    } finally {
      setCreating(false)
    }
  }

  function handleDownload(filename) {
    const url = exportApi.downloadUrl(filename)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">数据导出</h1>
          <p className="text-muted-foreground text-sm mt-1">导出高质量数据（仅含通过冲突检测的数据）</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          <RefreshCw className="w-4 h-4 mr-2" /> 刷新
        </Button>
      </div>

      {/* Export action card */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center gap-6">
            <div className="flex-1">
              <h3 className="font-semibold">生成导出文件</h3>
              <p className="text-sm text-muted-foreground mt-1">
                当前可导出 <span className="font-medium text-foreground">{checkedCount}</span> 条高质量数据
                （已通过冲突检测）
              </p>
            </div>

            <Select value={format} onValueChange={setFormat}>
              <SelectTrigger className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="json">
                  <div className="flex items-center gap-2">
                    <FileJson className="w-4 h-4" /> JSON
                  </div>
                </SelectItem>
                <SelectItem value="excel">
                  <div className="flex items-center gap-2">
                    <FileSpreadsheet className="w-4 h-4" /> Excel
                  </div>
                </SelectItem>
              </SelectContent>
            </Select>

            <Button onClick={handleCreate} disabled={creating || checkedCount === 0}>
              {creating
                ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> 生成中</>
                : <><Package className="w-4 h-4 mr-2" /> 生成导出</>
              }
            </Button>
          </div>

          {/* Format preview */}
          <div className="mt-4 bg-muted/50 rounded-lg p-4 text-xs font-mono text-muted-foreground">
            {format === 'json'
              ? `[{"id":"uuid","text":"用户输入","label":"寿险意图","model_pred":"寿险意图","model_score":0.95,...}]`
              : `id | text | label | model_pred | model_score | annotator | annotated_at | source_file`
            }
          </div>
        </CardContent>
      </Card>

      {/* Exports list */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Download className="w-4 h-4" />
            导出历史
            <span className="text-sm font-normal text-muted-foreground">({exports.length} 个文件)</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="py-12 text-center text-muted-foreground text-sm">加载中...</div>
          ) : exports.length === 0 ? (
            <div className="py-12 text-center">
              <div className="w-12 h-12 rounded-xl bg-muted flex items-center justify-center mx-auto mb-3">
                <Download className="w-6 h-6 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground">暂无导出记录</p>
            </div>
          ) : (
            <div className="divide-y">
              {exports.map((file) => (
                <div key={file.filename} className="flex items-center gap-4 px-6 py-4 hover:bg-muted/30 transition-colors">
                  <div className="w-10 h-10 rounded-lg bg-muted flex items-center justify-center shrink-0">
                    {file.filename.endsWith('.xlsx')
                      ? <FileSpreadsheet className="w-5 h-5 text-green-600" />
                      : <FileJson className="w-5 h-5 text-blue-600" />
                    }
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{file.filename}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {formatBytes(file.size)} · {formatDate(file.created_at)}
                    </p>
                  </div>
                  <Badge variant={file.filename.endsWith('.xlsx') ? 'success' : 'info'}>
                    {file.filename.endsWith('.xlsx') ? 'Excel' : 'JSON'}
                  </Badge>
                  <Button variant="outline" size="sm" onClick={() => handleDownload(file.filename)}>
                    <Download className="w-4 h-4 mr-1.5" /> 下载
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
