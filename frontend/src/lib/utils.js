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

export function getStatusColor(status) {
  const map = {
    raw: 'bg-gray-100 text-gray-700',
    processed: 'bg-blue-100 text-blue-700',
    pre_annotated: 'bg-purple-100 text-purple-700',
    labeling: 'bg-yellow-100 text-yellow-700',
    labeled: 'bg-orange-100 text-orange-700',
    checked: 'bg-green-100 text-green-700',
    exported: 'bg-teal-100 text-teal-700',
  }
  return map[status] || 'bg-gray-100 text-gray-700'
}

export function getStatusLabel(status) {
  const map = {
    raw: '原始',
    processed: '已清洗',
    pre_annotated: '已预标注',
    labeling: '标注中',
    labeled: '已标注',
    checked: '已检测',
    exported: '已导出',
  }
  return map[status] || status
}
