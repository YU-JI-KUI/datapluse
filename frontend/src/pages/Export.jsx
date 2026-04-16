import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Download, FileJson, FileSpreadsheet, FileText, RefreshCw,
  Loader2, Package, Plus, Trash2, Pencil, X, Check, GripVertical,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { exportApi, templateApi, dataApi } from '@/lib/api'

// ── 工具 ─────────────────────────────────────────────────────────────────────

const FORMAT_ICONS = {
  json:  <FileJson className="w-4 h-4 text-blue-500" />,
  excel: <FileSpreadsheet className="w-4 h-4 text-green-600" />,
  csv:   <FileText className="w-4 h-4 text-orange-500" />,
}

// 与后端 AVAILABLE_FIELDS（base.py）保持一致
const ALL_FIELDS = [
  // ── 基础 ──────────────────────────────────────────────────────────────────
  { source: 'id',                label: '数据 ID' },
  { source: 'content',           label: '原始文本' },
  { source: 'source_ref',        label: '来源文件' },
  { source: 'status',            label: '数据阶段' },
  { source: 'created_at',        label: '创建时间' },
  { source: 'updated_at',        label: '数据更新时间' },
  // ── 最终标注结果（t_annotation_result）────────────────────────────────────
  { source: 'label',             label: '最终标注标签' },
  { source: 'label_source',      label: '标签来源 (auto/manual)' },
  { source: 'annotated_at',      label: '标注完成时间' },
  { source: 'result_updated_at', label: '结果最后更新时间' },
  // ── 标注人员 ──────────────────────────────────────────────────────────────
  { source: 'annotator',         label: '标注员（裁决者/全部参与者）' },
  { source: 'annotators',        label: '全部标注员（逗号分隔）' },
  { source: 'annotator_count',   label: '参与标注人数' },
  { source: 'resolver',          label: '冲突裁决人' },
  // ── 预标注（模型预测）────────────────────────────────────────────────────
  { source: 'model_pred',        label: '模型预测标签' },
  { source: 'model_score',       label: '模型置信度' },
  { source: 'model_name',        label: '预测模型名称' },
  // ── 冲突 ──────────────────────────────────────────────────────────────────
  { source: 'conflict_flag',     label: '是否存在冲突' },
  { source: 'conflict_type',     label: '冲突类型' },
]

// ── 模板编辑器 ─────────────────────────────────────────────────────────────────

function TemplateEditor({ initial, onSave, onCancel }) {
  // 默认模板：与后端 DEFAULT_COLUMNS 核心字段对齐
  const DEFAULT_SOURCES = ['id', 'content', 'label', 'label_source', 'annotator', 'annotated_at', 'model_pred', 'model_score', 'source_ref', 'status', 'created_at']
  const defaultColumns = DEFAULT_SOURCES
    .map(src => ALL_FIELDS.find(f => f.source === src))
    .filter(Boolean)
    .map(f => ({ source: f.source, target: f.source, include: true }))

  const [name, setName] = useState(initial?.name || '')
  const [description, setDescription] = useState(initial?.description || '')
  const [format, setFormat] = useState(initial?.format || 'json')
  const [columns, setColumns] = useState(
    initial?.columns?.length ? initial.columns : defaultColumns
  )
  const [saving, setSaving] = useState(false)

  const allEnabled  = columns.length > 0 && columns.every(c => c.include)
  const someEnabled = columns.some(c => c.include) && !allEnabled

  function toggleAllInclude() {
    const next = !allEnabled
    setColumns(cols => cols.map(c => ({ ...c, include: next })))
  }
  function toggleInclude(idx) {
    setColumns(cols => cols.map((c, i) => i === idx ? { ...c, include: !c.include } : c))
  }
  function setTarget(idx, value) {
    setColumns(cols => cols.map((c, i) => i === idx ? { ...c, target: value } : c))
  }
  function addField(source) {
    if (columns.find(c => c.source === source)) return
    const meta = ALL_FIELDS.find(f => f.source === source)
    setColumns(cols => [...cols, { source, target: source, include: true }])
  }
  function removeField(idx) {
    setColumns(cols => cols.filter((_, i) => i !== idx))
  }

  async function handleSave() {
    if (!name.trim()) { toast.error('请填写模板名称'); return }
    if (columns.length === 0) { toast.error('至少需要一个字段'); return }
    setSaving(true)
    try {
      await onSave({
        name: name.trim(),
        description: description.trim(),
        format,
        columns,
        filters: { status: 'checked', include_conflicts: false },
      })
    } finally {
      setSaving(false)
    }
  }

  const usedSources = new Set(columns.map(c => c.source))
  const availableToAdd = ALL_FIELDS.filter(f => !usedSources.has(f.source))

  return (
    <div className="space-y-5">
      {/* 基本信息 */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">模板名称 *</label>
          <Input value={name} onChange={e => setName(e.target.value)} placeholder="如：训练集标准格式" />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-muted-foreground">输出格式</label>
          <Select value={format} onValueChange={setFormat}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="json">JSON</SelectItem>
              <SelectItem value="excel">Excel</SelectItem>
              <SelectItem value="csv">CSV</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="space-y-1">
        <label className="text-xs font-medium text-muted-foreground">描述</label>
        <Input value={description} onChange={e => setDescription(e.target.value)} placeholder="可选，说明此模板的用途" />
      </div>

      {/* 字段映射 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-xs font-medium text-muted-foreground">字段映射（源变量 → 输出字段名）</label>
          {availableToAdd.length > 0 && (
            <Select onValueChange={(v) => { addField(v) }} value="__placeholder__">
              <SelectTrigger className="w-36 h-7 text-xs">
                <SelectValue placeholder="+ 添加字段" />
              </SelectTrigger>
              <SelectContent>
                {availableToAdd.map(f => (
                  <SelectItem key={f.source} value={f.source}>
                    {f.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        <div className="border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground w-20 whitespace-nowrap">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={toggleAllInclude}
                      title={allEnabled ? '全部禁用' : '全部启用'}
                      className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 ${
                        allEnabled
                          ? 'bg-primary border-primary text-white'
                          : someEnabled
                            ? 'bg-primary/30 border-primary'
                            : 'border-gray-300 hover:border-primary'
                      }`}
                    >
                      {allEnabled  && <Check className="w-3 h-3" />}
                      {someEnabled && <span className="text-primary text-xs font-bold leading-none">—</span>}
                    </button>
                    启用
                  </div>
                </th>
                <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">源变量</th>
                <th className="text-left px-3 py-2 text-xs font-medium text-muted-foreground">输出字段名</th>
                <th className="w-8"></th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {columns.map((col, idx) => {
                const meta = ALL_FIELDS.find(f => f.source === col.source)
                return (
                  <tr key={col.source} className={col.include ? '' : 'opacity-50'}>
                    <td className="px-3 py-2">
                      <button
                        onClick={() => toggleInclude(idx)}
                        className={`w-4 h-4 rounded border flex items-center justify-center ${col.include ? 'bg-primary border-primary text-white' : 'border-gray-300'}`}
                      >
                        {col.include && <Check className="w-3 h-3" />}
                      </button>
                    </td>
                    <td className="px-3 py-2">
                      <span className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded text-blue-600">
                        {'{{' + col.source + '}}'}
                      </span>
                      <span className="ml-2 text-xs text-muted-foreground">{meta?.label}</span>
                    </td>
                    <td className="px-3 py-2">
                      <Input
                        value={col.target}
                        onChange={e => setTarget(idx, e.target.value)}
                        className="h-7 text-xs"
                      />
                    </td>
                    <td className="px-2">
                      <button onClick={() => removeField(idx)} className="text-muted-foreground hover:text-destructive">
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-muted-foreground">
          <span className="font-mono bg-muted px-1 rounded text-blue-600">{'{{source}}'}</span>
          {' '}表示源字段变量，输出字段名可自定义（如 text → sentence）
        </p>
      </div>

      {/* 操作 */}
      <div className="flex justify-end gap-2 pt-2 border-t">
        <Button variant="outline" size="sm" onClick={onCancel}>取消</Button>
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {saving ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <Check className="w-4 h-4 mr-1.5" />}
          保存模板
        </Button>
      </div>
    </div>
  )
}

// ── 导出操作面板 ───────────────────────────────────────────────────────────────

function ExportPanel() {
  const [format, setFormat] = useState('json')
  const [templateId, setTemplateId] = useState('default')
  const [exporting, setExporting] = useState(false)

  const { data: checkedData } = useQuery({
    queryKey: ['checked-count'],
    queryFn: () => dataApi.list({ status: 'checked', page: 1, page_size: 1 }),
  })
  const { data: tplData } = useQuery({
    queryKey: ['templates'],
    queryFn: () => templateApi.list(),
  })

  const checkedCount = checkedData?.data?.data?.pagination?.total || 0
  const templates = tplData?.data?.data || []

  async function handleExport() {
    if (checkedCount === 0) { toast.error('没有通过检测的数据，请先运行冲突检测'); return }
    setExporting(true)
    try {
      const params = templateId === 'default'
        ? { format, status_filter: 'checked', include_conflicts: false }
        : { format, status_filter: 'checked', include_conflicts: false, template_id: templateId }
      const filename = await exportApi.download(params)
      toast.success(`已下载：${filename}`)
    } catch {
      toast.error('导出失败')
    } finally {
      setExporting(false)
    }
  }

  const selectedTpl = templates.find(t => t.id === templateId)

  return (
    <div className="space-y-5">
      <Card>
        <CardContent className="p-6 space-y-5">
          <div className="flex items-start gap-6">
            <div className="flex-1">
              <h3 className="font-semibold">生成导出文件</h3>
              <p className="text-sm text-muted-foreground mt-1">
                当前可导出 <span className="font-medium text-foreground">{checkedCount}</span> 条（已通过冲突检测）
              </p>
            </div>

            <div className="flex items-center gap-3">
              {/* 模板选择 */}
              <Select value={templateId} onValueChange={setTemplateId}>
                <SelectTrigger className="w-44">
                  <SelectValue placeholder="选择模板" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="default">默认字段</SelectItem>
                  {templates.map(t => (
                    <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* 格式（无模板时显示） */}
              {templateId === 'default' && (
                <Select value={format} onValueChange={setFormat}>
                  <SelectTrigger className="w-28">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="json">JSON</SelectItem>
                    <SelectItem value="excel">Excel</SelectItem>
                    <SelectItem value="csv">CSV</SelectItem>
                  </SelectContent>
                </Select>
              )}

              <Button onClick={handleExport} disabled={exporting || checkedCount === 0}>
                {exporting
                  ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />导出中</>
                  : <><Package className="w-4 h-4 mr-2" />立即导出</>
                }
              </Button>
            </div>
          </div>

          {/* 模板预览 */}
          {selectedTpl && (
            <div className="bg-muted/40 rounded-lg p-4 space-y-2">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                {FORMAT_ICONS[selectedTpl.format]}
                <span className="font-medium text-foreground">{selectedTpl.name}</span>
                {selectedTpl.description && <span>· {selectedTpl.description}</span>}
              </div>
              <div className="font-mono text-xs text-muted-foreground flex flex-wrap gap-1">
                {selectedTpl.columns?.filter(c => c.include).map(c => (
                  <span key={c.source} className="bg-background border rounded px-1.5 py-0.5">
                    <span className="text-blue-500">{`{{${c.source}}}`}</span>
                    {c.target !== c.source && <span className="text-muted-foreground"> → {c.target}</span>}
                  </span>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ── 模板管理面板 ───────────────────────────────────────────────────────────────

function TemplatesPanel() {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(null)  // null | 'new' | {template}
  const [deleting, setDeleting] = useState(null)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['templates'],
    queryFn: () => templateApi.list(),
    staleTime: 0,
  })
  const templates = data?.data?.data || []

  async function handleCreate(formData) {
    try {
      await templateApi.create(formData)
      toast.success('模板已创建')
      qc.invalidateQueries(['templates'])
      setEditing(null)
    } catch {
      toast.error('创建失败')
    }
  }

  async function handleUpdate(formData) {
    try {
      await templateApi.update(editing.id, formData)
      toast.success('模板已更新')
      qc.invalidateQueries(['templates'])
      setEditing(null)
    } catch {
      toast.error('更新失败')
    }
  }

  async function handleDelete(id) {
    setDeleting(id)
    try {
      await templateApi.delete(id)
      toast.success('已删除')
      qc.invalidateQueries(['templates'])
    } catch {
      toast.error('删除失败')
    } finally {
      setDeleting(null)
    }
  }

  if (editing !== null) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {editing === 'new' ? '新建模板' : `编辑：${editing.name}`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <TemplateEditor
            initial={editing === 'new' ? null : editing}
            onSave={editing === 'new' ? handleCreate : handleUpdate}
            onCancel={() => setEditing(null)}
          />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">导出模板</CardTitle>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw className="w-4 h-4" />
            </Button>
            <Button size="sm" onClick={() => setEditing('new')}>
              <Plus className="w-4 h-4 mr-1.5" /> 新建模板
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {isLoading ? (
          <div className="py-12 text-center text-muted-foreground text-sm">加载中...</div>
        ) : templates.length === 0 ? (
          <div className="py-12 text-center">
            <div className="w-12 h-12 rounded-xl bg-muted flex items-center justify-center mx-auto mb-3">
              <FileJson className="w-6 h-6 text-muted-foreground" />
            </div>
            <p className="text-sm text-muted-foreground mb-3">暂无导出模板</p>
            <Button size="sm" onClick={() => setEditing('new')}>
              <Plus className="w-4 h-4 mr-1.5" /> 新建第一个模板
            </Button>
          </div>
        ) : (
          <div className="divide-y">
            {templates.map(tpl => (
              <div key={tpl.id} className="flex items-center gap-4 px-6 py-4 hover:bg-muted/30 transition-colors">
                <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center shrink-0">
                  {FORMAT_ICONS[tpl.format] || <FileJson className="w-4 h-4" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium">{tpl.name}</p>
                    <Badge variant="outline" className="text-xs">{tpl.format.toUpperCase()}</Badge>
                  </div>
                  {tpl.description && (
                    <p className="text-xs text-muted-foreground mt-0.5">{tpl.description}</p>
                  )}
                  <div className="flex gap-1 mt-1 flex-wrap">
                    {tpl.columns?.filter(c => c.include).map(c => (
                      <span key={c.source} className="font-mono text-xs text-blue-500 bg-blue-50 px-1 rounded">
                        {`{{${c.source}}}`}{c.target !== c.source ? ` → ${c.target}` : ''}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex gap-2 shrink-0">
                  <Button variant="outline" size="sm" onClick={() => setEditing(tpl)}>
                    <Pencil className="w-3.5 h-3.5" />
                  </Button>
                  <Button
                    variant="outline" size="sm"
                    onClick={() => handleDelete(tpl.id)}
                    disabled={deleting === tpl.id}
                    className="text-destructive hover:text-destructive"
                  >
                    {deleting === tpl.id
                      ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      : <Trash2 className="w-3.5 h-3.5" />
                    }
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

export default function Export() {
  const [tab, setTab] = useState('export')

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">数据导出</h1>
        <p className="text-muted-foreground text-sm mt-1">导出高质量数据，支持自定义字段模板</p>
      </div>

      {/* Tab 切换 */}
      <div className="flex gap-1 bg-muted/50 p-1 rounded-lg w-fit">
        {[
          { key: 'export', label: '导出数据' },
          { key: 'templates', label: '模板管理' },
        ].map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              tab === key
                ? 'bg-white text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'export' ? <ExportPanel /> : <TemplatesPanel />}
    </div>
  )
}
