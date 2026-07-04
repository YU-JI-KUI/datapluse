/**
 * AI 评测 · 业务分类管理：按当前 BU 增删改查业务分类与定义。
 * 评测时模型据这些分类与定义对每条客户问题打标，故改后下次评测即生效。
 * 当前 BU 由左侧全局选择器决定，本页监听 buChanged 自动刷新。
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Loader2, Plus, Pencil, Trash2 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import TablePagination from '@/components/TablePagination'
import { evalApi, getCurrentBu } from '@/lib/api'
import { formatDate, scopeName } from '@/lib/utils'

const RESP = (r) => r?.data?.data ?? {}

export default function EvalCategories() {
  const [bu, setBu]           = useState(getCurrentBu())
  const [list, setList]       = useState([])
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(null)   // { id?, name, definition } 编辑/新增中的对象
  const [delTarget, setDelTarget] = useState(null)
  const [saving, setSaving]   = useState(false)
  const [page, setPage]         = useState(1)    // 前端本地分页：全量加载后内存切片
  const [pageSize, setPageSize] = useState(10)

  // 全量数据的当前页切片
  const pageList = list.slice((page - 1) * pageSize, page * pageSize)

  function load() {
    setLoading(true)
    evalApi.listCategories()
      .then(res => { setList(RESP(res).categories || []); setPage(1) })
      .catch(e => toast.error(e.response?.data?.message || '加载业务分类失败'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    // 全局 BU 切换时刷新本页
    const onBuChange = (e) => { setBu(e.detail?.bu || getCurrentBu()); load() }
    window.addEventListener('buChanged', onBuChange)
    return () => window.removeEventListener('buChanged', onBuChange)
  }, [])

  async function handleSave() {
    if (!editing?.name?.trim()) { toast.error('分类名不能为空'); return }
    setSaving(true)
    try {
      const payload = { name: editing.name.trim(), definition: editing.definition || '' }
      if (editing.id) await evalApi.updateCategory(editing.id, payload)
      else await evalApi.createCategory(payload)
      toast.success(editing.id ? '已更新' : '已新增')
      setEditing(null)
      load()
    } catch (e) {
      toast.error(e.response?.data?.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!delTarget) return
    try {
      await evalApi.deleteCategory(delTarget.id)
      toast.success('已删除')
      load()
    } catch (e) {
      toast.error(e.response?.data?.message || '删除失败')
    }
  }

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">业务分类管理</h1>
          <p className="text-muted-foreground text-sm mt-1">
            维护当前业务单元（<span className="font-medium">{scopeName(bu)}</span>）的业务分类与定义；
            评测时模型据此对每条问题打标，改后下次评测即生效。
          </p>
        </div>
        <Button size="sm" onClick={() => setEditing({ name: '', definition: '' })}>
          <Plus className="w-4 h-4 mr-1.5" />新增分类
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-48">业务分类</TableHead>
                <TableHead>定义</TableHead>
                <TableHead className="w-28">修改人</TableHead>
                <TableHead className="w-40 whitespace-nowrap">更新时间</TableHead>
                <TableHead className="w-20 text-center">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-10 text-muted-foreground">
                    <Loader2 className="w-5 h-5 animate-spin inline mr-2" />加载中…
                  </TableCell>
                </TableRow>
              ) : list.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-10 text-muted-foreground">
                    当前 BU 暂无业务分类，点右上角「新增分类」开始维护。
                  </TableCell>
                </TableRow>
              ) : pageList.map(c => (
                <TableRow key={c.id}>
                  <TableCell className="font-medium">{c.name}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{c.definition}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{c.updated_by || '—'}</TableCell>
                  <TableCell className="text-xs text-muted-foreground whitespace-nowrap">{formatDate(c.updated_at)}</TableCell>
                  <TableCell>
                    <div className="flex items-center justify-center gap-1">
                      <button title="编辑" onClick={() => setEditing({ ...c })} className="p-1.5 rounded hover:bg-accent">
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button title="删除" onClick={() => setDelTarget(c)} className="p-1.5 rounded hover:bg-red-50 text-red-500">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePagination
            page={page}
            pageSize={pageSize}
            total={list.length}
            onPageChange={setPage}
            onSizeChange={size => { setPageSize(size); setPage(1) }}
          />
        </CardContent>
      </Card>

      {/* 新增/编辑对话框 */}
      <Dialog open={!!editing} onOpenChange={v => { if (!v) setEditing(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing?.id ? '编辑业务分类' : '新增业务分类'}</DialogTitle>
          </DialogHeader>
          {editing && (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">分类名</label>
                <Input
                  value={editing.name}
                  onChange={e => setEditing({ ...editing, name: e.target.value })}
                  placeholder="如：资产查询"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">定义（含正例反例，喂给模型判定）</label>
                <textarea
                  value={editing.definition}
                  onChange={e => setEditing({ ...editing, definition: e.target.value })}
                  rows={8}
                  placeholder="描述该分类的判据，最好含正例与反例…"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="secondary" size="sm" onClick={() => setEditing(null)}>取消</Button>
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving && <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />}保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!delTarget}
        onOpenChange={v => { if (!v) setDelTarget(null) }}
        title="删除业务分类"
        description={`将删除分类「${delTarget?.name || ''}」，评测时不再使用该分类。`}
        confirmLabel="删除"
        onConfirm={handleDelete}
      />
    </div>
  )
}
