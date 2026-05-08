/**
 * AdminSQL — 管理员 SQL 执行工具
 * 仅 admin 角色可见，用于数据修复和临时数据操作。
 */

import { useState, useRef } from 'react'
import { toast } from 'sonner'
import { Play, Loader2, Copy, Trash2, Clock, AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { adminApi } from '@/lib/api'

// ── 预设常用查询 ───────────────────────────────────────────────────────────────

const PRESETS = [
  {
    label: '查看各数据集数据量',
    sql: `SELECT d.id, d.name, COUNT(i.id) AS total,
  SUM(CASE WHEN i.status = 'annotated' THEN 1 ELSE 0 END) AS annotated,
  SUM(CASE WHEN i.status = 'pre_annotated' THEN 1 ELSE 0 END) AS pre_annotated
FROM t_dataset d
LEFT JOIN t_data_item i ON i.dataset_id = d.id
GROUP BY d.id, d.name
ORDER BY d.id;`,
  },
  {
    label: '查看最近 20 条标注',
    sql: `SELECT a.id, a.data_id, a.username, a.label, a.category, a.keywords, a.is_active, a.created_at
FROM t_annotation a
ORDER BY a.created_at DESC
LIMIT 20;`,
  },
  {
    label: '查看标注结果汇总',
    sql: `SELECT ar.data_id, ar.final_label, ar.label_source, ar.annotator_count, ar.resolver, ar.updated_at
FROM t_annotation_result ar
ORDER BY ar.updated_at DESC
LIMIT 50;`,
  },
  {
    label: '数据状态分布',
    sql: `SELECT dataset_id, status, COUNT(*) AS cnt
FROM t_data_item
GROUP BY dataset_id, status
ORDER BY dataset_id, status;`,
  },
  {
    label: '查看业务分类',
    sql: `SELECT c.id, c.dataset_id, c.name, c.description
FROM t_category c
ORDER BY c.dataset_id, c.id;`,
  },
]

// ── 结果表格 ───────────────────────────────────────────────────────────────────

function ResultTable({ columns, rows, message }) {
  if (columns.length === 0) {
    return (
      <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-4 py-3">
        <Play className="w-4 h-4" />
        {message}
      </div>
    )
  }
  return (
    <div>
      <p className="text-xs text-muted-foreground mb-2">{message}</p>
      <div className="border rounded-lg overflow-auto max-h-[480px]">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map(col => (
                <TableHead key={col} className="whitespace-nowrap text-xs font-semibold bg-gray-50 sticky top-0">
                  {col}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, ri) => (
              <TableRow key={ri}>
                {row.map((cell, ci) => (
                  <TableCell
                    key={ci}
                    className="text-xs whitespace-nowrap max-w-[320px] truncate"
                    title={cell != null ? String(cell) : ''}
                  >
                    {cell == null
                      ? <span className="text-muted-foreground italic">NULL</span>
                      : String(cell)
                    }
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

export default function AdminSQL() {
  const [sql, setSql]           = useState('')
  const [result, setResult]     = useState(null)
  const [error, setError]       = useState(null)
  const [loading, setLoading]   = useState(false)
  const [elapsed, setElapsed]   = useState(null)
  const [presetsOpen, setPresetsOpen] = useState(false)
  const textareaRef = useRef()

  async function handleExecute() {
    if (!sql.trim()) { toast.error('请输入 SQL'); return }
    setLoading(true)
    setResult(null)
    setError(null)
    const t0 = Date.now()
    try {
      const res = await adminApi.executeSQL(sql.trim())
      setElapsed(Date.now() - t0)
      setResult(res.data?.data)
      toast.success(res.data?.data?.message || '执行成功')
    } catch (err) {
      setElapsed(Date.now() - t0)
      const detail = err.response?.data?.detail || err.message || '执行失败'
      setError(detail)
      toast.error('执行失败')
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    // Ctrl/Cmd + Enter 执行
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      handleExecute()
    }
    // Tab 插入两个空格
    if (e.key === 'Tab') {
      e.preventDefault()
      const el = textareaRef.current
      const start = el.selectionStart
      const end   = el.selectionEnd
      const newVal = sql.substring(0, start) + '  ' + sql.substring(end)
      setSql(newVal)
      requestAnimationFrame(() => {
        el.selectionStart = el.selectionEnd = start + 2
      })
    }
  }

  function copySQL() {
    navigator.clipboard.writeText(sql)
    toast.success('已复制到剪贴板')
  }

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            SQL 执行工具
            <span className="text-xs font-normal bg-red-100 text-red-700 border border-red-200 rounded px-2 py-0.5">
              Admin Only
            </span>
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            执行任意 SQL，用于数据修复和临时数据操作。<span className="text-orange-600 font-medium">DML 操作将立即提交，请谨慎执行。</span>
          </p>
        </div>
      </div>

      {/* 预设查询 */}
      <Card>
        <CardHeader
          className="py-3 px-4 cursor-pointer select-none"
          onClick={() => setPresetsOpen(v => !v)}
        >
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            {presetsOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            常用查询模板
          </CardTitle>
        </CardHeader>
        {presetsOpen && (
          <CardContent className="pt-0 px-4 pb-3">
            <div className="flex flex-wrap gap-2">
              {PRESETS.map((p, i) => (
                <button
                  key={i}
                  onClick={() => setSql(p.sql)}
                  className="text-xs px-3 py-1.5 rounded-lg border bg-muted/50 hover:bg-muted transition-colors text-left"
                >
                  {p.label}
                </button>
              ))}
            </div>
          </CardContent>
        )}
      </Card>

      {/* SQL 编辑器 */}
      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-muted-foreground font-medium">SQL 编辑器</span>
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-muted-foreground">Ctrl+Enter 执行 · Tab 缩进</span>
              <button onClick={copySQL} className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors" title="复制 SQL">
                <Copy className="w-3.5 h-3.5" />
              </button>
              <button onClick={() => { setSql(''); setResult(null); setError(null) }} className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors" title="清空">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
          <textarea
            ref={textareaRef}
            value={sql}
            onChange={e => setSql(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="-- 输入 SQL，支持 SELECT / INSERT / UPDATE / DELETE&#10;-- 示例：SELECT * FROM t_dataset LIMIT 10;"
            rows={12}
            spellCheck={false}
            className="w-full font-mono text-sm border rounded-lg px-4 py-3 resize-y focus:outline-none focus:ring-2 focus:ring-blue-200 border-gray-200 bg-gray-950 text-green-300 placeholder:text-gray-600 leading-relaxed"
          />
          <div className="flex items-center justify-between">
            {elapsed != null && (
              <span className="text-xs text-muted-foreground flex items-center gap-1">
                <Clock className="w-3 h-3" />{elapsed} ms
              </span>
            )}
            <div className="ml-auto">
              <Button onClick={handleExecute} disabled={loading || !sql.trim()}>
                {loading
                  ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />执行中…</>
                  : <><Play className="w-4 h-4 mr-2" />执 行</>
                }
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 错误信息 */}
      {error && (
        <div className="flex items-start gap-3 border border-red-200 bg-red-50 rounded-lg px-4 py-3">
          <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-red-700 mb-1">执行错误</p>
            <pre className="text-xs text-red-600 whitespace-pre-wrap font-mono">{error}</pre>
          </div>
        </div>
      )}

      {/* 查询结果 */}
      {result && (
        <Card>
          <CardHeader className="py-3 px-4">
            <CardTitle className="text-sm font-medium">执行结果</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 pt-0">
            <ResultTable
              columns={result.columns}
              rows={result.rows}
              message={result.message}
            />
          </CardContent>
        </Card>
      )}
    </div>
  )
}
