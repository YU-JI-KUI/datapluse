/**
 * SearchBar — 统一搜索栏组件
 *
 * 规范：
 *   - 所有带列表/表格的页面必须使用此组件作为搜索区域
 *   - 统一支持三类过滤字段：关键字 / 状态 / 更新时间范围
 *   - 按 Enter 或点击「搜索」按钮触发；点击「重置」清空所有条件
 *   - statusOptions 为空时不渲染状态下拉框
 *
 * 用法示例：
 *   <SearchBar
 *     placeholder="搜索文本内容..."
 *     statusOptions={[{ value: 'raw', label: '原始' }, { value: 'annotated', label: '已标注' }]}
 *     onSearch={({ keyword, status, start_date, end_date }) => { setKeyword(keyword); ... setPage(1) }}
 *   />
 */

import { useState } from 'react'
import { Search, RotateCcw } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

/**
 * @param {object}     props
 * @param {function}   props.onSearch        ({ keyword, status, start_date, end_date }) => void
 * @param {Array}      [props.statusOptions] [{ value: string, label: string }]
 * @param {string}     [props.placeholder]   关键字输入框占位符
 * @param {string}     [props.className]     额外样式
 */
export default function SearchBar({
  onSearch,
  statusOptions,
  placeholder = '搜索关键字…',
  className = '',
}) {
  const [keyword,   setKeyword]   = useState('')
  const [status,    setStatus]    = useState('all')
  const [startDate, setStartDate] = useState('')
  const [endDate,   setEndDate]   = useState('')

  function buildParams() {
    return {
      keyword:    keyword.trim() || undefined,
      status:     status === 'all' ? undefined : status,
      start_date: startDate || undefined,
      end_date:   endDate   || undefined,
    }
  }

  function handleSearch() {
    onSearch(buildParams())
  }

  function handleReset() {
    setKeyword('')
    setStatus('all')
    setStartDate('')
    setEndDate('')
    onSearch({})
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') handleSearch()
  }

  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      {/* 关键字 */}
      <div className="relative min-w-44 flex-1">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
        <Input
          value={keyword}
          onChange={e => setKeyword(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="pl-8 h-8 text-sm"
        />
      </div>

      {/* 状态 */}
      {statusOptions && statusOptions.length > 0 && (
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="h-8 w-32 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            {statusOptions.map(opt => (
              <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {/* 更新时间范围 */}
      <div className="flex items-center gap-1">
        <Input
          type="date"
          value={startDate}
          onChange={e => setStartDate(e.target.value)}
          className="h-8 w-34 text-sm"
          title="更新时间（起）"
        />
        <span className="text-gray-400 text-xs select-none">—</span>
        <Input
          type="date"
          value={endDate}
          onChange={e => setEndDate(e.target.value)}
          className="h-8 w-34 text-sm"
          title="更新时间（止）"
        />
      </div>

      {/* 按钮 */}
      <Button size="sm" className="h-8 px-3 text-sm" onClick={handleSearch}>
        搜索
      </Button>
      <Button size="sm" variant="outline" className="h-8 px-2 text-sm" onClick={handleReset} title="重置">
        <RotateCcw className="w-3.5 h-3.5" />
      </Button>
    </div>
  )
}
