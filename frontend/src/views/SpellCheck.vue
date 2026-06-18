<template>
  <div class="spell-check-container">
    <div class="header-section">
      <h2>拼写检查</h2>
      <p class="subtitle">检查文档中的英文拼写和语法错误</p>
    </div>

    <div class="upload-section">
      <el-upload
        class="upload-demo"
        :auto-upload="false"
        :on-change="handleFileChange"
        :on-remove="handleFileRemove"
        :file-list="fileList"
        accept=".txt,.docx,.xlsx,.pptx,.dita,.md,.idml,.xml,.zip"
        drag
        :show-file-list="true"
      >
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="upload-text">点击或拖拽文件到此处上传</div>
        <div class="upload-hint">支持 .txt, .docx, .xlsx, .pptx, .dita, .md, .idml, .xml, .zip 格式</div>
      </el-upload>
      <div v-if="fileList.length > 0" class="file-info">
        <el-tag type="info">{{ fileList.length }} 个文件已选择</el-tag>
        <el-button size="small" style="margin-left:8px" @click="clearFile">清除文件</el-button>
      </div>
    </div>

    <div class="input-section">
      <el-textarea
        v-model="inputText"
        :rows="8"
        placeholder="或在此输入文本进行检查..."
        class="text-input"
      ></el-textarea>
    </div>

    <div class="button-section">
      <el-button type="primary" size="large" @click="startCheck" :loading="loading">
        <el-icon><Search /></el-icon>
        开始检查
      </el-button>
      <el-button size="large" @click="clearAll">
        <el-icon><Delete /></el-icon>
        清空
      </el-button>
      <el-button size="large" @click="downloadTemplate">
        <el-icon><Download /></el-icon>
        词典模板
      </el-button>
    </div>

    <!-- 审核进度 -->
    <div v-if="progress.visible" class="progress-section">
      <div class="progress-header">
        <span class="progress-title">{{ progress.message }}</span>
        <span class="progress-percent">{{ progress.percent }}%</span>
      </div>
      <el-progress
        :percentage="progress.percent"
        :status="progress.status"
        :stroke-width="16"
        :text-inside="true"
      />
      <div v-if="progress.detail" class="progress-detail">{{ progress.detail }}</div>
    </div>

    <div v-if="checkResult" class="result-section">
      <div class="result-header">
        <div class="result-stats">
          <el-tag type="danger" size="large">拼写错误: {{ checkResult.spell_count }}</el-tag>
          <el-tag type="warning" size="large">语法错误: {{ checkResult.grammar_count }}</el-tag>
          <el-tag type="info" size="large">总计: {{ checkResult.total_count }}</el-tag>
          <el-tag v-if="checkResult.filename" type="success" size="large">文件: {{ checkResult.filename }}</el-tag>
        </div>
        <div class="result-actions">
          <el-button size="small" @click="exportErrors">导出错误列表</el-button>
        </div>
      </div>

      <div class="content-section">
        <div class="content-header">
          <span class="content-title">原文内容</span>
        </div>
        <div class="content-body">
          <div class="highlighted-text" v-html="highlightedText"></div>
        </div>
      </div>

      <div class="errors-section">
        <div class="errors-header">
          <span class="errors-title">错误列表</span>
          <div class="errors-header-actions">
            <el-select v-model="filterType" placeholder="筛选类型" size="small" class="filter-select">
              <el-option label="全部" value="all"></el-option>
              <el-option label="拼写错误" value="spell"></el-option>
              <el-option label="语法错误" value="grammar"></el-option>
              <el-option label="风格建议" value="style"></el-option>
            </el-select>
            <el-button
              type="success"
              size="small"
              :disabled="selectedWordRows.length === 0"
              @click="batchAddToDict"
            >
              批量加入词典 ({{ selectedWordRows.length }})
            </el-button>
          </div>
        </div>
        <el-table
          :data="filteredErrors"
          border
          stripe
          class="errors-table"
          @selection-change="onSelectionChange"
          ref="errorsTableRef"
          row-key="rowKey"
        >
          <el-table-column type="selection" width="48" :selectable="isRowSelectable" />
          <el-table-column prop="index" label="序号" width="60" type="index"></el-table-column>
          <el-table-column prop="type" label="类型" width="100">
            <template #default="scope">
              <el-tag :type="scope.row.type === 'spell' ? 'danger' : (scope.row.type === 'style' ? 'info' : 'warning')">
                {{ scope.row.type === 'spell' ? '拼写' : (scope.row.type === 'style' ? '风格' : '语法') }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="message" label="错误描述" width="150"></el-table-column>
          <el-table-column prop="word" label="问题单词" width="150">
            <template #default="scope">
              <span v-if="scope.row.word" class="problem-word">{{ scope.row.word }}</span>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="suggestions" label="建议" min-width="220">
            <template #default="scope">
              <el-button
                v-for="(suggestion, idx) in scope.row.suggestions"
                :key="idx"
                size="small"
                plain
                @click="replaceWord(scope.row, suggestion)"
              >
                {{ suggestion }}
              </el-button>
              <span v-if="!scope.row.suggestions || scope.row.suggestions.length === 0">-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="scope">
              <el-button
                size="small"
                type="success"
                plain
                :disabled="!scope.row.word"
                @click="addToDict(scope.row)"
              >
                添加词典
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <div v-if="!loading && !checkResult && (inputText || fileList.length > 0)" class="empty-tip">
      <el-empty description="点击「开始检查」按钮进行拼写检查"></el-empty>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Search, Delete, Download } from '@element-plus/icons-vue'
import { instance as request } from '@/api'

const inputText = ref('')
const fileList = ref([])
const loading = ref(false)
const checkResult = ref(null)
const filterType = ref('all')
const selectedWordRows = ref([])
const errorsTableRef = ref(null)

// 审核进度
const progress = ref({
  visible: false,
  percent: 0,
  message: '',
  detail: '',
  status: ''
})

// 为每条错误添加唯一key
const errorsWithKey = computed(() => {
  if (!checkResult.value?.errors) return []
  return checkResult.value.errors.map((e, idx) => ({
    ...e,
    rowKey: `${e.start}-${e.end}-${e.type}-${idx}`
  }))
})

const filteredErrors = computed(() => {
  const errors = errorsWithKey.value
  if (filterType.value === 'all') return errors
  return errors.filter(e => e.type === filterType.value)
})

const highlightedText = computed(() => {
  if (!checkResult.value) return ''
  let text = checkResult.value.text
  const errors = checkResult.value.errors
  if (!errors || errors.length === 0) return escapeHtml(text)

  let result = ''
  let lastEnd = 0
  errors.forEach(err => {
    result += escapeHtml(text.substring(lastEnd, err.start))
    const problemText = escapeHtml(text.substring(err.start, err.end))
    let bgColor, borderColor
    if (err.type === 'spell') {
      bgColor = '#FFF280'
      borderColor = '#FFD700'
    } else if (err.type === 'style') {
      bgColor = '#E0F2FE'
      borderColor = '#7DD3FC'
    } else {
      bgColor = '#CCE5FF'
      borderColor = '#93C5FD'
    }
    result += `<span style="background-color: ${bgColor}; padding: 1px 3px; border-radius: 3px; border-bottom: 2px solid ${borderColor};" title="${err.message}">${problemText}</span>`
    lastEnd = err.end
  })
  result += escapeHtml(text.substring(lastEnd))
  return result
})

function escapeHtml(text) {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML.replace(/\n/g, '<br/>').replace(/\s/g, '&nbsp;')
}

async function handleFileChange(file) {
  fileList.value = [file]
  inputText.value = ''
}

function handleFileRemove() {
  fileList.value = []
}

function clearFile() {
  fileList.value = []
}

function isRowSelectable(row) {
  return !!row.word
}

function onSelectionChange(rows) {
  selectedWordRows.value = rows
}

async function startCheck() {
  loading.value = true
  progress.value = { visible: true, percent: 0, message: '准备中...', detail: '', status: '' }
  checkResult.value = null
  selectedWordRows.value = []

  try {
    if (fileList.value.length > 0) {
      const file = fileList.value[0]
      const formData = new FormData()
      formData.append('file', file.raw)

      progress.value = { visible: true, percent: 10, message: '正在上传文件...', detail: file.name, status: '' }
      await new Promise(r => setTimeout(r, 100))

      progress.value = { visible: true, percent: 30, message: '正在解析文件内容...', detail: file.name, status: '' }

      // 使用 XMLHttpRequest 以便监听进度
      const result = await uploadWithProgress(formData, file.name, (p) => {
        progress.value = {
          visible: true,
          percent: Math.min(95, 30 + Math.floor(p * 0.3)),
          message: '正在上传并检查...',
          detail: `${file.name} (${p}%)`,
          status: ''
        }
      })

      progress.value = { visible: true, percent: 70, message: '正在分析拼写和语法...', detail: '', status: '' }
      await new Promise(r => setTimeout(r, 200))

      checkResult.value = result
      saveToHistory(result)

      progress.value = { visible: true, percent: 100, message: '检查完成', detail: `共发现 ${result.total_count} 个问题`, status: 'success' }
      setTimeout(() => { progress.value.visible = false }, 1500)
      ElMessage.success(`检查完成，共发现 ${result.total_count} 个问题`)
    } else if (inputText.value.trim()) {
      progress.value = { visible: true, percent: 30, message: '正在分析拼写和语法...', detail: '', status: '' }
      const resp = await request.post('/spell-check/check', { text: inputText.value })
      checkResult.value = resp.data
      saveToHistory(resp.data)

      progress.value = { visible: true, percent: 100, message: '检查完成', detail: `共发现 ${resp.data.total_count} 个问题`, status: 'success' }
      setTimeout(() => { progress.value.visible = false }, 1500)
      ElMessage.success(`检查完成，共发现 ${resp.data.total_count} 个问题`)
    } else {
      progress.value.visible = false
      checkResult.value = null
      ElMessage.warning('请上传文件或输入文本')
    }
  } catch (error) {
    console.error('检查失败:', error)
    const errorMsg = error.response?.data?.detail || error.message || '未知错误'
    progress.value = { visible: true, percent: 100, message: '检查失败', detail: errorMsg, status: 'exception' }
    setTimeout(() => { progress.value.visible = false }, 3000)
    ElMessage.error('检查失败：' + errorMsg)
  } finally {
    loading.value = false
  }
}

function uploadWithProgress(formData, filename, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const token = localStorage.getItem('token')

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        const percent = Math.round((e.loaded / e.total) * 100)
        onProgress(percent)
      }
    })

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText))
        } catch (e) {
          reject(new Error('响应解析失败'))
        }
      } else {
        let errorMsg = `HTTP ${xhr.status}`
        try {
          const data = JSON.parse(xhr.responseText)
          errorMsg = data.detail || errorMsg
        } catch (e) {}
        reject(new Error(errorMsg))
      }
    })

    xhr.addEventListener('error', () => reject(new Error('网络错误')))
    xhr.addEventListener('abort', () => reject(new Error('请求已取消')))

    xhr.open('POST', '/api/spell-check/upload')
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.send(formData)
  })
}

function clearAll() {
  inputText.value = ''
  fileList.value = []
  checkResult.value = null
  selectedWordRows.value = []
  progress.value.visible = false
}

function downloadTemplate() {
  const content = '# 每行一个单词（# 开头为注释）\nDNA\nRNA\nPCR\nng\nul\n'
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = '词典模板.txt'
  link.click()
  URL.revokeObjectURL(url)
}

async function addToDict(error) {
  const word = error.word
  if (!word) {
    ElMessage.warning('该错误无具体单词可加入词典')
    return
  }
  try {
    await request.post('/spell-check/add-word', null, { params: { word } })
    ElMessage.success(`已添加单词 "${word}" 到词典`)
    // 标记该条已加入词典
    if (error.rowKey) {
      error._added = true
    }
  } catch (error) {
    console.error('添加单词失败:', error)
    ElMessage.error('添加单词失败')
  }
}

async function batchAddToDict() {
  const words = [...new Set(selectedWordRows.value.map(r => r.word).filter(Boolean))]
  if (words.length === 0) {
    ElMessage.warning('请勾选有具体单词的错误项')
    return
  }
  try {
    let successCount = 0
    for (const word of words) {
      try {
        await request.post('/spell-check/add-word', null, { params: { word } })
        successCount++
      } catch (e) {
        console.error(`添加 ${word} 失败:`, e)
      }
    }
    ElMessage.success(`成功添加 ${successCount}/${words.length} 个单词到词典`)
    // 标记已添加
    selectedWordRows.value.forEach(r => { r._added = true })
    selectedWordRows.value = []
    if (errorsTableRef.value) errorsTableRef.value.clearSelection()
  } catch (error) {
    console.error('批量添加失败:', error)
    ElMessage.error('批量添加失败')
  }
}

function replaceWord(error, suggestion) {
  if (!checkResult.value) return
  const text = checkResult.value.text
  const newText = text.substring(0, error.start) + suggestion + text.substring(error.end)
  checkResult.value.text = newText
  checkResult.value.errors = checkResult.value.errors.filter(e => e.start !== error.start)
  checkResult.value.spell_count = checkResult.value.errors.filter(e => e.type === 'spell').length
  checkResult.value.grammar_count = checkResult.value.errors.filter(e => e.type === 'grammar').length
  checkResult.value.total_count = checkResult.value.errors.length
}

function exportErrors() {
  if (!checkResult.value || !checkResult.value.errors) return
  let content = '序号,类型,错误描述,问题单词,建议\n'
  checkResult.value.errors.forEach((err, idx) => {
    const suggestions = err.suggestions ? err.suggestions.join('; ') : ''
    content += `${idx + 1},${err.type === 'spell' ? '拼写' : '语法'},${err.message},${err.word || ''},${suggestions}\n`
  })
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = '拼写检查错误列表.csv'
  link.click()
  URL.revokeObjectURL(url)
}

const STORAGE_KEY = 'spell_check_history'

function saveToHistory(result) {
  try {
    const history = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    // 限制历史记录只保留摘要，避免localStorage过大
    const summary = {
      id: `spell_${Date.now()}`,
      filename: result.filename || '文本输入',
      created_at: new Date().toISOString(),
      spell_count: result.spell_count,
      grammar_count: result.grammar_count,
      total_count: result.total_count,
      text: result.text ? result.text.substring(0, 1000) : '', // 限制原文长度
      errors: result.errors || []
    }
    history.unshift(summary)
    // 最多保留20条
    if (history.length > 20) history.length = 20
    localStorage.setItem(STORAGE_KEY, JSON.stringify(history))
  } catch (e) {
    console.warn('保存历史记录失败:', e)
  }
}

// 从历史页面"重新加载"时，从 sessionStorage 读取
onMounted(() => {
  try {
    const reapply = sessionStorage.getItem('spell_check_reapply')
    if (reapply) {
      const data = JSON.parse(reapply)
      checkResult.value = data
      sessionStorage.removeItem('spell_check_reapply')
      ElMessage.success(`已重新加载「${data.filename}」的检查结果`)
    }
  } catch (e) {
    console.warn('加载重新应用数据失败:', e)
  }
})
</script>

<style scoped>
.spell-check-container {
  max-width: 1200px;
  margin: 0 auto;
}

.header-section {
  margin-bottom: 24px;
}

.header-section h2 {
  font-size: 24px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 4px;
}

.subtitle {
  font-size: 14px;
  color: #6b7280;
}

.upload-section {
  margin-bottom: 16px;
}

.upload-demo {
  margin-bottom: 12px;
}

.upload-icon {
  font-size: 48px;
  color: #3b82f6;
  margin-bottom: 8px;
}

.upload-text {
  font-size: 16px;
  color: #374151;
  margin-bottom: 4px;
}

.upload-hint {
  font-size: 12px;
  color: #9ca3af;
}

.file-info {
  margin-top: 8px;
  display: flex;
  align-items: center;
}

.input-section {
  margin-bottom: 16px;
}

.text-input {
  width: 100%;
  border-radius: 8px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.button-section {
  margin-bottom: 24px;
  display: flex;
  gap: 12px;
}

.progress-section {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.progress-title {
  font-size: 14px;
  font-weight: 500;
  color: #1f2937;
}

.progress-percent {
  font-size: 14px;
  font-weight: 600;
  color: #3b82f6;
}

.progress-detail {
  font-size: 12px;
  color: #6b7280;
  margin-top: 6px;
}

.result-section {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  padding: 24px;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.result-stats {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.content-section {
  margin-bottom: 24px;
}

.content-header {
  margin-bottom: 12px;
}

.content-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.content-body {
  background: #f9fafb;
  border-radius: 8px;
  padding: 16px;
  max-height: 300px;
  overflow-y: auto;
}

.highlighted-text {
  font-size: 14px;
  line-height: 1.8;
  color: #374151;
  white-space: pre-wrap;
  word-break: break-word;
}

.errors-section {
  margin-top: 20px;
}

.errors-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.errors-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.errors-header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.filter-select {
  width: 120px;
}

.errors-table {
  width: 100%;
}

.problem-word {
  color: #dc2626;
  font-weight: 600;
  background: #fef3c7;
  padding: 1px 4px;
  border-radius: 3px;
}

.empty-tip {
  margin-top: 40px;
}
</style>
