<template>
  <div class="competitor-container">
    <!-- 竞品列表页面 -->
    <div v-if="currentView === 'list'" class="competitor-list">
      <div class="page-header">
        <h2>竞品说明书分析</h2>
        <el-button type="primary" @click="showCreateDialog = true">
          <el-icon><Plus /></el-icon>新增竞品
        </el-button>
      </div>

      <div class="search-bar">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索竞品名称或品牌"
          clearable
          style="width: 300px"
          @clear="loadCompetitors"
          @keyup.enter="loadCompetitors"
        >
          <template #append>
            <el-button @click="loadCompetitors">搜索</el-button>
          </template>
        </el-input>
      </div>

      <el-table :data="competitors" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="竞品名称" min-width="150" />
        <el-table-column prop="brand" label="品牌" width="120" />
        <el-table-column prop="website" label="官网" width="200">
          <template #default="{ row }">
            <a v-if="row.website" :href="row.website" target="_blank" class="link">{{ row.website }}</a>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="document_count" label="文档数" width="100" align="center" />
        <el-table-column prop="created_at" label="创建时间" width="150">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="viewCompetitor(row)">详情</el-button>
            <el-button type="success" link @click="goToCompare(row)">立即对比</el-button>
            <el-button type="danger" link @click="deleteCompetitor(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadCompetitors"
          @current-change="loadCompetitors"
        />
      </div>
    </div>

    <!-- 竞品详情页 -->
    <div v-else-if="currentView === 'detail'" class="competitor-detail">
      <div class="detail-header">
        <el-button @click="$router.push('/competitor')">
          <el-icon><ArrowLeft /></el-icon>返回列表
        </el-button>
        <h2>{{ selectedCompetitor.name }} <span class="brand">{{ selectedCompetitor.brand }}</span></h2>
      </div>

      <el-row :gutter="20">
        <el-col :span="16">
          <!-- 基本信息 -->
          <el-card class="info-card">
            <template #header>
              <span>基本信息</span>
              <el-button type="primary" link style="float: right" @click="showEditDialog = true">编辑</el-button>
            </template>
            <el-descriptions :column="3" border>
              <el-descriptions-item label="竞品名称">{{ selectedCompetitor.name }}</el-descriptions-item>
              <el-descriptions-item label="品牌">{{ selectedCompetitor.brand || '-' }}</el-descriptions-item>
              <el-descriptions-item label="官网">
                <a v-if="selectedCompetitor.website" :href="selectedCompetitor.website" target="_blank">{{ selectedCompetitor.website }}</a>
                <span v-else>-</span>
              </el-descriptions-item>
              <el-descriptions-item label="简介" :span="3">{{ selectedCompetitor.description || '-' }}</el-descriptions-item>
              <el-descriptions-item label="标签">{{ selectedCompetitor.tags || '-' }}</el-descriptions-item>
            </el-descriptions>
          </el-card>

          <!-- 文档管理 -->
          <el-card class="docs-card">
            <template #header>
              <span>文档管理</span>
              <el-button type="primary" style="float: right" @click="showUploadDialog = true">
                <el-icon><Upload /></el-icon>上传文档
              </el-button>
            </template>
            
            <el-row :gutter="20">
              <el-col :span="12">
                <div class="doc-section">
                  <h4>竞品文档 ({{ competitorDocs.length }})</h4>
                  <el-table :data="competitorDocs" v-loading="docsLoading" size="small" max-height="250">
                    <el-table-column prop="file_name" label="文件名" min-width="150" />
                    <el-table-column prop="version" label="版本" width="80" />
                    <el-table-column prop="upload_date" label="上传时间" width="150">
                      <template #default="{ row }">{{ formatDate(row.upload_date) }}</template>
                    </el-table-column>
                    <el-table-column label="操作" width="80">
                      <template #default="{ row }">
                        <el-button type="danger" link size="small" @click="deleteDoc(row)">删除</el-button>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
              </el-col>
              <el-col :span="12">
                <div class="doc-section">
                  <h4>我方文档 ({{ ourDocs.length }})</h4>
                  <el-table :data="ourDocs" v-loading="docsLoading" size="small" max-height="250">
                    <el-table-column prop="file_name" label="文件名" min-width="150" />
                    <el-table-column prop="version" label="版本" width="80" />
                    <el-table-column prop="upload_date" label="上传时间" width="150">
                      <template #default="{ row }">{{ formatDate(row.upload_date) }}</template>
                    </el-table-column>
                    <el-table-column label="操作" width="80">
                      <template #default="{ row }">
                        <el-button type="danger" link size="small" @click="deleteDoc(row)">删除</el-button>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
              </el-col>
            </el-row>
          </el-card>

          <!-- 对比分析 -->
          <el-card class="compare-card">
            <template #header><span>对比分析</span></template>
            
            <div class="compare-form">
              <el-row :gutter="20">
                <el-col :span="7">
                  <el-select v-model="compareForm.competitorDocId" placeholder="选择竞品文档" style="width: 100%">
                    <el-option
                      v-for="doc in competitorDocs"
                      :key="doc.id"
                      :label="doc.file_name"
                      :value="doc.id"
                    />
                  </el-select>
                </el-col>
                <el-col :span="7">
                  <el-select v-model="compareForm.ourDocId" placeholder="选择我方文档" style="width: 100%">
                    <el-option
                      v-for="doc in ourDocs"
                      :key="doc.id"
                      :label="doc.file_name"
                      :value="doc.id"
                    />
                  </el-select>
                </el-col>
                <el-col :span="4">
                  <el-button type="primary" @click="startCompare" :loading="compareLoading" :disabled="!compareForm.competitorDocId || !compareForm.ourDocId">
                    <el-icon><Refresh /></el-icon>开始对比
                  </el-button>
                </el-col>
              </el-row>
            </div>

            <h4 style="margin-top: 20px">本竞品对比历史</h4>
            <el-table :data="compareTasks" v-loading="tasksLoading" size="small" max-height="300">
              <el-table-column prop="id" label="ID" width="80" />
              <el-table-column prop="competitor_doc_name" label="竞品文档" min-width="150" />
              <el-table-column prop="our_doc_name" label="我方文档" min-width="150" />
              <el-table-column prop="similarity" label="相似度" width="100">
                <template #default="{ row }">
                  <span v-if="row.similarity" :class="getSimilarityClass(row.similarity)">
                    {{ row.similarity }}%
                  </span>
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column prop="status" label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="getStatusType(row.status)" size="small">{{ getStatusText(row.status) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="created_at" label="时间" width="150">
                <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="200">
                <template #default="{ row }">
                  <el-button type="primary" link size="small" @click="viewCompareResult(row)" v-if="row.status === 'completed'">查看</el-button>
                  <el-button type="success" link size="small" @click="generateSuggestions(row)" v-if="row.status === 'completed' && !row.suggestions">建议</el-button>
                  <el-button type="info" link size="small" @click="exportReport(row)" v-if="row.status === 'completed'">导出</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>

        <el-col :span="8">
          <!-- 快捷操作 -->
          <el-card class="quick-card">
            <template #header><span>快捷操作</span></template>
            <div class="quick-links">
              <div class="quick-item" @click="showUploadDialog = true">
                <el-icon><Upload /></el-icon>
                <span>上传文档</span>
              </div>
              <div class="quick-item" @click="$router.push('/competitor/tasks')">
                <el-icon><Clock /></el-icon>
                <span>全部对比历史</span>
              </div>
            </div>
          </el-card>

          <!-- 统计信息 -->
          <el-card class="stats-card">
            <template #header><span>统计信息</span></template>
            <div class="stats">
              <div class="stat-item">
                <div class="stat-value">{{ competitorDocs.length }}</div>
                <div class="stat-label">竞品文档</div>
              </div>
              <div class="stat-item">
                <div class="stat-value">{{ ourDocs.length }}</div>
                <div class="stat-label">我方文档</div>
              </div>
              <div class="stat-item">
                <div class="stat-value">{{ compareTasks.length }}</div>
                <div class="stat-label">对比次数</div>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- 对比历史页面（全局） -->
    <div v-else-if="currentView === 'tasks'" class="competitor-tasks">
      <div class="page-header">
        <h2>对比历史</h2>
        <el-button @click="$router.push('/competitor')">
          <el-icon><ArrowLeft /></el-icon>返回竞品管理
        </el-button>
      </div>

      <el-table :data="allTasks" v-loading="tasksLoading" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="competitor_name" label="竞品名称" min-width="120" />
        <el-table-column prop="competitor_doc_name" label="竞品文档" min-width="150" />
        <el-table-column prop="our_doc_name" label="我方文档" min-width="150" />
        <el-table-column prop="similarity" label="相似度" width="100">
          <template #default="{ row }">
            <span v-if="row.similarity" :class="getSimilarityClass(row.similarity)">
              {{ row.similarity }}%
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">{{ getStatusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="160">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="viewCompareResult(row)" v-if="row.status === 'completed'">查看结果</el-button>
            <el-button type="success" link size="small" @click="generateSuggestions(row)" v-if="row.status === 'completed' && !row.suggestions">生成建议</el-button>
            <el-button type="info" link size="small" @click="exportReport(row)" v-if="row.status === 'completed'">导出报告</el-button>
            <el-button type="default" link size="small" @click="goToCompetitor(row)">查看竞品</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="tasksPage"
          v-model:page-size="tasksPageSize"
          :total="tasksTotal"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="loadAllTasks"
          @current-change="loadAllTasks"
        />
      </div>
    </div>

    <!-- 新增竞品对话框 -->
    <el-dialog v-model="showCreateDialog" title="新增竞品" width="500px">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="竞品名称" required>
          <el-input v-model="createForm.name" placeholder="请输入竞品名称" />
        </el-form-item>
        <el-form-item label="品牌">
          <el-input v-model="createForm.brand" placeholder="请输入品牌" />
        </el-form-item>
        <el-form-item label="官网">
          <el-input v-model="createForm.website" placeholder="请输入官网地址" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="createForm.description" type="textarea" :rows="3" placeholder="请输入竞品简介" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="createForm.tags" placeholder="多个标签用逗号分隔" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="createCompetitor">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑竞品对话框 -->
    <el-dialog v-model="showEditDialog" title="编辑竞品" width="500px">
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="竞品名称" required>
          <el-input v-model="editForm.name" />
        </el-form-item>
        <el-form-item label="品牌">
          <el-input v-model="editForm.brand" />
        </el-form-item>
        <el-form-item label="官网">
          <el-input v-model="editForm.website" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="editForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="editForm.tags" placeholder="多个标签用逗号分隔" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="updateCompetitor">保存</el-button>
      </template>
    </el-dialog>

    <!-- 上传文档对话框 -->
    <el-dialog v-model="showUploadDialog" title="上传文档" width="500px">
      <el-form :model="uploadForm" label-width="80px">
        <el-form-item label="文档类型" required>
          <el-radio-group v-model="uploadForm.docType">
            <el-radio value="competitor">竞品文档</el-radio>
            <el-radio value="ours">我方文档</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="文件" required>
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            accept=".pdf,.docx,.doc,.dita,.md,.txt"
          >
            <el-button type="primary">选择文件</el-button>
            <template #tip>
              <div class="el-upload__tip">支持 PDF、DOCX、DITA、MD、TXT 格式</div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item label="版本">
          <el-input v-model="uploadForm.version" placeholder="如 v2.0" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="uploadForm.notes" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button type="primary" @click="uploadDocument" :loading="uploadLoading">上传</el-button>
      </template>
    </el-dialog>

    <!-- 对比结果对话框 -->
    <el-dialog v-model="showResultDialog" title="对比结果" width="80%" top="5vh">
      <div v-if="currentTask" class="compare-result">
        <div class="result-summary">
          <div class="similarity-box">
            <div class="similarity-value" :class="getSimilarityClass(currentTask.similarity)">
              {{ currentTask.similarity }}%
            </div>
            <div class="similarity-label">总体相似度</div>
          </div>
          <div class="task-info">
            <p><strong>竞品：</strong>{{ currentTask.competitor_name }}</p>
            <p><strong>竞品文档：</strong>{{ currentTask.competitor_doc_name }}</p>
            <p><strong>我方文档：</strong>{{ currentTask.our_doc_name }}</p>
            <p><strong>对比时间：</strong>{{ formatDate(currentTask.created_at) }}</p>
          </div>
        </div>

        <el-tabs>
          <el-tab-pane label="章节结构对比">
            <el-table :data="resultData.structure_diff" size="small" max-height="400">
              <el-table-column prop="section" label="章节" min-width="200" />
              <el-table-column prop="status" label="状态" width="120">
                <template #default="{ row }">
                  <el-tag :type="getStructureStatusType(row.status)" size="small">
                    {{ getStructureStatusText(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="说明" min-width="200">
                <template #default="{ row }">
                  <span v-if="row.status === 'match'">双方都有</span>
                  <span v-else-if="row.status === 'competitor_only'" class="danger">竞品独有，我方缺失</span>
                  <span v-else-if="row.status === 'ours_only'" class="info">我方独有</span>
                  <span v-else-if="row.status === 'similar'">名称相似</span>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="内容差异">
            <el-table :data="resultData.content_diff" size="small" max-height="400">
              <el-table-column prop="section" label="章节" width="150" />
              <el-table-column prop="type" label="类型" width="120">
                <template #default="{ row }">
                  <el-tag :type="getDiffType(row.type)" size="small">{{ getDiffText(row.type) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="详情" min-width="300">
                <template #default="{ row }">{{ row.content || row.detail }}</template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="AI改进建议">
            <div v-if="suggestions.length > 0" class="suggestions-list">
              <div v-for="(sug, index) in suggestions" :key="index" class="suggestion-item" :class="'priority-' + sug.priority.toLowerCase()">
                <div class="sug-header">
                  <el-tag size="small">{{ sug.category }}</el-tag>
                  <el-tag :type="getPriorityType(sug.priority)" size="small">{{ sug.priority }}</el-tag>
                </div>
                <div class="sug-content">{{ sug.content }}</div>
                <div class="sug-reason"><strong>原因：</strong>{{ sug.reason }}</div>
                <div v-if="sug.reference" class="sug-ref"><strong>参考：</strong>{{ sug.reference }}</div>
              </div>
            </div>
            <div v-else class="no-suggestions">
              <el-empty description="尚未生成改进建议">
                <el-button type="primary" @click="generateSuggestions(currentTask)">生成建议</el-button>
              </el-empty>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
      <template #footer>
        <el-button @click="showResultDialog = false">关闭</el-button>
        <el-button type="success" @click="generateSuggestions(currentTask)" v-if="!suggestions.length">生成建议</el-button>
        <el-button type="primary" @click="exportReport(currentTask)">导出报告</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, ArrowLeft, Upload, Refresh, Clock } from '@element-plus/icons-vue'
import { competitorAPI } from '@/api'

const route = useRoute()
const router = useRouter()

// 当前视图模式
const currentView = computed(() => {
  if (route.path === '/competitor/tasks') return 'tasks'
  if (route.params.id) return 'detail'
  return 'list'
})

// 状态
const loading = ref(false)
const docsLoading = ref(false)
const tasksLoading = ref(false)
const compareLoading = ref(false)
const uploadLoading = ref(false)

const competitors = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const searchKeyword = ref('')

const selectedCompetitor = ref(null)
const competitorDocs = ref([])
const ourDocs = ref([])
const compareTasks = ref([])

const allTasks = ref([])
const tasksTotal = ref(0)
const tasksPage = ref(1)
const tasksPageSize = ref(20)

// 表单
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const showUploadDialog = ref(false)
const showResultDialog = ref(false)

const createForm = reactive({ name: '', brand: '', website: '', description: '', tags: '' })
const editForm = reactive({ name: '', brand: '', website: '', description: '', tags: '' })
const uploadForm = reactive({ docType: 'competitor', version: '', notes: '', file: null })
const compareForm = reactive({ competitorDocId: null, ourDocId: null })

const currentTask = ref(null)
const resultData = reactive({ structure_diff: [], content_diff: [], chapter_similarity: [] })
const suggestions = ref([])

const uploadRef = ref(null)

// 方法
function formatDate(dateStr) {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN') + ' ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function getSimilarityClass(sim) {
  if (sim >= 80) return 'high'
  if (sim >= 60) return 'medium'
  return 'low'
}

function getStatusType(status) {
  const map = { pending: 'info', processing: 'warning', completed: 'success', failed: 'danger' }
  return map[status] || 'info'
}

function getStatusText(status) {
  const map = { pending: '等待中', processing: '处理中', completed: '已完成', failed: '失败' }
  return map[status] || status
}

function getStructureStatusType(status) {
  const map = { match: 'success', similar: 'warning', competitor_only: 'danger', ours_only: 'info' }
  return map[status] || 'info'
}

function getStructureStatusText(status) {
  const map = { match: '匹配', similar: '相似', competitor_only: '竞品独有', ours_only: '我方独有' }
  return map[status] || status
}

function getDiffType(type) {
  const map = { competitor_only: 'danger', ours_only: 'info', content_diff: 'warning' }
  return map[type] || 'info'
}

function getDiffText(type) {
  const map = { competitor_only: '竞品独有', ours_only: '我方独有', content_diff: '内容差异' }
  return map[type] || type
}

function getPriorityType(priority) {
  const map = { 高: 'danger', 中: 'warning', 低: 'success' }
  return map[priority] || 'info'
}

// 加载竞品列表
async function loadCompetitors() {
  loading.value = true
  try {
    const res = await competitorAPI.list({ keyword: searchKeyword.value, page: currentPage.value, page_size: pageSize.value })
    competitors.value = res.data.items || []
    total.value = res.data.total || 0
  } catch (e) {
    ElMessage.error('加载竞品列表失败')
  } finally {
    loading.value = false
  }
}

// 查看竞品详情
async function viewCompetitor(row) {
  selectedCompetitor.value = row
  await loadDocuments()
  await loadCompareTasks()
  router.push(`/competitor/${row.id}`)
}

// 跳转到对比页面
function goToCompare(row) {
  router.push(`/competitor/${row.id}`)
}

// 创建竞品
async function createCompetitor() {
  if (!createForm.name) { ElMessage.warning('请输入竞品名称'); return }
  try {
    await competitorAPI.create(createForm)
    ElMessage.success('创建成功')
    showCreateDialog.value = false
    Object.assign(createForm, { name: '', brand: '', website: '', description: '', tags: '' })
    loadCompetitors()
  } catch (e) { ElMessage.error('创建失败') }
}

// 更新竞品
async function updateCompetitor() {
  if (!editForm.name) { ElMessage.warning('请输入竞品名称'); return }
  try {
    await competitorAPI.update(selectedCompetitor.value.id, editForm)
    ElMessage.success('更新成功')
    showEditDialog.value = false
    selectedCompetitor.value = await competitorAPI.get(selectedCompetitor.value.id).then(r => r.data)
  } catch (e) { ElMessage.error('更新失败') }
}

// 删除竞品
async function deleteCompetitor(row) {
  try {
    await ElMessageBox.confirm('确定要删除该竞品及其所有文档吗？', '删除确认', { type: 'warning' })
    await competitorAPI.delete(row.id)
    ElMessage.success('删除成功')
    loadCompetitors()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}

// 加载文档
async function loadDocuments() {
  docsLoading.value = true
  try {
    const res = await competitorAPI.getDocuments(selectedCompetitor.value.id)
    competitorDocs.value = res.data.competitor_docs || []
    ourDocs.value = res.data.our_docs || []
  } catch (e) { ElMessage.error('加载文档失败') } finally { docsLoading.value = false }
}

// 文件选择
function handleFileChange(file) { uploadForm.file = file.raw }

// 上传文档
async function uploadDocument() {
  if (!uploadForm.file) { ElMessage.warning('请选择文件'); return }
  uploadLoading.value = true
  try {
    await competitorAPI.uploadDocument(selectedCompetitor.value.id, uploadForm.file, uploadForm.docType, uploadForm.version, uploadForm.notes)
    ElMessage.success('上传成功')
    showUploadDialog.value = false
    uploadForm.file = null; uploadForm.version = ''; uploadForm.notes = ''
    if (uploadRef.value) uploadRef.value.clearFiles()
    await loadDocuments()
  } catch (e) { ElMessage.error('上传失败') } finally { uploadLoading.value = false }
}

// 删除文档
async function deleteDoc(row) {
  try {
    await ElMessageBox.confirm('确定要删除该文档吗？', '删除确认', { type: 'warning' })
    await competitorAPI.deleteDocument(selectedCompetitor.value.id, row.id)
    ElMessage.success('删除成功')
    await loadDocuments()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}

// 加载对比任务（指定竞品）
async function loadCompareTasks() {
  tasksLoading.value = true
  try {
    const res = await competitorAPI.getCompareTasks(selectedCompetitor.value.id, { page: 1, page_size: 20 })
    compareTasks.value = res.data.items || []
  } catch (e) { ElMessage.error('加载对比历史失败') } finally { tasksLoading.value = false }
}

// 加载所有对比任务（全局）
async function loadAllTasks() {
  tasksLoading.value = true
  try {
    const res = await competitorAPI.getAllCompareTasks({ page: tasksPage.value, page_size: tasksPageSize.value })
    allTasks.value = res.data.items || []
    tasksTotal.value = res.data.total || 0
  } catch (e) { ElMessage.error('加载对比历史失败') } finally { tasksLoading.value = false }
}

// 跳转到竞品详情
function goToCompetitor(row) {
  router.push(`/competitor/${row.competitor_id}`)
}

// 开始对比
async function startCompare() {
  if (!compareForm.competitorDocId || !compareForm.ourDocId) { ElMessage.warning('请选择文档'); return }
  compareLoading.value = true
  try {
    const res = await competitorAPI.createCompare(selectedCompetitor.value.id, compareForm.competitorDocId, compareForm.ourDocId)
    ElMessage.success('对比任务已创建')
    await pollTaskStatus(res.data.id)
    await loadCompareTasks()
  } catch (e) { ElMessage.error('创建对比任务失败') } finally { compareLoading.value = false }
}

// 轮询任务状态
async function pollTaskStatus(taskId) {
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 2000))
    const res = await competitorAPI.getCompareTask(selectedCompetitor.value.id, taskId)
    if (res.data.status === 'completed' || res.data.status === 'failed') return res.data
  }
  throw new Error('任务处理超时')
}

// 查看对比结果
async function viewCompareResult(row) {
  currentTask.value = row
  if (row.result_data) {
    try {
      const data = JSON.parse(row.result_data)
      Object.assign(resultData, { structure_diff: data.structure_diff || [], content_diff: data.content_diff || [], chapter_similarity: data.chapter_similarity || [] })
    } catch (e) { Object.assign(resultData, { structure_diff: [], content_diff: [], chapter_similarity: [] }) }
  } else {
    Object.assign(resultData, { structure_diff: [], content_diff: [], chapter_similarity: [] })
  }
  suggestions.value = row.suggestions ? JSON.parse(row.suggestions) : []
  showResultDialog.value = true
}

// 生成建议
async function generateSuggestions(row) {
  try {
    ElMessage.info('正在生成AI改进建议...')
    const res = await competitorAPI.generateSuggestions(row.competitor_id, row.id)
    suggestions.value = res.data.suggestions || []
    ElMessage.success('建议已生成')
    await loadCompareTasks()
    if (currentTask.value && currentTask.value.id === row.id) currentTask.value.suggestions = JSON.stringify(suggestions.value)
  } catch (e) { ElMessage.error('生成建议失败') }
}

// 导出报告
async function exportReport(row) {
  try {
    const res = await competitorAPI.exportReport(row.competitor_id, row.id)
    const blob = new Blob([res.data], { type: 'text/html' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url; link.download = `竞品对比报告_${row.competitor_name}_${new Date().toISOString().slice(0, 10)}.html`; link.click()
    link.remove(); window.URL.revokeObjectURL(url)
    ElMessage.success('报告已导出')
  } catch (e) { ElMessage.error('导出报告失败') }
}

// 监听路由变化
watch(() => route.params.id, async (id) => {
  if (id) {
    selectedCompetitor.value = await competitorAPI.get(Number(id)).then(r => r.data)
    await loadDocuments()
    await loadCompareTasks()
  }
})

watch(() => route.path, (path) => {
  if (path === '/competitor/tasks') loadAllTasks()
})

// 初始化
onMounted(() => {
  if (route.path === '/competitor/tasks') {
    loadAllTasks()
  } else if (route.params.id) {
    competitorAPI.get(Number(route.params.id)).then(res => {
      selectedCompetitor.value = res.data
      loadDocuments()
      loadCompareTasks()
    }).catch(() => ElMessage.error('加载竞品失败'))
  } else {
    loadCompetitors()
  }
})

// 编辑表单初始化
watch(showEditDialog, (val) => {
  if (val && selectedCompetitor.value) {
    Object.assign(editForm, {
      name: selectedCompetitor.value.name,
      brand: selectedCompetitor.value.brand || '',
      website: selectedCompetitor.value.website || '',
      description: selectedCompetitor.value.description || '',
      tags: selectedCompetitor.value.tags || ''
    })
  }
})
</script>

<style scoped>
.competitor-container { padding: 20px; }

.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h2 { margin: 0; }

.search-bar { margin-bottom: 20px; }

.pagination { margin-top: 20px; display: flex; justify-content: flex-end; }

.link { color: #409eff; text-decoration: none; }
.link:hover { text-decoration: underline; }

/* 详情页 */
.detail-header { display: flex; align-items: center; gap: 20px; margin-bottom: 20px; }
.detail-header h2 { margin: 0; }
.brand { color: #909399; font-size: 14px; margin-left: 10px; }

.info-card, .docs-card, .compare-card, .quick-card, .stats-card { margin-bottom: 20px; }

.doc-section h4 { margin: 0 0 10px 0; color: #303133; }

.compare-form { padding: 10px 0; }

/* 快捷操作 */
.quick-links { display: flex; flex-direction: column; gap: 10px; }
.quick-item { display: flex; align-items: center; gap: 10px; padding: 12px; background: #f5f7fa; border-radius: 8px; cursor: pointer; transition: all 0.2s; }
.quick-item:hover { background: #ecf5ff; }
.quick-item span { font-size: 14px; color: #303133; }

/* 统计信息 */
.stats { display: flex; justify-content: space-around; }
.stat-item { text-align: center; }
.stat-value { font-size: 28px; font-weight: bold; color: #409eff; }
.stat-label { font-size: 12px; color: #909399; margin-top: 5px; }

/* 对比结果 */
.compare-result .result-summary { display: flex; gap: 30px; margin-bottom: 20px; padding: 20px; background: #f5f7fa; border-radius: 8px; }

.similarity-box { text-align: center; }
.similarity-value { font-size: 48px; font-weight: bold; }
.similarity-value.high { color: #67c23a; }
.similarity-value.medium { color: #e6a23c; }
.similarity-value.low { color: #f56c6c; }
.similarity-label { color: #909399; margin-top: 5px; }

.task-info p { margin: 5px 0; }

/* 建议 */
.suggestions-list { max-height: 500px; overflow-y: auto; }
.suggestion-item { padding: 15px; border-radius: 8px; margin-bottom: 10px; border-left: 4px solid #909399; }
.suggestion-item.priority-high { border-left-color: #f56c6c; background: #fef0f0; }
.suggestion-item.priority-medium { border-left-color: #e6a23c; background: #fdf6ec; }
.suggestion-item.priority-low { border-left-color: #67c23a; background: #f0f9eb; }

.sug-header { display: flex; gap: 10px; margin-bottom: 10px; }
.sug-content { font-size: 14px; font-weight: 500; margin-bottom: 5px; }
.sug-reason, .sug-ref { color: #606266; font-size: 13px; margin: 5px 0; }

.no-suggestions { padding: 40px; }

.danger { color: #f56c6c; }
.info { color: #409eff; }
</style>