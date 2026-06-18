import { defineStore } from 'pinia'
import { ref } from 'vue'
import { polishAPI } from '@/api'

export const usePolishStore = defineStore('polish', () => {
  const tasks = ref({})

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

  return { tasks, submitFile, startPolling, getTask, removeTask, hasRunningTasks }
})
