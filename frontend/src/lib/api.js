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

// 响应拦截：401 跳转登录
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
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

// dataset_id 为 null 时返回空响应，不发起请求，避免后端 422
// （发生于已登录用户刷新页面、localStorage 中尚未写入 current_dataset_id 的瞬间）
const _empty = (defaultData = null) => Promise.resolve({ data: { success: true, data: defaultData } })

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
}

// ── Datasets ───────────────────────────────────────────────────────────────────

export const datasetApi = {
  list:   ()         => api.get('/datasets'),
  get:    (id)       => api.get(`/datasets/${id}`),
  create: (data)     => api.post('/datasets', data),
  update: (id, data) => api.put(`/datasets/${id}`, data),
  delete: (id)       => api.delete(`/datasets/${id}`),
}

// ── Users ──────────────────────────────────────────────────────────────────────

export const userApi = {
  list:           ()         => api.get('/users'),
  create:         (data)     => api.post('/users', data),
  update:         (id, data) => api.put(`/users/${id}`, data),
  delete:         (id)       => api.delete(`/users/${id}`),
  listRoles:      ()         => api.get('/users/roles'),
  resetPassword:  (id, data) => api.post(`/users/${id}/reset-password`, data),
}

// ── Data ───────────────────────────────────────────────────────────────────────

export const dataApi = {
  upload: (file, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty()
    const form = new FormData()
    form.append('file', file)
    return api.post('/data/upload', form, { params: { dataset_id: datasetId } })
  },
  list: (params = {}, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty({ total: 0, items: [], page: 1, page_size: 20 })
    return api.get('/data/list', { params: { ...params, dataset_id: datasetId } })
  },
  stats: (datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty({})
    return api.get('/data/stats', { params: { dataset_id: datasetId } })
  },
  getItem:    (id) => api.get(`/data/${id}`),
  deleteItem: (id) => api.delete(`/data/${id}`),
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

// ── Annotation ─────────────────────────────────────────────────────────────────

export const annotationApi = {
  queue: (params = {}, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty({ total: 0, items: [] })
    return api.get('/annotation/queue', { params: { ...params, dataset_id: datasetId } })
  },
  next: (datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty(null)
    return api.get('/annotation/next', { params: { dataset_id: datasetId } })
  },
  labeled: (params = {}, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return _empty({ total: 0, items: [] })
    return api.get('/annotation/labeled', { params: { ...params, dataset_id: datasetId } })
  },
  submit:      (item_id, label) => api.post('/annotation/submit', { item_id, label }),
  batchSubmit: (annotations)    => api.post('/annotation/batch-submit', { annotations }),
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
  download: async (params, datasetId = getCurrentDatasetId()) => {
    if (!datasetId) return null
    const body = { ...params, dataset_id: datasetId }
    const res = await api.post('/export/create', body, { responseType: 'blob' })
    const disposition = res.headers['content-disposition'] || ''
    const match = disposition.match(/filename="?([^"]+)"?/)
    const filename = match ? match[1] : `datapulse_export.${params.format || 'json'}`
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
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
