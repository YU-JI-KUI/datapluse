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
  status: (datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty({ status: 'idle', progress: 0, detail: {} })
    return api.get('/pipeline/status', { params: { dataset_id: datasetId } })
  },
  steps: () => api.get('/pipeline/steps'),
}

// ── Annotations (v2) ──────────────────────────────────────────────────────────

export const annotationApi = {
  // 提交标注（POST /api/annotations）
  submit: (data_id, label, cot = null) =>
    api.post('/annotations', { data_id, label, ...(cot ? { cot } : {}) }),

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
    if (!datasetId) return _empty([])
    return api.get('/conflicts', {
      params: { dataset_id: datasetId, ...params },
    })
  },
  listByDataId: (data_id) =>
    api.get('/conflicts', { params: { data_id } }),

  detect: (datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty()
    return api.post('/conflicts/detect', {}, { params: { dataset_id: datasetId } })
  },

  resolve: (conflictId, label, cot = null) =>
    api.patch(`/conflicts/${conflictId}/resolve`, { label, ...(cot ? { cot } : {}) }),
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
  rebuildIndex: () => api.post('/config/rebuild-index'),
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

export default api
