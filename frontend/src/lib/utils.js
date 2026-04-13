import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs) {
  return twMerge(clsx(inputs))
}

export function formatDate(iso) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

export function formatBytes(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

// v2 status names: raw → cleaned → pre_annotated → annotated → checked
export function getStatusColor(status) {
  const map = {
    raw:           'bg-gray-100 text-gray-700',
    cleaned:       'bg-blue-100 text-blue-700',
    pre_annotated: 'bg-purple-100 text-purple-700',
    annotated:     'bg-orange-100 text-orange-700',
    checked:       'bg-green-100 text-green-700',
    exported:      'bg-teal-100 text-teal-700',
  }
  return map[status] || 'bg-gray-100 text-gray-700'
}

export function getStatusLabel(status) {
  const map = {
    raw:           '原始',
    cleaned:       '已清洗',
    pre_annotated: '已预标注',
    annotated:     '已标注',
    checked:       '已检测',
    exported:      '已导出',
  }
  return map[status] || status
}

// 从 v2 数据项中提取最终标注标签
// 优先使用 item.label（来自 t_annotation_result.final_label，后端 _enrich 写入）
// 退化兼容：若旧接口未返回 label 字段，则从 annotations 数组找第一个有效标注
export function getActiveLabel(item) {
  if (!item) return null
  if (item.label != null) return item.label          // t_annotation_result.final_label（多数投票或裁决）
  const anns = item.annotations || []
  return anns.find(a => a.is_active)?.label ?? null  // 兜底兼容
}

// 从 v2 数据项中提取预标注标签
export function getPreLabel(item) {
  if (!item) return null
  const pre = item.pre_annotation
  return pre?.label ?? null
}

export function getPreScore(item) {
  if (!item) return null
  const pre = item.pre_annotation
  return pre?.score ?? null
}

// 分数颜色（置信度）
export function scoreColor(score) {
  if (score == null) return 'text-muted-foreground'
  if (score >= 0.9) return 'text-green-600'
  if (score >= 0.7) return 'text-orange-500'
  return 'text-red-500'
}
