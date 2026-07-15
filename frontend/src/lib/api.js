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

// ── 统一文件下载 ─────────────────────────────────────────────────────────────
//
// 全站唯一的下载实现。用 axios(responseType:blob) 拉取 → 同域 blob URL + <a download>
// 触发保存。相比 window.location.href 整页导航到无扩展名 URL（会被 Chrome Safe
// Browsing 判为可疑、弹「保留/放弃」不安全提示），blob + 明确文件名 + 用户手势是浏览器
// 最信任的方式，不会触发警告；且复用 axios 拦截器自动带 token、走同域相对路径 /api。
//
// url         相对 /api 的路径（如 `/export/download/${token}`），或已生成好文件的 GET 端点
// fallbackName 服务端未给 Content-Disposition 时用的文件名
async function downloadFile(url, fallbackName = 'download') {
  // 下载是长操作（大文件生成/传输），放宽超时到 5 分钟，不受常规 API 30s 限制
  const res = await api.get(url, { responseType: 'blob', timeout: 300000 })
  const disposition = res.headers['content-disposition'] || ''
  const match = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)/i)
  const name = match ? decodeURIComponent(match[1]) : fallbackName

  const blobUrl = URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(blobUrl)
  return name
}

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

// ── 当前 BU（AI 评测模块全局上下文，存 localStorage，字符串 code）──────────────

export const getCurrentBu = () => localStorage.getItem('current_bu') || 'securities'

export const setCurrentBu = (code) => {
  if (code) localStorage.setItem('current_bu', code)
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
  listAll:        ()         => api.get('/users/all'),   // 全量不分页，供分配用户下拉（避免新用户被分页截断）
  create:         (data)     => api.post('/users', data),
  update:         (id, data) => api.put(`/users/${id}`, data),
  delete:         (id)       => api.delete(`/users/${id}`),
  listRoles:      ()         => api.get('/users/roles'),
  resetPassword:  (id, data) => api.post(`/users/${id}/reset-password`, data),
}

// ── Roles & Permissions ─────────────────────────────────────────────────────────

export const roleApi = {
  listPermissions:       ()                  => api.get('/permissions'),
  listRoles:             ()                  => api.get('/roles'),
  updatePermissions:     (name, permissions) => api.put(`/roles/${name}/permissions`, { permissions }),
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
  deleteBySource: (datasetId, sourceRef) =>
    api.post('/data-items/delete-by-source', { dataset_id: datasetId, source_ref: sourceRef }),
  listSources: (datasetId) =>
    api.get('/data-items/sources', { params: { dataset_id: datasetId } }),
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
   *  2. downloadFile → blob + <a download> 触发保存（全站统一实现）
   */
  download: async (params, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return null
    const body = { ...params, dataset_id: datasetId }
    const res = await api.post('/export/prepare', body)
    const { token, filename } = res.data?.data ?? {}
    if (!token) throw new Error('导出失败：未获取到下载 token')
    return downloadFile(`/export/download/${token}`, filename)
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
    await downloadFile(`/export/download/${token}`, filename)
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

export const evalApi = {
  // 配置 / BU / 意图（meta）
  config:  ()   => api.get('/eval/meta/config'),
  bus:     ()   => api.get('/eval/meta/bus'),
  intents: (bu = getCurrentBu()) => api.get('/eval/meta/intents', { params: { bu } }),

  // 上传 Excel 起评测（仅存文件 + 建任务，立即返回 task_id）。bu 默认当前全局 BU。
  // 大文件（如 90M+）传输耗时远超全局 30s 超时，这里单独放开 timeout=0（不超时），
  // 否则会「后端已存成功、前端却因超时误报失败」。onProgress 上报上传进度。
  upload: (file, bu = getCurrentBu(), onProgress) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/eval/upload', form, {
      params: { bu }, onUploadProgress: onProgress, timeout: 0,
    })
  },
  // 用内置样例起评测（kind: calib | prod）
  runSample: (bu = getCurrentBu(), kind = 'calib') =>
    api.get('/eval/sample', { params: { bu, kind } }),

  // 业务分类管理（按 BU 增删改查）
  listCategories:  (bu = getCurrentBu()) => api.get('/eval/categories', { params: { bu } }),
  createCategory:  (data, bu = getCurrentBu()) => api.post('/eval/categories', data, { params: { bu } }),
  updateCategory:  (id, data) => api.put(`/eval/categories/${id}`, data),
  deleteCategory:  (id) => api.delete(`/eval/categories/${id}`),

  // 活动标问管理（写死按钮触发的写死回复，评测时整条跳过、不计指标）。按 BU 增删改查
  listActivityQuestions:  (bu = getCurrentBu()) => api.get('/eval/activity-questions', { params: { bu } }),
  createActivityQuestion: (data, bu = getCurrentBu()) => api.post('/eval/activity-questions', data, { params: { bu } }),  // data.questions 传数组即批量
  updateActivityQuestion: (id, data) => api.put(`/eval/activity-questions/${id}`, data),
  deleteActivityQuestion: (id) => api.delete(`/eval/activity-questions/${id}`),

  // 规则短路管理（命中写死结果、免 LLM 调用，计入指标）。按 BU 增删查
  listRules:  (bu = getCurrentBu()) => api.get('/eval/rules', { params: { bu } }),
  upsertRule: (data, bu = getCurrentBu()) => api.post('/eval/rules', data, { params: { bu } }),
  deleteRule: (id) => api.delete(`/eval/rules/${id}`),

  // 任务列表 / 状态 / 结果 / 续跑。bu 默认当前全局 BU（传空字符串可查全部）
  listTasks: (page = 1, pageSize = 50, { keyword = '', mode = '' } = {}, bu = getCurrentBu()) =>
    api.get('/eval/tasks', { params: { page, page_size: pageSize, bu, keyword, mode } }),
  getTask:   (taskId) => api.get(`/eval/tasks/${taskId}`),
  getResult: (taskId) => api.get(`/eval/tasks/${taskId}/result`),
  // 逐条明细分页（百万级下不再随 result 返回全量 rows）。flag: all | review
  // q=客户问题关键字，intent=业务分类（仅 flag=all 生效）
  getRows:   (taskId, page = 1, pageSize = 20, flag = 'all', q = '', intent = '', extra = {}) =>
    api.get(`/eval/tasks/${taskId}/rows`, { params: {
      page, page_size: pageSize, flag, q, intent,
      dispatched_bu: extra.dispatched_bu || '',
      j_dispatch: extra.j_dispatch || '',
      j_resolved: extra.j_resolved || '',
    } }),
  pause:     (taskId) => api.post(`/eval/tasks/${taskId}/pause`),
  resume:    (taskId) => api.post(`/eval/tasks/${taskId}/resume`),
  rerun:     (taskId) => api.post(`/eval/tasks/${taskId}/rerun`),
  remove:    (taskId) => api.delete(`/eval/tasks/${taskId}`),

  // 人工复核：提交/撤销某条明细的复核覆盖（指标按最终值重算，重进结果页生效）
  submitReview: (taskId, rowIndex, data) =>
    api.put(`/eval/tasks/${taskId}/rows/${rowIndex}/review`, data),
  deleteReview: (taskId, rowIndex) =>
    api.delete(`/eval/tasks/${taskId}/rows/${rowIndex}/review`),
  // 单条试跑：用当前提示词重评这一条，返回新旧对比，不落库。
  // businessKnowledge 传入则用这段临时业务知识试跑（详情页改后未保存即可验证）
  dryrunRow: (taskId, rowIndex, businessKnowledge) =>
    api.post(`/eval/tasks/${taskId}/rows/${rowIndex}/dryrun`,
      businessKnowledge != null ? { business_knowledge: businessKnowledge } : {}),
  // 子集重跑：用最新提示词对某筛选子集重评、覆盖、全量重算指标（同步，上限 50 条）
  rerunSubset: (taskId, flag = 'review') =>
    api.post(`/eval/tasks/${taskId}/rerun-subset`, {}, { params: { flag } }),
  // 异步重跑用户勾选的明细行(任意视图),立即返回,轮询任务状态看进度
  rerunRows: (taskId, rowIndices) =>
    api.post(`/eval/tasks/${taskId}/rerun-rows`, { row_indices: rowIndices }),
  // 只重算优化建议:不重 judge、复用已落盘 rows,用最新提示词秒级出新建议
  // cardIds 非空 = 只重生这些卡（按卡单独重生）；空 = 全量
  rerunAdvice: (taskId, cardIds) =>
    api.post(`/eval/tasks/${taskId}/rerun-advice`, cardIds ? { card_ids: cardIds } : {}),
  // 查看某张建议卡真实喂给模型的完整 prompt（system+user，含填满的 payload）
  getAdvicePrompt: (taskId, cardId) =>
    api.get(`/eval/tasks/${taskId}/advice-prompt`, { params: { card_id: cardId } }),

  // 三种导出（统一 blob 下载）
  // 文件名以后端 Content-Disposition 为准（含原始上传文件名前缀）；下方 fallback 仅在
  // 响应头缺失时兜底。
  exportDisagreements: (taskId) =>
    downloadFile(`/eval/tasks/${taskId}/export`, `不一致case_${taskId}.xlsx`),
  exportRows: (taskId) =>
    downloadFile(`/eval/tasks/${taskId}/export/rows`, `评测明细_${taskId}.xlsx`),
  exportReport: (taskId) =>
    downloadFile(`/eval/tasks/${taskId}/export/report`, `评估报告_${taskId}.xlsx`),

  // 提示词管理（按 BU 列全部模板槽位，改后不重启即生效）
  listPrompts: (bu = getCurrentBu()) => api.get('/eval/prompts', { params: { bu } }),
  getPrompt:   (bu, name) => api.get(`/eval/prompts/${bu}/${encodeURIComponent(name)}`),
  savePrompt:  (bu, name, content) =>
    api.put(`/eval/prompts/${bu}/${encodeURIComponent(name)}`, { content }),
  resetPrompt: (bu, name) =>
    api.post(`/eval/prompts/${bu}/${encodeURIComponent(name)}/reset`),

  // 问题洞察：高频问 + 每日频率（intent/start/end 可选筛选）；关键词提炼（纯展示）
  insightsQuestions: (bu = getCurrentBu(), { intent = '', start = '', end = '' } = {}) =>
    api.get('/eval/insights/questions', { params: { bu, intent, start, end } }),
  insightsKeywords: (bu = getCurrentBu(), intent = '') =>
    api.get('/eval/insights/keywords', { params: { bu, intent } }),
}

export default api
