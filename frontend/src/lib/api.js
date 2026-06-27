import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截：自动附加 Token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截：401 跳转登录（登录页本身不跳转，否则 401 错误 toast 会因页面刷新而消失）
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && !window.location.pathname.includes('/login')) {
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      localStorage.removeItem('roles')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// ── 当前 Dataset（存 localStorage，始终为 integer）────────────────────────────

export const getCurrentDatasetId = () => {
  const v = localStorage.getItem('current_dataset_id')
  const n = v !== null ? parseInt(v, 10) : NaN
  return Number.isFinite(n) ? n : null
}

export const setCurrentDatasetId = (id) => {
  if (id !== null && id !== undefined) {
    localStorage.setItem('current_dataset_id', String(id))
  }
}

// dataset_id 为 null 时返回空响应，不发起请求
const _empty = (defaultData = null) =>
  Promise.resolve({ data: { code: 0, data: defaultData } })

// ── Auth ───────────────────────────────────────────────────────────────────────

export const authApi = {
  login: (username, password) => {
    const form = new URLSearchParams()
    form.append('username', username)
    form.append('password', password)
    return api.post('/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
  },
  me: () => api.get('/auth/me'),
  changePassword: (oldPassword, newPassword) =>
    api.post('/auth/change-password', { old_password: oldPassword, new_password: newPassword }),
}

// ── Datasets ───────────────────────────────────────────────────────────────────

export const datasetApi = {
  list:         ()           => api.get('/datasets'),
  listAll:      ()           => api.get('/datasets/all'),
  get:          (id)         => api.get(`/datasets/${id}`),
  create:       (data)       => api.post('/datasets', data),
  update:       (id, data)   => api.put(`/datasets/${id}`, data),
  delete:       (id)         => api.delete(`/datasets/${id}`),
  getUsers:     (id)         => api.get(`/datasets/${id}/users`),
  assignUsers:  (id, names)  => api.put(`/datasets/${id}/users`, { usernames: names }),
}

// ── Users ──────────────────────────────────────────────────────────────────────

export const userApi = {
  list:           (params = {}) => api.get('/users', { params }),
  create:         (data)     => api.post('/users', data),
  update:         (id, data) => api.put(`/users/${id}`, data),
  delete:         (id)       => api.delete(`/users/${id}`),
  listRoles:      ()         => api.get('/users/roles'),
  resetPassword:  (id, data) => api.post(`/users/${id}/reset-password`, data),
}

// ── Data Items (v2) ────────────────────────────────────────────────────────────

export const dataApi = {
  upload: (file, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty()
    const form = new FormData()
    form.append('file', file)
    return api.post('/data-items/upload', form, {
      params: { dataset_id: datasetId },
    })
  },
  list: (params = {}, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty({ total: 0, items: [], page: 1, page_size: 20 })
    return api.get('/data-items', {
      params: { dataset_id: datasetId, ...params },
    })
  },
  labelOptions: (datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty([])
    return api.get('/data-items/label-options', { params: { dataset_id: datasetId } })
  },
  stats: (datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty({})
    return api.get('/data-items/stats', { params: { dataset_id: datasetId } })
  },
  create: (content, sourceRef = '', datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty()
    return api.post('/data-items', { dataset_id: datasetId, content, source_ref: sourceRef })
  },
  getItem:     (id)  => api.get(`/data-items/${id}`),
  deleteItem:  (id)  => api.delete(`/data-items/${id}`),
  deleteBatch: (ids) => api.post('/data-items/batch-delete', { ids }),
}

// ── Pipeline ───────────────────────────────────────────────────────────────────

export const pipelineApi = {
  run: (datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty()
    return api.post('/pipeline/run', {}, { params: { dataset_id: datasetId } })
  },
  runStep: (step, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty()
    return api.post('/pipeline/run-step', { step, dataset_id: datasetId })
  },
  // 触发 Embed 离线任务（向量化 + 重建 FAISS 索引），与主 pipeline 解耦
  runEmbed: (datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty()
    return api.post('/pipeline/embed', {}, { params: { dataset_id: datasetId } })
  },
  // 重置 Pipeline 状态为 idle（解除卡住/错误状态）
  // resetEmbed=true 时同时清除 embed_job 状态
  resetStatus: (datasetId, resetEmbed = false) => {
    if (!datasetId) return _empty()
    return api.post('/pipeline/reset', {}, {
      params: { dataset_id: datasetId, reset_embed: resetEmbed },
    })
  },
  status: (datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty({ status: 'idle', progress: 0, detail: {} })
    return api.get('/pipeline/status', { params: { dataset_id: datasetId } })
  },
  steps: () => api.get('/pipeline/steps'),
}

// ── Annotations (v2) ──────────────────────────────────────────────────────────

export const annotationApi = {
  // 提交标注（POST /api/annotations）
  submit: (data_id, label, cot = null, category = null, keywords = null, keywords_desc = null) =>
    api.post('/annotations', {
      data_id,
      label,
      ...(cot           ? { cot }           : {}),
      ...(category      ? { category }      : {}),
      ...(keywords      ? { keywords }      : {}),
      ...(keywords_desc ? { keywords_desc } : {}),
    }),

  // 批量提交（POST /api/annotations/batch）
  batchSubmit: (annotations) =>
    api.post('/annotations/batch', annotations),

  // 获取某条数据的当前标注（GET /api/annotations?data_id=X）
  list: (data_id) =>
    api.get('/annotations', { params: { data_id } }),

  // 标注历史（GET /api/annotations/history?data_id=X）
  history: (data_id, username) =>
    api.get('/annotations/history', { params: { data_id, username } }),

  // 撤销当前用户标注（DELETE /api/annotations?data_id=X）
  revoke: (data_id) =>
    api.delete('/annotations', { params: { data_id } }),

  // 待标注队列（GET /api/annotations/queue）
  queue: (params = {}, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty({ total: 0, items: [] })
    return api.get('/annotations/queue', {
      params: { dataset_id: datasetId, ...params },
    })
  },

  // 获取下一条待标注（GET /api/annotations/next）
  next: (datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty(null)
    return api.get('/annotations/next', { params: { dataset_id: datasetId } })
  },

  // 标注工作台统一接口：全部 / 未标注 / 我的标注（含 my_annotation 字段）
  // view: 'all' | 'unannotated' | 'my_annotated'
  myItems: (params = {}, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty({ list: [], pagination: { total: 0, page: 1, page_size: 50 } })
    return api.get('/annotations/my-items', {
      params: { dataset_id: datasetId, ...params },
    })
  },

  // 已标注列表（复用 dataApi，status=annotated）
  labeled: (params = {}, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty({ total: 0, items: [] })
    return api.get('/data-items', {
      params: { dataset_id: datasetId, status: 'annotated', ...params },
    })
  },
}

// ── Conflicts (v2) ────────────────────────────────────────────────────────────

export const conflictApi = {
  list: (params = {}, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty({ list: [], pagination: { page: 1, page_size: 10, total: 0 } })
    return api.get('/conflicts', {
      params: { dataset_id: datasetId, ...params },
    })
  },
  listByDataId: (data_id) =>
    api.get('/conflicts/by-data', { params: { data_id } }),

  detect: (datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty()
    return api.post('/conflicts/detect', {}, { params: { dataset_id: datasetId } })
  },

  resolve: (conflictId, label, cot = null) =>
    api.patch(`/conflicts/${conflictId}/resolve`, { label, ...(cot ? { cot } : {}) }),

  batchResolve: (conflictIds, label, cot = null) =>
    api.post('/conflicts/batch-resolve', {
      conflict_ids: conflictIds,
      label,
      ...(cot ? { cot } : {}),
    }),

  batchRevoke: (conflictIds) =>
    api.post('/conflicts/batch-revoke', { conflict_ids: conflictIds }),

  selfCheck: (datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty()
    return api.post('/conflicts/self-check', {}, { params: { dataset_id: datasetId } })
  },
}

// ── Comments (v2) ─────────────────────────────────────────────────────────────

export const commentApi = {
  list: (data_id) =>
    api.get('/comments', { params: { data_id } }),

  add: (data_id, comment) =>
    api.post('/comments', { data_id, comment }),
}

// ── Pre-Annotations (v2) ──────────────────────────────────────────────────────

export const preAnnotationApi = {
  run: (datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty()
    return api.post('/pre-annotations/run', {}, {
      params: { dataset_id: datasetId },
    })
  },
  get: (data_id) =>
    api.get('/pre-annotations', { params: { data_id } }),
}

// ── Config ─────────────────────────────────────────────────────────────────────

export const configApi = {
  get: (datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty({})
    return api.get('/config', { params: { dataset_id: datasetId } })
  },
  update: (config, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty()
    return api.post('/config/update', { config }, { params: { dataset_id: datasetId } })
  },
  reloadModel:  () => api.post('/config/reload-model'),
  rebuildIndex: (datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty()
    return api.post('/config/rebuild-index', {}, { params: { dataset_id: datasetId } })
  },
}

// ── Export ─────────────────────────────────────────────────────────────────────

export const exportApi = {
  /**
   * 两步下载：
   *  1. POST /export/prepare → 服务端生成临时文件，返回 token
   *  2. window.location.href → 浏览器原生 GET 导航触发下载
   * 这样浏览器把下载视为用户主动导航，不会触发 Chrome "不安全下载" 拦截。
   */
  download: async (params, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return null
    const body = { ...params, dataset_id: datasetId }
    const res = await api.post('/export/prepare', body)
    const { token, filename } = res.data?.data ?? {}
    if (!token) throw new Error('导出失败：未获取到下载 token')
    // 浏览器原生导航下载（无需 Authorization header，token 即凭据）
    window.location.href = `/api/export/download/${token}`
    return filename
  },
  fields: (datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty([])
    return api.get('/export/fields', { params: { dataset_id: datasetId } })
  },
  /**
   * 冲突列表全量导出（按当前过滤参数，不限当前页）。
   * params: { format, status, conflict_type, keyword }
   */
  conflictsDownload: async (params, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return null
    const body = { ...params, dataset_id: datasetId }
    const res = await api.post('/export/conflicts/prepare', body)
    const { token, filename, count } = res.data?.data ?? {}
    if (!token) throw new Error('导出失败：未获取到下载 token')
    window.location.href = `/api/export/download/${token}`
    return { filename, count }
  },
}

// ── Templates ──────────────────────────────────────────────────────────────────

export const templateApi = {
  list: (datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty([])
    return api.get('/templates', { params: { dataset_id: datasetId } })
  },
  get:    (id)              => api.get(`/templates/${id}`),
  create: (data, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty()
    return api.post('/templates', { ...data, dataset_id: datasetId })
  },
  update: (id, data)        => api.put(`/templates/${id}`, data),
  delete: (id)              => api.delete(`/templates/${id}`),
}

// ── Categories ─────────────────────────────────────────────────────────────────

export const categoryApi = {
  list: (params = {}, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty({ list: [], pagination: { page: 1, page_size: 10, total: 0 } })
    return api.get('/categories', { params: { dataset_id: datasetId, ...params } })
  },
  create: (data, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty()
    return api.post('/categories', { ...data, dataset_id: datasetId })
  },
  update: (id, data)  => api.patch(`/categories/${id}`, data),
  delete:      (id)       => api.delete(`/categories/${id}`),
  bulkDelete:  (ids)      => api.post('/categories/bulk-delete', { ids }),
  upload: (file, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty()
    const form = new FormData()
    form.append('file', file)
    form.append('dataset_id', String(datasetId))
    return api.post('/categories/upload', form)
  },
}

// ── Admin ──────────────────────────────────────────────────────────────────────

export const adminApi = {
  executeSQL: (sql) => api.post('/admin/execute-sql', { sql }),
}

// ── Dashboard ──────────────────────────────────────────────────────────────────

export const dashboardApi = {
  // 每个标注员的今日 / 本周 / 本月工作量；不传 dataset_id = 跨数据集汇总
  annotatorStats: (datasetId) =>
    api.get('/dashboard/annotator-stats',
      datasetId != null ? { params: { dataset_id: datasetId } } : {}),
}

// ── AI 评测 ─────────────────────────────────────────────────────────────────────

// 导出文件需带 token（FileResponse 走 <a href> 时拦截器不生效），用 fetch+blob 触发下载
async function _downloadWithToken(path, fallbackName) {
  const token = localStorage.getItem('token')
  const res = await fetch(`/api${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error(`下载失败（${res.status}）`)
  const blob = await res.blob()
  const disposition = res.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)/i)
  const name = match ? decodeURIComponent(match[1]) : fallbackName
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export const evalApi = {
  // 配置 / BU / 意图（meta）
  config:  ()   => api.get('/eval/meta/config'),
  bus:     ()   => api.get('/eval/meta/bus'),
  intents: (bu) => api.get('/eval/meta/intents', { params: { bu } }),

  // 上传 Excel 起评测（仅存文件 + 建任务，立即返回 task_id）
  upload: (file, bu = 'securities', onProgress) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/eval/upload', form, { params: { bu }, onUploadProgress: onProgress })
  },
  // 用内置样例起评测（kind: calib | prod）
  runSample: (bu = 'securities', kind = 'calib') =>
    api.get('/eval/sample', { params: { bu, kind } }),

  // 任务列表 / 状态 / 结果 / 续跑
  listTasks: (page = 1, pageSize = 50) =>
    api.get('/eval/tasks', { params: { page, page_size: pageSize } }),
  getTask:   (taskId) => api.get(`/eval/tasks/${taskId}`),
  getResult: (taskId) => api.get(`/eval/tasks/${taskId}/result`),
  // 逐条明细分页（百万级下不再随 result 返回全量 rows）。flag: all | review
  getRows:   (taskId, page = 1, pageSize = 20, flag = 'all') =>
    api.get(`/eval/tasks/${taskId}/rows`, { params: { page, page_size: pageSize, flag } }),
  resume:    (taskId) => api.post(`/eval/tasks/${taskId}/resume`),

  // 三种导出（带 token 的 blob 下载）
  exportDisagreements: (taskId) =>
    _downloadWithToken(`/eval/tasks/${taskId}/export`, `不一致case_${taskId}.xlsx`),
  exportRows: (taskId) =>
    _downloadWithToken(`/eval/tasks/${taskId}/export/rows`, `评测明细_${taskId}.xlsx`),
  exportReport: (taskId) =>
    _downloadWithToken(`/eval/tasks/${taskId}/export/report`, `评估报告_${taskId}.xlsx`),

  // 提示词管理（页面实时编辑，改后不重启即生效）
  listPrompts: () => api.get('/eval/prompts'),
  getPrompt:   (bu, name) => api.get(`/eval/prompts/${bu}/${encodeURIComponent(name)}`),
  savePrompt:  (bu, name, content) =>
    api.put(`/eval/prompts/${bu}/${encodeURIComponent(name)}`, { content }),
  resetPrompt: (bu, name) =>
    api.post(`/eval/prompts/${bu}/${encodeURIComponent(name)}/reset`),
}

export default api
