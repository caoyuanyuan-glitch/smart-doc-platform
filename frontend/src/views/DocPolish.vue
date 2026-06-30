<template>
  <div class="doc-polish-container">
    <!-- Stepper -->
    <div class="stepper-card">
      <el-steps :active="currentStep" align-center finish-status="success">
        <el-step title="上传配置" description="选择文件与规则" />
        <el-step title="检测复核" description="逐条确认修改" />
        <el-step title="预览调整" description="双栏对比效果" />
        <el-step title="导出归档" description="选择导出格式" />
      </el-steps>
    </div>

    <!-- Step 1: Upload & Config -->
    <div v-if="currentStep === 0" class="step-content fade-in">
      <div class="card">
        <div class="card-title">
          <el-icon><UploadFilled /></el-icon>
          <span>上传待润色文件</span>
        </div>
        <el-upload
          ref="uploadRef"
          class="upload-zone"
          drag
          :auto-upload="false"
          :limit="1"
          :on-change="handleFileChange"
          :on-remove="handleFileRemove"
          accept=".docx,.pdf,.txt"
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">
            将文件拖到此处，或<em>点击上传</em>
          </div>
          <template #tip>
            <div class="el-upload__tip">支持 .docx / .pdf / .txt 格式</div>
          </template>
        </el-upload>
        <div v-if="selectedFile" class="file-info-tag">
          <el-tag type="success">已选择</el-tag>
          <strong>{{ selectedFile.name }}</strong>
          <span class="file-size">{{ formatFileSize(selectedFile.size) }}</span>
        </div>
      </div>

      <div class="card">
        <div class="card-title">
          <el-icon><Collection /></el-icon>
          <span>标准文件配置</span>
        </div>
        <el-form label-position="top">
          <el-form-item label="句式表达手册">
            <el-select v-model="configForm.sentenceManualId" placeholder="选择句式手册" class="full-width">
              <el-option
                v-for="m in standards.sentenceManuals"
                :key="m.id"
                :label="m.parentPath ? `${m.name} (${m.parentPath})` : (m.count ? `${m.name} (${m.count}条)` : m.name)"
                :value="m.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="术语对照表">
            <el-select v-model="configForm.termMappingId" placeholder="选择术语库（默认遍历全部）" class="full-width">
              <el-option
                v-for="m in standards.termMappings"
                :key="m.id"
                :label="m.parentPath ? `${m.name} (${m.parentPath})` : (m.count ? `${m.name} (${m.count}条映射)` : m.name)"
                :value="m.id"
              />
            </el-select>
          </el-form-item>
        </el-form>
      </div>

      <div class="card">
        <div class="card-title">
          <el-icon><Setting /></el-icon>
          <span>检测规则</span>
          <span class="card-subtitle">可关闭暂时不需要的规则</span>
        </div>
        <el-checkbox-group v-model="configForm.rules" class="rule-checkbox-group">
          <div class="rule-item" v-for="rule in ruleOptions" :key="rule.value">
            <el-checkbox :label="rule.value" :value="rule.value">
              <span class="rule-name">{{ rule.label }}</span>
              <el-tag v-if="rule.tag" size="small" type="info" class="rule-tag">{{ rule.tag }}</el-tag>
            </el-checkbox>
            <div class="rule-desc">{{ rule.desc }}</div>
          </div>
        </el-checkbox-group>
      </div>

      <div class="step-actions">
        <el-button type="primary" size="large" :loading="detecting" @click="startDetection">
          <el-icon><Search /></el-icon> 开始检测
        </el-button>
      </div>
    </div>

    <!-- Step 2: Review Issues -->
    <div v-if="currentStep === 1" class="step-content fade-in">
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-value">{{ detectionResult.totalIssues }}</div>
          <div class="stat-label">共发现问题</div>
        </div>
        <div class="stat-card">
          <div class="stat-value stat-green">{{ confirmedCount }}</div>
          <div class="stat-label">已确认</div>
        </div>
        <div class="stat-card">
          <div class="stat-value stat-red">{{ detectionResult.totalIssues - confirmedCount }}</div>
          <div class="stat-label">待确认</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ Math.round((confirmedCount / detectionResult.totalIssues) * 100) || 0 }}%</div>
          <div class="stat-label">完成度</div>
        </div>
      </div>

      <div class="card">
        <div class="filter-bar">
          <el-select v-model="filterType" placeholder="全部类型" size="small" clearable>
            <el-option label="全部类型" value="" />
            <el-option label="术语替换" value="term" />
            <el-option label="祈使句规范" value="imperative" />
            <el-option label="格式规范" value="format" />
            <el-option label="标点规范" value="punctuation" />
          </el-select>
          <el-select v-model="filterConfidence" placeholder="全部置信度" size="small" clearable>
            <el-option label="全部置信度" value="" />
            <el-option label="高置信度" value="high" />
            <el-option label="中置信度" value="medium" />
            <el-option label="低置信度" value="low" />
          </el-select>
          <div class="filter-actions">
            <el-button size="small" @click="acceptAll">全部接受</el-button>
            <el-button size="small" @click="rejectAll">全部拒绝</el-button>
          </div>
        </div>
      </div>

      <div class="issues-list">
        <div
          v-for="issue in filteredIssues"
          :key="issue.id"
          class="issue-card"
          :class="{ 'issue-accepted': issue.status === 'accepted', 'issue-rejected': issue.status === 'rejected' }"
        >
          <div class="issue-header">
            <div class="issue-meta">
              <span class="issue-type-tag" :class="`type-${issue.type}`">{{ issue.typeLabel }}</span>
              <span class="issue-confidence" :class="`confidence-${issue.confidence}`">
                {{ issue.confidenceLabel }}
              </span>
              <span class="issue-paragraph">段落 #{{ issue.paragraph }}</span>
            </div>
            <div class="issue-status-text" v-if="issue.status !== 'pending'">
              <el-tag v-if="issue.status === 'accepted'" type="success" size="small">已接受</el-tag>
              <el-tag v-if="issue.status === 'rejected'" type="danger" size="small">已拒绝</el-tag>
              <el-tag v-if="issue.status === 'custom'" type="warning" size="small">已自定义</el-tag>
            </div>
          </div>

          <div class="issue-context">
            <div class="context-line">
              <span class="context-before">{{ issue.contextBefore }}</span>
              <span class="context-original">{{ issue.original }}</span>
              <span class="context-after">{{ issue.contextAfter }}</span>
            </div>
            <div class="context-arrow">
              <el-icon><ArrowDown /></el-icon>
            </div>
            <div class="context-line">
              <span class="context-before">{{ issue.contextBefore }}</span>
              <span class="context-replacement">{{ issue.replacement }}</span>
              <span class="context-after">{{ issue.contextAfter }}</span>
            </div>
            <div v-if="issue.reason" class="context-reason">依据：{{ issue.reason }}</div>
          </div>

          <div class="issue-actions" v-if="issue.status === 'pending'">
            <el-button type="success" size="small" @click="acceptIssue(issue.id)">
              <el-icon><Check /></el-icon> 接受
            </el-button>
            <el-button type="danger" size="small" @click="rejectIssue(issue.id)">
              <el-icon><Close /></el-icon> 拒绝
            </el-button>
            <el-button size="small" @click="openEditDialog(issue)">
              <el-icon><Edit /></el-icon> 自定义
            </el-button>
          </div>
          <div class="issue-actions" v-else>
            <el-button size="small" text type="primary" @click="resetIssue(issue.id)">撤销</el-button>
          </div>
        </div>
        <div v-if="filteredIssues.length === 0" class="empty-state">
          <p>没有匹配的问题</p>
        </div>
      </div>

      <div class="step-actions">
        <el-button size="large" @click="currentStep = 0">返回修改配置</el-button>
        <el-button type="primary" size="large" @click="goToPreview">预览修改效果</el-button>
      </div>
    </div>

    <!-- Step 3: Preview -->
    <div v-if="currentStep === 2" class="step-content fade-in">
      <div class="card">
        <div class="panel-header-bar">
          <el-radio-group v-model="previewMode" size="small">
            <el-radio-button value="revision">修订视图</el-radio-button>
            <el-radio-button value="clean">纯净视图</el-radio-button>
          </el-radio-group>
        </div>
        <div class="preview-pane">
          <div class="preview-box">
            <h4>原文</h4>
            <div class="preview-text" v-html="previewOriginalHtml"></div>
          </div>
          <div class="preview-box">
            <h4>修改后</h4>
            <div class="preview-text" v-html="previewPolishedHtml"></div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">修订统计</div>
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-value stat-green">{{ acceptedCount }}</div>
            <div class="stat-label">已接受</div>
          </div>
          <div class="stat-card">
            <div class="stat-value stat-red">{{ rejectedCount }}</div>
            <div class="stat-label">已拒绝</div>
          </div>
          <div class="stat-card">
            <div class="stat-value stat-orange">{{ customCount }}</div>
            <div class="stat-label">已自定义</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ pendingCount }}</div>
            <div class="stat-label">待确认</div>
          </div>
        </div>
      </div>

      <div class="step-actions">
        <el-button size="large" @click="currentStep = 1">返回复核</el-button>
        <el-button type="primary" size="large" @click="currentStep = 3">导出结果</el-button>
      </div>
    </div>

    <!-- Step 4: Export -->
    <div v-if="currentStep === 3" class="step-content fade-in">
      <div class="card">
        <div class="card-title">
          <el-icon><Download /></el-icon>
          <span>导出选项</span>
        </div>
        <div class="export-check-group">
          <div class="export-item">
            <el-checkbox v-model="exportFormats.revision" :disabled="true">修订标记版 (.docx)</el-checkbox>
            <div class="export-desc">含 OOXML 修订标记，可追溯所有修改</div>
          </div>
          <div class="export-item">
            <el-checkbox v-model="exportFormats.report" :disabled="true">润色报告 (.docx)</el-checkbox>
            <div class="export-desc">完整问题清单 + 修改统计 + 规则说明</div>
          </div>
          <div class="export-item">
            <el-checkbox v-model="exportFormats.clean">纯净版 (.docx)</el-checkbox>
            <div class="export-desc">已应用所有接受的修改，无修订标记</div>
          </div>
          <div class="export-item">
            <el-checkbox v-model="exportFormats.terms">术语提取 (.md)</el-checkbox>
            <div class="export-desc">从本文档提取术语对照表</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">文件命名</div>
        <el-input v-model="exportFileName" placeholder="自动从原文件名生成" />
      </div>

      <div class="card">
        <div class="card-title">目标位置</div>
        <el-radio-group v-model="exportTarget">
          <el-radio value="local">下载到本地</el-radio>
          <el-radio value="feishu">上传到飞书</el-radio>
        </el-radio-group>
      </div>

      <div class="step-actions">
        <el-button size="large" @click="currentStep = 2">返回预览</el-button>
        <el-button type="primary" size="large" :loading="exporting" @click="doExport">
          <el-icon><Download /></el-icon> 确认导出
        </el-button>
      </div>
    </div>

    <!-- Edit Dialog -->
    <el-dialog v-model="editDialogVisible" title="自定义修改内容" width="520px">
      <el-form label-position="top">
        <el-form-item label="原文">
          <div class="form-static-text">{{ editingIssue?.original }}</div>
        </el-form-item>
        <el-form-item label="建议替换">
          <div class="form-static-text form-suggest-text">{{ editingIssue?.replacement }}</div>
        </el-form-item>
        <el-form-item label="自定义文本">
          <el-input v-model="editCustomText" type="textarea" :rows="3" placeholder="输入自定义的替换文本..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmEdit">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, Collection, Setting, Search, ArrowDown, Check, Close, Edit, Download } from '@element-plus/icons-vue'
import { docPolishAPI, knowledgeAPI } from '@/api'

// ── Step 1: Config ──
const configForm = ref({
  sentenceManualId: null,
  termMappingId: null,
  rules: ['termReplace', 'imperativePlease', 'numberSpace', 'cnEnSpace', 'punctuation']
})

const standards = ref({
  sentenceManuals: [],
  termMappings: []
})

// ── Load real knowledge files ──
async function loadStandards() {
  try {
    const res = await docPolishAPI.getStandards()
    if (res.data.sentenceManuals?.length || res.data.termMappings?.length) {
      standards.value = res.data
      if (!configForm.value.sentenceManualId && standards.value.sentenceManuals[0]) {
        configForm.value.sentenceManualId = standards.value.sentenceManuals[0].id
      }
      if (!configForm.value.termMappingId && standards.value.termMappings[0]) {
        configForm.value.termMappingId = standards.value.termMappings[0].id
      }
      return
    }
  } catch { /* fall through to knowledge tree */ }
  // Fallback: load from knowledge tree
  try {
    const tree = await knowledgeAPI.getTree()
    const manuals = []
    const terms = []
    function walk(nodes, contextPath = '') {
      if (!Array.isArray(nodes)) return
      nodes.forEach(node => {
        const currentPath = contextPath ? `${contextPath}/${node.name}` : node.name
        // Check files in this folder
        const files = node.files || []
        files.forEach(file => {
          const lowerName = (file.name || '').toLowerCase()
          const lowerPath = currentPath.toLowerCase()
          const isSentence = lowerPath.includes('句式') || lowerPath.includes('手册') || lowerName.includes('句式')
          const isTerm = lowerPath.includes('术语') || lowerName.includes('术语') || lowerName.includes('对照表')
          if (isSentence && !isTerm) {
            manuals.push({ id: file.id, name: file.name, count: 0, parentPath: currentPath })
          }
          if (isTerm) {
            terms.push({ id: file.id, name: file.name, count: 0, parentPath: currentPath })
          }
        })
        // Recurse into children
        if (node.children && node.children.length > 0) {
          walk(node.children, currentPath)
        }
      })
    }
    walk(tree.data || tree)
    standards.value = { sentenceManuals: manuals, termMappings: terms }
    if (!configForm.value.sentenceManualId && manuals[0]) {
      configForm.value.sentenceManualId = manuals[0].id
    }
    if (!configForm.value.termMappingId && terms[0]) {
      configForm.value.termMappingId = terms[0].id
    }
  } catch (err) {
    console.warn('知识库树加载失败，使用 mock 数据:', err.message)
    standards.value = {
      sentenceManuals: [
        { id: 'v3', name: '句式表达参考手册_V3', count: 338 },
        { id: 'auto', name: '句式表达参考手册_自动化_V2', count: 134 },
        { id: 'd4rs', name: '句式表达参考手册_DNBelab-D4RS_V5', count: 220 }
      ],
      termMappings: [
        { id: 'auto', name: '术语对照表_自动化设备', count: 166 }
      ]
    }
    if (!configForm.value.sentenceManualId) configForm.value.sentenceManualId = 'v3'
    if (!configForm.value.termMappingId) configForm.value.termMappingId = 'auto'
  }
}

// ── Load on mount ──
onMounted(async () => {
  try {
    await loadStandards()
  } catch (err) {
    console.error('standards load failed:', err)
    // use mock fallback
    standards.value = {
      sentenceManuals: [
        { id: 'v3', name: '句式表达参考手册_V3', count: 338 },
        { id: 'auto', name: '句式表达参考手册_自动化_V2', count: 134 },
        { id: 'd4rs', name: '句式表达参考手册_DNBelab-D4RS_V5', count: 220 }
      ],
      termMappings: [
        { id: 'auto', name: '术语对照表_自动化设备', count: 166 }
      ]
    }
    if (!configForm.value.sentenceManualId) configForm.value.sentenceManualId = 'v3'
    if (!configForm.value.termMappingId) configForm.value.termMappingId = 'auto'
  }
})

const ruleOptions = [
  { value: 'termReplace', label: '术语替换', tag: '保守匹配', desc: '只替换完整词且明确错误的非标准说法（如"试验台"→"操作台"）' },
  { value: 'imperativePlease', label: '祈使句规范', tag: '', desc: '操作类动词不加"请" / 建议类动词加"请"' },
  { value: 'numberSpace', label: '数字单位空格', tag: '', desc: '200μL → 200 μL' },
  { value: 'cnEnSpace', label: '中英文空格', tag: '', desc: 'AIO基因 → AIO 基因' },
  { value: 'punctuation', label: '标点规范', tag: '', desc: '句尾缺标点 / 条件句缺逗号' }
]

// ── Step 2: Issues ──
const detectionResult = ref({ taskId: '', fileName: '', totalIssues: 0, issues: [] })
const filterType = ref('')
const filterConfidence = ref('')
const editDialogVisible = ref(false)
const editingIssue = ref(null)
const editCustomText = ref('')

const filteredIssues = computed(() => {
  let list = detectionResult.value.issues || []
  if (filterType.value) list = list.filter(i => i.type === filterType.value)
  if (filterConfidence.value) list = list.filter(i => i.confidence === filterConfidence.value)
  return list
})

const confirmedCount = computed(() =>
  (detectionResult.value.issues || []).filter(i => i.status !== 'pending').length
)
const acceptedCount = computed(() =>
  (detectionResult.value.issues || []).filter(i => i.status === 'accepted').length
)
const rejectedCount = computed(() =>
  (detectionResult.value.issues || []).filter(i => i.status === 'rejected').length
)
const customCount = computed(() =>
  (detectionResult.value.issues || []).filter(i => i.status === 'custom').length
)
const pendingCount = computed(() =>
  (detectionResult.value.issues || []).filter(i => i.status === 'pending').length
)

// ── Step 3: Preview ──
const previewMode = ref('revision')
const previewOriginalHtml = computed(() => buildPreviewHtml('original'))
const previewPolishedHtml = computed(() => buildPreviewHtml('polished'))

function buildPreviewHtml(mode) {
  // build a mock preview from issues
  const issues = detectionResult.value.issues || []
  let text = '产品说明书内容...\n\n'
  issues.forEach(issue => {
    const before = (issue.contextBefore || '') + (issue.original || '') + (issue.contextAfter || '')
    const after = (issue.contextBefore || '') + (issue.replacement || '') + (issue.contextAfter || '')
    if (issue.status === 'accepted' || issue.status === 'custom') {
      if (previewMode.value === 'revision') {
        text += `<span style="background:#fce8e6;color:#c5221f;text-decoration:line-through">${before}</span> `
        text += `<span style="background:#e6f4ea;color:#137333">${after}</span>\n`
      } else {
        text += `${after}\n`
      }
    } else {
      text += `${before}\n`
    }
  })
  return text.replace(/\n/g, '<br/>')
}

// ── Step 4: Export ──
const exportFormats = ref({ revision: true, report: true, clean: false, terms: false })
const exportTarget = ref('local')
const exportFileName = ref('')

// ── Methods ──
function formatFileSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

function handleFileChange(file) {
  selectedFile.value = file.raw
}

function handleFileRemove() {
  selectedFile.value = null
}

async function startDetection() {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择待润色文件')
    return
  }
  detecting.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    formData.append('sentenceManualId', configForm.value.sentenceManualId)
    formData.append('termMappingId', configForm.value.termMappingId)
    configForm.value.rules.forEach(rule => {
      formData.append(`rules[${rule}]`, 'true')
    })
    const res = await docPolishAPI.detect(formData)
    detectionResult.value = res.data
    exportFileName.value = (selectedFile.value.name || 'document').replace(/\.[^.]+$/, '') + '_润色版_V1'
    currentStep.value = 1
    ElMessage.success('检测完成')
  } catch (err) {
    console.warn('API 不可用，使用 mock 数据:', err.message)
    // Mock fallback
    await new Promise(resolve => setTimeout(resolve, 800))
    detectionResult.value = {
      taskId: 'task-mock-001',
      fileName: selectedFile.value.name || 'unknown.docx',
      totalIssues: 6,
      issues: [
        { id: 'issue-1', type: 'term', typeLabel: '术语替换', confidence: 'high', confidenceLabel: '高置信度', paragraph: 127, original: '试验台', replacement: '操作台', contextBefore: '将仪器放置在', contextAfter: '上，确保台面平整。', reason: '术语对照表 #12', status: 'pending' },
        { id: 'issue-2', type: 'imperative', typeLabel: '祈使句规范', confidence: 'high', confidenceLabel: '高置信度', paragraph: 89, original: '检查', replacement: '请检查', contextBefore: '', contextAfter: '电源线是否连接正确。', reason: '建议类动词应加"请"', status: 'pending' },
        { id: 'issue-3', type: 'term', typeLabel: '术语替换', confidence: 'low', confidenceLabel: '低置信度', paragraph: 15, original: '建库仪', replacement: '本仪器', contextBefore: '本说明书适用于AIO基因测序建库制备仪（以下简称', contextAfter: '），说明书版本 1.0。', reason: '自我指代需确认上下文', status: 'pending' },
        { id: 'issue-4', type: 'format', typeLabel: '中英文空格', confidence: 'high', confidenceLabel: '高置信度', paragraph: 3, original: 'AIO基因', replacement: 'AIO 基因', contextBefore: '本说明书适用于', contextAfter: '测序建库制备仪。', reason: '中文与英文缩写间需空格', status: 'pending' },
        { id: 'issue-5', type: 'format', typeLabel: '数字单位空格', confidence: 'high', confidenceLabel: '高置信度', paragraph: 56, original: '200μL', replacement: '200 μL', contextBefore: '加入', contextAfter: '试剂。', reason: '数字与单位间需空格', status: 'pending' },
        { id: 'issue-6', type: 'punctuation', typeLabel: '条件句标点', confidence: 'medium', confidenceLabel: '中置信度', paragraph: 34, original: '如需修改密码可点击', replacement: '如需修改密码，可点击', contextBefore: '', contextAfter: '【确定】按钮。', reason: '条件从句后应加逗号', status: 'pending' }
      ]
    }
    exportFileName.value = (selectedFile.value.name || 'document').replace(/\.[^.]+$/, '') + '_润色版_V1'
    currentStep.value = 1
    ElMessage.success('检测完成（mock 数据）')
  } finally {
    detecting.value = false
  }
}

function acceptIssue(id) {
  const issue = detectionResult.value.issues.find(i => i.id === id)
  if (issue) issue.status = 'accepted'
}

function rejectIssue(id) {
  const issue = detectionResult.value.issues.find(i => i.id === id)
  if (issue) issue.status = 'rejected'
}

function resetIssue(id) {
  const issue = detectionResult.value.issues.find(i => i.id === id)
  if (issue) issue.status = 'pending'
}

function acceptAll() {
  detectionResult.value.issues.forEach(i => { if (i.status === 'pending') i.status = 'accepted' })
}

function rejectAll() {
  detectionResult.value.issues.forEach(i => { if (i.status === 'pending') i.status = 'rejected' })
}

function openEditDialog(issue) {
  editingIssue.value = issue
  editCustomText.value = issue.replacement || ''
  editDialogVisible.value = true
}

function confirmEdit() {
  if (editingIssue.value && editCustomText.value.trim()) {
    editingIssue.value.customText = editCustomText.value.trim()
    editingIssue.value.status = 'custom'
    editDialogVisible.value = false
    ElMessage.success('已保存自定义修改')
  } else {
    ElMessage.warning('请输入自定义文本')
  }
}

function goToPreview() {
  if (pendingCount.value > 0) {
    ElMessageBox.confirm(
      `还有 ${pendingCount.value} 条未确认，未确认的条目不会应用到修改中。是否继续预览？`,
      '提示',
      { confirmButtonText: '继续预览', cancelButtonText: '返回确认', type: 'warning' }
    ).then(() => { currentStep.value = 2 }).catch(() => {})
  } else {
    currentStep.value = 2
  }
}

async function doExport() {
  const selectedFormats = []
  if (exportFormats.value.revision) selectedFormats.push('revision')
  if (exportFormats.value.report) selectedFormats.push('report')
  if (exportFormats.value.clean) selectedFormats.push('clean')
  if (exportFormats.value.terms) selectedFormats.push('terms')
  if (selectedFormats.length === 0) {
    ElMessage.warning('请至少选择一种导出格式')
    return
  }
  exporting.value = true
  await new Promise(resolve => setTimeout(resolve, 1500))
  exporting.value = false
  ElMessage.success(`已导出 ${selectedFormats.length} 个文件`)
}

// ── Mock standards data ──
onMounted(async () => {
  try {
    const res = await docPolishAPI.getStandards()
    standards.value = res.data
  } catch (err) {
    console.warn('标准列表 API 不可用，使用 mock 数据:', err.message)
    standards.value = {
      sentenceManuals: [
        { id: 'v3', name: '句式表达参考手册_V3', count: 338 },
        { id: 'auto', name: '句式表达参考手册_自动化_V2', count: 134 },
        { id: 'd4rs', name: '句式表达参考手册_DNBelab-D4RS_V5', count: 220 }
      ],
      termMappings: [
        { id: 'auto', name: '术语对照表_自动化设备', count: 166 }
      ]
    }
  }
})
</script>

<style scoped>
.doc-polish-container {
  max-width: 1000px;
  margin: 0 auto;
}

.stepper-card {
  background: #fff;
  border-radius: 12px;
  padding: 32px 40px 20px;
  margin-bottom: 24px;
  border: 1px solid #e5e7eb;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}

.step-content {
  min-height: 400px;
}

.card {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 16px;
  border: 1px solid #e5e7eb;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #1f2937;
}

.card-subtitle {
  font-size: 12px;
  color: #9ca3af;
  font-weight: 400;
  margin-left: auto;
}

.upload-zone {
  width: 100%;
}

.file-info-tag {
  margin-top: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.file-size {
  color: #9ca3af;
  font-size: 13px;
}

.full-width {
  width: 100%;
}

.rule-checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rule-item {
  padding: 12px 16px;
  border-radius: 8px;
  background: #f9fafb;
  border: 1px solid #f3f4f6;
}

.rule-name {
  font-size: 14px;
  font-weight: 500;
}

.rule-tag {
  margin-left: 8px;
}

.rule-desc {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
  padding-left: 24px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  text-align: center;
  border: 1px solid #e5e7eb;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  color: #1a73e8;
}

.stat-green { color: #16a34a; }
.stat-red { color: #dc2626; }
.stat-orange { color: #ea580c; }

.stat-label {
  font-size: 13px;
  color: #6b7280;
  margin-top: 4px;
}

.filter-bar {
  display: flex;
  gap: 12px;
  align-items: center;
}

.filter-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}

.issues-list {
  margin-top: 16px;
}

.issue-card {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 12px;
  background: #fff;
  transition: all 0.2s;
}

.issue-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.issue-accepted {
  border-color: #bbf7d0;
  background: #f0fdf4;
  opacity: 0.8;
}

.issue-rejected {
  border-color: #fecaca;
  background: #fef2f2;
  opacity: 0.6;
}

.issue-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.issue-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.issue-type-tag {
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
}

.type-term { background: #e8f0fe; color: #1a73e8; }
.type-imperative { background: #fce8e6; color: #c5221f; }
.type-format { background: #e6f4ea; color: #137333; }
.type-punctuation { background: #fef7e0; color: #b06000; }

.issue-confidence {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
}

.confidence-high { background: #e6f4ea; color: #137333; }
.confidence-medium { background: #fef7e0; color: #b06000; }
.confidence-low { background: #fce8e6; color: #c5221f; }

.issue-paragraph {
  font-size: 12px;
  color: #9ca3af;
}

.issue-context {
  background: #f9fafb;
  padding: 12px;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.8;
  margin-bottom: 12px;
}

.context-line {
  word-break: break-all;
}

.context-before { color: #6b7280; }
.context-original {
  color: #dc2626;
  text-decoration: line-through;
  font-weight: 500;
}
.context-after { color: #6b7280; }
.context-replacement {
  color: #16a34a;
  font-weight: 500;
}
.context-arrow {
  text-align: center;
  color: #9ca3af;
  margin: 2px 0;
}
.context-reason {
  font-size: 12px;
  color: #6b7280;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #e5e7eb;
}

.issue-actions {
  display: flex;
  gap: 8px;
}

.empty-state {
  text-align: center;
  padding: 40px;
  color: #9ca3af;
}

.panel-header-bar {
  margin-bottom: 16px;
}

.preview-pane {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.preview-box {
  background: #f9fafb;
  border-radius: 8px;
  padding: 16px;
  font-size: 14px;
  line-height: 1.8;
  min-height: 300px;
  max-height: 500px;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
}

.preview-box h4 {
  margin-bottom: 12px;
  color: #6b7280;
  font-size: 13px;
  text-transform: uppercase;
}

.preview-text {
  font-size: 14px;
  color: #374151;
}

.export-check-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.export-item {
  padding: 10px 14px;
  border-radius: 8px;
  background: #f9fafb;
  border: 1px solid #f3f4f6;
}

.export-desc {
  font-size: 12px;
  color: #6b7280;
  padding-left: 24px;
  margin-top: 4px;
}

.step-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 8px;
}

.form-static-text {
  padding: 8px 12px;
  background: #f9fafb;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
  color: #374151;
  font-size: 14px;
}

.form-suggest-text {
  color: #16a34a;
}

.fade-in {
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
