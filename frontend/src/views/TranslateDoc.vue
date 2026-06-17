<template>
  <div class="doc-translate-container">
    <div class="page-header">
      <h2 class="page-title">文档翻译</h2>
      <p class="page-desc">上传文档或从已审核文档中选取，AI翻译后下载同格式译文</p>
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
            <el-form-item label="AI 模型" v-if="engine !== 'memory'">
              <el-select v-model="model" style="width: 100%">
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
              accept=".zip,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.pdf,.md,.txt,.dita,.xlf"
            >
              <el-icon class="upload-icon"><UploadFilled /></el-icon>
              <div class="upload-text">
                <p class="upload-title">将文件拖到此处，或点击上传</p>
                <p class="upload-hint">支持 DITA ZIP、Word、Excel、PPT、PDF、Markdown 格式</p>
              </div>
            </el-upload>
            <el-button class="upload-submit-btn" type="primary" :loading="translating" @click="submitFileUpload">
              <el-icon><Switch /></el-icon>
              上传并翻译
            </el-button>
          </div>

          <div v-if="docSource === 'reviewed'" class="reviewed-area">
            <div v-if="reviewedDocsLoading" class="loading-hint">加载已审核文档列表...</div>
            <div v-else-if="reviewedDocs.length === 0" class="empty-hint">暂无已审核完成的文档</div>
            <el-table v-else :data="reviewedDocs" highlight-current-row
              :row-class-name="tableRowClassName" max-height="320" @row-click="selectReviewedDocRow">
              <el-table-column prop="filename" label="文档名称" min-width="180" />
              <el-table-column prop="file_type" label="类型" width="80" />
              <el-table-column prop="preview" label="预览" min-width="200" show-overflow-tooltip />
            </el-table>
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
            <p>正在翻译文档，请稍候...</p>
          </div>

          <div v-if="result && !translating" class="result-content">
            <el-result icon="success" title="翻译完成" :sub-title="`原文件: ${result.original_filename}`">
              <template #extra>
                <el-button type="primary" @click="downloadTranslatedFile">
                  <el-icon><Download /></el-icon>
                  下载译文 ({{ result.translated_filename }})
                </el-button>
              </template>
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
import { translationAPI } from '@/api'

const engine = ref('hybrid')
const model = ref('qwen')
const sourceLang = ref('zh')
const targetLang = ref('en')
const docSource = ref('upload')
const translating = ref(false)
const result = ref(null)

const fileUploadRef = ref(null)
const selectedFile = ref(null)

const reviewedDocs = ref([])
const reviewedDocsLoading = ref(false)
const selectedReviewedDoc = ref(null)
const selectedReviewedRow = ref(null)

onMounted(() => {
  loadReviewedDocs()
})

function onEngineChange(val) {
  if (val === 'memory') {
    model.value = 'qwen'
  }
}

function tableRowClassName({ row }) {
  if (selectedReviewedRow.value && selectedReviewedRow.value.id === row.id) {
    return 'selected-row'
  }
  return ''
}

function selectReviewedDocRow(row) {
  selectedReviewedDoc.value = row
  selectedReviewedRow.value = row
}

async function loadReviewedDocs() {
  reviewedDocsLoading.value = true
  try {
    const res = await translationAPI.getReviewedDocs()
    reviewedDocs.value = res.data || []
  } catch (e) {
    ElMessage.error('加载已审核文档失败')
  } finally {
    reviewedDocsLoading.value = false
  }
}

async function translateReviewedDoc() {
  if (!selectedReviewedDoc.value) return
  translating.value = true
  result.value = null
  try {
    const res = await translationAPI.getDocument(selectedReviewedDoc.value.id)
    const content = res.data.content || ''
    const formData = new FormData()
    const blob = new Blob([content], { type: 'text/plain' })
    const fname = selectedReviewedDoc.value.filename
    formData.append('file', blob, fname)
    formData.append('engine', engine.value)
    formData.append('model', engine.value === 'memory' ? 'qwen' : model.value)
    formData.append('source_lang', sourceLang.value)
    formData.append('target_lang', targetLang.value)
    const tres = await translationAPI.translateFile(formData)
    result.value = tres.data
    ElMessage.success('文档翻译完成')
  } catch (e) {
    ElMessage.error('翻译失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    translating.value = false
  }
}

function onFileChange(file) {
  selectedFile.value = file
}

function beforeFileUpload(file) {
  const ext = file.name.split('.').pop().toLowerCase()
  const allowed = ['zip', 'docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt', 'pdf', 'md', 'txt', 'dita', 'xlf']
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
  const formData = new FormData()
  formData.append('file', options.file)
  formData.append('engine', engine.value)
  formData.append('model', engine.value === 'memory' ? 'qwen' : model.value)
  formData.append('source_lang', sourceLang.value)
  formData.append('target_lang', targetLang.value)

  translationAPI.translateFile(formData).then(res => {
    result.value = res.data
    ElMessage.success('文档翻译完成')
  }).catch(e => {
    ElMessage.error('文件翻译失败: ' + (e.response?.data?.detail || e.message))
  }).finally(() => {
    translating.value = false
  })
}

function downloadTranslatedFile() {
  if (result.value?.download_url) {
    window.open(result.value.download_url, '_blank')
  }
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

@media (max-width: 1024px) {
  .content-grid {
    grid-template-columns: 1fr;
  }
}
</style>
