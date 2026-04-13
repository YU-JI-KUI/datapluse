/**
 * TablePagination — 统一分页组件
 *
 * 规范：
 *   - 默认 pageSize = 10
 *   - 支持切换每页条数：10 / 25 / 50 / 100
 *   - 固定放置在列表/表格容器的右下角
 *   - 始终显示（即使只有 1 页），方便用户切换每页条数
 */

import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
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

  return (
    <div className={`flex items-center justify-end gap-3 px-4 py-3 border-t ${className}`}>
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
            onPageChange(1)   // 切换每页条数时回到第 1 页
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

      {/* 翻页按钮 */}
      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          className="h-7 px-2"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft className="w-3.5 h-3.5" />
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-7 px-2"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </Button>
      </div>
    </div>
  )
}
