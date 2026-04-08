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

// ── 当前 Dataset（存 localStorage）──────────────────────────────────────────

export const getCurrentDatasetId = () =>
  localStorage.getItem('current_dataset_id') || 'default'

export const setCurrentDatasetId = (id) =>
  localStorage.setItem('current_dataset_id', id)

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
  upload: (file, datasetId) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/data/upload', form, { params: { dataset_id: datasetId } })
  },
  list:       (params)      => api.get('/data/list', { params }),
  stats:      (datasetId)   => api.get('/data/stats', { params: { dataset_id: datasetId } }),
  getItem:    (id)          => api.get(`/data/${id}`),
  deleteItem: (id)          => api.delete(`/data/${id}`),
}

// ── Pipeline ───────────────────────────────────────────────────────────────────

export const pipelineApi = {
  run:      (datasetId)         => api.post('/pipeline/run', { dataset_id: datasetId }),
  runStep:  (datasetId, step)   => api.post('/pipeline/run-step', { dataset_id: datasetId, step }),
  status:   (datasetId)         => api.get('/pipeline/status', { params: { dataset_id: datasetId } }),
  steps:    ()                  => api.get('/pipeline/steps'),
}

// ── Annotation ─────────────────────────────────────────────────────────────────

export const annotationApi = {
  queue:       (params)              => api.get('/annotation/queue', { params }),
  next:        (datasetId)           => api.get('/annotation/next', { params: { dataset_id: datasetId } }),
  submit:      (item_id, label)      => api.post('/annotation/submit', { item_id, label }),
  batchSubmit: (annotations)         => api.post('/annotation/batch-submit', { annotations }),
  labeled:     (params)              => api.get('/annotation/labeled', { params }),
}

// ── Config ─────────────────────────────────────────────────────────────────────

export const configApi = {
  get:          (datasetId)   => api.get('/config', { params: { dataset_id: datasetId } }),
  update:       (datasetId, config) => api.post('/config/update', { config }, { params: { dataset_id: datasetId } }),
  reloadModel:  ()            => api.post('/config/reload-model'),
  rebuildIndex: ()            => api.post('/config/rebuild-index'),
}

// ── Export ─────────────────────────────────────────────────────────────────────

export const exportApi = {
  download: async (params) => {
    const res = await api.post('/export/create', params, { responseType: 'blob' })
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
  fields: (datasetId) => api.get('/export/fields', { params: { dataset_id: datasetId } }),
}

// ── Templates ──────────────────────────────────────────────────────────────────

export const templateApi = {
  list:   (datasetId)       => api.get('/templates', { params: { dataset_id: datasetId } }),
  get:    (id)              => api.get(`/templates/${id}`),
  create: (data)            => api.post('/templates', data),
  update: (id, data)        => api.put(`/templates/${id}`, data),
  delete: (id)              => api.delete(`/templates/${id}`),
}

export default api
