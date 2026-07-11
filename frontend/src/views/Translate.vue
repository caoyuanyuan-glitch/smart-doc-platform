<template>
  <div class="translate-container">
    <div class="page-header">
      <h2 class="page-title">文本翻译</h2>
      <p class="page-desc">支持 AI、AI + 记忆库、仅记忆库三种模式，记忆库配置可从知识库资源库调用</p>
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
            <el-select v-model="model" placeholder="选择AI模型" style="width: 160px">
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
            <span class="card-header-title">翻译内容</span>
          </template>
          <div class="text-input-area">
            <el-input
              v-model="inputText"
              type="textarea"
              :rows="14"
              placeholder="请输入需要翻译的文本内容..."
              resize="none"
            />
            <div class="input-actions">
              <span class="char-count">{{ inputText.length }} 字符</span>
              <el-button type="primary" :loading="translating" @click="translateText" :disabled="!inputText.trim()">
                <el-icon><Switch /></el-icon>
                开始翻译
              </el-button>
            </div>
          </div>
        </el-card>
      </div>

      <div class="right-panel">
        <el-card class="result-card" shadow="never">
          <template #header>
            <div class="card-header-row">
              <span class="card-header-title">翻译结果</span>
              <div v-if="result" class="result-meta">
                <el-tag v-if="result.from_memory" type="success" size="small">来自记忆库</el-tag>
                <el-tag v-if="result.from_ai" type="warning" size="small">来自AI引擎</el-tag>
              </div>
            </div>
          </template>

          <div v-if="!result && !translating" class="result-empty">
            <el-icon class="empty-icon"><Document /></el-icon>
            <p>翻译结果将显示在这里</p>
            <p class="sub-hint">选择翻译引擎并输入内容后点击开始翻译</p>
          </div>

          <div v-if="translating" class="result-loading">
            <div class="loading-spinner"></div>
            <p>正在翻译中，请稍候...</p>
          </div>

          <div v-if="result && !translating" class="result-content">
            <el-input
              v-if="editingResult"
              v-model="translatedDraft"
              type="textarea"
              :rows="10"
              resize="none"
              class="translated-editor"
            />
            <div v-else class="result-text translated-text">{{ currentTranslatedText }}</div>
            <div class="memory-write-section">
              <span class="memory-write-label">写入目标记忆库</span>
              <el-select
                v-model="memoryWriteFileId"
                placeholder="请选择知识库管理 > 资源库 > 记忆库 下的 Excel 文件"
                filterable
                clearable
                :loading="memoryLibraryLoading"
                class="memory-write-select"
              >
                <el-option v-for="file in writableMemoryLibraryFiles" :key="file.id" :label="file.label" :value="file.id" />
              </el-select>
            </div>
            <div class="result-actions">
              <el-button v-if="!editingResult" size="small" @click="startEditResult">
                <el-icon><EditPen /></el-icon>
                编辑译文
              </el-button>
              <el-button v-if="editingResult" size="small" type="primary" @click="saveEditedResult">
                <el-icon><Check /></el-icon>
                保存修改
              </el-button>
              <el-button v-if="editingResult" size="small" @click="cancelEditResult">
                <el-icon><Close /></el-icon>
                取消编辑
              </el-button>
              <el-button size="small" type="success" :loading="writingMemory" :disabled="!canWriteMemory" @click="writeToMemoryLibrary">
                <el-icon><Plus /></el-icon>
                写入记忆库
              </el-button>
              <el-button size="small" @click="copyResult">
                <el-icon><CopyDocument /></el-icon>
                复制译文
              </el-button>
              <el-button size="small" @click="downloadResult">
                <el-icon><Download /></el-icon>
                下载译文
              </el-button>
            </div>
            <p class="memory-write-hint">写入记忆库会追加到【知识库管理】>【资源库】>【记忆库】下当前选中的 Excel 文件。</p>
            <p v-if="writableMemoryLibraryFiles.length === 0" class="memory-write-warning">当前路径下还没有可写入的 Excel 记忆库文件。</p>
            <p v-else-if="!memoryWriteFileId" class="memory-write-warning">请选择一个 Excel 记忆库文件后再写入。</p>
          </div>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Switch, Document, CopyDocument, Download, EditPen, Check, Close, Plus, Sort } from '@element-plus/icons-vue'
import { knowledgeAPI, translationAPI } from '@/api'
import { extractMemoryLibraryFiles } from '@/utils/memoryLibrary'

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
const memoryWriteFileId = ref(null)
const memoryLibraryFiles = ref([])
const memoryLibraryLoading = ref(false)
const inputText = ref('')
const translating = ref(false)
const result = ref(null)
const editingResult = ref(false)
const translatedDraft = ref('')
const writingMemory = ref(false)
const writableMemoryFileTypes = ['xlsx', 'xlsm', 'xltx', 'xltm']

const writableMemoryLibraryFiles = computed(() => {
  return memoryLibraryFiles.value.filter(file => writableMemoryFileTypes.includes(String(file.fileType || '').toLowerCase()))
})
const selectedMemoryWriteFile = computed(() => {
  const currentId = memoryWriteFileId.value
  if (currentId == null || currentId === '') {
    return null
  }
  return writableMemoryLibraryFiles.value.find(file => String(file.id) === String(currentId)) || null
})
const canWriteMemory = computed(() => Boolean(selectedMemoryWriteFile.value))
const currentTranslatedText = computed(() => editingResult.value ? translatedDraft.value : (result.value?.translated || ''))

onMounted(async () => {
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
    if (!memoryWriteFileId.value && memoryFileId.value != null) {
      const matchedFile = memoryLibraryFiles.value.find(file => String(file.id) === String(memoryFileId.value))
      if (matchedFile && writableMemoryFileTypes.includes(String(matchedFile.fileType || '').toLowerCase())) {
        memoryWriteFileId.value = matchedFile.id
      }
    }
  } catch (e) {
    memoryLibraryFiles.value = []
  } finally {
    memoryLibraryLoading.value = false
  }
}

function onEngineChange(val) {
  // no-op now
}

async function translateText() {
  if (!inputText.value.trim()) {
    ElMessage.warning('请输入翻译内容')
    return
  }
  translating.value = true
  result.value = null
  try {
    const res = await translationAPI.translate({
      content: inputText.value,
      engine: engine.value,
      model: model.value,
      source_lang: sourceLang.value,
      target_lang: targetLang.value,
      memory_bank: memoryBank.value || null,
      memory_file_id: memoryFileId.value || null
    })
    result.value = res.data
    translatedDraft.value = res.data.translated || ''
    editingResult.value = false
    if (!memoryWriteFileId.value && memoryFileId.value != null) {
      const matchedFile = writableMemoryLibraryFiles.value.find(file => String(file.id) === String(memoryFileId.value))
      if (matchedFile) {
        memoryWriteFileId.value = matchedFile.id
      }
    }
    ElMessage.success('翻译完成')
  } catch (e) {
    ElMessage.error('翻译失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    translating.value = false
  }
}

function startEditResult() {
  translatedDraft.value = result.value?.translated || ''
  editingResult.value = true
}

function saveEditedResult() {
  const nextText = translatedDraft.value.trim()
  if (!nextText) {
    ElMessage.warning('译文内容不能为空')
    return
  }
  result.value = {
    ...result.value,
    translated: translatedDraft.value
  }
  editingResult.value = false
  ElMessage.success('译文修改已保存')
}

function cancelEditResult() {
  translatedDraft.value = result.value?.translated || ''
  editingResult.value = false
}

async function writeToMemoryLibrary() {
  if (!result.value?.original?.trim()) {
    ElMessage.warning('当前没有可写入的原文')
    return
  }
  if (!memoryWriteFileId.value) {
    ElMessage.warning('请先选择记忆库配置文件')
    return
  }
  if (!selectedMemoryWriteFile.value) {
    ElMessage.warning('请选择可写入的 Excel 记忆库文件')
    return
  }

  const translatedText = currentTranslatedText.value.trim()
  if (!translatedText) {
    ElMessage.warning('当前没有可写入的译文')
    return
  }

  writingMemory.value = true
  try {
    await translationAPI.writeMemoryFileEntry({
      memory_file_id: memoryWriteFileId.value,
      source_text: result.value.original,
      translated_text: currentTranslatedText.value,
      source_lang: sourceLang.value,
      target_lang: targetLang.value
    })
    ElMessage.success('已写入选中的记忆库 Excel 文件')
  } catch (e) {
    ElMessage.error('写入记忆库失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    writingMemory.value = false
  }
}

function copyResult() {
  if (currentTranslatedText.value) {
    navigator.clipboard.writeText(currentTranslatedText.value).then(() => {
      ElMessage.success('已复制到剪贴板')
    }).catch(() => {
      ElMessage.error('复制失败')
    })
  }
}

function downloadResult() {
  if (currentTranslatedText.value) {
    const blob = new Blob([currentTranslatedText.value], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `translation_${Date.now()}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }
}
</script>

<style scoped>
.translate-container {
  padding: 0;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 16px;
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
  overflow: hidden;
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

.text-input-area {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.text-input-area :deep(.el-textarea) {
  flex: 1;
}

.text-input-area :deep(.el-textarea__inner) {
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.7;
  height: 100% !important;
  min-height: 320px;
}

.input-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}

.char-count {
  font-size: 13px;
  color: #9ca3af;
}

.result-meta {
  display: flex;
  gap: 6px;
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

.sub-hint {
  font-size: 13px;
  margin-top: 6px;
  color: #c0c4cc;
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
  flex: 1;
  display: flex;
  flex-direction: column;
}

.translated-editor :deep(.el-textarea__inner) {
  min-height: 220px;
  border-radius: 8px;
  line-height: 1.8;
}

.translated-text {
  background: #f8fafc;
  border-radius: 8px;
  padding: 16px;
  font-size: 14px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 420px;
  overflow-y: auto;
  color: #1f2937;
  flex: 1;
}

.memory-write-section {
  margin-top: 16px;
}

.memory-write-label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  color: #374151;
  font-weight: 500;
}

.memory-write-select {
  width: 100%;
}

.result-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 16px;
}

.memory-write-hint {
  margin-top: 12px;
  font-size: 12px;
  line-height: 1.6;
  color: #64748b;
}

.memory-write-warning {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: #d97706;
}

.memory-library-hint {
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.5;
  margin-top: 6px;
}

@media (max-width: 1024px) {
  .content-grid {
    grid-template-columns: 1fr;
  }
}
</style>
