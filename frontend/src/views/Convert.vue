<template>
  <div class="convert-container">
    <div v-if="currentView === 'convert'">
      <h2 class="page-title">格式转换</h2>

      <div v-if="converting || taskResult" class="panel">
        <div class="panel-header">
          <span>转换进度</span>
        </div>
        <el-steps :active="activeStep" finish-status="success" align-center>
          <el-step
            v-for="(step, idx) in pipelineSteps"
            :key="idx"
            :title="step.name"
            :status="step.status === 'failed' ? 'error' : (idx < activeStep ? 'success' : (idx === activeStep && converting ? 'process' : 'wait'))"
          >
            <template #description>
              <span v-if="step.status === 'processing'">进行中...</span>
              <span v-else-if="step.status === 'done'">完成</span>
              <span v-else-if="step.status === 'failed'">失败</span>
            </template>
          </el-step>
        </el-steps>
        <div class="progress-bar-wrap">
          <el-progress :percentage="taskProgress" :color="progressColor" />
        </div>

        <div v-if="taskResult && converting === false" class="result-section">
          <div v-if="taskResult.overall === 'passed'" class="result-banner success">
            <el-icon><CircleCheck /></el-icon>
            <span>转换完成！共生成 {{ conversionDetail.length }} 个 topic，点击下方下载 ZIP</span>
          </div>
          <div v-else class="result-banner warning">
            <el-icon><Warning /></el-icon>
            <span>转换完成，但存在验证警告</span>
          </div>

          <div v-if="report" class="verify-report">
            <h4>验证报告</h4>
            <div v-for="check in report.checks" :key="check.name" class="check-item">
              <el-icon v-if="check.status === 'passed'" class="check-pass"><CircleCheck /></el-icon>
              <el-icon v-else class="check-warn"><Warning /></el-icon>
              <span>{{ check.name }}: {{ check.status === 'passed' ? '通过' : '警告' }}</span>
              <span v-if="check.detail" class="check-detail">{{ check.detail }}</span>
            </div>
            <div v-if="report.active_rules && report.active_rules.length > 0" class="active-rules">
              <p><el-icon><Check /></el-icon>本次转换应用的规则 ({{ report.active_rules.length }})：</p>
              <ul>
                <li v-for="r in report.active_rules" :key="r.rule_number">
                  <span class="rule-num">{{ r.rule_number }}</span>
                  <span class="rule-cat">[{{ r.category }}]</span>
                  {{ r.description }}
                </li>
              </ul>
            </div>

            <div v-if="report.unmapped_sections && report.unmapped_sections.length > 0" class="unmapped-warn">
              <p><el-icon><Warning /></el-icon>以下章节未映射：</p>
              <ul>
                <li v-for="s in report.unmapped_sections" :key="s.title">"{{ s.title }}" — {{ s.reason }}</li>
              </ul>
              <p class="suggestion">建议: 在特殊需求中指定这些章节的映射规则后重试</p>
            </div>
          </div>

          <div v-if="conversionDetail.length > 0" class="detail-table-wrap">
            <h4>转换详情</h4>
            <el-table :data="conversionDetail" border size="small">
              <el-table-column prop="source_section" label="源章节" />
              <el-table-column prop="target_type" label="目标类型" width="100" />
              <el-table-column prop="topic_file" label="topic文件" />
              <el-table-column prop="status" label="状态" width="80">
                <template #default="scope">
                  <el-tag :type="scope.row.status === 'ok' ? 'success' : 'warning'" size="small">
                    {{ scope.row.status === 'ok' ? 'OK' : scope.row.status }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <div class="result-actions">
            <div class="download-row">
              <span class="download-label">文件名：</span>
              <el-input v-model="customFilename" size="small" style="width: 260px;" placeholder="output.zip" />
              <span class="download-ext">.zip</span>
              <el-button type="primary" @click="downloadZip" :disabled="!customFilename.trim()">
                <el-icon><Download /></el-icon>
                下载 ZIP
              </el-button>
            </div>
            <el-button @click="fetchReport">
              <el-icon><Document /></el-icon>
              查看验证报告
            </el-button>
            <el-button @click="resetConvert">
              <el-icon><Refresh /></el-icon>
              重新转换
            </el-button>
          </div>

          <div class="ime-feedback-panel">
            <div class="panel-header">
              <span>IME 导入反馈</span>
              <el-tag size="small" type="warning">导入 IME 平台时遇到问题？</el-tag>
            </div>
            <el-form-item label="问题描述">
              <el-input
                v-model="imeFeedback"
                type="textarea"
                :rows="3"
                placeholder="例如: dita中缺少imesofttype属性、主题结构缺失封面章节、缺少bookmeta元数据等"
              />
            </el-form-item>
            <el-form-item label="报错截图">
              <div class="upload-area upload-area-small" @click="triggerScreenshotUpload"
                @dragover.prevent @drop.prevent="onScreenshotDrop"
                @paste="onScreenshotPaste" tabindex="0">
                <input ref="screenshotInput" type="file" accept="image/*" style="display:none"
                  @change="onScreenshotChange" />
                <p v-if="!imeScreenshot">
                  <el-icon><Upload /></el-icon>
                  拖拽、粘贴或点击上传报错截图</p>
                <div v-else class="file-info">
                  <el-icon><Picture /></el-icon>
                  <span>{{ imeScreenshot.name }}</span>
                  <el-button size="small" type="danger" link @click.stop="imeScreenshot = null">移除</el-button>
                </div>
              </div>
            </el-form-item>
            <el-form-item>
              <el-button type="warning" :loading="retrying" :disabled="!sourceFile && !imeFeedback" @click="retryConvert">
                <el-icon><Refresh /></el-icon>
                反馈并重新转换
              </el-button>
            </el-form-item>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <span>上传文档并选择目标格式</span>
        </div>
        <el-form label-width="130px" style="max-width: 800px;">
          <el-form-item label="源文件">
            <div class="upload-area" @click="triggerSourceUpload" @dragover.prevent @drop.prevent="onSourceDrop">
              <input ref="sourceInput" type="file" accept=".md,.markdown,.docx,.doc" style="display:none"
                @change="onSourceChange" />
              <el-icon class="upload-icon"><Upload /></el-icon>
              <p v-if="!sourceFile">拖拽或点击上传 (.md / .docx, &le; 50MB)</p>
              <div v-else class="file-info">
                <el-icon><Document /></el-icon>
                <span>{{ sourceFile.name }}</span>
                <span class="file-size">({{ formatSize(sourceFile.size) }})</span>
                <el-button size="small" type="danger" link @click.stop="sourceFile = null">移除</el-button>
              </div>
            </div>
          </el-form-item>

          <el-form-item label="目标格式">
            <el-radio-group v-model="targetFormat">
              <el-radio label="dita">DITA (默认)</el-radio>
              <el-radio label="markdown">Markdown</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item label="参考模板 (IME DITA包)">
            <div class="upload-area upload-area-small" @click="triggerTemplateUpload"
              @dragover.prevent @drop.prevent="onTemplateDrop">
              <input ref="templateInput" type="file" accept=".zip" style="display:none"
                @change="onTemplateChange" />
              <p v-if="!templateFile">
                <el-icon><FolderOpened /></el-icon>
                拖拽或点击上传 (.zip, IME平台导出的DITA包)
              </p>
              <div v-else class="file-info">
                <el-icon><FolderOpened /></el-icon>
                <span>{{ templateFile.name }}</span>
                <el-button size="small" type="danger" link @click.stop="templateFile = null; templateTree = null">移除</el-button>
              </div>
            </div>
            <div v-if="templateTree" class="template-tree">
              <div class="tree-title">模板包内容解析：</div>
              <div v-for="(val, key) in templateTree" :key="key" class="tree-entry">
                <span class="tree-folder">📁 {{ key }}/</span>
                <div v-for="file in getTemplateFiles(val)" :key="file" class="tree-file">
                  📄 {{ file }}
                </div>
              </div>
            </div>
          </el-form-item>

          <el-form-item label="特殊需求">
            <el-input
              v-model="requirements"
              type="textarea"
              :rows="3"
              placeholder="例如: product_overview.dita的topic结构直接沿用模板包中的结构"
            />
            <div class="form-tip">支持自然语言描述转换映射规则</div>
          </el-form-item>

          <el-form-item>
            <el-button type="primary" size="large" :loading="converting" :disabled="!sourceFile"
              @click="startConvert">
              {{ converting ? '转换中...' : '开始转换' }}
            </el-button>
            <el-button v-if="converting" size="large" @click="cancelPolling">取消</el-button>
          </el-form-item>
        </el-form>
      </div>
    </div>

    <div v-if="currentView === 'history'">
      <h2 class="page-title">转换历史</h2>
      <div class="panel">
        <el-table :data="history" border style="width: 100%" v-loading="historyLoading">
          <el-table-column prop="source_filename" label="源文件" min-width="160" />
          <el-table-column prop="target_format" label="目标格式" width="100">
            <template #default="scope">
              <el-tag size="small">{{ scope.row.target_format?.toUpperCase() }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="template_filename" label="模板包" min-width="140">
            <template #default="scope">
              {{ scope.row.template_filename || '—' }}
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100">
            <template #default="scope">
              <el-tag :type="statusTagType(scope.row.status)" size="small">{{ statusText(scope.row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="大小" width="100">
            <template #default="scope">
              {{ scope.row.output_size ? formatSize(scope.row.output_size) : '—' }}
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" width="180">
            <template #default="scope">
              {{ formatTime(scope.row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160">
            <template #default="scope">
              <el-button v-if="scope.row.status === 'completed'" size="small" type="primary" link
                @click="downloadHistoryZip(scope.row)">下载</el-button>
              <el-button size="small" type="danger" link @click="deleteTask(scope.row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="history.length === 0 && !historyLoading" class="empty-hint">暂无转换历史</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { convertAPI } from '@/api'
import { Upload, Document, FolderOpened, CircleCheck, Warning, Download, Refresh, Picture } from '@element-plus/icons-vue'

const route = useRoute()

const currentView = computed(() => (route.path === '/convert/history' ? 'history' : 'convert'))

const sourceInput = ref(null)
const sourceFile = ref(null)
const templateInput = ref(null)
const templateFile = ref(null)
const templateTree = ref(null)
const targetFormat = ref('dita')
const requirements = ref('')

const converting = ref(false)
const taskId = ref('')
const taskProgress = ref(0)
const taskResult = ref(null)
const customFilename = ref('')
const pipelineSteps = ref([
  { name: '解析', status: 'pending' },
  { name: '结构映射', status: 'pending' },
  { name: '内容替换', status: 'pending' },
  { name: '验证', status: 'pending' },
  { name: '打包', status: 'pending' },
])

const activeStep = computed(() => {
  for (let i = pipelineSteps.value.length - 1; i >= 0; i--) {
    if (pipelineSteps.value[i].status === 'done') return i + 1
    if (pipelineSteps.value[i].status === 'processing') return i
  }
  return 0
})

const report = ref(null)
const conversionDetail = ref([])

const history = ref([])
const historyLoading = ref(false)

const imeFeedback = ref('')
const imeScreenshot = ref(null)
const retrying = ref(false)
const screenshotInput = ref(null)

const progressColor = computed(() => {
  if (taskResult.value && taskResult.value.overall === 'warning') return '#e6a23c'
  return '#67c23a'
})


function triggerSourceUpload() { sourceInput.value?.click() }
function triggerTemplateUpload() { templateInput.value?.click() }

function onSourceChange(e) {
  const f = e.target.files[0]
  if (f) {
    if (f.size > 50 * 1024 * 1024) {
      ElMessage.warning('文件大小不能超过 50MB')
      return
    }
    sourceFile.value = f
  }
}

function onSourceDrop(e) {
  const f = e.dataTransfer.files[0]
  if (f) {
    if (f.size > 50 * 1024 * 1024) {
      ElMessage.warning('文件大小不能超过 50MB')
      return
    }
    sourceFile.value = f
  }
}

function onTemplateChange(e) {
  const f = e.target.files[0]
  if (f) {
    templateFile.value = f
    parseTemplate(f)
  }
}

function onTemplateDrop(e) {
  const f = e.dataTransfer.files[0]
  if (f) {
    templateFile.value = f
    parseTemplate(f)
  }
}

async function parseTemplate(file) {
  try {
    const JSZip = (await import('jszip')).default
    const zip = await JSZip.loadAsync(file)
    const tree = {}
    zip.forEach((relativePath, zipEntry) => {
      if (zipEntry.dir) return
      const parts = relativePath.split('/')
      let current = tree
      for (let i = 0; i < parts.length - 1; i++) {
        const p = parts[i]
        if (!current[p]) current[p] = { _files: [] }
        current = current[p]
      }
      const leaf = parts[parts.length - 1]
      if (leaf) {
        if (!current._files) current._files = []
        current._files.push(leaf)
      }
    })
    templateTree.value = tree
  } catch (e) {
    ElMessage.warning('模板包解析失败，请确认是有效的 ZIP 文件')
    templateTree.value = null
  }
}

function getTemplateFiles(node) {
  if (!node) return []
  if (Array.isArray(node._files)) return node._files
  if (typeof node === 'object') {
    const files = []
    for (const key of Object.keys(node)) {
      if (key === '_files' && Array.isArray(node[key])) {
        files.push(...node[key])
      } else if (typeof node[key] === 'object') {
        files.push(...getTemplateFiles(node[key]))
      }
    }
    return files
  }
  return []
}

async function startConvert() {
  if (!sourceFile.value) { ElMessage.info('请先选择源文件'); return }
  converting.value = true
  taskResult.value = null
  taskProgress.value = 0
  report.value = null
  conversionDetail.value = []
  const baseName = sourceFile.value.name.replace(/\.[^.]+$/, '')
  customFilename.value = `output_${baseName}`
  pipelineSteps.value = pipelineSteps.value.map(s => ({ ...s, status: 'pending' }))

  try {
    const resp = await convertAPI.convert(
      sourceFile.value,
      targetFormat.value,
      templateFile.value,
      requirements.value || null
    )
    taskId.value = resp.data.task_id
    ElMessage.success('转换任务已提交')
    startPolling()
  } catch (e) {
    ElMessage.error('启动转换失败: ' + (e.response?.data?.detail || e.message))
    converting.value = false
  }
}

function startPolling() {
  pollTimer = setInterval(async () => {
    try {
      const resp = await convertAPI.getProgress(taskId.value)
      const data = resp.data
      taskProgress.value = data.progress
      pipelineSteps.value = data.steps.map(s => ({
        name: s.name,
        status: s.status,
      }))

      if (data.status === 'completed') {
        stopPolling()
        converting.value = false
        taskResult.value = { overall: 'passed' }
        await loadTaskResult()
        ElMessage.success('转换完成')
      } else if (data.status === 'failed') {
        stopPolling()
        converting.value = false
        taskResult.value = { overall: 'failed' }
        ElMessage.error('转换失败')
      }
    } catch (e) {
      stopPolling()
      converting.value = false
      ElMessage.error('查询进度失败')
    }
  }, 1500)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

function cancelPolling() {
  stopPolling()
  converting.value = false
  ElMessage.info('已取消')
}

async function loadTaskResult() {
  try {
    const [reportResp, detailResp] = await Promise.all([
      convertAPI.getReport(taskId.value).catch(() => ({ data: null })),
      convertAPI.getDetail(taskId.value).catch(() => ({ data: null })),
    ])
    if (reportResp.data) {
      report.value = reportResp.data
      taskResult.value = { overall: reportResp.data.overall }
    }
    if (detailResp.data && detailResp.data.detail) {
      conversionDetail.value = detailResp.data.detail
    }
    loadHistory()
  } catch (e) {
    console.error('加载任务结果失败', e)
  }
}

async function downloadZip() {
  if (!taskId.value) return
  const filename = customFilename.value.trim() || `output_${taskId.value}`
  try {
    const resp = await convertAPI.download(taskId.value)
    const url = window.URL.createObjectURL(new Blob([resp.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = `${filename}.zip`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('下载已开始')
  } catch (e) {
    ElMessage.error('下载失败')
  }
}

async function downloadHistoryZip(row) {
  try {
    const resp = await convertAPI.download(row.task_id)
    const url = window.URL.createObjectURL(new Blob([resp.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = `output_${row.task_id}.zip`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('下载已开始')
  } catch (e) {
    ElMessage.error('下载失败')
  }
}

async function fetchReport() {
  if (!taskId.value) return
  try {
    const resp = await convertAPI.getReport(taskId.value)
    report.value = resp.data
    ElMessage.success('验证报告已加载')
  } catch (e) {
    ElMessage.error('获取报告失败')
  }
}

function resetConvert() {
  taskId.value = ''
  taskProgress.value = 0
  taskResult.value = null
  report.value = null
  conversionDetail.value = []
  customFilename.value = ''
  imeFeedback.value = ''
  imeScreenshot.value = null
  pipelineSteps.value = pipelineSteps.value.map(s => ({ ...s, status: 'pending' }))
  converting.value = false
}

function triggerScreenshotUpload() { screenshotInput.value?.click() }

function onScreenshotChange(e) {
  const f = e.target.files[0]
  if (f) imeScreenshot.value = f
}

function onScreenshotDrop(e) {
  const items = e.dataTransfer.items
  if (items && items.length) {
    for (const item of items) {
      if (item.kind === 'file' && item.type.startsWith('image/')) {
        imeScreenshot.value = item.getAsFile()
        return
      }
    }
  }
  const f = e.dataTransfer.files[0]
  if (f && f.type.startsWith('image/')) imeScreenshot.value = f
}

function onScreenshotPaste(e) {
  const items = e.clipboardData?.items
  if (!items) return
  for (const item of items) {
    if (item.kind === 'file' && item.type.startsWith('image/')) {
      imeScreenshot.value = item.getAsFile()
      return
    }
  }
}

async function retryConvert() {
  if (!sourceFile.value && !imeFeedback.value) {
    ElMessage.info('请先选择源文件或填写IME反馈')
    return
  }
  retrying.value = true
  taskResult.value = null
  taskProgress.value = 0
  report.value = null
  conversionDetail.value = []
  const baseName = sourceFile.value ? sourceFile.value.name.replace(/\.[^.]+$/, '') : 'output'
  customFilename.value = `output_${baseName}`
  pipelineSteps.value = pipelineSteps.value.map(s => ({ ...s, status: 'pending' }))

  try {
    const resp = await convertAPI.convert(
      sourceFile.value,
      targetFormat.value,
      templateFile.value,
      requirements.value || null,
      imeFeedback.value || null,
      imeScreenshot.value || null
    )
    taskId.value = resp.data.task_id
    converting.value = true
    retrying.value = false
    ElMessage.success('反馈已提交，重新转换中...')
    startPolling()
  } catch (e) {
    retrying.value = false
    ElMessage.error('重新转换失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const resp = await convertAPI.list()
    if (resp.data && Array.isArray(resp.data)) {
      history.value = resp.data
    }
  } catch (e) {
    console.error('加载历史失败', e)
  } finally {
    historyLoading.value = false
  }
}

async function deleteTask(row) {
  try {
    await ElMessageBox.confirm(`确定要删除任务 "${row.source_filename}" 吗？`, '确认删除', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning'
    })
    await convertAPI.delete(row.task_id)
    ElMessage.success('已删除')
    loadHistory()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

function formatSize(bytes) {
  if (!bytes) return '0B'
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB'
  return (bytes / (1024 * 1024)).toFixed(1) + 'MB'
}

function formatTime(t) {
  if (!t) return ''
  return new Date(t).toLocaleString()
}

function statusTagType(status) {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  return 'warning'
}

function statusText(status) {
  if (status === 'completed') return '成功'
  if (status === 'failed') return '失败'
  return '处理中'
}

watch(currentView, (val) => {
  if (val === 'history') loadHistory()
})

onMounted(() => {
  if (currentView.value === 'history') loadHistory()
})

onBeforeUnmount(() => stopPolling())
</script>

<style>
.convert-container { padding: 0; }

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

.upload-area {
  border: 2px dashed #d1d5db;
  border-radius: 8px;
  padding: 20px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s;
  width: 100%;
  color: #6b7280;
}

.upload-area:hover { border-color: #3b82f6; color: #3b82f6; }

.upload-area-small { padding: 12px; }

.upload-icon { font-size: 32px; margin-bottom: 8px; }

.file-info {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #1f2937;
  font-weight: 500;
}

.file-size { color: #9ca3af; font-weight: 400; }

.template-tree {
  margin-top: 12px;
  padding: 12px;
  background: #f9fafb;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
}

.tree-title { font-weight: 600; margin-bottom: 8px; color: #374151; }

.tree-entry { margin-bottom: 4px; }

.tree-folder { font-weight: 600; color: #1e40af; }

.tree-file { padding-left: 24px; color: #6b7280; font-size: 13px; }

.form-tip { color: #9ca3af; font-size: 12px; margin-top: 4px; }

.progress-bar-wrap { margin-top: 20px; padding: 0 40px; }

.result-overview { margin: 12px 0; }

.result-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 18px;
  font-weight: 600;
}

.result-status.passed { color: #16a34a; }
.result-status.warning { color: #e6a23c; }
.result-status.failed { color: #dc2626; }

.status-icon { font-size: 22px; }

.result-meta { margin-top: 8px; color: #6b7280; font-size: 13px; }

.verify-report {
  background: #f9fafb;
  padding: 16px;
  border-radius: 8px;
  margin: 16px 0;
}

.verify-report h4 { margin-bottom: 12px; color: #374151; }

.check-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 0;
  font-size: 14px;
}

.check-pass { color: #16a34a; }
.check-warn { color: #e6a23c; }

.active-rules {
  margin-bottom: 12px;
  padding: 10px;
  background: #ecfdf5;
  border-radius: 6px;
  border: 1px solid #bbf7d0;
}
.active-rules p { display: flex; align-items: center; gap: 4px; font-size: 13px; color: #166534; margin-bottom: 8px; }
.active-rules ul { list-style: none; padding: 0; }
.active-rules li { padding: 3px 0; font-size: 12px; color: #374151; }
.rule-num { display: inline-block; background: #166534; color: #fff; padding: 1px 6px; border-radius: 3px; font-size: 11px; margin-right: 4px; }
.rule-cat { color: #6b7280; margin-right: 4px; }

.check-detail { color: #9ca3af; font-size: 12px; margin-left: auto; }

.unmapped-warn {
  margin-top: 12px;
  padding: 10px;
  background: #fef3c7;
  border-radius: 6px;
  border-left: 4px solid #f59e0b;
}

.unmapped-warn p { font-size: 14px; color: #92400e; }
.unmapped-warn ul { padding-left: 20px; margin: 4px 0; }
.unmapped-warn li { font-size: 13px; color: #92400e; }

.suggestion { font-size: 13px; color: #92400e; margin-top: 6px; }

.detail-table-wrap { margin: 16px 0; }

.detail-table-wrap h4 { margin-bottom: 8px; color: #374151; }

.result-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 16px 0;
  padding: 12px 0;
  border-top: 1px solid #f0f0f0;
}

.download-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.download-label {
  font-weight: 500;
  color: #374151;
  font-size: 14px;
}

.download-ext {
  color: #6b7280;
  font-weight: 500;
}

.empty-hint {
  text-align: center;
  color: #9ca3af;
  padding: 40px;
}

.ime-feedback-panel {
  margin-top: 16px;
  padding: 16px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
}

.ime-feedback-panel .panel-header {
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
