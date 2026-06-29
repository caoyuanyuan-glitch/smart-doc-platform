<template>
  <div class="review-container">
    <!-- 文档管理 -->
    <div v-if="currentView === 'documents'">
      <h2 class="page-title">文档管理</h2>
      <div class="upload-section">
        <el-upload
          class="upload-demo"
          :http-request="uploadDocument"
          :before-upload="beforeUpload"
          accept=".pdf,.docx,.xlsx,.xls,.md,.zip,.txt,.idml"
          :auto-upload="true"
          :show-file-list="false"
        >
          <el-button type="primary">上传文档</el-button>
          <template #tip>
            <div class="upload-tip">支持 PDF、DOCX、Excel、MD、TXT、IDML 格式，单文件最大 50MB</div>
          </template>
        </el-upload>
        <div v-if="uploadProgress > 0 && uploadProgress < 100" class="progress-section">
          <el-progress :percentage="uploadProgress" :stroke-width="4" />
          <span class="progress-text">{{ uploadProgressText }}</span>
        </div>
      </div>

      <div class="table-section">
        <h3>文档列表</h3>
        <el-table :data="documents" border>
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="filename" label="文件名" />
          <el-table-column prop="file_type" label="类型" width="100" />
          <el-table-column prop="file_size" label="大小" width="100">
            <template #default="scope">
              {{ formatSize(scope.row.file_size) }}
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="上传时间" width="180" />
          <el-table-column label="审核状态" width="200">
            <template #default="scope">
              <div v-if="docReviewStatus[scope.row.id]">
                <el-progress 
                  v-if="docReviewStatus[scope.row.id].progress < 100" 
                  :percentage="docReviewStatus[scope.row.id].progress" 
                  :text-inside="true" 
                  :stroke-width="18"
                  :status="docReviewStatus[scope.row.id].status === 'failed' ? 'exception' : ''"
                />
                <span style="font-size:12px;color:#666">{{ reviewStatusText(docReviewStatus[scope.row.id]) }}</span>
              </div>
              <span v-else style="color:#999">未审核</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="340">
            <template #default="scope">
              <el-button 
                size="small" 
                :disabled="docReviewStatus[scope.row.id]?.status === 'running'"
                @click="startReview(scope.row.id)"
              >
                {{ docReviewStatus[scope.row.id]?.status === 'running' ? '审核中...' : '开始审核' }}
              </el-button>
              <el-button 
                size="small" 
                type="success" 
                :disabled="!docReviewStatus[scope.row.id]?.review_id || docReviewStatus[scope.row.id]?.status !== 'completed'"
                @click="downloadReviewResultByDoc(scope.row)"
              >
                {{ resultButtonLabel(scope.row.file_type) }}
              </el-button>
              <el-button 
                size="small"
                type="info"
                plain
                :disabled="!docReviewStatus[scope.row.id]?.review_id || docReviewStatus[scope.row.id]?.status !== 'completed'"
                @click="openIssueDialogByDoc(scope.row.id)"
              >
                问题详情
              </el-button>
              <el-button size="small" type="danger" @click="deleteDocument(scope.row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 审核任务 - 行内展开显示报告 -->
    <div v-if="currentView === 'tasks'">
      <h2 class="page-title">审核任务</h2>
      <div class="table-section">
          <el-table :data="reviews" border>
          <!-- 问题详情已迁移到下方弹窗 (openIssueDialog) -->
          <el-table-column prop="id" label="任务ID" width="80" />
          <el-table-column prop="document_id" label="文档ID" width="80" />
          <el-table-column prop="document_name" label="文档名" min-width="200" show-overflow-tooltip />
          <el-table-column prop="mode" label="模式" width="80" />
          <el-table-column prop="status" label="状态" width="90">
            <template #default="scope">
              <el-tag :type="scope.row.status === 'completed' ? 'success' : scope.row.status === 'failed' ? 'danger' : 'info'">
                {{ scope.row.status === 'completed' ? '已完成' : scope.row.status === 'failed' ? '失败' : '进行中' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="进度" min-width="220">
            <template #default="scope">
              <div v-if="scope.row.status === 'running' && scope.row.progress">
                <el-progress :percentage="scope.row.progress.progress || 0" :stroke-width="16" />
                <div class="task-progress-text">{{ reviewProgressText(scope.row.progress) }}</div>
              </div>
              <span v-else-if="scope.row.status === 'completed'">审核完成</span>
              <span v-else-if="scope.row.status === 'failed'">{{ reviewFailureText(scope.row) }}</span>
              <span v-else style="color:#999">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="total_issues" label="问题数" width="100" />
          <el-table-column label="判定状态" width="180">
            <template #default="scope">
              <span v-if="judgmentStats[scope.row.id]">
                <el-tag type="success" size="small" effect="plain" style="margin-right:4px">已确认 {{ judgmentStats[scope.row.id].confirmed }}</el-tag>
                <el-tag type="info" size="small" effect="plain" style="margin-right:4px">误报 {{ judgmentStats[scope.row.id].false_positive }}</el-tag>
                <el-tag type="warning" size="small" effect="plain">待审 {{ judgmentStats[scope.row.id].pending }}</el-tag>
              </span>
              <span v-else style="color:#999">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="开始时间" width="160" />
          <el-table-column label="操作" width="360" fixed="right">
            <template #default="scope">
              <el-button 
                size="small" 
                type="primary" 
                :disabled="scope.row.status !== 'completed'"
                @click="openIssueDialog(scope.row)"
              >
                查看问题
              </el-button>
              <el-button 
                size="small" 
                :disabled="scope.row.status !== 'completed' || !taskIssues[scope.row.id] || taskIssues[scope.row.id].length === 0" 
                @click="batchConfirmAll(scope.row.id)"
              >
                一键确认
              </el-button>
              <el-button 
                size="small" 
                type="success" 
                :disabled="scope.row.status !== 'completed'"
                @click="downloadReviewResult(scope.row)"
              >
                {{ resultButtonLabel(scope.row.document_file_type) }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 问题详情弹窗 -->
    <el-dialog v-model="issueDialogVisible" :title="`问题详情 - 任务#${currentTaskId}`" width="95%" top="5vh">
      <div class="issue-dialog-toolbar">
        <el-input v-model="issueFilter.keyword" placeholder="搜索原文/上下文/建议" style="width:300px" clearable />
        <el-select v-model="issueFilter.category" placeholder="分类" clearable style="width:140px;margin-left:8px">
          <el-option v-for="cat in dialogCategories" :key="cat" :label="cat" :value="cat" />
        </el-select>
          <el-select v-model="issueFilter.status" placeholder="状态" clearable style="width:120px;margin-left:8px">
          <el-option label="待确认" value="pending" />
          <el-option label="已确认" value="confirmed" />
          <el-option label="误报" value="false_positive" />
        </el-select>
        <el-select v-model="issueFilter.severity" placeholder="严重度" clearable style="width:120px;margin-left:8px">
          <el-option label="致命" value="fatal" />
          <el-option label="严重" value="serious" />
          <el-option label="一般" value="general" />
          <el-option label="建议" value="suggestion" />
        </el-select>
        <span style="margin-left:auto">
          <el-button size="small" @click="batchSetStatus('confirmed')">批量确认</el-button>
          <el-button size="small" @click="batchSetStatus('false_positive')">批量误报</el-button>
        </span>
      </div>
      <el-table
        :data="filteredDialogIssues"
        border
        height="60vh"
        @selection-change="onIssueSelectionChange"
        ref="issueTableRef"
        row-key="id"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column label="ID" width="70">
          <template #default="scope">
            {{ formatIssueDisplayId(scope.$index) }}
          </template>
        </el-table-column>
        <el-table-column prop="severity" label="级别" width="80">
          <template #default="scope">
            <el-tag size="small" :type="severityTagType(scope.row.severity)" effect="plain">
              {{ severityLabel(scope.row.severity) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="分类" width="110" />
        <el-table-column prop="chapter" label="章节名称" width="180" show-overflow-tooltip />
        <el-table-column label="原文" min-width="450">
          <template #default="scope">
            <span class="context-cell" v-html="highlightOriginalText(scope.row.context, scope.row.original_text)"></span>
          </template>
        </el-table-column>
        <el-table-column prop="suggestion" label="建议" min-width="200" show-overflow-tooltip>
          <template #default="scope">
            <span class="text-success">{{ scope.row.suggestion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="判定" width="120">
          <template #default="scope">
            <el-tag size="small" :type="statusTagType(scope.row.status)" effect="plain">
              {{ statusLabel(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="320" fixed="right">
          <template #default="scope">
            <el-button size="small" type="success" @click="judgeSingle(scope.row, 'confirmed')">确认</el-button>
            <el-button size="small" type="danger" plain @click="judgeSingle(scope.row, 'false_positive')">误报</el-button>
            <el-button size="small" type="primary" plain @click="openTransferRuleDialog(scope.row)">转规则库</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="dialog-footer">
        <span>共 {{ filteredDialogIssues.length }} 条<span v-if="filteredDialogExcelRowCount">，涉及 {{ filteredDialogExcelRowCount }} 行</span> (已选 {{ selectedIssueIds.length }} 条)</span>
        <el-button @click="issueDialogVisible = false">关闭</el-button>
      </div>
    </el-dialog>

    <el-dialog v-model="transferRuleDialogVisible" title="转入规则库" width="620px">
      <el-form :model="transferRuleForm" label-width="90px">
        <el-form-item label="规则编号">
          <el-input v-model="transferRuleForm.rule_no" placeholder="如：R001" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="transferRuleForm.category" placeholder="如：拼写" />
        </el-form-item>
        <el-form-item label="规则描述">
          <el-input v-model="transferRuleForm.description" type="textarea" :rows="2" placeholder="规则描述" />
        </el-form-item>
        <el-form-item label="正则">
          <el-input v-model="transferRuleForm.regex" placeholder="正则表达式" />
        </el-form-item>
        <el-form-item label="示例">
          <el-input v-model="transferRuleForm.example" type="textarea" :rows="2" placeholder="示例文本" />
        </el-form-item>
        <el-form-item label="建议">
          <el-input v-model="transferRuleForm.suggestion" type="textarea" :rows="2" placeholder="修改建议" />
        </el-form-item>
        <el-form-item label="审核依据">
          <el-input v-model="transferRuleForm.audit_basis" placeholder="审核依据来源" />
        </el-form-item>
        <el-form-item label="语言">
          <el-select v-model="transferRuleForm.language" placeholder="请选择语言">
            <el-option label="中英通用" value="both" />
            <el-option label="中文" value="cn" />
            <el-option label="英文" value="en" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="transferRuleDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveTransferredRule">保存到规则库</el-button>
      </template>
    </el-dialog>

    <!-- 规则管理 -->
    <div v-if="currentView === 'rules'">
      <h2 class="page-title">规则管理</h2>
      <div class="table-section">
        <div class="table-header-actions">
          <el-button type="primary" @click="showRuleDialog = true">添加规则</el-button>
          <el-button @click="exportRules">导出规则库</el-button>
          <el-upload
            class="upload-btn"
            :action="rulesImportUrl"
            :on-success="handleRulesImport"
            :before-upload="beforeRulesUpload"
            accept=".json"
          >
            <el-button>批量导入规则</el-button>
          </el-upload>
          <el-button v-if="selectedRules.length > 0" type="danger" @click="batchDeleteRules">批量删除</el-button>
        </div>
        <el-table 
          :data="rules" 
          border 
          :default-sort="{prop: 'rule_no', order: 'ascending'}"
          @selection-change="onRuleSelectionChange"
          @sort-change="handleSortChange"
        >
          <el-table-column type="selection" width="55" />
          <el-table-column 
            prop="rule_no" 
            label="规则编号" 
            width="100"
            sortable="custom"
          />
          <el-table-column prop="category" label="分类" width="120" />
          <el-table-column prop="description" label="规则描述" />
          <el-table-column prop="regex" label="正则" width="200" />
          <el-table-column prop="example" label="示例" width="160" />
          <el-table-column prop="suggestion" label="建议" width="150" />
          <el-table-column prop="audit_basis" label="审核依据" width="180" />
          <el-table-column prop="created_at" label="创建时间" width="180" sortable="custom" />
          <el-table-column label="操作" width="180">
            <template #default="scope">
              <el-button size="small" @click="editRule(scope.row)">编辑</el-button>
              <el-button size="small" type="danger" @click="deleteRule(scope.row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-dialog v-model="showRuleDialog" :title="editingRule ? '编辑规则' : '添加规则'" width="550px">
        <el-form :model="ruleForm" label-width="80px">
          <el-form-item label="规则编号">
            <el-input v-model="ruleForm.rule_no" placeholder="如：R001" :disabled="!!editingRule" />
          </el-form-item>
          <el-form-item label="分类">
            <el-input v-model="ruleForm.category" placeholder="如：标点符号" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="ruleForm.description" placeholder="规则描述" />
          </el-form-item>
          <el-form-item label="正则">
            <el-input v-model="ruleForm.regex" placeholder="正则表达式" />
          </el-form-item>
          <el-form-item label="示例">
            <el-input v-model="ruleForm.example" placeholder="示例文本" />
          </el-form-item>
          <el-form-item label="建议">
            <el-input v-model="ruleForm.suggestion" placeholder="修改建议" />
          </el-form-item>
          <el-form-item label="审核依据">
            <el-input v-model="ruleForm.audit_basis" placeholder="审核依据来源" />
          </el-form-item>
          <el-form-item label="语言">
            <el-select v-model="ruleForm.language" placeholder="请选择语言">
              <el-option label="中英通用" value="both" />
              <el-option label="中文" value="cn" />
              <el-option label="英文" value="en" />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showRuleDialog = false">取消</el-button>
          <el-button type="primary" @click="saveRule">保存</el-button>
        </template>
      </el-dialog>
    </div>

    <!-- 审核报告 -->
    <div v-if="currentView === 'reports'">
      <h2 class="page-title">审核报告</h2>
      <div class="table-section">
        <el-table :data="reviews" border>
          <el-table-column prop="id" label="任务ID" width="100" />
          <el-table-column prop="document_id" label="文档ID" width="100" />
          <el-table-column prop="document_name" label="文档名" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="scope">
              <el-tag :type="scope.row.status === 'completed' ? 'success' : scope.row.status === 'failed' ? 'danger' : 'info'">
                {{ scope.row.status === 'completed' ? '已完成' : scope.row.status === 'failed' ? '失败' : '进行中' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="total_issues" label="问题数" width="100" />
          <el-table-column prop="created_at" label="时间" width="180" />
          <el-table-column label="操作" width="140">
            <template #default="scope">
              <el-button size="small" @click="loadReport(scope.row.id)">查看报告</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="showReport" class="report-section">
        <h3>报告详情预览</h3>
        <div class="report-content">
          <div class="report-header">
            <div><strong>任务 ID：</strong>{{ currentReport.id }}</div>
            <div><strong>文档：</strong>{{ currentReport.document_name }}</div>
            <div><strong>模式：</strong>{{ currentReport.mode }}</div>
            <div><strong>状态：</strong>{{ currentReport.status === 'completed' ? '已完成' : currentReport.status === 'failed' ? '失败' : '进行中' }}</div>
            <div><strong>问题总数：</strong>{{ currentReport.total_issues }}</div>
            <div><strong>创建时间：</strong>{{ formatDateTime(currentReport.created_at) }}</div>
          </div>
          <div class="report-summary">
            <h4>概览</h4>
            <div class="stats-row">
              <span class="stat-item fatal">致命: {{ reportStats.fatal }}</span>
              <span class="stat-item serious">严重: {{ reportStats.serious }}</span>
              <span class="stat-item general">一般: {{ reportStats.general }}</span>
              <span class="stat-item suggestion">建议: {{ reportStats.suggestion }}</span>
            </div>
          </div>
          <div class="report-issues">
            <h4>问题列表</h4>
            <el-table :data="reportIssues" border>
              <el-table-column prop="display_id" label="编号" width="90" />
              <el-table-column prop="severity" label="级别" width="100">
                <template #default="scope">
                  <el-tag :type="getSeverityType(scope.row.severity)">{{ getSeverityLabel(scope.row.severity) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="category" label="分类" width="120" />
              <el-table-column prop="chapter" label="章节" width="180" />
              <el-table-column label="上下文" min-width="500">
                <template #default="scope">
                  <span class="context-text" v-html="highlightIssue(scope.row)"></span>
                </template>
              </el-table-column>
              <el-table-column prop="suggestion" label="建议" min-width="200" />
              <el-table-column prop="audit_basis" label="审核依据" min-width="200" />
            </el-table>
          </div>
        </div>
        <div class="report-actions">
          <el-button type="primary" @click="exportReport">导出报告</el-button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, reactive } from 'vue'
import { useRoute } from 'vue-router'
import { documentAPI, reviewAPI, rulesAPI, getAPIErrorMessage } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'

const route = useRoute()
const documents = ref([])
const reviews = ref([])
const issues = ref([])
const rules = ref([])

// 行内报告：按任务ID存储问题列表和筛选条件
const taskIssues = reactive({})
const rowFilters = reactive({})

// 文档审核状态 (按文档ID存储)
const docReviewStatus = reactive({})
let progressPollingTimers = {}  // 轮询定时器
const progressPollingFailures = reactive({})
let reviewsPollingTimer = null

// 问题详情弹窗
const issueDialogVisible = ref(false)
const currentTaskId = ref(null)
const issueFilter = reactive({ keyword: '', category: '', status: '', severity: '' })
const selectedIssueIds = ref([])
const issueTableRef = ref(null)
const dialogCategories = computed(() => {
  const set = new Set()
  const list = taskIssues[currentTaskId.value] || []
  for (const i of list) {
    if (i.category) set.add(i.category)
  }
  return Array.from(set).sort()
})
const filteredDialogIssues = computed(() => {
  const list = taskIssues[currentTaskId.value] || []
  return list.filter(i => {
    if (issueFilter.category && i.category !== issueFilter.category) return false
    if (issueFilter.status && (i.status || 'pending') !== issueFilter.status) return false
    if (issueFilter.severity && i.severity !== issueFilter.severity) return false
    if (issueFilter.keyword) {
      const k = issueFilter.keyword.toLowerCase()
      const hay = `${i.original_text || ''} ${i.context || ''} ${i.suggestion || ''}`.toLowerCase()
      if (!hay.includes(k)) return false
    }
    return true
  })
})

const filteredDialogExcelRowCount = computed(() => {
  const rows = new Set()
  for (const issue of filteredDialogIssues.value) {
    const position = parseMaybeJson(issue.position)
    if (!position || !position.sheet || !position.row) continue
    rows.add(`${position.sheet}:${position.row}`)
  }
  return rows.size
})

function formatIssueDisplayId(index) {
  return String(index + 1).padStart(3, '0')
}

// 判定状态统计 (按任务ID)
const judgmentStats = computed(() => {
  const stats = {}
  for (const key in taskIssues) {
    const list = taskIssues[key]
    let confirmed = 0, false_positive = 0, pending = 0
    for (const i of list) {
      const s = i.status || 'pending'
      if (s === 'confirmed') confirmed++
      else if (s === 'false_positive') false_positive++
      else pending++
    }
    stats[key] = { confirmed, false_positive, pending }
  }
  return stats
})

const showRuleDialog = ref(false)
const editingRule = ref(null)
const ruleForm = ref({ rule_no: '', category: '', description: '', regex: '', example: '', suggestion: '', audit_basis: '', language: 'both' })
const transferRuleDialogVisible = ref(false)
const transferRuleSourceIssue = ref(null)
const transferRuleForm = ref({ rule_no: '', category: '', description: '', regex: '', example: '', suggestion: '', audit_basis: '', language: 'both' })

const selectedRules = ref([])
const rulesImportUrl = '/api/rules/bulk'

const uploadUrl = '/api/documents/upload/'
const uploadProgress = ref(0)
const uploadProgressText = ref('')
let uploadingTempId = 0

const filterKeyword = ref('')
const filterSeverity = ref('')
const filterCategory = ref('')

const sortField = ref('rule_no')
const sortOrder = ref('asc')

const currentView = computed(() => {
  if (route.path === '/review/tasks') return 'tasks'
  if (route.path === '/review/rules') return 'rules'
  return 'documents'
})

const issueStats = computed(() => {
  const stats = { fatal: 0, serious: 0, general: 0, suggestion: 0 }
  issues.value.forEach(issue => {
    if (stats[issue.severity] !== undefined) stats[issue.severity]++
  })
  return [
    { label: '致命', value: stats.fatal, class: 'stat-fatal' },
    { label: '严重', value: stats.serious, class: 'stat-serious' },
    { label: '一般', value: stats.general, class: 'stat-general' },
    { label: '建议', value: stats.suggestion, class: 'stat-suggestion' }
  ]
})

const reportStats = computed(() => {
  const stats = { fatal: 0, serious: 0, general: 0, suggestion: 0 }
  issues.value.forEach(issue => {
    if (stats[issue.severity] !== undefined) stats[issue.severity]++
  })
  return stats
})

const reportIssues = computed(() => {
  return issues.value.map((issue, index) => ({
    ...issue,
    display_id: `#${String(index + 1).padStart(4, '0')}`,
    db_id: issue.id,
  }))
})

const categories = computed(() => {
  const cats = new Set(issues.value.map(i => i.category))
  return Array.from(cats).filter(Boolean)
})

const filteredIssues = computed(() => {
  let result = [...issues.value]
  if (filterKeyword.value) {
    const keyword = filterKeyword.value.toLowerCase()
    result = result.filter(issue => 
      (issue.original_text && issue.original_text.toLowerCase().includes(keyword)) || 
      (issue.context && issue.context.toLowerCase().includes(keyword)) ||
      (issue.chapter && issue.chapter.toLowerCase().includes(keyword))
    )
  }
  if (filterSeverity.value) {
    result = result.filter(issue => issue.severity === filterSeverity.value)
  }
  if (filterCategory.value) {
    result = result.filter(issue => issue.category === filterCategory.value)
  }
  return result
})

watch(() => route.path, () => {
  loadByView()
})

onMounted(() => {
  loadByView()
})

function loadByView() {
  stopReviewsPolling()
  if (currentView.value === 'documents') loadDocuments()
  else if (currentView.value === 'tasks' || currentView.value === 'reports') loadReviews()
  else if (currentView.value === 'rules') loadRules()
}

async function loadDocuments() {
  try {
    const [docResp, reviewResp] = await Promise.all([
      documentAPI.list(),
      reviewAPI.list()
    ])
    const uploadingDocs = documents.value.filter(doc => String(doc.id).startsWith('uploading-'))
    documents.value = [...uploadingDocs, ...(docResp.data || [])]
    
    const reviewMap = {}
    for (const r of reviewResp.data || []) {
      if (!reviewMap[r.document_id] || r.id > reviewMap[r.document_id].id) {
        reviewMap[r.document_id] = r
      }
    }

    const activeDocIds = new Set()
    
    for (const doc of documents.value) {
      const latestReview = reviewMap[doc.id]
      const docCreatedAt = new Date(doc.created_at || 0).getTime()
      const reviewCreatedAt = new Date(latestReview?.created_at || 0).getTime()
      const hasValidReview = Boolean(latestReview) && (!docCreatedAt || !reviewCreatedAt || reviewCreatedAt >= docCreatedAt)

      if (hasValidReview) {
        const progressInfo = latestReview.progress || null
        const progressValue = latestReview.status === 'completed'
          ? 100
          : latestReview.status === 'running'
            ? (progressInfo?.progress || 0)
            : 0
        const message = latestReview.status === 'completed'
          ? reviewCompletionText(latestReview)
          : latestReview.status === 'failed'
            ? reviewFailureText(latestReview)
            : reviewProgressText(progressInfo)

        docReviewStatus[doc.id] = {
          review_id: latestReview.id,
          status: latestReview.status,
          progress: progressValue,
          message,
          summary: latestReview.summary,
          total_issues: latestReview.total_issues
        }
        activeDocIds.add(String(doc.id))

        if (latestReview.status === 'running') {
          startProgressPolling(doc.id, latestReview.id)
        }
      } else {
        delete docReviewStatus[doc.id]
      }
    }

    Object.keys(docReviewStatus).forEach((docId) => {
      if (!activeDocIds.has(String(docId)) && !String(docId).startsWith('uploading-')) {
        delete docReviewStatus[docId]
      }
    })
  } catch (e) {
    ElMessage.error(`加载文档列表失败: ${getAPIErrorMessage(e)}`)
  }
}

async function loadReviews() {
  try {
    const resp = await reviewAPI.list()
    reviews.value = resp.data || []
    syncReviewsPolling()
  } catch (e) {
    ElMessage.error(`加载任务列表失败: ${getAPIErrorMessage(e)}`)
  }
}

function syncReviewsPolling() {
  stopReviewsPolling()
  if (currentView.value !== 'tasks' && currentView.value !== 'reports') return
  if (!reviews.value.some(review => review.status === 'running')) return

  reviewsPollingTimer = setInterval(async () => {
    try {
      const resp = await reviewAPI.list()
      reviews.value = resp.data || []
      if (!reviews.value.some(review => review.status === 'running')) {
        stopReviewsPolling()
      }
    } catch (error) {
      stopReviewsPolling()
    }
  }, 3000)
}

function stopReviewsPolling() {
  if (reviewsPollingTimer) {
    clearInterval(reviewsPollingTimer)
    reviewsPollingTimer = null
  }
}

async function loadRules() {
  try {
    const resp = await rulesAPI.list()
    rules.value = resp.data || []
  } catch (e) {
    ElMessage.error(`加载规则列表失败: ${getAPIErrorMessage(e)}`)
  }
}

function formatSize(size) {
  if (!size) return '-'
  if (size < 1024) return size + ' B'
  if (size < 1024 * 1024) return (size / 1024).toFixed(1) + ' KB'
  return (size / 1024 / 1024).toFixed(1) + ' MB'
}

function formatDateTime(dateStr) {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN')
}

function beforeUpload(file) {
  const allowed = ['pdf', 'docx', 'xlsx', 'xls', 'md', 'zip', 'txt', 'idml']
  const ext = file.name.split('.').pop().toLowerCase()
  if (!allowed.includes(ext)) {
    ElMessage.error('不支持的文件格式: .' + ext)
    return false
  }
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('文件大小超过 50MB')
    return false
  }
  return true
}

function insertUploadingPlaceholder(file) {
  const tempId = `uploading-${++uploadingTempId}`
  documents.value = [
    {
      id: tempId,
      filename: file.name,
      file_type: file.name.split('.').pop().toLowerCase(),
      file_size: file.size,
      status: 'uploading',
      created_at: new Date().toISOString()
    },
    ...documents.value.filter(doc => String(doc.id) !== tempId)
  ]
  return tempId
}

function removeUploadingPlaceholder(tempId) {
  documents.value = documents.value.filter(doc => String(doc.id) !== String(tempId))
}

function upsertDocumentRow(document) {
  if (!document?.id) return
  documents.value = [
    document,
    ...documents.value.filter(doc => String(doc.id) !== String(document.id) && !String(doc.id).startsWith('uploading-'))
  ]
}

function beforeRulesUpload(file) {
  const ext = file.name.split('.').pop().toLowerCase()
  if (ext !== 'json') {
    ElMessage.error('仅支持 JSON 格式文件')
    return false
  }
  return true
}

async function uploadDocument(options) {
  const file = options.file
  const tempId = insertUploadingPlaceholder(file)
  uploadProgress.value = 1
  uploadProgressText.value = '上传中 1%'

  try {
    const response = await documentAPI.upload(file, {
      onUploadProgress: (event) => {
        if (!event.total) return
        const percent = Math.min(99, Math.max(1, Math.round((event.loaded / event.total) * 100)))
        uploadProgress.value = percent
        uploadProgressText.value = percent >= 99 ? '文件已上传，正在解析文档...' : `上传中 ${percent}%`
      }
    })
    uploadProgress.value = 100
    uploadProgressText.value = '文档已入库'
    removeUploadingPlaceholder(tempId)
    upsertDocumentRow(response.data)
    delete docReviewStatus[response.data.id]
    await loadDocuments()
    options.onSuccess?.(response.data)
    ElMessage.success('上传成功')
  } catch (error) {
    removeUploadingPlaceholder(tempId)
    options.onError?.(error)
    ElMessage.error(`上传失败: ${getAPIErrorMessage(error)}`)
  } finally {
    setTimeout(() => {
      uploadProgress.value = 0
      uploadProgressText.value = ''
    }, 600)
  }
}

function handleRulesImport(response) {
  ElMessage.success(`成功导入 ${response.message || '多条'} 规则`)
  loadRules()
}

async function startReview(documentId) {
  try {
    const response = await reviewAPI.create(documentId, 'hybrid')
    const reviewId = response.data.review_id
    const statusMessage = response.data.message || '审核任务已创建，正在初始化...'
    
    docReviewStatus[documentId] = {
      review_id: reviewId,
      status: 'running',
      progress: 0,
      message: statusMessage
    }
    
    startProgressPolling(documentId, reviewId)
  } catch (error) {
    docReviewStatus[documentId] = {
      status: 'failed',
      progress: 0,
      message: error.response?.data?.detail || '创建审核任务失败'
    }
    ElMessage.error('审核失败，请重试: ' + (error.response?.data?.detail || error.message))
  }
}

function startProgressPolling(documentId, reviewId) {
  if (progressPollingTimers[documentId]) {
    clearInterval(progressPollingTimers[documentId])
  }
  progressPollingFailures[documentId] = 0
  
  progressPollingTimers[documentId] = setInterval(async () => {
    try {
      const resp = await reviewAPI.getProgress(reviewId)
      const progress = resp.data
      progressPollingFailures[documentId] = 0
      
      docReviewStatus[documentId] = {
        review_id: reviewId,
        status: progress.status,
        progress: progress.progress || 0,
        message: reviewProgressText(progress)
      }
      
      if (progress.status === 'completed' || progress.status === 'failed') {
        clearInterval(progressPollingTimers[documentId])
        delete progressPollingTimers[documentId]
        delete progressPollingFailures[documentId]
        
        if (progress.status === 'completed') {
          await loadReviewIssues(reviewId)
          await loadReviews()
          docReviewStatus[documentId] = {
            review_id: reviewId,
            status: 'completed',
            progress: 100,
            message: progress.message,
            summary: null,
            total_issues: (taskIssues[reviewId] || []).length
          }
          ElMessage.success(reviewCompletionText({ summary: progress.message, total_issues: (taskIssues[reviewId] || []).length }))
        } else if (progress.status === 'failed') {
          ElMessage.error('审核失败: ' + reviewFailureText({ summary: progress.message }))
        }
      }
    } catch (err) {
      progressPollingFailures[documentId] = (progressPollingFailures[documentId] || 0) + 1
      console.error('轮询进度失败:', err)
      if (progressPollingFailures[documentId] >= 3) {
        clearInterval(progressPollingTimers[documentId])
        delete progressPollingTimers[documentId]
        delete progressPollingFailures[documentId]
        docReviewStatus[documentId] = {
          review_id: reviewId,
          status: 'failed',
          progress: 0,
          message: '审核状态同步失败，请刷新后重试'
        }
        ElMessage.error('审核状态同步失败，请刷新后重试')
        loadDocuments()
        loadReviews()
      }
    }
  }, 2000)
}

async function loadReviewIssues(reviewId) {
  try {
    const response = await reviewAPI.getIssues(reviewId)
    const data = response.data || []
    issues.value = data
    taskIssues[reviewId] = data
    if (!rowFilters[reviewId]) {
      rowFilters[reviewId] = { keyword: '', severity: '', category: '' }
    }
  } catch (error) {
    taskIssues[reviewId] = []
    ElMessage.error('加载问题列表失败')
  }
}

// 行展开时加载问题列表
async function handleRowExpand(row, expandedRows) {
  if (!row) return
  if (taskIssues[row.id] === undefined) {
    await loadReviewIssues(row.id)
  }
}

// 计算任务问题统计
function computeIssueStats(issueList) {
  const stats = { fatal: 0, serious: 0, general: 0, suggestion: 0 }
  issueList.forEach(issue => {
    if (stats[issue.severity] !== undefined) stats[issue.severity]++
  })
  return [
    { label: '致命', value: stats.fatal, class: 'stat-fatal' },
    { label: '严重', value: stats.serious, class: 'stat-serious' },
    { label: '一般', value: stats.general, class: 'stat-general' },
    { label: '建议', value: stats.suggestion, class: 'stat-suggestion' }
  ]
}

// 筛选任务问题
function filterTaskIssues(taskId) {
  const list = taskIssues[taskId] || []
  const filter = rowFilters[taskId] || { keyword: '', severity: '', category: '' }
  let result = [...list]
  if (filter.keyword) {
    const kw = filter.keyword.toLowerCase()
    result = result.filter(issue =>
      (issue.original_text && issue.original_text.toLowerCase().includes(kw)) ||
      (issue.context && issue.context.toLowerCase().includes(kw)) ||
      (issue.chapter && issue.chapter.toLowerCase().includes(kw))
    )
  }
  if (filter.severity) {
    result = result.filter(issue => issue.severity === filter.severity)
  }
  if (filter.category) {
    result = result.filter(issue => issue.category === filter.category)
  }
  return result
}

function resetRowFilter(taskId) {
  if (rowFilters[taskId]) {
    rowFilters[taskId].keyword = ''
    rowFilters[taskId].severity = ''
    rowFilters[taskId].category = ''
  }
}

function exportTaskReport(row) {
  try {
    const taskId = row.id
    const taskIssuesList = taskIssues[taskId] || []
    const stats = computeIssueStats(taskIssuesList)

    let html = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>审核报告 - ${row.document_name || ''}</title>
<style>body{font-family:"Microsoft YaHei",Arial,sans-serif;margin:30px}
.header{text-align:center;margin-bottom:30px;border-bottom:2px solid #333;padding-bottom:20px}
.report-info{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:20px;padding:15px;background:#f8f9fa;border-radius:8px}
.stats-row{display:flex;gap:20px;margin-bottom:20px}
.stat-item{padding:8px 16px;border-radius:20px;font-weight:bold}
.stat-fatal{background:#fef0f0;color:#dc3545}
.stat-serious{background:#fff7ed;color:#fd7e14}
.stat-general{background:#fffbeb;color:#ffc107}
.stat-suggestion{background:#ecfdf5;color:#10b981}
table{width:100%;border-collapse:collapse;margin-top:20px}
th,td{border:1px solid #ddd;padding:12px;text-align:left}
th{background:#f8f9fa;font-weight:bold}
.issue-row:hover{background:#f8f9fa}
.context-text{font-size:13px;color:#666}
</style></head><body>
<div class="header"><h1>智能技术文档审核报告</h1>
<p>生成时间：${new Date().toLocaleString('zh-CN')}</p></div>
<div class="report-info">
<div><strong>任务 ID：</strong>${row.id}</div>
<div><strong>文档名称：</strong>${row.document_name || '-'}</div>
<div><strong>审核模式：</strong>${row.mode || '-'}</div>
<div><strong>审核状态：</strong>${row.status === 'completed' ? '已完成' : row.status === 'failed' ? '失败' : '进行中'}</div>
<div><strong>问题总数：</strong>${row.total_issues || 0}</div>
<div><strong>创建时间：</strong>${formatDateTime(row.created_at)}</div>
</div>
<h2>问题统计</h2><div class="stats-row">`
    stats.forEach(s => {
      html += `<span class="stat-item stat-${s.class.split('-')[1]}">${s.label}: ${s.value}</span>`
    })
    html += `</div><h2>问题详情</h2><table><thead><tr>
<th>级别</th><th>分类</th><th>章节</th><th>原文</th><th>上下文</th><th>修改建议</th><th>审核依据</th></tr></thead><tbody>`

    filterTaskIssues(taskId).forEach(issue => {
      html += `<tr class="issue-row"><td>${getSeverityLabel(issue.severity)}</td>
<td>${issue.category || '-'}</td><td>${issue.chapter || '-'}</td>
<td>${issue.original_text || '-'}</td>
<td class="context-text">${issue.context || '-'}</td>
<td>${issue.suggestion || '-'}</td><td>${issue.audit_basis || '-'}</td></tr>`
    })

    html += '</tbody></table></body></html>'

    const blob = new Blob([html], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `audit_report_${row.id}_${new Date().toISOString().slice(0, 10)}.html`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    ElMessage.success('报告导出成功')
  } catch (error) {
    ElMessage.error('导出失败: ' + error.message)
  }
}

function resultButtonLabel(fileType) {
  if (fileType === 'docx') return '下载Word'
  if (fileType === 'xlsx') return '下载Excel'
  return '导出HTML'
}

function parseMaybeJson(value) {
  if (typeof value !== 'string') return null
  const text = value.trim()
  if (!text || (text[0] !== '{' && text[0] !== '[')) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

function reviewProgressText(progress) {
  const parsed = parseMaybeJson(progress?.message)
  if (parsed && typeof parsed === 'object') {
    return parsed.message || parsed.step || '审核进行中...'
  }
  return progress?.message || progress?.step || '审核进行中...'
}

function reviewFailureText(review) {
  const parsed = parseMaybeJson(review?.summary)
  if (parsed && typeof parsed === 'object') {
    return parsed.message || '审核失败'
  }
  return review?.summary || '审核失败'
}

function reviewCompletionText(review) {
  const parsed = parseMaybeJson(review?.summary ?? review?.message)
  const matchedTotal = typeof review?.message === 'string'
    ? review.message.match(/(\d+)\s*个问题/)
    : null
  const total = parsed?.total ?? review?.total_issues ?? (matchedTotal ? Number(matchedTotal[1]) : 0)
  return `审核完成，共 ${total} 个问题`
}

function reviewStatusText(statusInfo) {
  if (!statusInfo) return '未审核'
  if (statusInfo.status === 'completed') {
    return reviewCompletionText(statusInfo)
  }
  if (statusInfo.status === 'failed') {
    return reviewFailureText(statusInfo)
  }
  return reviewProgressText(statusInfo)
}

function clearFilters() {
  filterKeyword.value = ''
  filterSeverity.value = ''
  filterCategory.value = ''
}

// 打开问题详情弹窗
async function openIssueDialog(row) {
  currentTaskId.value = row.id
  issueFilter.keyword = ''
  issueFilter.category = ''
  issueFilter.status = ''
  issueFilter.severity = ''
  selectedIssueIds.value = []
  issueDialogVisible.value = true
  if (taskIssues[row.id] === undefined) {
    await loadReviewIssues(row.id)
  }
}

// 通过文档ID打开问题详情弹窗
async function openIssueDialogByDoc(documentId) {
  const status = docReviewStatus[documentId]
  if (!status || !status.review_id) {
    ElMessage.warning('暂无审核结果')
    return
  }
  const reviewId = status.review_id
  currentTaskId.value = reviewId
  issueFilter.keyword = ''
  issueFilter.category = ''
  issueFilter.status = ''
  issueFilter.severity = ''
  selectedIssueIds.value = []
  issueDialogVisible.value = true
  if (taskIssues[reviewId] === undefined) {
    await loadReviewIssues(reviewId)
  }
}

async function downloadReviewResultByDoc(document) {
  const status = docReviewStatus[document.id]
  if (!status || !status.review_id) {
    ElMessage.warning('暂无审核结果')
    return
  }
  await downloadReviewResult({
    id: status.review_id,
    document_name: document.filename,
    document_file_type: document.file_type
  })
}

// 单个问题判定
async function judgeSingle(issue, status) {
  try {
    await reviewAPI.updateIssue(issue.id, status)
    if (status === 'false_positive') {
      removeLocalIssues(currentTaskId.value, [issue.id])
    } else {
      issue.status = status
    }
    ElMessage.success(`已标记为${statusLabel(status)}`)
  } catch (err) {
    ElMessage.error('判定失败: ' + (err.response?.data?.detail || err.message))
  }
}

function removeLocalIssues(taskId, issueIds) {
  const removeIds = new Set(issueIds)
  taskIssues[taskId] = (taskIssues[taskId] || []).filter(issue => !removeIds.has(issue.id))
  issues.value = issues.value.filter(issue => !removeIds.has(issue.id))
  selectedIssueIds.value = selectedIssueIds.value.filter(id => !removeIds.has(id))
}

function escapeRegexLiteral(text) {
  return String(text || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function nextReviewRuleNo() {
  const now = new Date()
  const stamp = [
    String(now.getFullYear()).slice(2),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
    String(now.getHours()).padStart(2, '0'),
    String(now.getMinutes()).padStart(2, '0'),
    String(now.getSeconds()).padStart(2, '0')
  ].join('')
  return `REV-${stamp}`
}

function openTransferRuleDialog(issue) {
  transferRuleSourceIssue.value = issue
  const originalText = issue.original_text || ''
  const category = issue.category || '其他'
  transferRuleForm.value = {
    rule_no: nextReviewRuleNo(),
    category,
    description: issue.description || `${category}问题：${originalText || issue.context || ''}`,
    regex: originalText ? escapeRegexLiteral(originalText) : '',
    example: originalText || issue.context || '',
    suggestion: issue.suggestion || '',
    audit_basis: issue.audit_basis || '审核确认问题转入',
    language: /[\u4e00-\u9fa5]/.test(`${originalText} ${issue.context || ''}`) ? 'both' : 'en'
  }
  transferRuleDialogVisible.value = true
}

async function saveTransferredRule() {
  try {
    if (!transferRuleForm.value.rule_no) {
      ElMessage.error('请填写规则编号')
      return
    }
    if (!transferRuleForm.value.category) {
      ElMessage.error('请填写分类')
      return
    }
    if (!transferRuleForm.value.description) {
      ElMessage.error('请填写规则描述')
      return
    }
    await rulesAPI.create(transferRuleForm.value)
    if (transferRuleSourceIssue.value) {
      transferRuleSourceIssue.value.transferred_to_rule = true
    }
    transferRuleDialogVisible.value = false
    ElMessage.success('已转入规则库')
    if (currentView.value === 'rules') {
      await loadRules()
    }
  } catch (error) {
    ElMessage.error('转入规则库失败: ' + (error.response?.data?.detail || error.message))
  }
}

// 批量设置状态
async function batchSetStatus(status) {
  if (selectedIssueIds.value.length === 0) {
    ElMessage.warning('请先选择问题')
    return
  }
  try {
    const judgments = selectedIssueIds.value.map(id => ({ issue_id: id, status }))
    const res = await reviewAPI.batchJudge(currentTaskId.value, judgments)
    // 更新本地状态
    const list = taskIssues[currentTaskId.value] || []
    const selectedIds = [...selectedIssueIds.value]
    if (status === 'false_positive') {
      removeLocalIssues(currentTaskId.value, selectedIds)
    } else {
      for (const i of list) {
        if (selectedIds.includes(i.id)) i.status = status
      }
    }
    ElMessage.success(`已更新 ${res.data.updated} 条问题为${statusLabel(status)}`)
  } catch (err) {
    ElMessage.error('批量判定失败: ' + (err.response?.data?.detail || err.message))
  }
}

// 一键确认所有未判定问题
async function batchConfirmAll(taskId) {
  const list = taskIssues[taskId] || []
  const pending = list.filter(i => !i.status || i.status === 'pending')
  if (pending.length === 0) {
    ElMessage.info('没有待确认的问题')
    return
  }
  try {
    await ElMessageBox.confirm(`将确认 ${pending.length} 条问题为有效问题, 是否继续?`, '一键确认', {
      confirmButtonText: '确认', cancelButtonText: '取消', type: 'warning'
    })
  } catch { return }
  try {
    const judgments = pending.map(i => ({ issue_id: i.id, status: 'confirmed' }))
    const res = await reviewAPI.batchJudge(taskId, judgments)
    for (const i of pending) i.status = 'confirmed'
    ElMessage.success(`已确认 ${res.data.updated} 条问题`)
  } catch (err) {
    ElMessage.error('批量确认失败: ' + (err.response?.data?.detail || err.message))
  }
}

// 导出 HTML 报告 (调用后端接口)
async function exportReviewHtml(taskId) {
  try {
    const res = await reviewAPI.exportHtml(taskId)
    const blob = new Blob([res.data], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const doc = reviews.value.find(r => r.id === taskId)
    const name = doc?.document_name || `task_${taskId}`
    link.download = `审核报告_${taskId}_${new Date().toISOString().slice(0, 10)}.html`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    ElMessage.success('报告导出成功')
  } catch (err) {
    ElMessage.error('导出失败: ' + (err.response?.data?.detail || err.message))
  }
}

async function downloadReviewResult(row) {
  try {
    const fileType = row.document_file_type || row.file_type || ''
    const res = await reviewAPI.exportResult(row.id)
    const blobType = fileType === 'docx'
      ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      : fileType === 'xlsx'
        ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        : 'text/html;charset=utf-8'
    const blob = new Blob([res.data], { type: blobType })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const baseName = (row.document_name || `task_${row.id}`).replace(/\.[^.]+$/, '')
    const suffix = fileType === 'docx' ? '.docx' : fileType === 'xlsx' ? '.xlsx' : '.html'
    link.download = `${baseName}_审核结果_${new Date().toISOString().slice(0, 10)}${suffix}`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    ElMessage.success(fileType === 'docx' ? 'Word审核结果下载成功' : fileType === 'xlsx' ? 'Excel审核结果下载成功' : 'HTML审核报告导出成功')
  } catch (err) {
    ElMessage.error('导出失败: ' + (err.response?.data?.detail || err.message))
  }
}

function onRuleSelectionChange(rows) {
  selectedRules.value = rows.map(row => row.id)
}

function onIssueSelectionChange(rows) {
  selectedIssueIds.value = rows.map(r => r.id)
}

function severityTagType(sev) {
  return { fatal: 'danger', serious: 'warning', general: 'info', suggestion: 'success' }[sev] || 'info'
}
function severityLabel(sev) {
  return { fatal: '致命', serious: '严重', general: '一般', suggestion: '建议' }[sev] || sev || '-'
}
function statusTagType(s) {
  return { confirmed: 'success', false_positive: 'info', pending: 'warning' }[s || 'pending'] || 'warning'
}
function statusLabel(s) {
  return { confirmed: '已确认', false_positive: '误报' }[s] || '待确认'
}

async function viewDocument(id) {
  try {
    await documentAPI.get(id)
    ElMessage.info('已加载文档信息')
  } catch (error) {
    ElMessage.error('查看失败')
  }
}

async function deleteDocument(id) {
  try {
    await documentAPI.delete(id)
    loadDocuments()
    ElMessage.success('删除成功')
  } catch (error) {
    ElMessage.error('删除失败')
  }
}

function editRule(row) {
  editingRule.value = row
    ruleForm.value = {
      rule_no: row.rule_no || '',
      category: row.category || '',
      description: row.description || '',
      regex: row.regex || '',
      example: row.example || '',
      suggestion: row.suggestion || '',
      audit_basis: row.audit_basis || '',
      language: row.language || 'both'
    }
  showRuleDialog.value = true
}

async function saveRule() {
  try {
    if (!ruleForm.value.rule_no) {
      ElMessage.error('请填写规则编号')
      return
    }
    if (!ruleForm.value.category) {
      ElMessage.error('请填写分类')
      return
    }
    if (!ruleForm.value.description) {
      ElMessage.error('请填写规则描述')
      return
    }
    
    if (editingRule.value) {
      await rulesAPI.update(editingRule.value.id, ruleForm.value)
      ElMessage.success('更新成功')
    } else {
      await rulesAPI.create(ruleForm.value)
      ElMessage.success('添加成功')
    }
    showRuleDialog.value = false
    editingRule.value = null
    ruleForm.value = { rule_no: '', category: '', description: '', regex: '', example: '', suggestion: '', audit_basis: '', language: 'both' }
    loadRules()
  } catch (error) {
    ElMessage.error('保存失败: ' + (error.response?.data?.detail || error.message))
  }
}

async function deleteRule(id) {
  try {
    await ElMessageBox.confirm('确定要删除这条规则吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })
    await rulesAPI.delete(id)
    loadRules()
    ElMessage.success('删除成功')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

async function batchDeleteRules() {
  try {
    await ElMessageBox.confirm(`确定要删除选中的 ${selectedRules.value.length} 条规则吗？`, '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })
    await rulesAPI.batchDelete(selectedRules.value)
    selectedRules.value = []
    loadRules()
    ElMessage.success('批量删除成功')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

async function exportRules() {
  try {
    const response = await rulesAPI.export()
    const dataStr = JSON.stringify(response.data, null, 2)
    const blob = new Blob([dataStr], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `rules_export_${new Date().toISOString().slice(0, 10)}.json`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (error) {
    ElMessage.error('导出失败')
  }
}

function handleSortChange({ prop, order }) {
  sortField.value = prop
  sortOrder.value = order === 'ascending' ? 'asc' : 'desc'
  
  rules.value.sort((a, b) => {
    let aVal = a[prop]
    let bVal = b[prop]
    
    if (typeof aVal === 'string') {
      aVal = aVal.toLowerCase()
      bVal = bVal.toLowerCase()
    }
    
    if (sortOrder.value === 'asc') {
      return aVal > bVal ? 1 : -1
    } else {
      return aVal < bVal ? 1 : -1
    }
  })
}

async function loadReport(id) {
  try {
    const report = reviews.value.find(r => r.id === id) || {}
    currentReport.value = report
    const response = await reviewAPI.getIssues(id)
    issues.value = response.data || []
    showReport.value = true
  } catch (error) {
    ElMessage.error('加载报告失败')
  }
}

async function exportReport() {
  try {
    if (!currentReport.value?.id) {
      ElMessage.warning('当前没有可导出的审核任务')
      return
    }
    const response = await reviewAPI.exportHtml(currentReport.value.id)
    const blob = new Blob([response.data], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const baseName = (currentReport.value.document_name || `task_${currentReport.value.id}`).replace(/\.[^.]+$/, '')
    link.download = `${baseName}_审核报告_${new Date().toISOString().slice(0, 10)}.html`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    ElMessage.success('报告导出成功')
  } catch (error) {
    ElMessage.error('导出失败: ' + error.message)
  }
}

function getSeverityType(severity) {
  const types = { fatal: 'danger', serious: 'warning', general: 'info', suggestion: 'success' }
  return types[severity] || 'info'
}

function getSeverityLabel(severity) {
  const labels = { fatal: '致命', serious: '严重', general: '一般', suggestion: '建议' }
  return labels[severity] || severity
}

function highlightIssue(issue) {
  if (!issue.context && !issue.original_text) return '-'
  
  let text = issue.context || issue.original_text
  
  if (issue.original_text && text.includes(issue.original_text)) {
    const escaped = issue.original_text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const regex = new RegExp(`(${escaped})`, 'g')
    text = text.replace(regex, '<span style="color: red; font-weight: bold; background-color: #ffeaea; padding: 1px 3px; border-radius: 2px;">$1</span>')
  }
  
  return text
}

function highlightOriginalText(context, originalText) {
  if (!context && !originalText) return '-'
  
  let text = context || originalText || ''
  
  if (originalText && text.includes(originalText)) {
    const escaped = originalText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const regex = new RegExp(`(${escaped})`, 'gi')
    text = text.replace(regex, '<span class="highlight-problem">$1</span>')
  }
  
  return text
}

onUnmounted(() => {
  Object.values(progressPollingTimers).forEach(timer => clearInterval(timer))
  progressPollingTimers = {}
  Object.keys(progressPollingFailures).forEach(key => delete progressPollingFailures[key])
  stopReviewsPolling()
})
</script>

<style>
.review-container {
  padding: 20px;
}

.page-title {
  margin-bottom: 20px;
  color: #333;
  font-size: 20px;
  font-weight: 600;
}

.upload-section,
.table-section,
.issues-section,
.report-section {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.upload-tip {
  color: #909399;
  font-size: 12px;
  margin-top: 6px;
}

.progress-section {
  margin-top: 15px;
  width: 260px;
}

.progress-text {
  display: block;
  text-align: left;
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
}

.table-section h3,
.issues-section h3,
.report-section h3 {
  margin-bottom: 15px;
  color: #333;
  font-size: 16px;
  font-weight: 600;
}

.table-header-actions {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.upload-btn {
  display: inline-block;
}

.filter-section {
  display: flex;
  gap: 12px;
  margin-bottom: 15px;
  flex-wrap: wrap;
}

.filter-input {
  width: 200px;
}

.filter-select {
  width: 150px;
}

.issue-stats {
  margin-bottom: 15px;
}

.stat-badge {
  display: inline-block;
  padding: 5px 12px;
  border-radius: 20px;
  margin-right: 10px;
  font-size: 14px;
}

.stat-fatal { background: #fef0f0; color: #dc3545; }
.stat-serious { background: #fff7ed; color: #fd7e14; }
.stat-general { background: #fffbeb; color: #ffc107; }
.stat-suggestion { background: #ecfdf5; color: #10b981; }

.context-text {
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
  word-break: break-all;
}

.report-content {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 16px;
  background: #fafafa;
}

.report-header {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #ebeef5;
  line-height: 1.8;
}

.report-summary {
  margin-bottom: 16px;
}

.report-summary h4,
.report-issues h4 {
  margin-bottom: 10px;
  color: #333;
  font-size: 14px;
  font-weight: 600;
}

.report-summary p {
  color: #606266;
  line-height: 1.7;
}

.report-actions {
  margin-top: 20px;
  text-align: right;
}

.stats-row {
  display: flex;
  gap: 15px;
  flex-wrap: wrap;
}

.stat-item {
  padding: 6px 14px;
  border-radius: 18px;
  font-size: 14px;
}

.stat-item.fatal { background: #fef0f0; color: #dc3545; }
.stat-item.serious { background: #fff7ed; color: #fd7e14; }
.stat-item.general { background: #fffbeb; color: #ffc107; }
.stat-item.suggestion { background: #ecfdf5; color: #10b981; }

/* 行内报告样式 */
.inline-report {
  padding: 16px 24px;
  background: #fafafa;
  border-left: 3px solid #409eff;
}

.inline-report .report-meta {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  padding: 12px 16px;
  background: #fff;
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 13px;
  color: #606266;
}

.inline-report .meta-item {
  display: inline-block;
}

.inline-report .report-content {
  background: #fff;
  border-radius: 6px;
  padding: 16px;
}

.inline-report .loading-report {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 24px;
  color: #909399;
  font-size: 14px;
}

.inline-report .empty-report {
  padding: 24px;
}

.inline-report .issue-detail {
  line-height: 1.7;
}

.inline-report .issue-detail .suggestion-text,
.inline-report .issue-detail .basis-text {
  margin-top: 6px;
  font-size: 13px;
  color: #606266;
}

.inline-report .issue-detail .suggestion-text strong,
.inline-report .issue-detail .basis-text strong {
  color: #409eff;
}

.inline-report .issue-detail .context-text {
  font-size: 13px;
  color: #606266;
  word-break: break-word;
}

.inline-report .filter-section {
  margin: 12px 0;
}

/* 问题详情弹窗样式 */
.issue-dialog-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
  padding: 8px 0;
  color: #606266;
}
.task-progress-text {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.5;
  color: #606266;
}
.text-error { color: #f56c6c; font-family: 'Courier New', monospace; font-size: 13px; }
.text-success { color: #67c23a; font-size: 13px; }

.context-cell {
  font-size: 13px;
  line-height: 1.6;
  word-break: break-all;
  color: #303133;
}

.highlight-problem {
  color: #dc3545;
  font-weight: bold;
  background-color: #fef0f0;
  padding: 1px 4px;
  border-radius: 3px;
  border: 1px solid #fbcfe8;
}
</style>
