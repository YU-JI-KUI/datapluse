/**
 * AI 评测 · 提示词管理：按当前 BU 组织提示词，页面实时编辑、Markdown 实时预览，
 * 保存后下次评测即生效，无需重启。左侧分「当前 BU 专属 / 通用（跨 BU 共享）」两组。
 */
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import ReactMarkdown from 'react-markdown'
import { Loader2, Save, RotateCcw, FileText, CheckCircle2, ArrowLeft } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { EvalBadge } from '@/components/eval/EvalPrimitives'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { evalApi, getCurrentBu } from '@/lib/api'
import { formatDate } from '@/lib/utils'

const RESP = (r) => r?.data?.data ?? {}

const SCOPE_LABEL = { _root: '通用（根）', _default: '通用兜底', securities: '证券', life: '寿险' }
const scopeName = (bu) => SCOPE_LABEL[bu] || bu
const SHARED = new Set(['_root', '_default'])   // 跨 BU 共享的作用域

// Markdown 渲染样式（无 typography 插件，内联给关键元素，避免新增依赖）
const MD = {
  h1: (p) => <h1 className="text-lg font-bold mt-3 mb-2" {...p} />,
  h2: (p) => <h2 className="text-base font-bold mt-3 mb-1.5" {...p} />,
  h3: (p) => <h3 className="text-sm font-semibold mt-2 mb-1" {...p} />,
  p:  (p) => <p className="my-1.5 leading-relaxed" {...p} />,
  ul: (p) => <ul className="list-disc pl-5 my-1.5 space-y-0.5" {...p} />,
  ol: (p) => <ol className="list-decimal pl-5 my-1.5 space-y-0.5" {...p} />,
  li: (p) => <li className="leading-relaxed" {...p} />,
  code: (p) => <code className="rounded bg-gray-200 px-1 py-0.5 text-[0.85em] font-mono" {...p} />,
  pre: (p) => <pre className="rounded bg-gray-100 p-2 my-2 overflow-x-auto text-xs" {...p} />,
  blockquote: (p) => <blockquote className="border-l-2 border-gray-300 pl-3 italic text-muted-foreground my-2" {...p} />,
  table: (p) => <table className="border-collapse my-2 text-xs" {...p} />,
  th: (p) => <th className="border border-gray-300 px-2 py-1 bg-gray-100 text-left" {...p} />,
  td: (p) => <td className="border border-gray-300 px-2 py-1" {...p} />,
  a:  (p) => <a className="text-blue-600 underline" {...p} />,
}

export default function EvalPrompts() {
  const [bu, setBu]           = useState(getCurrentBu())
  const [list, setList]       = useState([])
  const [active, setActive]   = useState(null)   // { bu, name }
  const [detail, setDetail]   = useState(null)
  const [draft, setDraft]     = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving]   = useState(false)
  const [resetOpen, setResetOpen] = useState(false)

  const dirty = detail && draft !== detail.content

  // 只展示「当前 BU 专属」+「通用（共享）」，其它 BU 隐藏；分两组有序渲染
  const groups = useMemo(() => {
    const own = list.filter(it => it.bu === bu)
    const shared = list.filter(it => SHARED.has(it.bu))
    return [
      { key: 'own', title: scopeName(bu), items: own },
      { key: 'shared', title: '通用（跨 BU 共享）', items: shared },
    ].filter(g => g.items.length > 0)
  }, [list, bu])

  async function loadList() {
    try {
      const data = RESP(await evalApi.listPrompts())
      setList(data.prompts || [])
      return data.prompts || []
    } catch (e) {
      toast.error(e.response?.data?.message || '加载提示词清单失败')
      return []
    }
  }

  async function openPrompt(b, name) {
    setActive({ bu: b, name }); setLoading(true)
    try {
      const d = RESP(await evalApi.getPrompt(b, name))
      setDetail(d); setDraft(d.content || '')
    } catch (e) {
      toast.error(e.response?.data?.message || '加载提示词失败')
      setDetail(null)
    } finally {
      setLoading(false)
    }
  }

  // 首屏：选当前 BU 第一个，没有则选通用第一个
  function openFirst(items) {
    const cur = getCurrentBu()
    const first = items.find(it => it.bu === cur) || items.find(it => SHARED.has(it.bu))
    if (first) openPrompt(first.bu, first.name)
  }

  useEffect(() => {
    loadList().then(openFirst)
    const onBuChange = (e) => { setBu(e.detail?.bu || getCurrentBu()); setDetail(null); setActive(null) }
    window.addEventListener('buChanged', onBuChange)
    return () => window.removeEventListener('buChanged', onBuChange)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleSave() {
    if (!detail || !draft.trim()) { toast.error('提示词内容不能为空'); return }
    setSaving(true)
    try {
      await evalApi.savePrompt(detail.bu, detail.name, draft)
      toast.success('已保存，下次评测即生效')
      await loadList()
      await openPrompt(detail.bu, detail.name)
    } catch (e) {
      toast.error(e.response?.data?.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  async function handleReset() {
    if (!detail) return
    try {
      const d = RESP(await evalApi.resetPrompt(detail.bu, detail.name))
      setDetail(d); setDraft(d.content || '')
      toast.success('已重置为出厂默认')
      await loadList()
    } catch (e) {
      toast.error(e.response?.data?.message || '重置失败')
    }
  }

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">提示词管理</h1>
          <p className="text-muted-foreground text-sm mt-1">
            编辑当前业务单元（<span className="font-medium">{scopeName(bu)}</span>）的提示词，
            左侧编辑、右侧实时预览 Markdown，保存后<strong>下次评测即生效</strong>。
          </p>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link to="/eval"><ArrowLeft className="w-4 h-4 mr-1.5" />返回评测</Link>
        </Button>
      </div>

      <div className="grid grid-cols-[260px_1fr] gap-6">
        {/* 左侧：分组列表 */}
        <Card className="h-fit">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">模板列表</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {groups.map(g => (
              <div key={g.key}>
                <div className="text-xs font-medium text-muted-foreground mb-1.5">
                  <EvalBadge tone="slate">{g.title}</EvalBadge>
                </div>
                <div className="space-y-1">
                  {g.items.map(it => {
                    const on = active?.bu === it.bu && active?.name === it.name
                    return (
                      <button
                        key={`${it.bu}/${it.name}`}
                        onClick={() => openPrompt(it.bu, it.name)}
                        className={[
                          'w-full rounded-md px-2.5 py-2 text-left text-sm transition-colors',
                          on ? 'bg-blue-100 text-blue-700' : 'hover:bg-accent',
                        ].join(' ')}
                      >
                        <div className="flex items-center gap-1.5">
                          <FileText className="w-3.5 h-3.5 shrink-0 opacity-60" />
                          <span className="flex-1 truncate">{it.description || it.name}</span>
                          {it.customized && (
                            <CheckCircle2 className="w-3.5 h-3.5 text-green-600 shrink-0" title="已自定义" />
                          )}
                        </div>
                        <div className="text-[11px] text-muted-foreground mt-0.5 truncate pl-5">{it.name}</div>
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* 右侧：编辑器 + Markdown 预览 */}
        <Card>
          {loading ? (
            <CardContent className="py-16 flex items-center justify-center text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />加载中…
            </CardContent>
          ) : !detail ? (
            <CardContent className="py-16 text-center text-muted-foreground">请选择左侧模板</CardContent>
          ) : (
            <>
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <CardTitle className="text-base flex items-center gap-2">
                      {detail.description || detail.name}
                      {detail.customized
                        ? <EvalBadge tone="good">已自定义</EvalBadge>
                        : <EvalBadge tone="slate">出厂默认</EvalBadge>}
                    </CardTitle>
                    <div className="text-xs text-muted-foreground mt-1">
                      <span className="font-mono">{scopeName(detail.bu)} / {detail.name}</span>
                      {detail.customized && detail.updated_at && (
                        <span className="ml-3">最后修改：{detail.updated_by} · {formatDate(detail.updated_at)}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {detail.customized && (
                      <Button variant="outline" size="sm" onClick={() => setResetOpen(true)}>
                        <RotateCcw className="w-4 h-4 mr-1.5" />重置默认
                      </Button>
                    )}
                    <Button size="sm" onClick={handleSave} disabled={saving || !dirty}>
                      {saving ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : <Save className="w-4 h-4 mr-1.5" />}
                      保存
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {/* 左编辑 / 右预览 */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col">
                    <div className="text-xs text-muted-foreground mb-1">编辑（Markdown 源码）</div>
                    <textarea
                      value={draft}
                      onChange={e => setDraft(e.target.value)}
                      spellCheck={false}
                      className="h-[560px] w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-ring"
                    />
                  </div>
                  <div className="flex flex-col">
                    <div className="text-xs text-muted-foreground mb-1">预览</div>
                    <div className="h-[560px] overflow-y-auto rounded-md border border-input bg-muted/30 px-4 py-3 text-sm">
                      <ReactMarkdown components={MD}>{draft || '_（空）_'}</ReactMarkdown>
                    </div>
                  </div>
                </div>
                <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground">
                  <span>{dirty ? '有未保存的修改' : '无改动'}</span>
                  <span>{draft.length} 字符</span>
                </div>
              </CardContent>
            </>
          )}
        </Card>
      </div>

      <ConfirmDialog
        open={resetOpen}
        onOpenChange={setResetOpen}
        title="重置为出厂默认"
        description="将删除你对该模板的自定义内容，恢复为代码内置的默认提示词。此操作不可撤销。"
        confirmLabel="重置"
        onConfirm={handleReset}
      />
    </div>
  )
}
