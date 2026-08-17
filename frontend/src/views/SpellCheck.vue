<template>
  <div class="spell-check-container">
    <div class="header-section">
      <h2>拼写检查</h2>
      <p class="subtitle">检查文档中的英文拼写、语法、格式和显而易见的低级错误，并进行直接修改</p>
    </div>

    <el-tabs v-model="activeTab" class="mode-tabs">
      <el-tab-pane label="文本检查" name="text" />
      <el-tab-pane label="文件检查" name="file" />
    </el-tabs>

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

    <div class="doc-inline-bar">
      <span class="doc-inline-label">当前文档</span>
      <span class="doc-inline-name">{{ activeTab === 'file' ? (fileList[0]?.name || '未加载文件') : '文本输入' }}</span>
      <span class="doc-inline-hint">
        {{ activeTab === 'file' ? '支持 .pdf / .txt / .md / .docx / .xlsx / .pptx / .dita / .zip' : '在右侧粘贴或编辑文本，再点击“一键检查”' }}
      </span>
    </div>

    <div class="desktop-shell">
      <aside class="workspace-sidebar">
        <div class="panel summary-panel">
          <div class="summary-compact-head">
            <span class="mini-label summary-title">检查概览</span>
            <span class="summary-total-inline">{{ checkResult?.total_count || 0 }}</span>
          </div>
          <div class="stats-row">
            <div class="metric-card">
              <span class="metric-label">总</span>
              <strong>{{ checkResult?.total_count || 0 }}</strong>
            </div>
            <div class="metric-card">
              <span class="metric-label">拼写</span>
              <strong>{{ checkResult?.spell_count || 0 }}</strong>
            </div>
            <div class="metric-card">
              <span class="metric-label">规则</span>
              <strong>{{ checkResult?.grammar_count || 0 }}</strong>
            </div>
          </div>
        </div>

        <div class="panel issue-panel">
          <div class="issue-panel-header">
            <div class="issue-header-meta">
              <span class="panel-title">当前问题</span>
              <span class="issue-kind">{{ activeIssue ? getErrorTypeLabel(activeIssue.type) : (checkResult?.total_count === 0 && checkResult ? '处理完成' : '未选中问题') }}</span>
            </div>
            <span class="nav-meta">{{ filteredErrors.length > 0 ? `${currentIssueIndex + 1} / ${filteredErrors.length}` : '0 / 0' }}</span>
          </div>

          <div class="issue-snippet">{{ getIssueToken(activeIssue) }}</div>

          <div class="mini-label suggestion-title">修订建议</div>
          <div class="suggestion-stack">
            <template v-if="activeIssue && activeIssue.suggestions && activeIssue.suggestions.length">
              <div v-for="(suggestion, idx) in activeIssue.suggestions.slice(0, 3)" :key="idx" class="suggestion-card">
                <span class="suggestion-index">方案 {{ idx + 1 }}</span>
                <span class="suggestion-text">{{ suggestion }}</span>
                <el-button size="small" @click="replaceWord(activeIssue, suggestion)">应用</el-button>
              </div>
            </template>
            <div v-else class="suggestion-empty">当前问题没有可靠的自动修订方案。可点击下方“编辑”手动写入修订内容。</div>
          </div>

        </div>
      </aside>

      <section class="workspace-editor panel">
        <div class="editor-toolbar">
          <div class="editor-toolbar-left">
            <el-button v-if="activeTab === 'file'" type="primary" @click="triggerUploadPick">打开文件</el-button>
            <el-button type="primary" @click="startCheck" :loading="loading">一键检查</el-button>
            <el-button @click="exportCurrentResult" :disabled="!checkResult?.text">导出结果</el-button>
            <el-button @click="activeTab === 'file' ? clearFile() : clearAll()">清空{{ activeTab === 'file' ? '文件' : '内容' }}</el-button>
          </div>
        </div>

        <div class="editor-header">
          <div class="editor-header-meta">
            <span class="editor-title">{{ activeTab === 'file' ? '文档内容' : '原文内容' }}</span>
            <span class="editor-tip">
              {{ activeTab === 'file' ? '点击高亮位置可在左侧处理当前问题' : '在这里粘贴或编辑文本，检查后可用左侧面板逐条处理问题' }}
            </span>
          </div>
          <div v-if="checkResult" class="editor-header-actions">
            <el-button size="small" @click="prevIssue" :disabled="!activeIssue">上一处</el-button>
            <el-button size="small" type="primary" @click="nextIssue" :disabled="!activeIssue">下一处</el-button>
            <el-button size="small" @click="undoLastApply" :disabled="undoStack.length === 0">撤销应用</el-button>
            <el-button size="small" @click="editSuggestion(activeIssue)" :disabled="!activeIssue">编辑</el-button>
            <el-button size="small" @click="ignoreIssue" :disabled="!activeIssue">忽略</el-button>
            <el-button size="small" @click="addToDict(activeIssue)" :disabled="!activeIssue || !canAddWord(activeIssue)">加入白名单</el-button>
          </div>
        </div>

        <div v-if="activeTab === 'file' && !checkResult" class="file-stage">
          <el-upload
            ref="uploadRef"
            class="hidden-upload-input"
            :auto-upload="false"
            :on-change="handleFileChange"
            :on-remove="handleFileRemove"
            :limit="1"
            :file-list="fileList"
            accept=".pdf,.txt,.docx,.xlsx,.pptx,.dita,.md,.idml,.xml,.zip"
            :show-file-list="false"
          />
        </div>

        <el-input
          v-if="activeTab === 'text' && !checkResult"
          ref="textEditorRef"
          v-model="inputText"
          type="textarea"
          :rows="22"
          placeholder="在这里输入或粘贴文本进行检查..."
          class="text-editor-area"
        />

        <div v-if="(activeTab === 'file' || activeTab === 'text') && checkResult" ref="contentBodyRef" class="content-body" tabindex="0" @click="handleHighlightClick">
          <div class="highlighted-text" v-html="highlightedText"></div>
        </div>
      </section>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getAPIErrorMessage, instance as request } from '@/api'

const uploadRef = ref(null)
const contentBodyRef = ref(null)
const textEditorRef = ref(null)
const activeTab = ref('text')
const inputText = ref('')
const fileList = ref([])
const loading = ref(false)
const checkResult = ref(null)
const addedWords = ref([])
const undoStack = ref([])
const currentIssueIndex = ref(0)

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
  return errorsWithKey.value
})

const activeIssue = computed(() => filteredErrors.value[currentIssueIndex.value] || null)
watch(filteredErrors, () => {
  if (currentIssueIndex.value >= filteredErrors.value.length) {
    currentIssueIndex.value = filteredErrors.value.length > 0 ? filteredErrors.value.length - 1 : 0
  }
})

watch(currentIssueIndex, async () => {
  await nextTick()
  syncCurrentIssueView()
})

watch(activeTab, () => {
  checkResult.value = null
  currentIssueIndex.value = 0
  undoStack.value = []
  progress.value.visible = false
})

const highlightedText = computed(() => {
  if (!checkResult.value) return ''
  let text = checkResult.value.text
  const appliedRanges = [...(checkResult.value.appliedRanges || [])].map(item => ({ ...item, kind: 'applied' }))
  const errors = [...(checkResult.value.errors || [])].map(item => ({ ...item, kind: 'pending' }))
  const ranges = [...appliedRanges, ...errors].sort((a, b) => a.start - b.start || (a.kind === 'applied' ? -1 : 1))
  if (!ranges || ranges.length === 0) return escapeHtml(text)

  let result = ''
  let lastEnd = 0
  ranges.forEach(err => {
    result += escapeHtml(text.substring(lastEnd, err.start))
    const problemText = escapeHtml(text.substring(err.start, err.end))
    const isActive = err.kind === 'pending' && filteredErrors.value[currentIssueIndex.value] && filteredErrors.value[currentIssueIndex.value].start === err.start && filteredErrors.value[currentIssueIndex.value].end === err.end && filteredErrors.value[currentIssueIndex.value].type === err.type
    const bgColor = isActive ? '#FDBA74' : (err.kind === 'applied' ? '#DCFCE7' : '#FFF280')
    const borderColor = isActive ? '#EA580C' : (err.kind === 'applied' ? '#86EFAC' : '#FACC15')
    const extraClass = isActive ? ' active-highlight' : ''
    const issueIndex = err.kind === 'pending'
      ? filteredErrors.value.findIndex(item => item.start === err.start && item.end === err.end && item.type === err.type)
      : -1
    const issueAttr = issueIndex >= 0 ? ` data-issue-index="${issueIndex}"` : ''
    result += `<span class="highlight-chip${extraClass}"${issueAttr} tabindex="-1" style="background-color: ${bgColor}; padding: 1px 3px; border-radius: 3px; border-bottom: 2px solid ${borderColor};" title="${escapeHtmlAttribute(err.message || '')}">${problemText}</span>`
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

function escapeHtmlAttribute(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function getErrorTypeLabel(type) {
  if (type === 'spell') return '拼写'
  if (type === 'style') return '风格'
  if (type === 'unit') return '单位'
  if (type === 'grammar') return '语法'
  return type || '其他'
}

function canAddWord(row) {
  const word = getOriginalIssueWord(row)
  return !!word && !hasWordBeenAdded(word)
}

function normalizeWord(word) {
  return String(word || '').trim()
}

function getOriginalIssueWord(issue) {
  const text = checkResult.value?.text || ''
  const start = issue?.start
  const end = issue?.end
  if (Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end > start && end <= text.length) {
    return text.substring(start, end)
  }
  return normalizeWord(issue?.word)
}

function hasWordBeenAdded(word) {
  const normalized = normalizeWord(word)
  return !!normalized && addedWords.value.includes(normalized)
}

function markWordsAsAdded(words) {
  const normalizedWords = words.map(normalizeWord).filter(Boolean)
  if (normalizedWords.length === 0) return
  addedWords.value = [...new Set([...addedWords.value, ...normalizedWords])]
}

function applyWhitelistToCurrentResult(words) {
  if (!checkResult.value?.errors?.length) return 0
  const normalizedWords = new Set(words.map(normalizeWord).filter(Boolean))
  if (normalizedWords.size === 0) return 0

  const beforeCount = checkResult.value.errors.length
  checkResult.value.errors = checkResult.value.errors.filter((item) => {
    const itemWord = normalizeWord(item.word)
    return !normalizedWords.has(itemWord)
  })
  syncCounts()
  syncCurrentIssueIndex()
  return beforeCount - checkResult.value.errors.length
}

async function handleFileChange(file) {
  fileList.value = [file]
  checkResult.value = null
  undoStack.value = []
  currentIssueIndex.value = 0
  inputText.value = ''
  ElMessage.success(`已选择文件 ${file.name}，请点击“一键检查”继续`)
}

function handleFileRemove() {
  fileList.value = []
}

function clearFile() {
  fileList.value = []
  checkResult.value = null
  undoStack.value = []
  currentIssueIndex.value = 0
}

function triggerUploadPick() {
  const input = uploadRef.value?.$el?.querySelector('input[type="file"]')
  if (input) input.click()
}

function focusIssue(index) {
  if (index < 0 || index >= filteredErrors.value.length) return
  currentIssueIndex.value = index
}

function prevIssue() {
  if (filteredErrors.value.length === 0) return
  currentIssueIndex.value = (currentIssueIndex.value - 1 + filteredErrors.value.length) % filteredErrors.value.length
}

function nextIssue() {
  if (filteredErrors.value.length === 0) return
  currentIssueIndex.value = (currentIssueIndex.value + 1) % filteredErrors.value.length
}

function syncCounts() {
  if (!checkResult.value) return
  checkResult.value.spell_count = checkResult.value.errors.filter(e => e.type === 'spell').length
  checkResult.value.grammar_count = checkResult.value.errors.length - checkResult.value.spell_count
  checkResult.value.total_count = checkResult.value.errors.length
}

function syncCurrentIssueIndex() {
  if (filteredErrors.value.length === 0) {
    currentIssueIndex.value = 0
    return
  }
  if (currentIssueIndex.value >= filteredErrors.value.length) {
    currentIssueIndex.value = filteredErrors.value.length - 1
  }
}

function removeIssue(error) {
  if (!checkResult.value) return
  const targetIndex = Number(String(error.rowKey || '').split('-').pop())
  const hasValidTargetIndex = Number.isInteger(targetIndex) && targetIndex >= 0
  checkResult.value.errors = checkResult.value.errors.filter((item, index) => {
    if (hasValidTargetIndex) return index !== targetIndex
    return !(item.start === error.start && item.end === error.end && item.type === error.type)
  })
  syncCounts()
  syncCurrentIssueIndex()
}

function ignoreIssue() {
  if (!activeIssue.value) return
  pushUndoSnapshot()
  removeIssue(activeIssue.value)
  ElMessage.success('已忽略当前问题')
}

function handleHighlightClick(event) {
  const target = event.target?.closest?.('[data-issue-index]')
  if (!target) return
  const index = Number(target.getAttribute('data-issue-index'))
  if (Number.isInteger(index) && index >= 0) focusIssue(index)
}

function scrollToCurrentIssue() {
  const body = contentBodyRef.value
  if (!body) return
  const activeEl = body.querySelector('.active-highlight')
  if (!activeEl) return
   body.focus({ preventScroll: true })
  activeEl.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'smooth' })
  requestAnimationFrame(() => {
    activeEl.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'smooth' })
    activeEl.focus({ preventScroll: true })
  })
}

function focusTextSelection() {
  if (!activeIssue.value) return
  const textarea = textEditorRef.value?.textarea
  if (!textarea) return
  textarea.focus()
  textarea.setSelectionRange(activeIssue.value.start, activeIssue.value.end)
}

function syncCurrentIssueView() {
  if (activeTab.value === 'text' && !checkResult.value) {
    focusTextSelection()
    return
  }
  scrollToCurrentIssue()
}

function getIssueDetailText(issue) {
  if (issue) {
    return issue.message || '右侧高亮位置对应当前问题。'
  }

  if (checkResult.value?.total_count === 0 && checkResult.value) {
    return '所有当前命中问题都已处理完毕。点击下方“导出结果”保存当前正文。'
  }

  return '在这里处理当前问题：右侧高亮位置会同步当前项，左侧可继续浏览、忽略或手动修改。'
}

function getIssueToken(issue) {
  if (issue) {
    return getOriginalIssueWord(issue) || '当前问题'
  }

  if (checkResult.value?.total_count === 0 && checkResult.value) {
    return '当前没有剩余问题'
  }

  return '先点击文档中的高亮问题，或使用“下一处”开始浏览。'
}


async function startCheck() {
  loading.value = true
  progress.value = { visible: true, percent: 0, message: '准备中...', detail: '', status: '' }
  checkResult.value = null
  addedWords.value = []
  currentIssueIndex.value = 0

  try {
    if (activeTab.value === 'file') {
      if (fileList.value.length === 0) {
        progress.value.visible = false
        checkResult.value = null
        ElMessage.warning('请先选择文件')
        return
      }
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

      checkResult.value = { ...result, appliedRanges: [] }
      undoStack.value = []
      saveToHistory(result)
      await nextTick()
      syncCurrentIssueView()

      progress.value = { visible: true, percent: 100, message: '检查完成', detail: `共发现 ${result.total_count} 个问题`, status: 'success' }
      setTimeout(() => { progress.value.visible = false }, 1500)
      ElMessage.success(`检查完成，共发现 ${result.total_count} 个问题`)
    } else if (inputText.value.trim()) {
      progress.value = { visible: true, percent: 30, message: '正在分析拼写和语法...', detail: '', status: '' }
      const resp = await request.post('/spell-check/check', { text: inputText.value })
      checkResult.value = { ...resp.data, appliedRanges: [] }
      inputText.value = resp.data.text || inputText.value
      undoStack.value = []
      saveToHistory(resp.data)
      await nextTick()
      syncCurrentIssueView()

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
    const errorMsg = getAPIErrorMessage(error, '检查失败')
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
  addedWords.value = []
  currentIssueIndex.value = 0
  undoStack.value = []
  progress.value.visible = false
}

async function addToDict(error) {
  const word = getOriginalIssueWord(error)
  if (hasWordBeenAdded(word)) {
    ElMessage.info(`单词 "${word}" 已在本次结果中加入白名单`)
    return
  }
  if (!word) {
    ElMessage.warning('该错误无具体单词可加入白名单')
    return
  }
  try {
    await request.post('/spell-check/add-word', null, { params: { word } })
    ElMessage.success(`已添加单词 "${word}" 到白名单，后续所有格式会生效`)
    markWordsAsAdded([word])
    const removedCount = applyWhitelistToCurrentResult([word])
    if (removedCount > 0) {
      ElMessage.success(`已从当前结果移除 ${removedCount} 处命中`)
    }
  } catch (error) {
    console.error('添加单词失败:', error)
    ElMessage.error(getAPIErrorMessage(error, '添加单词失败'))
  }
}

function pushUndoSnapshot() {
  if (!checkResult.value) return
  undoStack.value.push(JSON.parse(JSON.stringify(checkResult.value)))
  if (undoStack.value.length > 20) undoStack.value.shift()
}

function restoreSnapshot(snapshot) {
  checkResult.value = JSON.parse(JSON.stringify(snapshot))
  if (activeTab.value === 'text') inputText.value = checkResult.value?.text || ''
  syncCurrentIssueIndex()
}

function undoLastApply() {
  if (undoStack.value.length === 0) return
  const snapshot = undoStack.value.pop()
  restoreSnapshot(snapshot)
  ElMessage.success('已撤销上次应用')
}

function replaceWord(error, suggestion) {
  if (!checkResult.value) return
  pushUndoSnapshot()
  const text = checkResult.value.text
  const replacement = suggestion ?? ''
  const originalLength = error.end - error.start
  const delta = replacement.length - originalLength
  const targetIndex = Number(String(error.rowKey || '').split('-').pop())
  const hasValidTargetIndex = Number.isInteger(targetIndex) && targetIndex >= 0
  const newText = text.substring(0, error.start) + replacement + text.substring(error.end)
  checkResult.value.text = newText
  if (activeTab.value === 'text') inputText.value = newText
  checkResult.value.errors = checkResult.value.errors
    .filter((item, index) => {
      if (hasValidTargetIndex) {
        return index !== targetIndex
      }
      return !(item.start === error.start && item.end === error.end && item.type === error.type)
    })
    .map((item) => {
      if (delta !== 0 && item.start >= error.end) {
        return {
          ...item,
          start: item.start + delta,
          end: item.end + delta
        }
      }
      return item
    })
    .sort((a, b) => a.start - b.start)
  const nextAppliedRanges = (checkResult.value.appliedRanges || [])
    .map((item) => {
      if (item.start >= error.end) {
        return {
          ...item,
          start: item.start + delta,
          end: item.end + delta
        }
      }
      return item
    })
  checkResult.value.appliedRanges = [...nextAppliedRanges, {
    start: error.start,
    end: error.start + replacement.length,
    message: `已应用: ${error.message || ''}`.trim()
  }]
  syncCounts()
  syncCurrentIssueIndex()
}

async function editSuggestion(error) {
  if (!checkResult.value) return
  try {
    const { value } = await ElMessageBox.prompt('请输入替换内容', '编辑建议', {
      confirmButtonText: '应用',
      cancelButtonText: '取消',
      inputValue: error.word || '',
      closeOnClickModal: false,
      closeOnPressEscape: true
    })
    replaceWord(error, value)
  } catch (e) {
    // 取消编辑
  }
}

function getExportBaseName() {
  const filename = checkResult.value?.filename || '拼写检查结果'
  return String(filename).replace(/\.[^.]+$/, '')
}

function exportCurrentResult() {
  if (!checkResult.value?.text) {
    ElMessage.warning('当前没有可导出的正文')
    return
  }
  const blob = new Blob([checkResult.value.text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${getExportBaseName()}-校对结果.txt`
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
      checkResult.value = { ...data, appliedRanges: data.appliedRanges || [] }
      addedWords.value = []
      currentIssueIndex.value = 0
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
  max-width: 1400px;
  margin: 0 auto;
  padding: 8px 4px 24px;
  background:
    radial-gradient(circle at top left, rgba(59, 130, 246, 0.08), transparent 28%),
    linear-gradient(180deg, rgba(255,255,255,0.92), rgba(248,250,252,1));
}

.header-section {
  margin-bottom: 18px;
}

.header-section h2 {
  font-size: 24px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 4px;
}

.subtitle {
  margin: 4px 0 10px;
  font-size: 14px;
  color: #6b7280;
}

.doc-inline-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid #e2e8f0;
}

.doc-inline-label {
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
}

.doc-inline-name {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.doc-inline-hint {
  font-size: 12px;
  color: #64748b;
}

.mode-tabs {
  margin-bottom: 18px;
}

.desktop-shell {
  display: grid;
  grid-template-columns: 328px minmax(0, 1fr);
  gap: 18px;
  align-items: stretch;
  min-height: 780px;
}

.panel {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 14px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
}

.panel-title {
  font-size: 16px;
  font-weight: 700;
  color: #111827;
}

.workspace-sidebar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  position: sticky;
  top: 12px;
  height: 780px;
}

.hidden-upload-input {
  position: absolute;
  width: 0;
  height: 0;
  overflow: hidden;
  opacity: 0;
  pointer-events: none;
}

.upload-icon {
  font-size: 42px;
  color: #2563eb;
  margin-bottom: 8px;
}

.workspace-editor {
  display: flex;
  flex-direction: column;
  height: 780px;
  overflow: hidden;
}

.summary-panel,
.issue-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.summary-compact-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.summary-total-inline {
  font-size: 18px;
  font-weight: 800;
  color: #0f172a;
}

.mini-label {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: #64748b;
  text-transform: uppercase;
}

.summary-title,
.suggestion-title {
  margin-top: 0;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.metric-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.metric-label {
  font-size: 11px;
  color: #64748b;
}

.metric-card strong {
  font-size: 18px;
  color: #0f172a;
}

.issue-panel {
  min-height: 0;
  flex: 1;
}

.issue-panel-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 14px;
}

.issue-header-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.issue-kind {
  font-size: 12px;
  color: #64748b;
  white-space: nowrap;
}

.issue-snippet {
  padding: 12px 14px;
  border-radius: 12px;
  background: #fff7cc;
  color: #854d0e;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.5;
  word-break: break-word;
}

.progress-section {
  position: sticky;
  top: 12px;
  z-index: 20;
  background: linear-gradient(180deg, #ffffff, #f8fbff);
  border: 1px solid #dbe4ee;
  border-radius: 14px;
  padding: 14px 18px;
  margin-bottom: 16px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.progress-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.progress-percent {
  font-size: 14px;
  font-weight: 600;
  color: #3b82f6;
}

.progress-detail {
  font-size: 12px;
  color: #64748b;
  margin-top: 8px;
  line-height: 1.6;
}

.suggestion-stack {
  display: flex;
  gap: 8px;
  flex-direction: column;
}

.suggestion-card {
  width: 100%;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #fff;
}

.suggestion-index {
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
}

.suggestion-text {
  min-width: 0;
  color: #1f2937;
  line-height: 1.5;
  word-break: break-word;
}

.suggestion-empty {
  padding: 10px 12px;
  border-radius: 12px;
  background: #f8fafc;
  color: #64748b;
  line-height: 1.6;
}

.nav-meta {
  font-size: 12px;
  color: #64748b;
  white-space: nowrap;
}

.editor-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.editor-toolbar-left {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.editor-header-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.editor-header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  position: sticky;
  top: 0;
  z-index: 2;
}

.editor-title {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}

.editor-tip {
  font-size: 12px;
  color: #64748b;
}

.file-stage {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.text-editor-area {
  flex: 1;
}

:deep(.text-editor-area .el-textarea__inner) {
  min-height: 620px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.85;
  padding: 16px 18px;
  resize: none;
}

.content-body {
  flex: 1;
  width: 100%;
  background: #f9fafb;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  padding: 18px;
  overflow-y: auto;
  scroll-behavior: smooth;
  min-height: 0;
}

.highlighted-text {
  font-size: 14px;
  line-height: 1.9;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
}

:deep(.highlight-chip) {
  cursor: pointer;
}

:deep(.active-highlight) {
  box-shadow: 0 0 0 3px rgba(234, 88, 12, 0.32);
  color: #7c2d12;
}

@media (max-width: 1100px) {
  .desktop-shell {
    grid-template-columns: 1fr;
  }

  .workspace-sidebar {
    position: static;
    height: auto;
  }

  .progress-section {
    top: 8px;
  }

  .workspace-editor {
    height: auto;
  }
}

@media (max-width: 768px) {
  .spell-check-container {
    padding: 0 0 20px;
  }

  .panel {
    padding: 14px;
  }

  .stats-row,
  .suggestion-card,
  .editor-toolbar,
  .editor-toolbar-left {
    width: 100%;
  }

  .doc-inline-bar,
  .stats-row,
  .suggestion-card {
    grid-template-columns: 1fr;
  }

  .editor-header-actions {
    width: 100%;
    justify-content: flex-start;
  }

  :deep(.text-editor-area .el-textarea__inner),
  .content-body {
    min-height: 420px;
  }

  .workspace-editor {
    overflow: visible;
  }
}
</style>
