import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Settings, Save, RefreshCw, Database, Cpu, Sliders, Loader2, Plus, X, Tag } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { configApi } from '@/lib/api'

// ── 子组件：通用 Section 卡片 ────────────────────────────────────────────────

function Section({ icon: Icon, title, description, children }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Icon className="w-4 h-4 text-primary" />
          </div>
          <div>
            <CardTitle className="text-base">{title}</CardTitle>
            {description && <CardDescription className="text-xs mt-0.5">{description}</CardDescription>}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">{children}</CardContent>
    </Card>
  )
}

// ── 子组件：表单字段 ──────────────────────────────────────────────────────────

function Field({ label, name, value, onChange, type = 'text', placeholder, hint }) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1.5">{label}</label>
      {type === 'toggle' ? (
        <div className="flex items-center gap-3">
          <button
            onClick={() => onChange({ target: { name, value: !value } })}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${value ? 'bg-primary' : 'bg-muted'}`}
          >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow-sm transition-transform ${value ? 'translate-x-6' : 'translate-x-1'}`} />
          </button>
          <span className="text-sm text-muted-foreground">{value ? '开启' : '关闭'}</span>
        </div>
      ) : (
        <Input
          type={type}
          name={name}
          value={value ?? ''}
          onChange={onChange}
          placeholder={placeholder}
          className="max-w-md"
        />
      )}
      {hint && <p className="text-xs text-muted-foreground mt-1">{hint}</p>}
    </div>
  )
}

// ── 子组件：批量添加标签对话框 ────────────────────────────────────────────────

function AddLabelsDialog({ open, onOpenChange, onAdd }) {
  const [text, setText] = useState('')

  function handleClose() {
    setText('')
    onOpenChange(false)
  }

  function handleSubmit() {
    // 支持换行符和逗号两种分隔方式
    const lines = text
      .split(/[\n,]/)
      .map(s => s.trim())
      .filter(s => s.length > 0)

    if (lines.length === 0) {
      toast.error('请输入至少一个标签名称')
      return
    }
    onAdd(lines)
    handleClose()
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>批量添加标签</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <p className="text-sm text-muted-foreground">
            每行一个标签，或用逗号分隔，支持批量粘贴。
          </p>
          <textarea
            autoFocus
            className="w-full min-h-[140px] rounded-md border border-input bg-background px-3 py-2 text-sm
                       placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-y"
            placeholder={"寿险意图\n健康险意图\n财险意图\n其他意图"}
            value={text}
            onChange={e => setText(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            已输入 <span className="font-semibold text-foreground">
              {text.split(/[\n,]/).filter(s => s.trim()).length}
            </span> 个标签
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={handleClose}>取消</Button>
          <Button onClick={handleSubmit}>
            <Plus className="w-4 h-4 mr-1.5" />
            添加
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

export default function ConfigCenter() {
  const [config, setConfig]     = useState(null)
  const [saving, setSaving]     = useState(false)
  const [reloading, setReloading] = useState(false)
  const [addOpen, setAddOpen]   = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['config'],
    queryFn:  () => configApi.get(),
  })

  useEffect(() => {
    if (data?.data?.data) setConfig(data.data.data)
  }, [data])

  function handleChange(section, key, value) {
    setConfig(prev => ({
      ...prev,
      [section]: { ...prev[section], [key]: value },
    }))
  }

  function makeHandler(section) {
    return (e) => {
      const { name, value } = e.target
      handleChange(
        section, name,
        typeof value === 'boolean'
          ? value
          : (value === '' ? '' : (!isNaN(value) && value !== '' ? Number(value) : value)),
      )
    }
  }

  async function handleSave() {
    setSaving(true)
    try {
      await configApi.update(config)
      toast.success('配置已保存并立即生效')
      refetch()
    } catch (err) {
      toast.error('保存失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      setSaving(false)
    }
  }

  async function handleReloadModel() {
    setReloading(true)
    try {
      await configApi.reloadModel()
      toast.success('Embedding 模型已重载')
    } catch (err) {
      toast.error(err.response?.data?.detail || '重载失败')
    } finally {
      setReloading(false)
    }
  }

  async function handleRebuildIndex() {
    try {
      const res = await configApi.rebuildIndex()
      toast.success(res.data.message)
    } catch {
      toast.error('索引重建失败')
    }
  }

  function handleAddLabels(newLabels) {
    setConfig(prev => {
      const existing = new Set(prev.labels || [])
      const toAdd    = newLabels.filter(l => !existing.has(l))
      if (toAdd.length === 0) {
        toast.info('所有标签均已存在，无需添加')
        return prev
      }
      toast.success(`已添加 ${toAdd.length} 个标签`)
      return { ...prev, labels: [...(prev.labels || []), ...toAdd] }
    })
  }

  function handleRemoveLabel(idx) {
    setConfig(prev => ({ ...prev, labels: prev.labels.filter((_, j) => j !== idx) }))
  }

  if (isLoading || !config) {
    return (
      <div className="p-8 flex items-center justify-center h-96">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">配置中心</h1>
          <p className="text-muted-foreground text-sm mt-1">所有关键参数可视化配置，保存后立即生效</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="w-4 h-4 mr-2" /> 重载
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving}>
            {saving
              ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />保存中</>
              : <><Save className="w-4 h-4 mr-2" />保存配置</>}
          </Button>
        </div>
      </div>

      {/* 1. 意图标签（置顶）*/}
      <Section icon={Tag} title="意图标签" description="可识别的意图类别，用于标注和预标注">
        <div className="flex flex-wrap gap-2">
          {(config.labels || []).map((label, i) => (
            <div key={i} className="flex items-center gap-1 bg-muted rounded-lg px-3 py-1.5">
              <span className="text-sm">{label}</span>
              <button
                onClick={() => handleRemoveLabel(i)}
                className="text-muted-foreground hover:text-destructive ml-1 transition-colors"
                title="删除此标签"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
          <button
            onClick={() => setAddOpen(true)}
            className="flex items-center gap-1 border border-dashed rounded-lg px-3 py-1.5 text-sm text-muted-foreground hover:border-primary hover:text-primary transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            添加标签
          </button>
        </div>
        {(config.labels || []).length === 0 && (
          <p className="text-xs text-muted-foreground">尚无标签，点击「添加标签」开始配置</p>
        )}
      </Section>

      {/* 2. Pipeline 参数 */}
      <Section icon={Settings} title="Pipeline 参数" description="数据处理流水线的运行参数">
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="批处理大小"
            name="batch_size"
            type="number"
            value={config.pipeline?.batch_size}
            onChange={makeHandler('pipeline')}
            hint="Pipeline 每步处理的数据批量大小"
          />
          <Field
            label="最低标注个数"
            name="min_annotation_count"
            type="number"
            value={config.pipeline?.min_annotation_count}
            onChange={makeHandler('pipeline')}
            hint="冲突检测只处理标注人数 ≥ 该值的数据"
          />
        </div>
        <Field
          label="展示 COT 输入框（标注理由）"
          name="require_cot"
          type="toggle"
          value={config.pipeline?.require_cot ?? false}
          onChange={makeHandler('pipeline')}
          hint="开启：在标注和裁决界面显示「标注理由」输入框（非必填）；关闭：隐藏该字段"
        />
      </Section>

      {/* 3. Embedding 模型 */}
      <Section icon={Cpu} title="Embedding 模型" description="本地向量模型配置，用于语义冲突检测">
        <Field
          label="模型路径"
          name="model_path"
          value={config.embedding?.model_path}
          onChange={makeHandler('embedding')}
          placeholder="./models/bge-base-zh"
          hint="本地模型目录路径（支持绝对/相对路径）"
        />
        <Field
          label="批处理大小"
          name="batch_size"
          type="number"
          value={config.embedding?.batch_size}
          onChange={makeHandler('embedding')}
          hint="每批编码的文本数量，内存不足时调小"
        />
        <Field
          label="Mock 模式"
          name="use_mock"
          type="toggle"
          value={config.embedding?.use_mock}
          onChange={makeHandler('embedding')}
          hint="开启后使用随机向量，无需加载真实模型（开发用）"
        />
        <div className="flex gap-2 pt-1">
          <Button variant="outline" size="sm" onClick={handleReloadModel} disabled={reloading}>
            {reloading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
            重载模型
          </Button>
          <Button variant="outline" size="sm" onClick={handleRebuildIndex}>
            重建向量索引
          </Button>
        </div>
      </Section>

      {/* 4. 相似度阈值 */}
      <Section icon={Sliders} title="相似度阈值" description="语义冲突检测的判断标准">
        <div className="grid grid-cols-3 gap-4">
          <Field
            label="高风险阈值"
            name="threshold_high"
            type="number"
            value={config.similarity?.threshold_high}
            onChange={makeHandler('similarity')}
            hint="cosine ≥ 此值 → 语义冲突"
          />
          <Field
            label="中风险阈值"
            name="threshold_mid"
            type="number"
            value={config.similarity?.threshold_mid}
            onChange={makeHandler('similarity')}
            hint="cosine ≥ 此值 → 需关注"
          />
          <Field
            label="检索 Top-K"
            name="topk"
            type="number"
            value={config.similarity?.topk}
            onChange={makeHandler('similarity')}
            hint="每条文本检索最近邻数量"
          />
        </div>
      </Section>

      {/* 5. 大模型平台 */}
      <Section icon={Cpu} title="大模型平台（预标注）" description="内部 LLM 平台接入配置">
        <Field
          label="API URL"
          name="api_url"
          value={config.llm?.api_url}
          onChange={makeHandler('llm')}
          placeholder="http://internal-llm-platform/api/v1/chat"
        />
        <Field
          label="模型名称"
          name="model_name"
          value={config.llm?.model_name}
          onChange={makeHandler('llm')}
          placeholder="internal-llm"
        />
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="超时（秒）"
            name="timeout"
            type="number"
            value={config.llm?.timeout}
            onChange={makeHandler('llm')}
          />
          <Field
            label="并发请求数"
            name="concurrency"
            type="number"
            value={config.llm?.concurrency}
            onChange={makeHandler('llm')}
            hint="预标注时最大并发 LLM 请求数，过高可能触发平台限流"
          />
        </div>
        <Field
          label="Mock 模式"
          name="use_mock"
          type="toggle"
          value={config.llm?.use_mock}
          onChange={makeHandler('llm')}
          hint="开启后随机分配标签，不调用真实 LLM"
        />
      </Section>

      {/* 6. 存储路径 */}
      <Section icon={Database} title="存储路径" description="NAS 文件系统基础路径">
        <Field
          label="NAS 基础路径"
          name="base_path"
          value={config.storage?.base_path}
          onChange={makeHandler('storage')}
          placeholder="/ark-nav/datapulse"
          hint="向量文件和 FAISS 索引存储根目录（支持 NAS 挂载绝对路径）"
        />
      </Section>

      {/* 底部保存按钮 */}
      <div className="flex justify-end pt-2">
        <Button onClick={handleSave} disabled={saving} size="lg">
          {saving
            ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />保存中</>
            : <><Save className="w-4 h-4 mr-2" />保存所有配置</>}
        </Button>
      </div>

      {/* 批量添加标签对话框 */}
      <AddLabelsDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        onAdd={handleAddLabels}
      />
    </div>
  )
}
