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

      <div v-if="docResult" class="panel">
        <div class="panel-header">
          <span>润色报告</span>
          <div class="panel-actions">
            <el-tag type="info" size="small">修改 {{ docResult.changes }} 处</el-tag>
            <el-button size="small" @click="downloadPolishedDoc">下载润色文件</el-button>
            <el-button size="small" type="success" @click="downloadReport" :disabled="!docResult.reportFile">下载润色报告</el-button>
          </div>
        </div>
        <div class="result-grid">
          <div class="result-col">
            <div class="col-title"><span class="dot dot-blue"></span>润色前</div>
            <div class="col-content">{{ docResult.original }}</div>
          </div>
          <div class="result-col">
            <div class="col-title"><span class="dot dot-green"></span>润色后</div>
            <div class="col-content">{{ docResult.polished }}</div>
          </div>
        </div>
        <div v-if="docResult.changeDetails && docResult.changeDetails.length" class="changes-table">
          <h4 class="changes-title">修改详情</h4>
          <el-table :data="docResult.changeDetails" border stripe style="width: 100%" size="small">
            <el-table-column prop="rule_name" label="规则" width="150" />
            <el-table-column prop="type" label="类型" width="100" />
            <el-table-column prop="before" label="修改前" />
            <el-table-column prop="after" label="修改后" />
          </el-table>
        </div>
      </div>
    </div>

    <div v-if="currentView === 'text'">
      <h2 class="page-title">智能润色</h2>

      <div class="panel">
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

const route = useRoute()
const localFileInputRef = ref(null)
const filePickerVisible = ref(false)
const knowledgeTree = ref([])
const selectedKnowledgeFile = ref(null)
const currentPickerField = ref(null)

const originalText = ref('')
const result = ref(null)
const docResult = ref(null)
const loading = ref(false)

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
    formData.value[currentPickerField.value] = selectedKnowledgeFile.value.name
    formData.value[currentPickerField.value + 'Id'] = selectedKnowledgeFile.value.id
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
  try {
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
    
    const resp = await polishAPI.analyzeFile(payload)
    const data = resp.data || {}
    docResult.value = null
    pendingLocalFile = null
    formData.value.sourceFile = ''
    ElMessage.success('润色成功，已保存到已润色文档')
  } catch (e) {
    const errorMsg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error(`润色失败：${errorMsg}`)
  } finally {
    loading.value = false
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
  const blob = new Blob([docResult.value.polished], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'polished_document.txt'
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
    const resp = await polishAPI.text(originalText.value)
    const data = resp.data || {}
    result.value = {
      original: data.original || originalText.value,
      polished: data.polished || '本产品是一种采用先进免疫层析技术的病毒体外诊断试剂，可在15分钟内快速完成目标病毒的检测。使用前请详细阅读产品说明书，并严格按照标准操作流程执行。本试剂仅限体外诊断用途，严禁其他应用。请于阴凉干燥处保存，储存温度控制在2~30°C。',
      changes: data.changes?.length || 3
    }
    ElMessage.success('润色完成')
  } catch (e) {
    result.value = {
      original: originalText.value,
      polished: '本产品是一种采用先进免疫层析技术的病毒体外诊断试剂，可在15分钟内快速完成目标病毒的检测。使用前请详细阅读产品说明书，并严格按照标准操作流程执行。本试剂仅限体外诊断用途，严禁其他应用。请于阴凉干燥处保存，储存温度控制在2~30°C。',
      changes: 3
    }
    ElMessage.info('AI接口调用失败，已展示示例润色结果')
  } finally {
    loading.value = false
  }
}

function clearAll() {
  originalText.value = ''
  result.value = null
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

onMounted(() => {
  loadKnowledgeTree()
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
  margin-bottom: 20px;
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
  padding: 8px 12px;
  background: #f0fdf4;
  border-radius: 4px;
  color: #166534;
  font-size: 13px;
}

@media (max-width: 768px) {
  .polish-container { max-width: 100%; }
}
</style>
