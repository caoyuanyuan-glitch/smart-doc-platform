import axios from 'axios'

const instance = axios.create({
  baseURL: '/api',
  timeout: 60000
})

instance.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.status, error.response?.data || error.message)
    return Promise.reject(error)
  }
)

export const authAPI = {
  login: (username, password) => {
    const formData = new FormData()
    formData.append('username', username)
    formData.append('password', password)
    return instance.post('/auth/login', formData)
  },
  register: (username, password) => instance.post('/auth/register', { username, password }),
  getMe: () => instance.get('/auth/users/me'),
  getUsers: () => instance.get('/auth/users'),
  updateRole: (userId, role) => instance.put(`/auth/users/${userId}/role`, { role })
}

export const documentAPI = {
  upload: (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return instance.post('/documents/upload/', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  list: () => instance.get('/documents/'),
  get: (id) => instance.get(`/documents/${id}`),
  delete: (id) => instance.delete(`/documents/${id}`)
}

export const reviewAPI = {
  create: (documentId, mode) => instance.post(`/review/${documentId}`, {}, { params: { mode } }),
  get: (id) => instance.get(`/review/${id}`),
  getIssues: (id) => instance.get(`/review/${id}/issues`),
  list: () => instance.get('/review/'),
  updateIssue: (issueId, status) => instance.put(`/review/issues/${issueId}`, { status }),
  getReport: (id) => instance.get(`/review/${id}/report`)
}

export const compareAPI = {
  create: (fileA, fileB) => {
    const formData = new FormData()
    formData.append('file_a', fileA)
    formData.append('file_b', fileB)
    return instance.post('/compare/', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  get: (id) => instance.get(`/compare/${id}`),
  list: () => instance.get('/compare/'),
  delete: (id) => instance.delete(`/compare/${id}`),
  getReport: (id, format) => instance.get(`/compare/${id}/report`, { params: { format } }),
  getConfig: () => instance.get('/compare/config'),
  updateConfig: (config) => instance.put('/compare/config', config)
}

export const rulesAPI = {
  list: () => instance.get('/rules/'),
  create: (rule) => instance.post('/rules/', rule),
  update: (id, rule) => instance.put(`/rules/${id}`, rule),
  delete: (id) => instance.delete(`/rules/${id}`),
  bulkCreate: (rules) => instance.post('/rules/bulk', rules),
  bulkDelete: (ids) => instance.delete('/rules/bulk', { params: { rule_ids: ids } }),
  export: () => instance.get('/rules/export')
}

export const termsAPI = {
  list: () => instance.get('/terms/'),
  create: (term) => instance.post('/terms/', term),
  update: (id, term) => instance.put(`/terms/${id}`, term),
  delete: (id) => instance.delete(`/terms/${id}`)
}

export const auditBasisAPI = {
  upload: (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return instance.post('/audit_basis/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  list: () => instance.get('/audit_basis/'),
  get: (id) => instance.get(`/audit_basis/${id}`),
  delete: (id) => instance.delete(`/audit_basis/${id}`)
}

export const polishAPI = {
  document: (id) => instance.post(`/polish/${id}`),
  text: (text) => instance.post('/polish/text', { text })
}

export const qaAPI = {
  ask: (documentId, question) => instance.post(`/qa/${documentId}`, {}, { params: { question } }),
  askGeneral: (question, knowledgeIds = []) => instance.post('/qa/general', { question, knowledge_ids: knowledgeIds })
}

export const generateAPI = {
  create: (productName, productModel, docType, targetChapter) =>
    instance.post('/generate/', { product_name: productName, product_model: productModel, doc_type: docType, target_chapter: targetChapter })
}

export const convertAPI = {
  md2dita: (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return instance.post('/convert/md2dita', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  docx2dita: (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return instance.post('/convert/docx2dita', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
  }
}
