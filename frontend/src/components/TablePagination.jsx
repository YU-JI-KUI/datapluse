/**
 * TablePagination — 统一分页组件
 *
 * 规范：
 *   - 默认 pageSize = 10
 *   - 支持切换每页条数：10 / 25 / 50 / 100
 *   - 固定放置在列表/表格容器的右下角
 *   - 始终显示（即使只有 1 页），方便用户切换每页条数
 *   - 支持首页/尾页跳转、页码直接输入
 */

import { useState } from 'react'
import { ChevronsLeft, ChevronLeft, ChevronRight, ChevronsRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const PAGE_SIZE_OPTIONS = ['10', '25', '50', '100']

/**
 * @param {object}   props
 * @param {number}   props.page         当前页（1-based）
 * @param {number}   props.pageSize     每页条数
 * @param {number}   props.total        总条数
 * @param {function} props.onPageChange (newPage: number) => void
 * @param {function} props.onSizeChange (newSize: number) => void
 * @param {string}   [props.className]  额外样式
 */
export default function TablePagination({
  page,
  pageSize,
  total,
  onPageChange,
  onSizeChange,
  className = '',
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const [inputVal, setInputVal] = useState('')

  function jumpToPage() {
    const n = parseInt(inputVal, 10)
    if (!isNaN(n) && n >= 1 && n <= totalPages) {
      onPageChange(n)
    }
    setInputVal('')
  }

  function handleInputKeyDown(e) {
    if (e.key === 'Enter') jumpToPage()
  }

  return (
    <div className={`flex items-center justify-end gap-2 px-4 py-3 border-t flex-wrap ${className}`}>
      {/* 总条数 */}
      <span className="text-xs text-muted-foreground mr-1">
        共 {total} 条
      </span>

      {/* 每页条数选择 */}
      <div className="flex items-center gap-1.5">
        <span className="text-xs text-muted-foreground whitespace-nowrap">每页</span>
        <Select
          value={String(pageSize)}
          onValueChange={v => {
            onSizeChange(Number(v))
            onPageChange(1)
          }}
        >
          <SelectTrigger className="h-7 w-[70px] text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PAGE_SIZE_OPTIONS.map(opt => (
              <SelectItem key={opt} value={opt} className="text-xs">
                {opt} 条
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* 页码信息 */}
      <span className="text-xs text-muted-foreground whitespace-nowrap">
        {page} / {totalPages} 页
      </span>

      {/* 翻页按钮组 */}
      <div className="flex items-center gap-1">
        {/* 首页 */}
        <Button
          variant="outline"
          size="sm"
          className="h-7 px-2"
          disabled={page <= 1}
          onClick={() => onPageChange(1)}
          title="第一页"
        >
          <ChevronsLeft className="w-3.5 h-3.5" />
        </Button>
        {/* 上一页 */}
        <Button
          variant="outline"
          size="sm"
          className="h-7 px-2"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          title="上一页"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
        </Button>
        {/* 下一页 */}
        <Button
          variant="outline"
          size="sm"
          className="h-7 px-2"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          title="下一页"
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </Button>
        {/* 尾页 */}
        <Button
          variant="outline"
          size="sm"
          className="h-7 px-2"
          disabled={page >= totalPages}
          onClick={() => onPageChange(totalPages)}
          title="最后一页"
        >
          <ChevronsRight className="w-3.5 h-3.5" />
        </Button>
      </div>

      {/* 页码跳转 */}
      <div className="flex items-center gap-1">
        <span className="text-xs text-muted-foreground whitespace-nowrap">跳转</span>
        <Input
          className="h-7 w-14 text-xs text-center px-1"
          value={inputVal}
          onChange={e => setInputVal(e.target.value)}
          onKeyDown={handleInputKeyDown}
          onBlur={jumpToPage}
          placeholder={String(page)}
        />
        <span className="text-xs text-muted-foreground whitespace-nowrap">页</span>
      </div>
    </div>
  )
}
