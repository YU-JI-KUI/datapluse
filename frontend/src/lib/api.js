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
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

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

// ── Data ───────────────────────────────────────────────────────────────────────

export const dataApi = {
  upload: (file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/data/upload', form)
  },
  list: (params) => api.get('/data/list', { params }),
  stats: () => api.get('/data/stats'),
  getItem: (id) => api.get(`/data/${id}`),
  deleteItem: (id) => api.delete(`/data/${id}`),
}

// ── Pipeline ───────────────────────────────────────────────────────────────────

export const pipelineApi = {
  run: () => api.post('/pipeline/run'),
  runStep: (step) => api.post('/pipeline/run-step', { step }),
  status: () => api.get('/pipeline/status'),
  steps: () => api.get('/pipeline/steps'),
}

// ── Annotation ─────────────────────────────────────────────────────────────────

export const annotationApi = {
  queue: (params) => api.get('/annotation/queue', { params }),
  next: () => api.get('/annotation/next'),
  submit: (item_id, label) => api.post('/annotation/submit', { item_id, label }),
  batchSubmit: (annotations) => api.post('/annotation/batch-submit', { annotations }),
  labeled: (params) => api.get('/annotation/labeled', { params }),
}

// ── Config ─────────────────────────────────────────────────────────────────────

export const configApi = {
  get: () => api.get('/config'),
  update: (config) => api.post('/config/update', { config }),
  reloadModel: () => api.post('/config/reload-model'),
  rebuildIndex: () => api.post('/config/rebuild-index'),
}

// ── Export ─────────────────────────────────────────────────────────────────────

export const exportApi = {
  // 下载导出文件（返回 blob，自动触发浏览器下载）
  download: async (params) => {
    const res = await api.post('/export/create', params, { responseType: 'blob' })
    // 从响应头取文件名
    const disposition = res.headers['content-disposition'] || ''
    const match = disposition.match(/filename="?([^"]+)"?/)
    const filename = match ? match[1] : `datapluse_export.${params.format || 'json'}`
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
  // 获取可用源字段列表（用于模板编辑器）
  fields: () => api.get('/export/fields'),
}

// ── Templates ──────────────────────────────────────────────────────────────────

export const templateApi = {
  list: () => api.get('/templates'),
  get: (id) => api.get(`/templates/${id}`),
  create: (data) => api.post('/templates', data),
  update: (id, data) => api.put(`/templates/${id}`, data),
  delete: (id) => api.delete(`/templates/${id}`),
}

export default api
