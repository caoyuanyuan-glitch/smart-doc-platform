<template>
  <div class="polish-container">
    <div v-if="currentView === 'document'">
      <h2 class="page-title">文档润色</h2>
      
      <div class="panel">
        <div class="form-item">
          <label class="form-label">句式表达文件</label>
          <div class="input-with-button">
            <el-input v-model="formData.sentenceFile" readonly placeholder="选择知识库中的句式表达文件" />
            <el-button type="primary" @click="openFilePicker('sentenceFile', 'knowledge')">选择文件</el-button>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">术语库文件</label>
          <div class="input-with-button">
            <el-input v-model="formData.terminologyFile" readonly placeholder="选择知识库中的术语库文件" />
            <el-button type="primary" @click="openFilePicker('terminologyFile', 'knowledge')">选择文件</el-button>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">待润色文件</label>
          <div class="input-with-button">
            <el-input v-model="formData.sourceFile" readonly placeholder="选择本地文件" />
            <el-button type="primary" @click="openLocalFilePicker()">选择文件</el-button>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">输出文件路径</label>
          <div class="input-with-button">
            <el-input v-model="formData.outputPath" readonly placeholder="已润色文档（默认）" />
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">润色要求</label>
          <el-input v-model="formData.requirements" type="textarea" :rows="3" placeholder="请输入额外的润色要求（选填）" />
        </div>
      </div>

      <div class="button-group">
        <el-button @click="resetForm">重置</el-button>
        <el-button type="primary" :loading="loading" @click="submitPolish">提交</el-button>
      </div>

      <div v-if="polishProgress > 0 && polishProgress < 100" class="progress-card">
        <div class="progress-header">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span class="progress-msg">{{ polishProgressMsg || '润色中...' }}</span>
          <span class="progress-pct">{{ polishProgress }}%</span>
        </div>
        <el-progress :percentage="polishProgress" :stroke-width="8" :show-text="false" />
      </div>
    </div>

    <div v-if="currentView === 'text'">
      <div class="page-title-row">
        <h2 class="page-title">智能润色</h2>
        <div class="stats-card" v-if="feedbackStats.totalCount > 0">
          <span class="stats-label">累计润色准确率</span>
          <span class="stats-value">{{ feedbackStats.averageAccuracy }}%</span>
          <span class="stats-sub">(共 {{ feedbackStats.totalCount }} 次)</span>
        </div>
      </div>

      <div class="panel">
        <div class="form-item">
          <label class="form-label">句式表达文件</label>
          <div class="input-with-button">
            <el-input v-model="textSentenceFileName" readonly placeholder="选择知识库中的句式表达文件（留空则加载全部）" />
            <el-button type="primary" @click="openTextSentencePicker">选择文件</el-button>
            <el-button v-if="textSentenceFileId" size="small" @click="clearTextSentenceFile">清除</el-button>
          </div>
        </div>
        <div class="form-item">
          <label class="form-label">术语库文件</label>
          <div class="input-with-button">
            <el-input v-model="textTerminologyFileName" readonly placeholder="选择知识库中的术语库文件（留空则使用数据库术语）" />
            <el-button type="primary" @click="openTextTerminologyPicker">选择文件</el-button>
            <el-button v-if="textTerminologyFileId" size="small" @click="clearTextTerminologyFile">清除</el-button>
          </div>
        </div>
        <div class="panel-header">
          <span>请输入需要润色的文本</span>
          <div class="panel-actions">
            <el-button type="primary" size="small" :loading="loading" @click="doPolish">开始润色</el-button>
            <el-button size="small" @click="clearAll">清空</el-button>
          </div>
        </div>
        <el-input
          v-model="originalText"
          type="textarea"
          :rows="10"
          placeholder="请输入需要润色的文本..."
        />
      </div>

      <div v-if="result" class="panel">
        <div class="panel-header">
          <span>润色结果</span>
          <div class="panel-actions">
            <el-tag type="info" size="small">修改 {{ result.changes }} 处</el-tag>
            <el-button size="small" @click="copyResult">复制结果</el-button>
            <el-button size="small" @click="downloadResult">导出文档</el-button>
          </div>
        </div>
        <div class="result-grid">
          <div class="result-col">
            <div class="col-title"><span class="dot dot-blue"></span>原文</div>
            <div class="col-content">{{ result.original }}</div>
          </div>
          <div class="result-col">
            <div class="col-title"><span class="dot dot-green"></span>润色结果</div>
            <div class="col-content">{{ result.polished }}</div>
          </div>
        </div>
      </div>

      <div v-if="result" class="panel feedback-panel">
        <div class="panel-header">
          <span>润色反馈</span>
        </div>
        <div class="form-item">
          <label class="form-label">准确率评分 (0-100%)</label>
          <el-slider v-model="feedbackAccuracy" :min="0" :max="100" :step="5" show-input />
        </div>
        <div class="form-item">
          <label class="form-label">需要修正的词语</label>
          <el-input
            v-model="feedbackCorrections"
            type="textarea"
            :rows="4"
            placeholder="每行一条，格式：非标准词 → 标准词&#10;例如：&#10;移液枪 → 移液器&#10;样品 → 样本"
          />
        </div>
        <div class="form-item">
          <label class="form-label">写入目标</label>
          <el-radio-group v-model="feedbackTarget">
            <el-radio value="terminology">术语库（数据库）</el-radio>
            <el-radio value="sentence_guide">句式清单（文件）</el-radio>
          </el-radio-group>
        </div>
        <div class="form-item" style="text-align: right">
          <el-button type="primary" :loading="feedbackLoading" @click="submitFeedback">提交反馈</el-button>
        </div>
      </div>
    </div>

    <input
      ref="localFileInputRef"
      type="file"
      style="display: none"
      accept=".txt,.md,.docx"
      @change="onLocalFileSelected"
    />

    <el-dialog v-model="filePickerVisible" title="从知识库选择文件" width="480px">
      <div class="file-picker-content">
        <el-tree
          ref="treeRef"
          :data="knowledgeTree"
          :props="{ label: 'name', children: 'children' }"
          node-key="id"
          :highlight-current="true"
          :expand-on-click-node="false"
          @node-click="onTreeNodeClick"
        >
          <template #default="{ node, data }">
            <div class="tree-node-content">
              <span class="node-icon">{{ data.file_path ? '📄' : '📁' }}</span>
              <span>{{ node.label }}</span>
            </div>
          </template>
        </el-tree>
        <div v-if="selectedKnowledgeFile" class="selected-info">
          已选择：{{ selectedKnowledgeFile.name }}
        </div>
      </div>
      <template #footer>
        <el-button @click="filePickerVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmKnowledgeFile" :disabled="!selectedKnowledgeFile">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { polishAPI, knowledgeAPI } from '@/api'
import { Loading } from '@element-plus/icons-vue'

const route = useRoute()
const localFileInputRef = ref(null)
const filePickerVisible = ref(false)
const knowledgeTree = ref([])
const selectedKnowledgeFile = ref(null)
const currentPickerField = ref(null)

const originalText = ref('')
const textSentenceFileName = ref('')
const textSentenceFileId = ref(null)
const textTerminologyFileName = ref('')
const textTerminologyFileId = ref(null)
const result = ref(null)
const docResult = ref(null)
const loading = ref(false)
const polishProgress = ref(0)
const polishProgressMsg = ref('')
// 反馈相关
const feedbackAccuracy = ref(80)
const feedbackCorrections = ref('')
const feedbackTarget = ref('terminology')
const feedbackLoading = ref(false)
const feedbackStats = ref({ totalCount: 0, averageAccuracy: 0 })

const formData = ref({
  sentenceFile: '',
  terminologyFile: '',
  sourceFile: '',
  outputPath: '已润色文档',
  requirements: ''
})

const currentView = computed(() => (route.path === '/polish/document' ? 'document' : 'text'))

let pendingLocalFile = null

function openFilePicker(field, type) {
  currentPickerField.value = field
  if (type === 'knowledge') {
    loadKnowledgeTree()
    selectedKnowledgeFile.value = null
    filePickerVisible.value = true
  }
}

function openTextSentencePicker() {
  openFilePicker('textSentenceFile', 'knowledge')
}

function openTextTerminologyPicker() {
  openFilePicker('textTerminologyFile', 'knowledge')
}

function clearTextSentenceFile() {
  textSentenceFileName.value = ''
  textSentenceFileId.value = null
}

function clearTextTerminologyFile() {
  textTerminologyFileName.value = ''
  textTerminologyFileId.value = null
}

async function loadKnowledgeTree() {
  try {
    const resp = await knowledgeAPI.getTree()
    const rawData = resp.data || []
    knowledgeTree.value = flattenTree(rawData)
  } catch (e) {
    ElMessage.error('加载知识库失败')
  }
}

function flattenTree(nodes) {
  return nodes.map(node => {
    const files = (node.files || []).map(f => ({
      ...f,
      isFile: true,
      parentFolder: node.name
    }))
    const children = flattenTree(node.children || [])
    return {
      ...node,
      children: [...files, ...children]
    }
  })
}

function onTreeNodeClick(data) {
  if (data.file_path) {
    selectedKnowledgeFile.value = data
  } else {
    selectedKnowledgeFile.value = null
  }
}

function confirmKnowledgeFile() {
  if (selectedKnowledgeFile.value && currentPickerField.value) {
    if (currentPickerField.value === 'textSentenceFile') {
      textSentenceFileName.value = selectedKnowledgeFile.value.name
      textSentenceFileId.value = selectedKnowledgeFile.value.id
    } else if (currentPickerField.value === 'textTerminologyFile') {
      textTerminologyFileName.value = selectedKnowledgeFile.value.name
      textTerminologyFileId.value = selectedKnowledgeFile.value.id
    } else {
      formData.value[currentPickerField.value] = selectedKnowledgeFile.value.name
      formData.value[currentPickerField.value + 'Id'] = selectedKnowledgeFile.value.id
    }
    filePickerVisible.value = false
    selectedKnowledgeFile.value = null
  }
}

function openLocalFilePicker() {
  currentPickerField.value = 'sourceFile'
  localFileInputRef.value?.click()
}

function onLocalFileSelected(event) {
  const file = event.target.files?.[0]
  if (file) {
    pendingLocalFile = file
    formData.value.sourceFile = file.name
  }
  if (localFileInputRef.value) {
    localFileInputRef.value.value = ''
  }
}

async function submitPolish() {
  if (!pendingLocalFile) {
    ElMessage.warning('请选择待润色文件')
    return
  }
  
  loading.value = true
  polishProgress.value = 0
  polishProgressMsg.value = '提交中...'
  
  const payload = new FormData()
  payload.append('file', pendingLocalFile)
  if (formData.value.sentenceFileId) {
    payload.append('sentence_file_id', formData.value.sentenceFileId)
  }
  if (formData.value.terminologyFileId) {
    payload.append('terminology_file_id', formData.value.terminologyFileId)
  }
  if (formData.value.requirements) {
    payload.append('requirements', formData.value.requirements)
  }
  
  try {
    const resp = await polishAPI.analyzeFile(payload)
    const data = resp.data || {}
    
    // 后端同步返回完整结果，直接使用
    polishProgress.value = 100
    polishProgressMsg.value = '润色完成'
    docResult.value = {
      id: data.id,
      original: data.original || '',
      polished: data.polished || '',
      changes: (data.changes || []).length,
      changeDetails: data.changes || [],
      reportFile: data.report_file || data.reportFile,
      download_filename: data.download_filename,
      file_type: data.file_type
    }
    ElMessage.success('润色成功')
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error(`润色失败：${errorMsg}`)
    polishProgress.value = 0
  } finally {
    loading.value = false
    pendingLocalFile = null
    formData.value.sourceFile = ''
  }
}

function resetForm() {
  formData.value = {
    sentenceFile: '',
    terminologyFile: '',
    sourceFile: '',
    outputPath: '已润色文档',
    requirements: ''
  }
  pendingLocalFile = null
  selectedKnowledgeFile.value = null
  docResult.value = null
}

function downloadPolishedDoc() {
  if (!docResult.value) {
    ElMessage.warning('暂无润色结果')
    return
  }
  // 如果后端已保存 DOCX 文件，通过 API 下载原始文件
  if (docResult.value.id) {
    const downloadName = docResult.value.download_filename || 'polished_document.docx'
    polishAPI.downloadPolishedFile(docResult.value.id, downloadName)
    return
  }
  // 纯文本结果 fallback
  const ext = docResult.value.fileType === 'docx' ? '.docx' : '.txt'
  const blob = new Blob([docResult.value.polished], { type: 'application/octet-stream' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `polished_document${ext}`
  a.click()
  URL.revokeObjectURL(url)
}

function downloadReport() {
  if (!docResult.value || !docResult.value.reportFile || !docResult.value.id) {
    ElMessage.warning('暂无润色报告')
    return
  }
  polishAPI.downloadPolishedReport(docResult.value.id, docResult.value.reportFile)
}

async function doPolish() {
  if (!originalText.value.trim()) {
    ElMessage.info('请先输入需要润色的文本')
    return
  }
  loading.value = true
  try {
    const resp = await polishAPI.text(originalText.value, textSentenceFileId.value, textTerminologyFileId.value)
    const data = resp.data || {}
    result.value = {
      original: data.original || originalText.value,
      polished: data.polished || data.original || originalText.value,
      changes: data.changes?.length || 0
    }
    if (!data.polished || data.polished === data.original) {
      ElMessage.info('润色完成，未检测到需要修改的内容')
    } else {
      ElMessage.success('润色完成')
    }
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error(`润色失败：${errorMsg}`)
    result.value = null
  } finally {
    loading.value = false
  }
}

function clearAll() {
  originalText.value = ''
  result.value = null
  textSentenceFileName.value = ''
  textSentenceFileId.value = null
  feedbackAccuracy.value = 80
  feedbackCorrections.value = ''
  feedbackTarget.value = 'terminology'
}

function copyResult() {
  navigator.clipboard.writeText(result.value.polished).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => ElMessage.info('复制失败，请手动复制'))
}

function downloadResult() {
  const blob = new Blob([result.value.polished], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'polished_document.txt'
  a.click()
  URL.revokeObjectURL(url)
}

async function submitFeedback() {
  if (!result.value) {
    ElMessage.warning('请先完成润色再提交反馈')
    return
  }
  feedbackLoading.value = true
  try {
    const resp = await polishAPI.submitFeedback(
      result.value.original,
      result.value.polished,
      feedbackAccuracy.value,
      feedbackCorrections.value,
      feedbackTarget.value
    )
    const data = resp.data || {}
    const targetName = feedbackTarget.value === 'terminology' ? '术语库' : '句式清单'
    if (data.processed_count > 0) {
      ElMessage.success(`反馈已提交，已将 ${data.processed_count} 条修正写入${targetName}`)
    } else {
      ElMessage.success('反馈已提交')
    }
    feedbackCorrections.value = ''
    // 刷新准确率统计
    await loadFeedbackStats()
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error(`反馈失败：${errorMsg}`)
  } finally {
    feedbackLoading.value = false
  }
}

async function loadFeedbackStats() {
  try {
    const resp = await polishAPI.getFeedbackStats()
    feedbackStats.value = resp.data || { totalCount: 0, averageAccuracy: 0 }
  } catch (e) {
    // 静默失败，不影响主流程
  }
}

onMounted(() => {
  loadKnowledgeTree()
  loadFeedbackStats()
})
</script>

<style scoped>
.polish-container { 
  padding: 0; 
  max-width: 900px;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 0;
}

.page-title-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.stats-card {
  display: flex;
  align-items: center;
  gap: 6px;
  background: linear-gradient(135deg, #ecfdf5, #d1fae5);
  border: 1px solid #6ee7b7;
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 13px;
}

.stats-label {
  color: #065f46;
  font-weight: 500;
}

.stats-value {
  color: #059669;
  font-size: 18px;
  font-weight: 700;
}

.stats-sub {
  color: #6b7280;
  font-size: 12px;
}

.panel {
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
  font-weight: 600;
  color: #1f2937;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.form-item { margin-bottom: 16px; }

.form-label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
  color: #374151;
  font-size: 14px;
}

.input-with-button {
  display: flex;
  gap: 8px;
  align-items: center;
}

.input-with-button .el-input {
  flex: 1;
  min-width: 0;
}

.button-group {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}

.result-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.result-col {
  background: #fafbfc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.col-title {
  padding: 10px 16px;
  background: #fff;
  font-weight: 500;
  color: #374151;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  gap: 8px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.dot-blue { background: #3b82f6; }
.dot-green { background: #10b981; }

.col-content {
  padding: 16px;
  line-height: 1.8;
  color: #374151;
  font-size: 14px;
  min-height: 200px;
  white-space: pre-wrap;
}

.changes-table {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #e5e7eb;
}

.changes-title {
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: #374151;
}

.file-picker-content {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px;
}

.tree-node-content {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.node-icon {
  font-size: 14px;
}

.selected-info {
  margin-top: 10px;
  color: #059669;
  font-size: 13px;
}

.progress-card {
  margin-top: 16px;
  padding: 14px 18px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.progress-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.progress-msg {
  flex: 1;
  font-size: 13px;
  color: #374151;
}

.progress-pct {
  font-size: 13px;
  font-weight: 600;
  color: #2563eb;
}

@media (max-width: 768px) {
  .polish-container { max-width: 100%; }
}
</style>
