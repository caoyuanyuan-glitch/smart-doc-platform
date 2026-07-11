<template>
  <div class="doc-translate-container">
    <div class="page-header">
      <h2 class="page-title">文档翻译</h2>
      <p class="page-desc">支持 AI、AI + 记忆库、仅记忆库三种模式，可翻译 Word、Excel、PPT、PDF、Markdown、TXT、IDML 文档</p>
    </div>

    <el-card class="config-card config-horizontal" shadow="never">
      <template #header>
        <span class="card-header-title">翻译配置</span>
      </template>
      <el-form :inline="true" size="default" class="config-form-inline">
        <el-form-item label="翻译引擎">
          <el-radio-group v-model="engine" @change="onEngineChange">
            <el-radio-button value="hybrid">AI + 记忆库</el-radio-button>
            <el-radio-button value="ai">仅 AI</el-radio-button>
            <el-radio-button value="memory">仅记忆库</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="记忆库配置" v-if="engine !== 'ai'">
          <el-select
            v-model="memoryFileId"
            placeholder="从知识库 / 资源库 / 记忆库选择，可不选"
            clearable
            filterable
            :loading="memoryLibraryLoading"
            style="width: 260px"
          >
            <el-option v-for="file in memoryLibraryFiles" :key="file.id" :label="file.label" :value="file.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="AI 模型" v-if="engine !== 'memory'">
          <el-select v-model="model" style="width: 160px">
            <el-option label="Kimi (Moonshot)" value="kimi" />
            <el-option label="DeepSeek Chat" value="deepseek" />
            <el-option label="ArkClaw Chat" value="arkclaw" />
          </el-select>
        </el-form-item>
        <el-form-item label="语言">
          <el-select v-model="sourceLang" style="width: 100px">
            <el-option label="自动" value="auto" />
            <el-option label="中文" value="zh" />
            <el-option label="英文" value="en" />
          </el-select>
          <el-icon class="swap-icon" @click="swapLanguages"><Sort /></el-icon>
          <el-select v-model="targetLang" style="width: 100px">
            <el-option label="英文" value="en" />
            <el-option label="中文" value="zh" />
            <el-option label="日文" value="ja" />
            <el-option label="韩文" value="ko" />
            <el-option label="法文" value="fr" />
            <el-option label="德文" value="de" />
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>

    <div class="content-grid">
      <div class="left-panel">
        <el-card class="source-card" shadow="never">
          <template #header>
            <div class="card-header-row">
              <span class="card-header-title">选择文档</span>
              <el-tabs v-model="docSource" class="source-tabs">
                <el-tab-pane label="上传文件" name="upload" />
                <el-tab-pane label="已审核文档" name="reviewed" />
              </el-tabs>
            </div>
          </template>

          <div v-if="docSource === 'upload'" class="file-upload-area">
            <el-upload
              class="upload-dragger"
              drag
              :before-upload="beforeFileUpload"
              :http-request="handleFileTranslate"
              :show-file-list="true"
              :auto-upload="false"
              multiple
              ref="fileUploadRef"
              accept=".docx,.doc,.xlsx,.xls,.pptx,.ppt,.pdf,.md,.txt,.xlf,.idml"
            >
              <el-icon class="upload-icon"><UploadFilled /></el-icon>
              <div class="upload-text">
                <p class="upload-title">将文件拖到此处，或点击上传</p>
                <p class="upload-hint">支持 Word、Excel、PPT、PDF、Markdown、IDML 格式</p>
                <p class="upload-tip">温馨提示：PDF直接翻译易出现排版错乱。建议先转换为Word格式上传，可获得更好的排版效果。</p>
              </div>
            </el-upload>
            <el-button class="upload-submit-btn" type="primary" :loading="hasActiveJobs" @click="submitFileUpload">
              <el-icon><Switch /></el-icon>
              上传并翻译
            </el-button>
          </div>

          <div v-if="docSource === 'reviewed'" class="reviewed-area">
            <div v-if="reviewedDocsLoading" class="loading-hint">加载已审核文档列表...</div>
            <div v-else-if="reviewedDocs.length === 0" class="empty-hint">暂无可翻译的已审核文档</div>
            <el-table v-else :data="reviewedDocs" highlight-current-row
              :row-class-name="tableRowClassName" max-height="320" @row-click="selectReviewedDocRow">
              <el-table-column prop="filename" label="文档名称" min-width="180" />
              <el-table-column prop="file_type" label="类型" width="80" />
              <el-table-column prop="preview" label="预览" min-width="200" show-overflow-tooltip />
            </el-table>
            <div v-if="reviewedDocs.length > 0" class="reviewed-doc-hint">已自动排除当前不支持翻译的格式。</div>
            <div v-if="selectedReviewedDoc" class="selected-doc-hint">
              已选择: {{ selectedReviewedDoc.filename }}
              <el-button type="primary" size="small" :loading="hasActiveJobs" @click="translateReviewedDoc" style="margin-left: 12px">
                翻译此文档
              </el-button>
            </div>
          </div>
        </el-card>
      </div>

      <div class="right-panel">
        <el-card class="result-card" shadow="never">
          <template #header>
            <span class="card-header-title">翻译结果</span>
          </template>

          <div v-if="translationJobs.length === 0" class="result-empty">
            <el-icon class="empty-icon"><FolderOpened /></el-icon>
            <p>选择一个或多个文档并翻译后，可在此分别下载译文</p>
          </div>

          <div v-else class="result-list">
            <div v-for="job in translationJobs" :key="job.jobKey" class="result-item">
              <div class="result-item-head">
                <div>
                  <div class="result-item-name">{{ job.original_filename }}</div>
                  <div class="result-item-meta">任务 #{{ job.doc_id || '待提交' }}</div>
                </div>
                <el-tag :type="statusTagType(job.status)" effect="plain">
                  {{ statusLabel(job) }}
                </el-tag>
              </div>

              <div v-if="job.status === 'submitting' || job.status === 'processing'" class="result-loading result-loading-inline">
                <div class="loading-spinner"></div>
                <p>{{ job.status === 'submitting' ? '正在提交翻译任务...' : `正在翻译... (${job.pollingCount}s)` }}</p>
                <el-button v-if="job.doc_id && job.status === 'processing'" class="stop-job-btn" type="warning" plain @click="cancelTranslationJob(job)">
                  停止翻译
                </el-button>
              </div>

              <div v-else-if="job.status === 'completed'" class="result-content">
                <el-result icon="success" title="翻译完成" :sub-title="`原文件: ${job.original_filename}`">
                  <template #extra>
                    <el-button type="primary" @click="downloadTranslatedFile(job)">
                      <el-icon><Download /></el-icon>
                      下载译文 ({{ job.translated_filename || job.original_filename }})
                    </el-button>
                  </template>
                </el-result>
              </div>

              <div v-else-if="job.status === 'error'" class="result-error">
                <el-result icon="error" title="翻译失败" :sub-title="job.error || '翻译过程中发生错误'">
                </el-result>
              </div>

              <div v-else-if="job.status === 'canceled'" class="result-error">
                <el-result icon="warning" title="已停止翻译" :sub-title="job.error || '翻译任务已停止'">
                </el-result>
              </div>
            </div>
          </div>
        </el-card>
      </div>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted, computed, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Switch, FolderOpened, Download, Sort } from '@element-plus/icons-vue'
import { knowledgeAPI, translationAPI } from '@/api'
import { extractMemoryLibraryFiles } from '@/utils/memoryLibrary'

const TRANSLATION_BATCH_STORAGE_KEY = 'translation:lastUploadBatchId'
const TRANSLATION_BATCH_EVENT = 'translation-batch-updated'
const TRANSLATION_STATS_EVENT = 'translation-stats-updated'

const engine = ref('hybrid')
const model = ref('kimi')
const sourceLang = ref('auto')
const targetLang = ref('en')

function swapLanguages() {
  if (sourceLang.value === 'auto') {
    ElMessage.info('自动识别模式下只需要选择目标语言')
    return
  }
  const tmp = sourceLang.value
  sourceLang.value = targetLang.value
  targetLang.value = tmp
}

const memoryBank = ref('')
const memoryBanks = ref([])
const memoryFileId = ref(null)
const memoryLibraryFiles = ref([])
const memoryLibraryLoading = ref(false)
const docSource = ref('upload')
const translationJobs = ref([])
const pollingTimers = new Map()
const hasActiveJobs = computed(() => translationJobs.value.some(job => job.status === 'submitting' || job.status === 'processing'))
const currentBatchId = ref('')

const fileUploadRef = ref(null)

const reviewedDocs = ref([])
const reviewedDocsLoading = ref(false)
const selectedReviewedDoc = ref(null)
const selectedReviewedRow = ref(null)
const unsupportedReviewedTypes = new Set(['dita', 'zip'])

onMounted(async () => {
  loadReviewedDocs()
  await Promise.all([loadMemoryBanks(), loadMemoryLibraryFiles()])
  await restoreLatestBatchJobs()
})

onBeforeUnmount(() => {
  for (const timer of pollingTimers.values()) {
    clearInterval(timer)
  }
  pollingTimers.clear()
})

async function loadMemoryBanks() {
  try {
    const res = await translationAPI.getMemoryBanks()
    memoryBanks.value = res.data.banks || []
  } catch (e) {
    // ignore
  }
}

async function loadMemoryLibraryFiles() {
  memoryLibraryLoading.value = true
  try {
    const res = await knowledgeAPI.getTree()
    memoryLibraryFiles.value = extractMemoryLibraryFiles(res.data || [])
  } catch (e) {
    memoryLibraryFiles.value = []
  } finally {
    memoryLibraryLoading.value = false
  }
}

function onEngineChange(val) {
  // no-op now
}

function tableRowClassName({ row }) {
  if (selectedReviewedRow.value && selectedReviewedRow.value.id === row.id) {
    return 'selected-row'
  }
  return ''
}

function selectReviewedDocRow(row) {
  if (unsupportedReviewedTypes.has(String(row?.file_type || '').toLowerCase())) {
    ElMessage.warning('当前文档格式暂不支持翻译')
    return
  }
  selectedReviewedDoc.value = row
  selectedReviewedRow.value = row
}

async function loadReviewedDocs() {
  reviewedDocsLoading.value = true
  try {
    const res = await translationAPI.getReviewedDocs()
    reviewedDocs.value = (res.data || []).filter(doc => !unsupportedReviewedTypes.has(String(doc.file_type || '').toLowerCase()))
  } catch (e) {
    ElMessage.error('加载已审核文档失败')
  } finally {
    reviewedDocsLoading.value = false
  }
}

async function translateReviewedDoc() {
  if (!selectedReviewedDoc.value) return
  if (unsupportedReviewedTypes.has(String(selectedReviewedDoc.value.file_type || '').toLowerCase())) {
    ElMessage.error('当前文档格式暂不支持翻译')
    return
  }
  const job = createJob(selectedReviewedDoc.value.filename)
  const batchId = createBatchId()
  currentBatchId.value = batchId
  sessionStorage.setItem(TRANSLATION_BATCH_STORAGE_KEY, batchId)
  localStorage.setItem(TRANSLATION_BATCH_STORAGE_KEY, batchId)
  window.dispatchEvent(new CustomEvent(TRANSLATION_BATCH_EVENT, { detail: { batchId } }))
  try {
    const res = await translationAPI.getDocument(selectedReviewedDoc.value.id)
    const content = res.data.content || ''
    const formData = new FormData()
    const blob = new Blob([content], { type: 'text/plain' })
    const fname = selectedReviewedDoc.value.filename
    formData.append('file', blob, fname)
    formData.append('engine', engine.value)
    formData.append('model', model.value)
    formData.append('source_lang', sourceLang.value)
    formData.append('target_lang', targetLang.value)
    formData.append('memory_bank', memoryBank.value || '')
    formData.append('batch_id', batchId)
    if (memoryFileId.value != null) {
      formData.append('memory_file_id', String(memoryFileId.value))
    }
    const tres = await translationAPI.translateFile(formData)
    updateJob(job.jobKey, {
      doc_id: tres.data.doc_id,
      original_filename: tres.data.original_filename || job.original_filename,
      status: 'processing',
      pollingCount: 0,
      error: ''
    })
    startPolling(job.jobKey, tres.data.doc_id)
  } catch (e) {
    const error = '提交翻译失败: ' + (e.response?.data?.detail || e.message)
    updateJob(job.jobKey, { status: 'error', error })
    ElMessage.error(error)
  }
}

function beforeFileUpload(file) {
  const ext = file.name.split('.').pop().toLowerCase()
  const allowed = ['docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt', 'pdf', 'md', 'txt', 'xlf', 'idml']
  if (!allowed.includes(ext)) {
    ElMessage.error(`不支持的文件格式: .${ext}`)
    return false
  }
  const maxSize = 50 * 1024 * 1024
  if (file.size > maxSize) {
    ElMessage.error('文件大小不能超过 50MB')
    return false
  }
  return true
}

function submitFileUpload() {
  currentBatchId.value = createBatchId()
  sessionStorage.setItem(TRANSLATION_BATCH_STORAGE_KEY, currentBatchId.value)
  localStorage.setItem(TRANSLATION_BATCH_STORAGE_KEY, currentBatchId.value)
  window.dispatchEvent(new CustomEvent(TRANSLATION_BATCH_EVENT, { detail: { batchId: currentBatchId.value } }))
  fileUploadRef.value.submit()
}

function handleFileTranslate(options) {
  const job = createJob(options.file.name)
  const batchId = currentBatchId.value || createBatchId()
  if (!currentBatchId.value) {
    currentBatchId.value = batchId
    sessionStorage.setItem(TRANSLATION_BATCH_STORAGE_KEY, batchId)
    localStorage.setItem(TRANSLATION_BATCH_STORAGE_KEY, batchId)
    window.dispatchEvent(new CustomEvent(TRANSLATION_BATCH_EVENT, { detail: { batchId } }))
  }
  const formData = new FormData()
  formData.append('file', options.file)
  formData.append('engine', engine.value)
  formData.append('model', model.value)
  formData.append('source_lang', sourceLang.value)
  formData.append('target_lang', targetLang.value)
  formData.append('memory_bank', memoryBank.value || '')
  formData.append('batch_id', batchId)
  if (memoryFileId.value != null) {
    formData.append('memory_file_id', String(memoryFileId.value))
  }

  translationAPI.translateFile(formData).then(res => {
    updateJob(job.jobKey, {
      doc_id: res.data.doc_id,
      original_filename: res.data.original_filename || job.original_filename,
      status: 'processing',
      pollingCount: 0,
      error: ''
    })
    startPolling(job.jobKey, res.data.doc_id)
  }).catch(e => {
    const error = '提交翻译失败: ' + (e.response?.data?.detail || e.message)
    updateJob(job.jobKey, { status: 'error', error })
    ElMessage.error(error)
  })
}

function createJob(filename) {
  const job = {
    jobKey: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    doc_id: null,
    original_filename: filename,
    translated_filename: '',
    download_url: '',
    status: 'submitting',
    error: '',
    pollingCount: 0
  }
  translationJobs.value = [job, ...translationJobs.value]
  return job
}

async function restoreLatestBatchJobs() {
  const batchId = sessionStorage.getItem(TRANSLATION_BATCH_STORAGE_KEY) || localStorage.getItem(TRANSLATION_BATCH_STORAGE_KEY) || ''
  if (!batchId) return

  currentBatchId.value = batchId

  try {
    const res = await translationAPI.getDocs(0, 50, batchId)
    const docs = Array.isArray(res.data) ? res.data : []
    if (docs.length === 0) return

    translationJobs.value = docs.map((doc) => ({
      jobKey: `restored-${doc.id}`,
      doc_id: doc.id,
      original_filename: doc.filename,
      translated_filename: doc.translated_filename || '',
      download_url: doc.translated_filename ? `/api/translation/download/${doc.id}` : '',
      status: doc.translated_filename
        ? (String(doc.translated_filename).startsWith('ERROR:') ? 'error' : (String(doc.translated_filename).startsWith('CANCELED:') ? 'canceled' : 'completed'))
        : 'processing',
      error: String(doc.translated_filename || '').startsWith('ERROR:')
        ? String(doc.translated_filename).slice(6)
        : (String(doc.translated_filename || '').startsWith('CANCELED:') ? String(doc.translated_filename).slice(9) : ''),
      pollingCount: 0
    }))

    for (const job of translationJobs.value) {
      if (job.status === 'processing' && job.doc_id) {
        startPolling(job.jobKey, job.doc_id)
      }
    }
  } catch (e) {
    console.error('恢复翻译任务失败', e)
  }
}

function createBatchId() {
  return `batch-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function updateJob(jobKey, patch) {
  translationJobs.value = translationJobs.value.map(job => job.jobKey === jobKey ? { ...job, ...patch } : job)
}

function startPolling(jobKey, docId) {
  stopPolling(jobKey)

  const pollOnce = async () => {
    const currentJob = translationJobs.value.find(job => job.jobKey === jobKey)
    if (!currentJob) {
      stopPolling(jobKey)
      return
    }

    updateJob(jobKey, { pollingCount: currentJob.pollingCount + 3 })
    try {
      const res = await translationAPI.getFileStatus(docId, { _ts: Date.now() })
      const statusData = res.data
      if (statusData.status === 'completed') {
        stopPolling(jobKey)
        updateJob(jobKey, {
          doc_id: docId,
          original_filename: statusData.original_filename || '',
          translated_filename: statusData.translated_filename || '',
          download_url: statusData.download_url || `/api/translation/download/${docId}`,
          status: 'completed',
          error: ''
        })
        window.dispatchEvent(new CustomEvent(TRANSLATION_STATS_EVENT, { detail: { batchId: currentBatchId.value, docId, status: 'completed' } }))
        ElMessage.success('文档翻译完成')
        return
      }

      if (statusData.status === 'error') {
        stopPolling(jobKey)
        const error = statusData.error || '翻译过程中发生错误'
        updateJob(jobKey, { status: 'error', error })
        window.dispatchEvent(new CustomEvent(TRANSLATION_STATS_EVENT, { detail: { batchId: currentBatchId.value, docId, status: 'error' } }))
        ElMessage.error(error)
        return
      }

      if (statusData.status === 'canceled') {
        stopPolling(jobKey)
        updateJob(jobKey, { status: 'canceled', error: statusData.error || '翻译任务已停止' })
        ElMessage.info(statusData.error || '翻译任务已停止')
        return
      }

      const timer = window.setTimeout(pollOnce, 3000)
      pollingTimers.set(jobKey, timer)
    } catch (e) {
      stopPolling(jobKey)
      updateJob(jobKey, { status: 'error', error: '查询翻译状态失败' })
      ElMessage.error('查询翻译状态失败')
    }
  }

  const timer = window.setTimeout(pollOnce, 3000)
  pollingTimers.set(jobKey, timer)
}

function stopPolling(jobKey) {
  const timer = pollingTimers.get(jobKey)
  if (timer) {
    clearInterval(timer)
    pollingTimers.delete(jobKey)
  }
}

function statusTagType(status) {
  if (status === 'completed') return 'success'
  if (status === 'canceled') return 'warning'
  if (status === 'error') return 'danger'
  return 'info'
}

function statusLabel(job) {
  if (job.status === 'submitting') return '提交中'
  if (job.status === 'processing') return `翻译中 ${job.pollingCount}s`
  if (job.status === 'completed') return '已完成'
  if (job.status === 'canceled') return '已停止'
  if (job.status === 'error') return '失败'
  return '等待中'
}

async function cancelTranslationJob(job) {
  if (!job?.doc_id) return

  try {
    const res = await translationAPI.cancelFileTranslation(job.doc_id)
    stopPolling(job.jobKey)
    updateJob(job.jobKey, {
      status: res.data.status === 'completed' ? 'completed' : 'canceled',
      translated_filename: res.data.translated_filename || job.translated_filename,
      download_url: res.data.download_url || job.download_url,
      error: res.data.error || '翻译任务已停止'
    })
    ElMessage.info(res.data.status === 'completed' ? '翻译已完成，无法停止' : '翻译任务已停止')
  } catch (e) {
    ElMessage.error('停止翻译失败')
  }
}

function downloadTranslatedFile(job) {
  if (!job?.download_url) return
  const link = document.createElement('a')
  link.href = job.download_url
  link.setAttribute('download', job.translated_filename || job.original_filename)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}
</script>

<style scoped>
.doc-translate-container {
  padding: 0;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 4px;
}

.page-desc {
  font-size: 14px;
  color: #6b7280;
}

.memory-library-hint {
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.5;
  margin-top: 6px;
}

.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  align-items: stretch;
}

.left-panel, .right-panel {
  display: flex;
  flex-direction: column;
}

.source-card {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.source-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.result-card {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.result-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.config-horizontal {
  margin-bottom: 16px;
}

.config-form-inline {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
}

.config-form-inline :deep(.el-form-item) {
  margin-bottom: 4px;
}

.swap-icon {
  margin: 0 4px;
  cursor: pointer;
  color: var(--el-color-primary);
  font-size: 16px;
  vertical-align: middle;
  transform: rotate(90deg);
}
.swap-icon:hover {
  color: var(--el-color-primary-light-3);
}

.card-header-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.source-tabs {
  margin-bottom: -12px;
}

.source-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.source-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

.config-card {
  margin-bottom: 16px;
}

.file-upload-area {
  text-align: center;
}

.upload-dragger :deep(.el-upload-dragger) {
  border-radius: 12px;
  border: 2px dashed #bfdbfe;
  background: #f8fafc;
  padding: 40px 20px;
}

.upload-dragger :deep(.el-upload-dragger:hover) {
  border-color: #3b82f6;
  background: #eff6ff;
}

.upload-icon {
  font-size: 40px;
  color: #3b82f6;
  margin-bottom: 12px;
}

.upload-title {
  font-size: 15px;
  color: #374151;
  margin-bottom: 6px;
}

.upload-hint {
  font-size: 13px;
  color: #9ca3af;
}

.upload-tip {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: #d97706;
}

.upload-submit-btn {
  margin-top: 16px;
  width: 100%;
}

.reviewed-area {
  min-height: 100px;
}

.loading-hint, .empty-hint {
  text-align: center;
  color: #9ca3af;
  padding: 40px 0;
  font-size: 14px;
}

.selected-doc-hint {
  margin-top: 12px;
  padding: 10px 14px;
  background: #eff6ff;
  border-radius: 8px;
  font-size: 13px;
  color: #1e40af;
  display: flex;
  align-items: center;
}

.reviewed-area :deep(.el-table .selected-row) {
  background-color: #eff6ff;
}

.result-empty {
  text-align: center;
  padding: 60px 20px;
  color: #9ca3af;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.result-loading {
  text-align: center;
  padding: 60px 20px;
  color: #6b7280;
}

.result-loading-inline {
  padding: 20px;
}

.stop-job-btn {
  margin-top: 12px;
}

.loading-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid #dbeafe;
  border-top: 3px solid #2563eb;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.result-content {
  padding: 20px 0;
}

.result-error {
  padding: 20px 0;
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.result-item {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 16px;
  background: #fff;
}

.result-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.result-item-name {
  font-size: 14px;
  font-weight: 600;
  color: #111827;
  word-break: break-all;
}

.result-item-meta {
  margin-top: 4px;
  font-size: 12px;
  color: #6b7280;
}

@media (max-width: 1024px) {
  .content-grid {
    grid-template-columns: 1fr;
  }
}
</style>
