import axios from 'axios'

const instance = axios.create({
  baseURL: '/api',
  timeout: 600000
})

instance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

instance.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    console.error('API Error:', error.response?.status, error.response?.data || error.message)
    return Promise.reject(error)
  }
)

export { instance }

export const authAPI = {
  login: (username, password) => {
    const formData = new FormData()
    formData.append('username', username)
    formData.append('password', password)
    return instance.post('/auth/login', formData)
  },
  register: (username, password) => instance.post('/auth/register', { username, password }),
  getMe: () => instance.get('/auth/users/me'),
}

export const userAPI = {
  list: (params = {}) => instance.get('/auth/users', { params }),
  create: (data) => instance.post('/auth/users', data),
  get: (id) => instance.get(`/auth/users/${id}`),
  update: (id, data) => instance.put(`/auth/users/${id}`, data),
  updateStatus: (id, status) => instance.put(`/auth/users/${id}/status`, null, { params: { status } }),
  resetPassword: (id, newPassword) => instance.post(`/auth/users/${id}/reset-password`, { new_password: newPassword }),
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
  create: (documentId, mode) => instance.post(`/review/${documentId}`, {}, { params: { mode }, timeout: 300000 }),
  get: (id) => instance.get(`/review/${id}`),
  getIssues: (id) => instance.get(`/review/${id}/issues`),
  getProgress: (reviewId) => instance.get(`/review/${reviewId}/progress`),
  list: () => instance.get('/review/'),
  updateIssue: (issueId, status) => instance.put(`/review/issues/${issueId}`, { status }),
  batchJudge: (reviewId, judgments) => instance.post(`/review/${reviewId}/judge`, { judgments }),
  getReport: (id) => instance.get(`/review/${id}/report`),
  exportHtml: (id) => instance.get(`/review/${id}/export-html`, { responseType: 'blob' })
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
  text: (text, styleGuideId = null, terminologyId = null) => instance.post('/polish/text', { text, style_guide_id: styleGuideId, terminology_id: terminologyId }),
  polishWithSkill: (text, skillId = 3, styleGuideId = 1, terminologyId = null) =>
    instance.post('/polish/skill', { text, skill_id: skillId, style_guide_id: styleGuideId, terminology_id: terminologyId }),
  analyzeFile: (formData) => {
    return instance.post('/polish/analyze-file', formData)
  },
  getProgress: (taskId) => instance.get(`/polish/progress/${taskId}`),
  listPolishedDocuments: () => instance.get('/polish/'),
  getPolishedDocument: (id) => instance.get(`/polish/${id}`),
  uploadPolishedFile: (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return instance.post('/polish/upload', formData)
  },
  previewPolishedFile: (id) => instance.get(`/polish/${id}/preview`),
  downloadPolishedFile: (id, filename) => {
    return instance.get(`/polish/${id}/download`, {
      responseType: 'blob',
      transformResponse: [(data) => data]
    }).then((response) => {
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', filename)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    })
  },
  downloadPolishedReport: (id, filename = '润色报告.docx') => {
    return instance.get(`/polish/${id}/download-report`, {
      responseType: 'blob',
      transformResponse: [(data) => data]
    }).then((response) => {
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', filename)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    })
  },
  deletePolishedDocument: (id) => instance.delete(`/polish/${id}`),
  submitFeedback: (originalText, polishedText, accuracy, corrections, target, terminologyFileId, sentenceFileId) =>
    instance.post('/polish/feedback', {
      original_text: originalText,
      polished_text: polishedText,
      accuracy,
      corrections,
      target,
      terminology_file_id: terminologyFileId || null,
      sentence_file_id: sentenceFileId || null
    }),
  getFeedbackStats: () => instance.get('/polish/feedback/stats')
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
  convert: (sourceFile, targetFormat, templateFile, requirements, retryFeedback, retryScreenshot) => {
    const formData = new FormData()
    formData.append('source_file', sourceFile)
    formData.append('target_format', targetFormat)
    if (templateFile) formData.append('template_file', templateFile)
    if (requirements) formData.append('requirements', requirements)
    if (retryFeedback) formData.append('retry_feedback', retryFeedback)
    if (retryScreenshot) formData.append('retry_screenshot', retryScreenshot)
    return instance.post('/convert/', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  getProgress: (taskId) => instance.get(`/convert/${taskId}/progress`),
  download: (taskId) => {
    return instance.get(`/convert/${taskId}/download`, {
      responseType: 'blob',
      timeout: 120000,
      transformResponse: [(data) => data]
    })
  },
  getReport: (taskId) => instance.get(`/convert/${taskId}/report`),
  getDetail: (taskId) => instance.get(`/convert/${taskId}/detail`),
  list: (skip = 0, limit = 100) => instance.get('/convert/', { params: { skip, limit } }),
  delete: (taskId) => instance.delete(`/convert/${taskId}`)
}

export const convertRulesAPI = {
  list: () => instance.get('/convert/rules'),
  create: (category, description) => {
    const formData = new FormData()
    formData.append('category', category)
    formData.append('description', description)
    return instance.post('/convert/rules', formData)
  },
  toggle: (id) => instance.put(`/convert/rules/${id}`),
  delete: (id) => instance.delete(`/convert/rules/${id}`),
  bulkDelete: (ids) => {
    const formData = new FormData()
    formData.append('rule_ids', ids.join(','))
    return instance.post('/convert/rules/bulk-delete', formData)
  }
}

export const translationAPI = {
  translate: (data) => instance.post('/translation/translate', data),
  translateFile: (formData) => instance.post('/translation/translate/file', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 600000
  }),
  getFileStatus: (docId) => instance.get(`/translation/translate/file/${docId}/status`),
  getMemoryBanks: () => instance.get('/translation/memory/banks'),
  getReviewedDocs: () => instance.get('/translation/reviewed-docs'),
  getDocument: (id) => instance.get(`/documents/${id}`),
  getMemory: (skip = 0, limit = 100, keyword) => {
    const params = { skip, limit }
    if (keyword) params.keyword = keyword
    return instance.get('/translation/memory', { params })
  },
  addMemory: (data) => instance.post('/translation/memory', data),
  writeMemoryFileEntry: (data) => instance.post('/translation/memory/file-entry', data),
  deleteMemory: (id) => instance.delete(`/translation/memory/${id}`),
  getDocs: (skip = 0, limit = 100) => instance.get('/translation/docs', { params: { skip, limit } }),
  getDoc: (id) => instance.get(`/translation/docs/${id}`),
  deleteDoc: (id) => instance.delete(`/translation/docs/${id}`)
}

export const knowledgeAPI = {
  getTree: () => instance.get('/knowledge/tree'),
  getFolderContent: (folderId) => instance.get(`/knowledge/folders/${folderId}`),
  createFolder: (folder) => instance.post('/knowledge/folders', folder),
  renameFolder: (folderId, data) => instance.put(`/knowledge/folders/${folderId}`, data),
  deleteFolder: (folderId) => instance.delete(`/knowledge/folders/${folderId}`),
  uploadFile: (folderId, file) => {
    const formData = new FormData()
    formData.append('file', file)
    return instance.post(`/knowledge/folders/${folderId}/files/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  },
  previewFile: (fileId) => instance.get(`/knowledge/files/${fileId}/preview`),
  downloadFile: (fileId, filename) => {
    return instance.get(`/knowledge/files/${fileId}/download`, {
      responseType: 'blob',
      transformResponse: [(data) => data]
    }).then((response) => {
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', filename)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    })
  },
  getFile: (fileId) => instance.get(`/knowledge/files/${fileId}`),
  deleteFile: (fileId) => instance.delete(`/knowledge/files/${fileId}`)
}
