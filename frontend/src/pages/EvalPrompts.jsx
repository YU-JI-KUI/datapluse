/**
 * AI 评测 · 提示词管理：把原先散在文件里的提示词搬到数据库，页面实时编辑，
 * 保存后下次评测即生效，无需重启。左侧按作用域分组列模板，右侧编辑 + 保存 / 重置。
 */
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Loader2, Save, RotateCcw, FileText, CheckCircle2, ArrowLeft } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { EvalBadge } from '@/components/eval/EvalPrimitives'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { evalApi } from '@/lib/api'
import { formatDate } from '@/lib/utils'

const RESP = (r) => r?.data?.data ?? {}

// 作用域展示名（与后端 t_eval_prompt.bu 约定一致）
const SCOPE_LABEL = {
  _root:       '通用（根）',
  _default:    '通用兜底',
  securities:  '证券',
  life:        '寿险',
}
const scopeName = (bu) => SCOPE_LABEL[bu] || bu

export default function EvalPrompts() {
  const [list, setList]       = useState([])
  const [active, setActive]   = useState(null)   // { bu, name }
  const [detail, setDetail]   = useState(null)   // 当前选中模板详情
  const [draft, setDraft]     = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving]   = useState(false)
  const [resetOpen, setResetOpen] = useState(false)

  // 按作用域分组，便于左侧渲染
  const grouped = useMemo(() => {
    const g = {}
    for (const it of list) (g[it.bu] ||= []).push(it)
    return g
  }, [list])

  const dirty = detail && draft !== detail.content

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

  async function openPrompt(bu, name) {
    setActive({ bu, name }); setLoading(true)
    try {
      const d = RESP(await evalApi.getPrompt(bu, name))
      setDetail(d); setDraft(d.content || '')
    } catch (e) {
      toast.error(e.response?.data?.message || '加载提示词失败')
      setDetail(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadList().then(items => { if (items[0]) openPrompt(items[0].bu, items[0].name) })
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
            编辑 AI 评测各环节的提示词，保存后<strong>下次评测即生效，无需重启</strong>。
            未编辑的模板使用代码内置的出厂默认。
          </p>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link to="/eval"><ArrowLeft className="w-4 h-4 mr-1.5" />返回评测</Link>
        </Button>
      </div>

      <div className="grid grid-cols-[300px_1fr] gap-6">
        {/* 左侧：分组列表 */}
        <Card className="h-fit">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">模板列表</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {Object.entries(grouped).map(([bu, items]) => (
              <div key={bu}>
                <div className="text-xs font-medium text-muted-foreground mb-1.5 flex items-center gap-1.5">
                  <EvalBadge tone="slate">{scopeName(bu)}</EvalBadge>
                </div>
                <div className="space-y-1">
                  {items.map(it => {
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

        {/* 右侧：编辑器 */}
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
                <textarea
                  value={draft}
                  onChange={e => setDraft(e.target.value)}
                  spellCheck={false}
                  rows={22}
                  className={[
                    'w-full rounded-md border border-input bg-background px-3 py-2',
                    'font-mono text-sm leading-relaxed resize-y',
                    'focus:outline-none focus:ring-2 focus:ring-ring',
                  ].join(' ')}
                />
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
