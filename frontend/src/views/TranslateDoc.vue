<template>
  <div class="doc-translate-container">
    <div class="page-header">
      <h2 class="page-title">文档翻译</h2>
      <p class="page-desc">支持 AI、AI + 记忆库、仅记忆库三种模式，可翻译 Word、Excel、PPT、PDF、Markdown、TXT、XLF 文档</p>
    </div>

    <div class="content-grid">
      <div class="left-panel">
        <el-card class="config-card" shadow="never">
          <template #header>
            <span class="card-header-title">翻译配置</span>
          </template>
          <el-form label-width="90px" label-position="left" size="default">
            <el-form-item label="翻译引擎">
              <el-radio-group v-model="engine" @change="onEngineChange">
                <el-radio-button value="hybrid">AI + 记忆库</el-radio-button>
                <el-radio-button value="ai">仅 AI</el-radio-button>
                <el-radio-button value="memory">仅记忆库</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="记忆库标签" v-if="engine !== 'ai'">
              <el-select v-model="memoryBank" placeholder="全部记忆库" clearable style="width: 100%">
                <el-option label="全部记忆库" value="" />
                <el-option v-for="bank in memoryBanks" :key="bank" :label="bank" :value="bank" />
              </el-select>
            </el-form-item>
            <el-form-item label="记忆库配置" v-if="engine !== 'ai'">
              <el-select
                v-model="memoryFileId"
                placeholder="从知识库 / 资源库 / 记忆库选择，可不选"
                clearable
                filterable
                :loading="memoryLibraryLoading"
                style="width: 100%"
              >
                <el-option
                  v-for="file in memoryLibraryFiles"
                  :key="file.id"
                  :label="file.label"
                  :value="file.id"
                />
              </el-select>
              <div class="memory-library-hint">仅读取知识库下“资源库 / 记忆库”中的文件，当前配置可留空。</div>
            </el-form-item>
            <el-form-item label="AI 模型" v-if="engine !== 'memory'">
              <el-select v-model="model" style="width: 100%">
                <el-option label="Kimi (Moonshot)" value="kimi" />
                <el-option label="Qwen3.6-Plus" value="qwen" />
                <el-option label="DeepSeek Chat" value="deepseek" />
              </el-select>
            </el-form-item>
            <el-form-item label="源语言">
              <el-select v-model="sourceLang" style="width: 100%">
                <el-option label="中文" value="zh" />
                <el-option label="英文" value="en" />
              </el-select>
            </el-form-item>
            <el-form-item label="目标语言">
              <el-select v-model="targetLang" style="width: 100%">
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
              ref="fileUploadRef"
              :on-change="onFileChange"
              accept=".docx,.doc,.xlsx,.xls,.pptx,.ppt,.pdf,.md,.txt,.xlf"
            >
              <el-icon class="upload-icon"><UploadFilled /></el-icon>
              <div class="upload-text">
                <p class="upload-title">将文件拖到此处，或点击上传</p>
                <p class="upload-hint">支持 Word、Excel、PPT、PDF、Markdown、XLF 格式</p>
                <p class="upload-tip">温馨提示：PDF直接翻译易出现排版错乱。建议先转换为Word格式上传，可获得更好的排版效果。</p>
              </div>
            </el-upload>
            <el-button class="upload-submit-btn" type="primary" :loading="translating" @click="submitFileUpload">
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
              <el-button type="primary" size="small" :loading="translating" @click="translateReviewedDoc" style="margin-left: 12px">
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

          <div v-if="!result && !translating" class="result-empty">
            <el-icon class="empty-icon"><FolderOpened /></el-icon>
            <p>选择文档并翻译后，可在此下载译文</p>
          </div>

          <div v-if="translating" class="result-loading">
            <div class="loading-spinner"></div>
            <p>{{ pollingStatus ? `正在翻译... (${pollingCount}s)` : '正在提交翻译任务...' }}</p>
          </div>

          <div v-if="result && !translating" class="result-content">
            <el-result icon="success" title="翻译完成" :sub-title="`原文件: ${result.original_filename}`">
              <template #extra>
                <el-button type="primary" @click="downloadTranslatedFile">
                  <el-icon><Download /></el-icon>
                  下载译文 ({{ result.translated_filename || result.original_filename }})
                </el-button>
              </template>
            </el-result>
          </div>

          <div v-if="pollError" class="result-error">
            <el-result icon="error" title="翻译失败" :sub-title="pollError">
            </el-result>
          </div>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Switch, FolderOpened, Download } from '@element-plus/icons-vue'
import { knowledgeAPI, translationAPI } from '@/api'
import { extractMemoryLibraryFiles } from '@/utils/memoryLibrary'

const engine = ref('hybrid')
const model = ref('kimi')
const sourceLang = ref('zh')
const targetLang = ref('en')
const memoryBank = ref('')
const memoryBanks = ref([])
const memoryFileId = ref(null)
const memoryLibraryFiles = ref([])
const memoryLibraryLoading = ref(false)
const docSource = ref('upload')
const translating = ref(false)
const result = ref(null)
const pollingStatus = ref(false)
const pollingCount = ref(0)
const pollError = ref('')
let pollTimer = null

const fileUploadRef = ref(null)
const selectedFile = ref(null)

const reviewedDocs = ref([])
const reviewedDocsLoading = ref(false)
const selectedReviewedDoc = ref(null)
const selectedReviewedRow = ref(null)
const unsupportedReviewedTypes = new Set(['dita', 'zip'])

onMounted(async () => {
  loadReviewedDocs()
  await Promise.all([loadMemoryBanks(), loadMemoryLibraryFiles()])
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
  translating.value = true
  result.value = null
  pollError.value = ''
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
    if (memoryFileId.value != null) {
      formData.append('memory_file_id', String(memoryFileId.value))
    }
    const tres = await translationAPI.translateFile(formData)
    startPolling(tres.data.doc_id)
  } catch (e) {
    translating.value = false
    pollError.value = '提交翻译失败: ' + (e.response?.data?.detail || e.message)
    ElMessage.error(pollError.value)
  }
}

function onFileChange(file) {
  selectedFile.value = file
}

function beforeFileUpload(file) {
  const ext = file.name.split('.').pop().toLowerCase()
  const allowed = ['docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt', 'pdf', 'md', 'txt', 'xlf']
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
  fileUploadRef.value.submit()
}

function handleFileTranslate(options) {
  translating.value = true
  result.value = null
  pollError.value = ''
  const formData = new FormData()
  formData.append('file', options.file)
  formData.append('engine', engine.value)
  formData.append('model', model.value)
  formData.append('source_lang', sourceLang.value)
  formData.append('target_lang', targetLang.value)
  formData.append('memory_bank', memoryBank.value || '')
  if (memoryFileId.value != null) {
    formData.append('memory_file_id', String(memoryFileId.value))
  }

  translationAPI.translateFile(formData).then(res => {
    startPolling(res.data.doc_id)
  }).catch(e => {
    translating.value = false
    pollError.value = '提交翻译失败: ' + (e.response?.data?.detail || e.message)
    ElMessage.error(pollError.value)
  })
}

function startPolling(docId) {
  stopPolling()
  pollingStatus.value = true
  pollingCount.value = 0
  pollError.value = ''

  pollTimer = setInterval(async () => {
    pollingCount.value++
    try {
      const res = await translationAPI.getFileStatus(docId)
      const statusData = res.data
      if (statusData.status === 'completed') {
        stopPolling()
        translating.value = false
        result.value = {
          doc_id: docId,
          original_filename: statusData.original_filename || '',
          translated_filename: statusData.translated_filename || '',
          download_url: statusData.download_url || `/api/translation/download/${docId}`
        }
        ElMessage.success('文档翻译完成')
      } else if (statusData.status === 'error') {
        stopPolling()
        translating.value = false
        pollError.value = statusData.error || '翻译过程中发生错误'
        ElMessage.error(pollError.value)
      }
    } catch (e) {
      stopPolling()
      translating.value = false
      pollError.value = '查询翻译状态失败'
      ElMessage.error(pollError.value)
    }
  }, 3000)
}

function stopPolling() {
  pollingStatus.value = false
  pollingCount.value = 0
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function downloadTranslatedFile() {
  if (!result.value?.download_url) return
  const link = document.createElement('a')
  link.href = result.value.download_url
  link.setAttribute('download', result.value.translated_filename || result.value.original_filename)
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
  align-items: start;
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

@media (max-width: 1024px) {
  .content-grid {
    grid-template-columns: 1fr;
  }
}
</style>
