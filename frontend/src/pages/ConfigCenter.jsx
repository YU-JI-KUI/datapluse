import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Settings, Save, RefreshCw, Database, Cpu, Sliders, Shield, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { configApi } from '@/lib/api'

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

export default function ConfigCenter() {
  const qc = useQueryClient()
  const [config, setConfig] = useState(null)
  const [saving, setSaving] = useState(false)
  const [reloading, setReloading] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['config'],
    queryFn: () => configApi.get(),
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
      handleChange(section, name, typeof value === 'boolean' ? value : (isNaN(value) ? value : (value === '' ? '' : Number(value) || value)))
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
    } catch (err) {
      toast.error('索引重建失败')
    }
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
            {saving ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> 保存中</> : <><Save className="w-4 h-4 mr-2" /> 保存配置</>}
          </Button>
        </div>
      </div>

      {/* Embedding */}
      <Section icon={Cpu} title="Embedding 模型" description="本地向量模型配置，用于语义冲突检测">
        <Field label="模型路径" name="model_path" value={config.embedding?.model_path}
          onChange={makeHandler('embedding')} placeholder="./models/bge-base-zh"
          hint="本地模型目录路径（支持绝对/相对路径）" />
        <Field label="批处理大小" name="batch_size" type="number" value={config.embedding?.batch_size}
          onChange={makeHandler('embedding')} hint="每批编码的文本数量，内存不足时调小" />
        <Field label="Mock 模式" name="use_mock" type="toggle" value={config.embedding?.use_mock}
          onChange={makeHandler('embedding')} hint="开启后使用随机向量，无需加载真实模型（开发用）" />
        <div className="flex gap-2 pt-1">
          <Button variant="outline" size="sm" onClick={handleReloadModel} disabled={reloading}>
            {reloading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
            重载模型
          </Button>
          <Button variant="outline" size="sm" onClick={handleRebuildIndex}>
            重建向量索引
          </Button>
        </div>
      </Section>

      {/* Similarity */}
      <Section icon={Sliders} title="相似度阈值" description="语义冲突检测的判断标准">
        <div className="grid grid-cols-3 gap-4">
          <Field label="高风险阈值" name="threshold_high" type="number" value={config.similarity?.threshold_high}
            onChange={makeHandler('similarity')} hint="cosine ≥ 此值 → 语义冲突" />
          <Field label="中风险阈值" name="threshold_mid" type="number" value={config.similarity?.threshold_mid}
            onChange={makeHandler('similarity')} hint="cosine ≥ 此值 → 需关注" />
          <Field label="检索 Top-K" name="topk" type="number" value={config.similarity?.topk}
            onChange={makeHandler('similarity')} hint="每条文本检索最近邻数量" />
        </div>
      </Section>

      {/* LLM */}
      <Section icon={Cpu} title="大模型平台（预标注）" description="内部 LLM 平台接入配置">
        <Field label="API URL" name="api_url" value={config.llm?.api_url}
          onChange={makeHandler('llm')} placeholder="http://internal-llm-platform/api/v1/chat" />
        <Field label="模型名称" name="model_name" value={config.llm?.model_name}
          onChange={makeHandler('llm')} placeholder="internal-llm" />
        <Field label="超时（秒）" name="timeout" type="number" value={config.llm?.timeout}
          onChange={makeHandler('llm')} />
        <Field label="Mock 模式" name="use_mock" type="toggle" value={config.llm?.use_mock}
          onChange={makeHandler('llm')} hint="开启后随机分配标签，不调用真实 LLM" />
      </Section>

      {/* Storage */}
      <Section icon={Database} title="存储路径" description="NAS 文件系统基础路径">
        <Field label="NAS 基础路径" name="base_path" value={config.storage?.base_path}
          onChange={makeHandler('storage')} placeholder="./nas"
          hint="所有数据文件存储根目录（支持绝对路径，如 /mnt/nas/datapluse）" />
      </Section>

      {/* Pipeline */}
      <Section icon={Settings} title="Pipeline 参数">
        <Field label="批处理大小" name="batch_size" type="number" value={config.pipeline?.batch_size}
          onChange={makeHandler('pipeline')} hint="Pipeline 每步处理的数据批量大小" />
      </Section>

      {/* Labels */}
      <Section icon={Shield} title="意图标签" description="可识别的意图类别">
        <div className="flex flex-wrap gap-2">
          {(config.labels || []).map((label, i) => (
            <div key={i} className="flex items-center gap-1 bg-muted rounded-lg px-3 py-1.5">
              <span className="text-sm">{label}</span>
              <button
                onClick={() => setConfig(prev => ({ ...prev, labels: prev.labels.filter((_, j) => j !== i) }))}
                className="text-muted-foreground hover:text-destructive ml-1 text-xs"
              >×</button>
            </div>
          ))}
          <button
            onClick={() => {
              const label = prompt('输入新标签名称')
              if (label) setConfig(prev => ({ ...prev, labels: [...(prev.labels || []), label] }))
            }}
            className="flex items-center gap-1 border border-dashed rounded-lg px-3 py-1.5 text-sm text-muted-foreground hover:border-primary hover:text-primary transition-colors"
          >
            + 添加标签
          </button>
        </div>
      </Section>

      {/* Bottom save */}
      <div className="flex justify-end pt-2">
        <Button onClick={handleSave} disabled={saving} size="lg">
          {saving ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> 保存中</> : <><Save className="w-4 h-4 mr-2" /> 保存所有配置</>}
        </Button>
      </div>
    </div>
  )
}
