<template>
  <div class="review-dashboard">
    <header class="hero">
      <div class="hero-copy">
        <p class="eyebrow">文档质检</p>
        <h2>审核看板</h2>
        <p class="hero-caption">{{ viewCaption }}</p>
      </div>
      <div class="hero-tools">
        <div v-if="isAdmin" class="view-switch" role="tablist">
          <button type="button" :class="{ active: viewMode === 'overview' }" @click="switchView('overview')">管理视图</button>
          <button type="button" :class="{ active: viewMode === 'personal' }" @click="switchView('personal')">个人视图</button>
        </div>
        <div class="filter-pills">
          <el-select v-model="filters.time_range" size="small" style="width:108px" @change="loadDashboard">
            <el-option label="今日" value="1d" />
            <el-option label="近7天" value="7d" />
            <el-option label="近30天" value="30d" />
            <el-option label="近90天" value="90d" />
          </el-select>
          <el-select v-model="filters.doc_type" size="small" style="width:110px" @change="loadDashboard">
            <el-option label="全部类型" value="all" />
            <el-option label="Excel" value="excel" />
            <el-option label="PDF" value="pdf" />
            <el-option label="DOCX" value="docx" />
            <el-option label="DITA" value="dita" />
          </el-select>
          <el-select
            v-if="!isPersonalView"
            v-model="filters.user_id"
            size="small"
            style="width:140px"
            @change="loadDashboard"
          >
            <el-option label="全部人员" value="all" />
            <el-option
              v-for="user in userOptions"
              :key="user.id"
              :label="user.display_name || user.username"
              :value="String(user.id)"
            />
          </el-select>
          <el-button size="small" @click="loadDashboard" :loading="loading">刷新</el-button>
        </div>
      </div>
    </header>

    <div class="kpi-row" :class="{ personal: isPersonalView }" v-loading="loading">
      <article class="kpi ink">
        <div class="kpi-kicker">{{ isPersonalView ? '我的任务' : '审核任务' }}</div>
        <div class="kpi-value">{{ kpi.range_tasks }}</div>
        <div class="kpi-meta">完成 {{ kpi.range_completed || 0 }} 份</div>
      </article>
      <article class="kpi amber">
        <div class="kpi-kicker">单文档问题</div>
        <div class="kpi-value">{{ kpi.avg_issues_per_doc }}</div>
        <div class="kpi-meta">平均耗时 {{ formatMinutes(kpi.avg_review_time) }}</div>
      </article>
      <article class="kpi rose">
        <div class="kpi-kicker">检出率</div>
        <div class="kpi-value" :class="{ muted: !quality.detection_rate_available }">{{ detectionRateText }}</div>
        <div class="kpi-formula">平台有效检出 / (平台有效检出 + 人工补录漏检)</div>
        <div class="kpi-meta">有效检出 {{ quality.platform_detected || 0 }} 条，漏检 {{ quality.manual_supplemented || 0 }} 条</div>
      </article>
      <article v-if="!isPersonalView" class="kpi teal">
        <div class="kpi-kicker">误报率</div>
        <div class="kpi-value">{{ percentText(quality.false_positive_rate) }}</div>
        <div class="kpi-meta">误报 {{ quality.false_positive_count || 0 }} / 上报 {{ quality.platform_reported || 0 }}</div>
      </article>
    </div>

    <section v-if="!isPersonalView" class="mix-card">
      <div class="mix-hd">
        <h3>问题构成</h3>
        <p>有效检出、人工补录漏检与误报的数量对比</p>
      </div>
      <div v-if="qualityMix.total" class="mix-bar">
        <div
          v-for="item in qualityMix.items"
          v-show="item.count"
          :key="item.key"
          class="mix-seg"
          :class="item.key"
          :style="{ flexGrow: item.count }"
        >
          <span>{{ item.label }} {{ item.count }}</span>
        </div>
      </div>
      <div v-else class="mix-empty">当前筛选范围内还没有有效检出、漏检或误报样本。</div>
    </section>

    <div class="charts-row single">
      <section class="panel">
        <div class="panel-hd">
          <div>
            <h3>{{ isPersonalView ? '我的高占比问题' : '高占比问题' }}</h3>
            <p>按问题条数占比取 Top5</p>
          </div>
        </div>
        <v-chart v-if="issueRows.length" class="chart" :option="issueBarOption" autoresize />
        <el-empty v-else description="暂无问题分布" :image-size="64" />
      </section>
    </div>

    <div class="tables-row" :class="{ single: isPersonalView }">
      <section v-if="!isPersonalView" class="panel">
        <div class="panel-hd">
          <div>
            <h3>人员负荷</h3>
            <p>任务量、完成量与问题数</p>
          </div>
        </div>
        <el-table :data="userStats" size="small" empty-text="暂无数据" class="desk-table">
          <el-table-column prop="username" label="人员" min-width="120" show-overflow-tooltip />
          <el-table-column prop="tasks" label="任务" width="72" />
          <el-table-column prop="completed" label="完成" width="72" />
          <el-table-column prop="issues" label="问题" width="72" />
        </el-table>
      </section>
      <section class="panel panel-wide">
        <div class="panel-hd">
          <div>
            <h3>{{ isPersonalView ? '我的最近任务' : '最近审核任务' }}</h3>
            <p>按提交时间倒序</p>
          </div>
        </div>
        <el-table :data="taskList" size="small" empty-text="暂无数据" class="desk-table">
          <el-table-column prop="review_id" label="ID" width="70" />
          <el-table-column v-if="!isPersonalView" prop="submitted_by" label="提交人" width="100" show-overflow-tooltip />
          <el-table-column prop="document_name" label="文档" min-width="180" show-overflow-tooltip />
          <el-table-column label="类型" width="88">
            <template #default="scope">{{ docTypeLabel(scope.row.document_type) }}</template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="96">
            <template #default="scope">
              <span class="status-pill" :class="scope.row.status">{{ statusText(scope.row.status) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="issue_count" label="问题" width="72" />
          <el-table-column prop="submitted_at" label="提交时间" width="160">
            <template #default="scope">{{ formatTime(scope.row.submitted_at) }}</template>
          </el-table-column>
        </el-table>
      </section>
    </div>

    <section v-if="!isPersonalView" class="panel cluster-panel">
      <div class="panel-hd">
        <div>
          <h3>人工意见样本池</h3>
          <p>{{ cluster.total }} 条意见，规则候选 {{ cluster.rule_candidate_count }}</p>
        </div>
        <div class="panel-actions">
          <el-button size="small" @click="loadCluster">刷新</el-button>
          <el-button size="small" type="primary" @click="openImportDialog">导入意见</el-button>
        </div>
      </div>
      <template v-if="clusterLoaded && cluster.total">
        <div class="cluster-grid">
          <el-table :data="clusterCategoryRows" size="small" max-height="280" class="desk-table">
            <el-table-column prop="category" label="类别" min-width="120" show-overflow-tooltip />
            <el-table-column prop="count" label="条数" width="72" />
            <el-table-column label="占比" width="80">
              <template #default="scope">{{ clusterPercent(scope.row.count) }}</template>
            </el-table-column>
          </el-table>
          <el-table :data="cluster.rule_candidates || []" size="small" max-height="280" class="desk-table">
            <el-table-column prop="category" label="类别" width="110" show-overflow-tooltip />
            <el-table-column prop="comment" label="意见" min-width="180" show-overflow-tooltip />
            <el-table-column prop="count" label="次数" width="72" />
            <el-table-column label="" width="240">
              <template #default="scope">
                <el-button size="small" type="primary" link @click="convertCandidate(scope.row)">转候选</el-button>
                <el-button size="small" type="success" link @click="toggleCandidateRule(scope.row, true)">启用</el-button>
                <el-button size="small" type="warning" link @click="toggleCandidateRule(scope.row, false)">停用</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
      <div v-else class="cluster-empty">导入整理好的 md / json / csv 后，可在这里看类别分布和高频规则候选。</div>
    </section>

    <el-dialog v-model="importDialogVisible" title="导入人工审核意见" width="640px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="意见文件">
          <el-upload
            drag
            :auto-upload="false"
            :limit="1"
            accept=".md,.json,.csv,.markdown,.txt"
            :on-change="onImportFileChange"
            :on-remove="onImportFileRemove"
          >
            <div class="upload-tip">
              <div>拖拽文件到此处，或点击选择</div>
              <div class="upload-sub">支持 gold_v0 评测集 .json / 标注集 .csv / 意见汇总 .md</div>
            </div>
          </el-upload>
        </el-form-item>
        <el-form-item label="批次名称">
          <el-input v-model="importBatchName" placeholder="留空则用文件名" />
        </el-form-item>
        <el-form-item v-if="importPreview.parsed > 0" label="解析预览">
          <div class="preview-box">
            <div class="preview-line">解析出 <b>{{ importPreview.parsed }}</b> 条人工意见</div>
            <div class="preview-cats">
              <el-tag v-for="(count, cat) in importPreview.category_distribution" :key="cat" size="small" effect="plain">
                {{ cat }} x{{ count }}
              </el-tag>
            </div>
            <div v-for="(row, idx) in importPreview.sample.slice(0, 3)" :key="idx" class="preview-sample">
              <div class="sample-doc">{{ row.doc_name || '(无文档名)' }} · p{{ row.page || '-' }}</div>
              <div class="sample-comment">{{ row.comment || '-' }}</div>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!selectedImportFile" :loading="importing" @click="doImport">解析并预览</el-button>
        <el-button v-if="importPreview.inserted > 0" type="success" :loading="importing" @click="confirmImport">确认入库（{{ importPreview.inserted }} 条）</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { reviewAPI, userAPI, getAPIErrorMessage } from '@/api'
import { useUserStore } from '@/store/user'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const loading = ref(false)
const userStore = useUserStore()
const isAdmin = computed(() => userStore.isAdmin)
const viewMode = ref(userStore.isAdmin ? 'overview' : 'personal')
const filters = reactive({ time_range: '7d', doc_type: 'all', user_id: 'all' })
const kpi = reactive({ range_tasks: 0, range_completed: 0, avg_issues_per_doc: 0, avg_review_time: null })
const quality = reactive({
  platform_detected: 0,
  manual_supplemented: 0,
  expected_issues: 0,
  false_positive_count: 0,
  platform_reported: 0,
  accuracy_rate: 0,
  false_positive_rate: 0,
  detection_rate: null,
  detection_rate_available: false
})
const issueDistribution = ref([])
const userStats = ref([])
const taskList = ref([])
const userOptions = ref([])
const isPersonalView = computed(() => viewMode.value === 'personal' || !isAdmin.value)
const viewCaption = computed(() => (
  isPersonalView.value
    ? '看我提交的任务、检出率和问题结构'
    : '看全员任务量、检出质量、问题结构和人员负荷'
))

let refreshTimer = null

const importDialogVisible = ref(false)
const selectedImportFile = ref(null)
const importBatchName = ref('')
const importing = ref(false)
const importPreview = reactive({ parsed: 0, inserted: 0, skipped: 0, category_distribution: {}, sample: [], batch_name: '' })
const cluster = reactive({ total: 0, category_distribution: {}, rule_candidates: [], rule_candidate_count: 0 })
const clusterLoaded = ref(false)

function openImportDialog() {
  selectedImportFile.value = null
  importBatchName.value = ''
  Object.assign(importPreview, { parsed: 0, inserted: 0, skipped: 0, category_distribution: {}, sample: [], batch_name: '' })
  importDialogVisible.value = true
}

function onImportFileChange(file) {
  selectedImportFile.value = file.raw
  importBatchName.value = ''
  Object.assign(importPreview, { parsed: 0, inserted: 0, skipped: 0, category_distribution: {}, sample: [], batch_name: '' })
}

function onImportFileRemove() {
  selectedImportFile.value = null
}

async function doImport() {
  if (!selectedImportFile.value) return
  importing.value = true
  try {
    const response = await reviewAPI.importSupplements(selectedImportFile.value, importBatchName.value)
    const data = response.data || {}
    Object.assign(importPreview, {
      parsed: data.parsed || 0,
      inserted: data.inserted || 0,
      skipped: data.skipped || 0,
      category_distribution: data.category_distribution || {},
      sample: data.sample || [],
      batch_name: data.batch_name || ''
    })
  } catch (error) {
    ElMessage.error(`解析失败: ${getAPIErrorMessage(error)}`)
  } finally {
    importing.value = false
  }
}

async function confirmImport() {
  importing.value = true
  try {
    ElMessage.success(`已入库 ${importPreview.inserted} 条人工审核意见（批次: ${importPreview.batch_name}）`)
    importDialogVisible.value = false
    await loadCluster()
  } catch (error) {
    ElMessage.error(`入库失败: ${getAPIErrorMessage(error)}`)
  } finally {
    importing.value = false
  }
}

const clusterCategoryRows = computed(() => {
  return Object.entries(cluster.category_distribution || {})
    .map(([category, count]) => ({ category, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 15)
})

function clusterPercent(count) {
  if (!cluster.total) return '--'
  return `${((count / cluster.total) * 100).toFixed(1)}%`
}

async function loadCluster() {
  clusterLoaded.value = false
  try {
    const response = await reviewAPI.clusterSupplements({ min_count: 3 })
    const data = response.data || {}
    Object.assign(cluster, {
      total: data.total || 0,
      category_distribution: data.category_distribution || {},
      rule_candidates: data.rule_candidates || [],
      rule_candidate_count: data.rule_candidate_count || 0
    })
    clusterLoaded.value = true
  } catch (error) {
    ElMessage.error(`聚类加载失败: ${getAPIErrorMessage(error)}`)
    clusterLoaded.value = false
  }
}

async function convertCandidate(row) {
  if (!row.ids || !row.ids.length) {
    ElMessage.warning('该候选缺少样本 id')
    return
  }
  try {
    await reviewAPI.convertSupplement(row.ids[0])
    ElMessage.success('已生成规则草案（默认禁用，需点「启用」才生效）')
    await loadCluster()
  } catch (error) {
    ElMessage.error(`操作失败: ${getAPIErrorMessage(error)}`)
  }
}

async function toggleCandidateRule(row, enable) {
  if (!row.ids || !row.ids.length) {
    ElMessage.warning('该候选缺少样本 id')
    return
  }
  try {
    if (enable) {
      await reviewAPI.enableSupplementRule(row.ids[0])
      ElMessage.success('已启用：后续审核会把该抽象检测要点作为审核依据（不会照搬原文）')
    } else {
      await reviewAPI.disableSupplementRule(row.ids[0])
      ElMessage.success('已停用，回到草案状态')
    }
    await loadCluster()
  } catch (error) {
    ElMessage.error(`操作失败: ${getAPIErrorMessage(error)}`)
  }
}

const issueRows = computed(() => {
  const rows = issueDistribution.value
    .map(item => ({ ...item, percent: Math.round((Number(item.percentage || 0) * 100) * 10) / 10 }))
    .sort((left, right) => right.percent - left.percent)
  const topRows = rows.slice(0, 5)
  const restRows = rows.slice(5)
  if (!restRows.length) return topRows
  const restCount = restRows.reduce((sum, item) => sum + Number(item.count || 0), 0)
  const restPercent = Math.round(restRows.reduce((sum, item) => sum + item.percent, 0) * 10) / 10
  return [...topRows, { type: '其他', count: restCount, percent: restPercent }]
})

const qualityMix = computed(() => {
  const items = [
    { key: 'detected', label: '有效检出', count: Number(quality.platform_detected || 0) },
    { key: 'miss', label: '人工漏检', count: Number(quality.manual_supplemented || 0) },
    { key: 'fp', label: '误报', count: Number(quality.false_positive_count || 0) }
  ]
  return {
    total: items.reduce((sum, item) => sum + item.count, 0),
    items
  }
})

function barColor(percent) {
  if (percent >= 30) return '#ef4444'
  if (percent >= 20) return '#f59e0b'
  return '#3b82f6'
}

function shortenLabel(text) {
  const value = String(text || '')
  return value.length > 16 ? `${value.slice(0, 15)}…` : value
}

const issueBarOption = computed(() => ({
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter: params => {
      const item = params?.[0]
      const row = issueRows.value[item?.dataIndex || 0]
      return row ? `${row.type}<br/>占比 ${row.percent}% · ${row.count} 条` : ''
    }
  },
  grid: { left: 92, right: 44, top: 8, bottom: 8 },
  xAxis: {
    type: 'value',
    axisLabel: { formatter: '{value}%', color: '#94a3b8' },
    splitLine: { lineStyle: { color: '#eef2f6' } }
  },
  yAxis: {
    type: 'category',
    data: issueRows.value.map(item => shortenLabel(item.type)),
    inverse: true,
    axisTick: { show: false },
    axisLine: { show: false },
    axisLabel: { color: '#475569', fontSize: 11 }
  },
  series: [
    {
      name: '问题占比',
      type: 'bar',
      data: issueRows.value.map(item => ({ value: item.percent, itemStyle: { color: barColor(item.percent) } })),
      barMaxWidth: 16,
      itemStyle: { borderRadius: [0, 8, 8, 0] },
      label: { show: true, position: 'right', formatter: '{c}%', color: '#334155', fontSize: 11 }
    }
  ]
}))

function percentText(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '--'
  return `${(number * 100).toFixed(1)}%`
}

const detectionRateText = computed(() => {
  if (!quality.detection_rate_available) return '暂无法计算'
  return percentText(quality.detection_rate)
})

function formatMinutes(value) {
  const number = Number(value)
  if (!Number.isFinite(number) || number <= 0) return '--'
  return `${number} 分钟`
}

function formatTime(value) {
  if (!value) return '--'
  return String(value).replace('T', ' ').slice(0, 19)
}

function statusText(status) {
  const map = { completed: '已完成', running: '进行中', pending: '待处理', failed: '失败' }
  return map[status] || status || '--'
}

function docTypeLabel(type) {
  return { excel: 'Excel', pdf: 'PDF', docx: 'Word', dita: 'DITA' }[type] || type || '其他'
}

function switchView(mode) {
  viewMode.value = mode
  if (isPersonalView.value) {
    filters.user_id = 'all'
  }
  loadDashboard()
}

async function loadDashboard() {
  loading.value = true
  try {
    const params = { time_range: filters.time_range, doc_type: filters.doc_type }
    if (!isPersonalView.value && filters.user_id && filters.user_id !== 'all') {
      params.user_id = filters.user_id
    }
    const response = isPersonalView.value
      ? await reviewAPI.getDashboardPersonal(params)
      : await reviewAPI.getDashboardOverview(params)
    const data = response.data || {}
    Object.assign(kpi, data.kpi || {})
    Object.assign(quality, {
      platform_detected: 0,
      manual_supplemented: 0,
      expected_issues: 0,
      false_positive_count: 0,
      platform_reported: 0,
      accuracy_rate: 0,
      false_positive_rate: 0,
      detection_rate: null,
      detection_rate_available: false
    }, data.quality || {})
    issueDistribution.value = data.issue_distribution || []
    userStats.value = data.user_stats || []
    taskList.value = data.task_list || []
  } catch (error) {
    ElMessage.error(`加载审核看板失败: ${getAPIErrorMessage(error)}`)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (!isAdmin.value) {
    viewMode.value = 'personal'
  }
  loadDashboard()
  if (isAdmin.value) {
    loadUsers()
    loadCluster()
  }
  refreshTimer = setInterval(loadDashboard, 5 * 60 * 1000)
})

async function loadUsers() {
  try {
    const response = await userAPI.list({ page: 1, page_size: 100 })
    userOptions.value = response.data?.items || []
  } catch (error) {
    userOptions.value = []
  }
}

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
.review-dashboard {
  max-width: 1280px;
  margin: 0 auto;
  color: #1e293b;
}
.hero {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: flex-end;
  padding: 22px 24px;
  margin-bottom: 16px;
  border-radius: 12px;
  color: #fff;
  background: linear-gradient(90deg, #3b82f6 0%, #60a5fa 50%, #3b82f6 100%);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.18);
  flex-wrap: wrap;
}
.eyebrow {
  margin: 0 0 6px;
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.78);
}
.hero h2 {
  margin: 0;
  font-size: 28px;
  font-weight: 650;
  letter-spacing: -0.03em;
}
.hero-caption {
  margin: 8px 0 0;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.78);
}
.hero-tools {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
}
.view-switch {
  display: inline-flex;
  padding: 3px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.18);
}
.view-switch button {
  border: 0;
  background: transparent;
  color: rgba(255, 255, 255, 0.86);
  padding: 6px 14px;
  border-radius: 999px;
  cursor: pointer;
  font-size: 13px;
}
.view-switch button.active {
  background: #fff;
  color: #2563eb;
  font-weight: 650;
}
.filter-pills {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.kpi-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}
.kpi-row.personal { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.kpi {
  position: relative;
  overflow: hidden;
  background: #fff;
  border: 1px solid #dbeafe;
  border-radius: 12px;
  padding: 16px 18px 14px;
  box-shadow: 0 1px 3px rgba(59, 130, 246, 0.06);
}
.kpi::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
}
.kpi.ink::before { background: #3b82f6; }
.kpi.amber::before { background: #60a5fa; }
.kpi.rose::before { background: #2563eb; }
.kpi.teal::before { background: #38bdf8; }
.kpi-kicker {
  font-size: 12px;
  color: #64748b;
  letter-spacing: 0.04em;
}
.kpi-value {
  margin-top: 10px;
  font-size: 30px;
  font-weight: 700;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  color: #1e293b;
}
.kpi-value.muted {
  color: #94a3b8;
  font-size: 22px;
  font-weight: 600;
}
.kpi-formula {
  margin-top: 10px;
  font-size: 12px;
  line-height: 1.45;
  color: #475569;
}
.kpi-meta {
  margin-top: 6px;
  font-size: 12px;
  color: #94a3b8;
}
.mix-card,
.panel {
  background: #fff;
  border: 1px solid #dbeafe;
  border-radius: 12px;
  padding: 16px 18px 14px;
  min-width: 0;
}
.mix-card { margin-bottom: 12px; }
.mix-hd h3,
.panel-hd h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
}
.mix-hd p,
.panel-hd p {
  margin: 4px 0 0;
  font-size: 12px;
  color: #94a3b8;
}
.mix-bar {
  display: flex;
  overflow: hidden;
  margin-top: 12px;
  height: 42px;
  border-radius: 999px;
  background: #eff6ff;
}
.mix-seg {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
}
.mix-seg.detected { background: #3b82f6; }
.mix-seg.miss { background: #f59e0b; }
.mix-seg.fp { background: #ef4444; }
.mix-empty {
  margin-top: 10px;
  color: #94a3b8;
  font-size: 13px;
}
.charts-row,
.tables-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}
.tables-row { grid-template-columns: minmax(260px, 0.72fr) minmax(0, 1.28fr); }
.charts-row.single,
.tables-row.single { grid-template-columns: 1fr; }
.panel-hd {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}
.panel-actions { display: flex; align-items: center; gap: 8px; }
.chart { height: 248px; width: 100%; }
.desk-table {
  --el-table-header-bg-color: #eff6ff;
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-row-hover-bg-color: #dbeafe;
}
.status-pill {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 12px;
}
.status-pill.completed { background: #d1fae5; color: #047857; }
.status-pill.running { background: #dbeafe; color: #1d4ed8; }
.status-pill.pending { background: #fef3c7; color: #b45309; }
.status-pill.failed { background: #fee2e2; color: #dc2626; }
.cluster-grid {
  display: grid;
  grid-template-columns: 0.85fr 1.15fr;
  gap: 12px;
}
.cluster-empty {
  color: #94a3b8;
  font-size: 13px;
  padding: 8px 0 4px;
}
.upload-tip { text-align: center; color: #475569; }
.upload-sub { font-size: 12px; color: #94a3b8; margin-top: 4px; }
.preview-box {
  width: 100%;
  background: #f8fafc;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  color: #475569;
  max-height: 280px;
  overflow: auto;
}
.preview-line { margin: 4px 0; }
.preview-cats { display: flex; flex-wrap: wrap; gap: 4px; margin: 6px 0; }
.preview-sample { border-top: 1px dashed #dbeafe; padding: 6px 0; }
.sample-doc { font-size: 12px; color: #94a3b8; }
.sample-comment { font-size: 13px; color: #1e293b; margin-top: 2px; }
@media (max-width: 1100px) {
  .kpi-row,
  .charts-row,
  .tables-row,
  .cluster-grid { grid-template-columns: 1fr; }
  .hero-tools { align-items: flex-start; }
}
@media (max-width: 640px) {
  .hero { padding: 18px; }
  .hero h2 { font-size: 22px; }
}
</style>
