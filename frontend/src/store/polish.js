import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { polishAPI } from '@/api'

export const usePolishStore = defineStore('polish', () => {
  const DOCUMENT_DRAFT_KEY = 'polish-document-draft'
  const DOCUMENT_SESSION_KEY = 'polish-document-session'

  function readSessionValue(key, fallback) {
    if (typeof window === 'undefined') {
      return fallback
    }
    try {
      const raw = window.sessionStorage.getItem(key)
      return raw ? { ...fallback, ...JSON.parse(raw) } : fallback
    } catch {
      return fallback
    }
  }

  function writeSessionValue(key, value) {
    if (typeof window === 'undefined') {
      return
    }
    try {
      window.sessionStorage.setItem(key, JSON.stringify(value))
    } catch {
      // Keep page interaction alive even when browser session storage is full.
    }
  }

  function clearSessionValue(key) {
    if (typeof window === 'undefined') {
      return
    }
    window.sessionStorage.removeItem(key)
  }

  const defaultDocumentDraft = {
    sentenceFile: '',
    sentenceFileId: null,
    terminologyFile: '',
    terminologyFileId: null,
    sourceFile: '',
    outputPath: '已润色文档',
    requirements: ''
  }

  const defaultDocumentSession = {
    loading: false,
    progress: 0,
    message: '',
    result: null
  }

  function normalizeRestoredDocumentSession(session) {
    const restored = {
      ...defaultDocumentSession,
      ...(session || {})
    }

    if (restored.loading && !restored.result) {
      return {
        ...restored,
        loading: false,
        progress: 0,
        message: '上次润色未完成，请重新提交'
      }
    }

    return restored
  }

  function serializeDocumentSession(session) {
    const safeSession = {
      loading: session.loading,
      progress: session.progress,
      message: session.message,
      result: null
    }

    if (!session.result) {
      return safeSession
    }

    const result = session.result
    const original = typeof result.original === 'string' ? result.original.slice(0, 4000) : ''
    const polished = typeof result.polished === 'string' ? result.polished.slice(0, 4000) : ''
    const changes = Array.isArray(result.changes)
      ? result.changes.slice(0, 100).map(change => ({
          before: change.before || change.original || change.summary || '',
          after: change.after || change.polished || '',
          type: change.type || ''
        }))
      : []

    safeSession.result = {
      id: result.id,
      original,
      polished,
      changes,
      report_file: result.report_file || result.reportFile,
      download_filename: result.download_filename,
      file_type: result.file_type
    }
    return safeSession
  }

  const tasks = ref({})
  const documentDraft = ref(readSessionValue(DOCUMENT_DRAFT_KEY, defaultDocumentDraft))
  const documentSession = ref(normalizeRestoredDocumentSession(readSessionValue(DOCUMENT_SESSION_KEY, defaultDocumentSession)))

  function submitFile(formData) {
    const taskId = 'pending'
    
    const task = {
      id: taskId,
      status: 'running',
      progress: 0,
      message: '提交中...',
      result: null
    }
    
    const promise = polishAPI.analyzeFile(formData)
      .then(resp => {
        const data = resp.data || {}
        const finalTaskId = data.task_id || taskId
        task.id = finalTaskId
        task.status = 'done'
        task.progress = 100
        task.message = '润色完成'
        task.result = data
        tasks.value[finalTaskId] = task
        return data
      })
      .catch(err => {
        task.status = 'error'
        task.message = err.response?.data?.detail || err.message || '润色失败'
        tasks.value[taskId] = task
        throw err
      })
    
    tasks.value[taskId] = task
    return { taskId, promise }
  }

  function startPolling(taskId) {
    const interval = setInterval(async () => {
      try {
        const resp = await polishAPI.getProgress(taskId)
        const data = resp.data || {}
        if (tasks.value[taskId]) {
          tasks.value[taskId].progress = data.progress || 0
          tasks.value[taskId].message = data.message || ''
          if (data.status === 'done' || data.status === 'error') {
            tasks.value[taskId].status = data.status
            if (data.result) {
              tasks.value[taskId].result = data.result
            }
            clearInterval(interval)
          }
        }
      } catch (e) {
        // Stop polling on error
        clearInterval(interval)
      }
    }, 1500)
  }

  function getTask(taskId) {
    return tasks.value[taskId]
  }

  function removeTask(taskId) {
    delete tasks.value[taskId]
  }

  function hasRunningTasks() {
    return Object.values(tasks.value).some(t => t.status === 'running')
  }

  function updateDocumentDraft(patch) {
    documentDraft.value = {
      ...documentDraft.value,
      ...patch
    }
  }

  function setDocumentSession(patch) {
    documentSession.value = {
      ...documentSession.value,
      ...patch
    }
  }

  async function submitDocumentPolish(payload, sourceName) {
    setDocumentSession({
      loading: true,
      progress: 0,
      message: '提交中...',
      result: null
    })
    updateDocumentDraft({ sourceFile: sourceName || documentDraft.value.sourceFile })

    try {
      const resp = await polishAPI.analyzeFile(payload)
      const data = resp.data || {}
      setDocumentSession({
        loading: false,
        progress: 100,
        message: '润色完成',
        result: data
      })
      return data
    } catch (err) {
      setDocumentSession({
        loading: false,
        progress: 0,
        message: err.response?.data?.detail || err.message || '润色失败',
        result: null
      })
      throw err
    }
  }

  function clearDocumentSession() {
    documentDraft.value = { ...defaultDocumentDraft }
    documentSession.value = { ...defaultDocumentSession }
    clearSessionValue(DOCUMENT_DRAFT_KEY)
    clearSessionValue(DOCUMENT_SESSION_KEY)
  }

  watch(documentDraft, (value) => {
    writeSessionValue(DOCUMENT_DRAFT_KEY, value)
  }, { deep: true })

  watch(documentSession, (value) => {
    writeSessionValue(DOCUMENT_SESSION_KEY, serializeDocumentSession(value))
  }, { deep: true })

  return {
    tasks,
    documentDraft,
    documentSession,
    submitFile,
    startPolling,
    getTask,
    removeTask,
    hasRunningTasks,
    updateDocumentDraft,
    setDocumentSession,
    submitDocumentPolish,
    clearDocumentSession
  }
})
