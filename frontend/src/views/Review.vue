<template>
  <div class="review-container">
    <!-- 文档管理 -->
    <div v-if="currentView === 'documents'">
      <h2 class="page-title">文档管理</h2>
      <div class="upload-section">
        <el-upload
          class="upload-demo"
          :action="uploadUrl"
          :on-success="handleUploadSuccess"
          :on-error="handleUploadError"
          :before-upload="beforeUpload"
          accept=".pdf,.docx,.md,.zip,.txt,.idml"
          :auto-upload="true"
        >
          <el-button type="primary">上传文档</el-button>
          <template #tip>
            <div class="upload-tip">支持 PDF、DOCX、MD、TXT、IDML 格式，单文件最大 50MB</div>
          </template>
        </el-upload>
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
          <el-table-column label="操作" width="260">
            <template #default="scope">
              <el-button size="small" @click="startReview(scope.row.id)">开始审核</el-button>
              <el-button size="small" @click="viewDocument(scope.row.id)">查看</el-button>
              <el-button size="small" type="danger" @click="deleteDocument(scope.row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 审核任务 -->
    <div v-if="currentView === 'tasks'">
      <h2 class="page-title">审核任务</h2>
      <div class="table-section">
        <el-table :data="reviews" border>
          <el-table-column prop="id" label="任务ID" width="100" />
          <el-table-column prop="document_id" label="文档ID" width="100" />
          <el-table-column prop="document_name" label="文档名" />
          <el-table-column prop="mode" label="模式" width="100" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="scope">
              <el-tag :type="scope.row.status === 'completed' ? 'success' : scope.row.status === 'failed' ? 'danger' : 'info'">
                {{ scope.row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="total_issues" label="问题数" width="100" />
          <el-table-column prop="created_at" label="开始时间" width="180" />
          <el-table-column label="操作" width="140">
            <template #default="scope">
              <el-button size="small" @click="loadReviewIssues(scope.row.id)">查看详情</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="showIssues" class="issues-section">
        <h3>审核结果</h3>
        <div class="issue-stats">
          <span v-for="stat in issueStats" :key="stat.label" class="stat-badge" :class="stat.class">
            {{ stat.label }}: {{ stat.value }}
          </span>
        </div>
        
        <div class="filter-section">
          <el-input v-model="filterKeyword" placeholder="关键词搜索" class="filter-input" />
          <el-select v-model="filterSeverity" placeholder="严重级别" class="filter-select">
            <el-option label="全部" value="" />
            <el-option label="致命" value="fatal" />
            <el-option label="严重" value="serious" />
            <el-option label="一般" value="general" />
            <el-option label="建议" value="suggestion" />
          </el-select>
          <el-select v-model="filterCategory" placeholder="分类" class="filter-select">
            <el-option label="全部" value="" />
            <el-option v-for="cat in categories" :key="cat" :label="cat" :value="cat" />
          </el-select>
          <el-button @click="clearFilters">重置筛选</el-button>
        </div>

        <el-table :data="filteredIssues" border>
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="severity" label="严重级别" width="120">
            <template #default="scope">
              <el-tag :type="getSeverityType(scope.row.severity)">{{ getSeverityLabel(scope.row.severity) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="category" label="分类" width="120" />
          <el-table-column prop="chapter" label="章节" width="150" />
          <el-table-column prop="original_text" label="原文" width="200" />
          <el-table-column prop="context" label="上下文" min-width="300">
            <template #default="scope">
              <span class="context-text">{{ scope.row.context }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="suggestion" label="修改建议" min-width="200" />
          <el-table-column prop="audit_basis" label="审核依据" min-width="200" />
        </el-table>
        <el-button @click="exportReport">导出报告</el-button>
      </div>
    </div>

    <!-- 规则管理 -->
    <div v-if="currentView === 'rules'">
      <h2 class="page-title">规则管理</h2>
      <div class="table-section">
        <div class="table-header-actions">
          <el-button type="primary" @click="showRuleDialog = true">添加规则</el-button>
        </div>
        <el-table :data="rules" border>
          <el-table-column prop="id" label="编号" width="100" />
          <el-table-column prop="category" label="分类" width="120" />
          <el-table-column prop="description" label="规则描述" />
          <el-table-column prop="regex" label="正则" width="200" />
          <el-table-column prop="example" label="示例" width="160" />
          <el-table-column label="操作" width="180">
            <template #default="scope">
              <el-button size="small" @click="editRule(scope.row)">编辑</el-button>
              <el-button size="small" type="danger" @click="deleteRule(scope.row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-dialog v-model="showRuleDialog" :title="editingRule ? '编辑规则' : '添加规则'" width="500px">
        <el-form :model="ruleForm" label-width="80px">
          <el-form-item label="分类">
            <el-input v-model="ruleForm.category" placeholder="如：术语" />
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
                {{ scope.row.status }}
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
            <div><strong>状态：</strong>{{ currentReport.status }}</div>
            <div><strong>问题总数：</strong>{{ currentReport.total_issues }}</div>
            <div><strong>创建时间：</strong>{{ currentReport.created_at }}</div>
          </div>
          <div class="report-summary">
            <h4>概览</h4>
            <p>{{ currentReport.summary || '暂无概览' }}</p>
          </div>
          <div class="report-issues">
            <h4>问题列表</h4>
            <el-table :data="issues" border>
              <el-table-column prop="severity" label="级别" width="100">
                <template #default="scope">
                  <el-tag :type="getSeverityType(scope.row.severity)">{{ getSeverityLabel(scope.row.severity) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="category" label="分类" width="120" />
              <el-table-column prop="chapter" label="章节" width="150" />
              <el-table-column prop="original_text" label="原文" width="220" />
              <el-table-column prop="suggestion" label="建议" />
              <el-table-column prop="audit_basis" label="审核依据" width="200" />
            </el-table>
          </div>
        </div>
      </div>
    </div>

    <!-- 审核依据 -->
    <div v-if="currentView === 'basis'">
      <h2 class="page-title">审核依据</h2>
      <div class="upload-section">
        <el-upload
          class="upload-demo"
          :action="basisUploadUrl"
          :on-success="handleBasisSuccess"
          :on-error="handleBasisError"
          :before-upload="beforeUpload"
          accept=".pdf,.docx,.md,.txt"
          :auto-upload="true"
        >
          <el-button type="primary">上传依据</el-button>
          <template #tip>
            <div class="upload-tip">支持 PDF、DOCX、MD、TXT 格式</div>
          </template>
        </el-upload>
      </div>

      <div class="table-section">
        <h3>依据列表</h3>
        <el-table :data="basisList" border>
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="filename" label="文件名" />
          <el-table-column prop="file_type" label="类型" width="100" />
          <el-table-column prop="created_at" label="上传时间" width="180" />
          <el-table-column label="操作" width="180">
            <template #default="scope">
              <el-button size="small" @click="viewBasis(scope.row.id)">查看</el-button>
              <el-button size="small" type="danger" @click="deleteBasis(scope.row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { documentAPI, reviewAPI, rulesAPI, auditBasisAPI } from '@/api'
import { ElMessage } from 'element-plus'

const route = useRoute()
const documents = ref([])
const reviews = ref([])
const issues = ref([])
const rules = ref([])
const basisList = ref([])
const showIssues = ref(false)
const showReport = ref(false)
const currentReport = ref({})

const showRuleDialog = ref(false)
const editingRule = ref(null)
const ruleForm = ref({ category: '', description: '', regex: '', example: '', suggestion: '', audit_basis: '' })

const uploadUrl = '/api/documents/upload/'
const basisUploadUrl = '/api/audit_basis/upload'

const filterKeyword = ref('')
const filterSeverity = ref('')
const filterCategory = ref('')

const currentView = computed(() => {
  if (route.path === '/review/tasks') return 'tasks'
  if (route.path === '/review/rules') return 'rules'
  if (route.path === '/review/reports') return 'reports'
  if (route.path === '/review/basis') return 'basis'
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

const categories = computed(() => {
  const cats = new Set(issues.value.map(i => i.category))
  return Array.from(cats).filter(Boolean)
})

const filteredIssues = computed(() => {
  return issues.value.filter(issue => {
    if (filterKeyword.value && !issue.original_text.includes(filterKeyword.value) && !issue.context.includes(filterKeyword.value)) {
      return false
    }
    if (filterSeverity.value && issue.severity !== filterSeverity.value) {
      return false
    }
    if (filterCategory.value && issue.category !== filterCategory.value) {
      return false
    }
    return true
  })
})

onMounted(() => {
  loadByView()
})

function loadByView() {
  if (currentView.value === 'documents') loadDocuments()
  else if (currentView.value === 'tasks' || currentView.value === 'reports') loadReviews()
  else if (currentView.value === 'rules') loadRules()
  else if (currentView.value === 'basis') loadBasis()
}

async function loadDocuments() {
  try {
    const resp = await documentAPI.list()
    documents.value = resp.data || []
  } catch (e) {
    ElMessage.info('加载文档列表失败')
  }
}

async function loadReviews() {
  try {
    const resp = await reviewAPI.list()
    reviews.value = resp.data || []
  } catch (e) {
    ElMessage.info('加载任务列表失败')
  }
}

async function loadRules() {
  try {
    const resp = await rulesAPI.list()
    rules.value = resp.data || []
  } catch (e) {
    ElMessage.info('加载规则列表失败')
  }
}

async function loadBasis() {
  try {
    const resp = await auditBasisAPI.list()
    basisList.value = resp.data || []
  } catch (e) {
    ElMessage.info('加载依据列表失败')
  }
}

function formatSize(size) {
  if (!size) return '-'
  if (size < 1024) return size + ' B'
  if (size < 1024 * 1024) return (size / 1024).toFixed(1) + ' KB'
  return (size / 1024 / 1024).toFixed(1) + ' MB'
}

function beforeUpload(file) {
  const allowed = ['pdf', 'docx', 'md', 'zip', 'txt', 'idml']
  const ext = file.name.split('.').pop().toLowerCase()
  if (!allowed.includes(ext)) {
    ElMessage.info('不支持的文件格式: .' + ext)
    return false
  }
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.info('文件大小超过 50MB')
    return false
  }
  return true
}

function handleUploadSuccess() {
  ElMessage.success('上传成功')
  loadDocuments()
}

function handleUploadError() {
  ElMessage.info('上传失败，请重试')
}

function handleBasisSuccess() {
  ElMessage.success('上传成功')
  loadBasis()
}

function handleBasisError() {
  ElMessage.info('上传失败，请重试')
}

async function startReview(documentId) {
  try {
    const response = await reviewAPI.create(documentId, 'hybrid')
    const reviewId = response.data.review_id
    if (reviewId) {
      await loadReviewIssues(reviewId)
    }
    showIssues.value = true
    ElMessage.success('审核完成')
  } catch (error) {
    ElMessage.info('审核失败，请重试')
  }
}

async function loadReviewIssues(reviewId) {
  try {
    const response = await reviewAPI.getIssues(reviewId)
    issues.value = response.data || []
    showIssues.value = true
  } catch (error) {
    ElMessage.info('加载问题列表失败')
  }
}

function clearFilters() {
  filterKeyword.value = ''
  filterSeverity.value = ''
  filterCategory.value = ''
}

async function viewDocument(id) {
  try {
    await documentAPI.get(id)
    ElMessage.info('已加载文档信息')
  } catch (error) {
    ElMessage.info('查看失败')
  }
}

async function deleteDocument(id) {
  try {
    await documentAPI.delete(id)
    loadDocuments()
    ElMessage.success('删除成功')
  } catch (error) {
    ElMessage.info('删除失败')
  }
}

async function viewBasis(id) {
  try {
    await auditBasisAPI.get(id)
    ElMessage.info('已加载依据信息')
  } catch (error) {
    ElMessage.info('查看失败')
  }
}

async function deleteBasis(id) {
  try {
    await auditBasisAPI.delete(id)
    loadBasis()
    ElMessage.success('删除成功')
  } catch (error) {
    ElMessage.info('删除失败')
  }
}

function editRule(row) {
  editingRule.value = row
  ruleForm.value = {
    category: row.category || '',
    description: row.description || '',
    regex: row.regex || '',
    example: row.example || '',
    suggestion: row.suggestion || '',
    audit_basis: row.audit_basis || ''
  }
  showRuleDialog.value = true
}

async function saveRule() {
  try {
    if (editingRule.value) {
      await rulesAPI.update(editingRule.value.id, ruleForm.value)
      ElMessage.success('更新成功')
    } else {
      await rulesAPI.create(ruleForm.value)
      ElMessage.success('添加成功')
    }
    showRuleDialog.value = false
    editingRule.value = null
    ruleForm.value = { category: '', description: '', regex: '', example: '', suggestion: '', audit_basis: '' }
    loadRules()
  } catch (error) {
    ElMessage.info('保存失败')
  }
}

async function deleteRule(id) {
  try {
    await rulesAPI.delete(id)
    loadRules()
    ElMessage.success('删除成功')
  } catch (error) {
    ElMessage.info('删除失败')
  }
}

async function loadReport(id) {
  try {
    const report = reviews.value.find(r => r.id === id) || {}
    currentReport.value = report
    const response = await reviewAPI.getIssues(id)
    issues.value = response.data || []
    showReport.value = true
  } catch (error) {
    ElMessage.info('加载报告失败')
  }
}

function exportReport() {
  ElMessage.success('报告导出功能演示')
}

function getSeverityType(severity) {
  const types = { fatal: 'danger', serious: 'warning', general: 'info', suggestion: 'success' }
  return types[severity] || 'info'
}

function getSeverityLabel(severity) {
  const labels = { fatal: '致命', serious: '严重', general: '一般', suggestion: '建议' }
  return labels[severity] || severity
}
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

.table-section h3,
.issues-section h3,
.report-section h3 {
  margin-bottom: 15px;
  color: #333;
  font-size: 16px;
  font-weight: 600;
}

.table-header-actions {
  margin-bottom: 12px;
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
</style>
