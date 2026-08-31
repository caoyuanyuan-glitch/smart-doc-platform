<template>
  <div class="review-dashboard">
    <div class="page-head">
      <div>
        <h2>文档审核统计看板</h2>
        <p>{{ pageSubtitle }}</p>
      </div>
      <el-button size="small" @click="loadDashboard" :loading="loading">刷新</el-button>
    </div>

    <div class="filter-bar">
      <el-tabs v-if="isAdmin" v-model="viewMode" @tab-change="onViewChange">
        <el-tab-pane label="管理视图" name="overview" />
        <el-tab-pane label="个人视图" name="personal" />
      </el-tabs>
      <el-tag :type="isPersonalView ? 'success' : 'primary'" effect="plain">{{ scopeLabel }}</el-tag>
      <el-select v-model="filters.time_range" size="small" style="width:120px" @change="loadDashboard">
        <el-option label="今日" value="1d" />
        <el-option label="近7天" value="7d" />
        <el-option label="近30天" value="30d" />
        <el-option label="近90天" value="90d" />
      </el-select>
      <el-select v-model="filters.doc_type" size="small" style="width:130px" @change="loadDashboard">
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
        style="width:160px"
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
    </div>

    <div class="summary-grid" v-loading="loading">
      <div class="summary-card kpi-card blue">
        <div class="kpi-label">{{ isPersonalView ? '我的审核任务' : '全员审核任务' }}</div>
        <div class="kpi-value">{{ kpi.range_tasks }}</div>
        <div class="kpi-desc">已完成 {{ kpi.range_completed || 0 }} 个</div>
      </div>
      <div class="summary-card kpi-card soft-blue">
        <div class="kpi-label">平均单文档问题</div>
        <div class="kpi-value">{{ kpi.avg_issues_per_doc }}</div>
        <div class="kpi-desc">平均耗时 {{ formatMinutes(kpi.avg_review_time) }}</div>
      </div>
      <div class="summary-card quality-card detection-rate">
        <div class="quality-label">检出率</div>
        <div class="quality-value" :class="{ 'is-muted': !quality.detection_rate_available }">{{ detectionRateText }}</div>
        <div class="quality-desc">平台有效检出 / (平台有效检出 + 人工补录漏检)</div>
        <div class="quality-subdesc">{{ detectionRateHint }}</div>
      </div>
      <div v-if="!isPersonalView" class="summary-card quality-card false-positive-rate">
        <div class="quality-label">误报率</div>
        <div class="quality-value">{{ percentText(quality.false_positive_rate) }}</div>
        <div class="quality-desc">人工标记误报 / 平台上报问题</div>
        <div class="quality-subdesc">误报 {{ quality.false_positive_count || 0 }} 条 · 平台上报 {{ quality.platform_reported || 0 }} 条</div>
      </div>
    </div>

    <div class="chart-card wide">
      <div class="section-title">
        <span>{{ isPersonalView ? '我的高占比问题 Top5' : '全员高占比问题 Top5' }}</span>
        <small>其余合并为其他细碎问题</small>
      </div>
      <v-chart class="chart" :option="issueBarOption" autoresize />
    </div>

    <div v-if="!isPersonalView" class="chart-card wide">
      <div class="section-title">
        <span>提交与完成趋势</span>
        <small>按任务创建日统计</small>
      </div>
      <v-chart class="chart" :option="trendOption" autoresize />
    </div>

    <div v-if="!isPersonalView" class="chart-card wide table-card">
      <div class="section-title">
        <span>人员任务量</span>
        <small>管理视图按提交人汇总</small>
      </div>
      <el-table :data="userStats" size="small" border>
        <el-table-column prop="username" label="人员" min-width="140" />
        <el-table-column prop="tasks" label="任务数" width="100" />
        <el-table-column prop="completed" label="已完成" width="100" />
        <el-table-column prop="issues" label="问题数" width="100" />
      </el-table>
    </div>

    <div class="chart-card wide table-card">
      <div class="section-title">
        <span>{{ isPersonalView ? '我的最近任务' : '最近审核任务' }}</span>
        <small>最多展示 50 条</small>
      </div>
      <el-table :data="taskList" size="small" border>
        <el-table-column prop="review_id" label="任务ID" width="90" />
        <el-table-column v-if="!isPersonalView" prop="submitted_by" label="提交人" width="120" />
        <el-table-column prop="document_name" label="文档" min-width="180" show-overflow-tooltip />
        <el-table-column prop="document_type" label="类型" width="90" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="scope">{{ statusText(scope.row.status) }}</template>
        </el-table-column>
        <el-table-column prop="issue_count" label="问题数" width="90" />
        <el-table-column prop="submitted_at" label="提交时间" min-width="160">
          <template #default="scope">{{ formatTime(scope.row.submitted_at) }}</template>
        </el-table-column>
      </el-table>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { reviewAPI, userAPI, getAPIErrorMessage } from '@/api'
import { useUserStore } from '@/store/user'

use([BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

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
const trend = reactive({ dates: [], submitted: [], completed: [] })
const userStats = ref([])
const taskList = ref([])
const userOptions = ref([])
const isPersonalView = computed(() => viewMode.value === 'personal' || !isAdmin.value)
const scopeLabel = computed(() => (isPersonalView.value ? '个人视图 · 仅我的任务' : '管理视图 · 全员任务'))
const pageSubtitle = computed(() => (
  isPersonalView.value
    ? '统计我提交的审核任务、问题分布和漏检补录'
    : '统计全部人员的审核任务、问题分布、误报和漏检补录'
))

let refreshTimer = null

const issueRows = computed(() => {
  const rows = issueDistribution.value
    .map(item => ({ ...item, percent: Math.round((Number(item.percentage || 0) * 100) * 10) / 10 }))
    .sort((left, right) => right.percent - left.percent)
  const topRows = rows.slice(0, 5)
  const restRows = rows.slice(5)
  if (!restRows.length) return topRows
  const restCount = restRows.reduce((sum, item) => sum + Number(item.count || 0), 0)
  const restPercent = Math.round(restRows.reduce((sum, item) => sum + item.percent, 0) * 10) / 10
  return [...topRows, { type: '其他细碎问题', count: restCount, percent: restPercent }]
})

function barColor(percent) {
  if (percent >= 30) return '#dc2626'
  if (percent >= 20) return '#f97316'
  return '#2563eb'
}

const issueBarOption = computed(() => ({
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter: params => {
      const item = params?.[0]
      const row = issueRows.value[item?.dataIndex || 0]
      return row ? `${row.type}<br/>占比: ${row.percent}%<br/>数量: ${row.count}` : ''
    }
  },
  grid: { left: 36, right: 18, top: 32, bottom: 98 },
  xAxis: {
    type: 'category',
    data: issueRows.value.map(item => item.type),
    axisTick: { show: false },
    axisLine: { lineStyle: { color: '#d9e2ec' } },
    axisLabel: { interval: 0, rotate: 28, width: 118, overflow: 'break', color: '#64748b', fontSize: 12 }
  },
  yAxis: {
    type: 'value',
    axisLabel: { formatter: '{value}%', color: '#94a3b8' },
    splitLine: { lineStyle: { color: '#edf2f7' } }
  },
  series: [
    {
      name: '问题占比',
      type: 'bar',
      data: issueRows.value.map(item => ({ value: item.percent, itemStyle: { color: barColor(item.percent) } })),
      barMaxWidth: 46,
      itemStyle: { borderRadius: [5, 5, 0, 0] },
      label: { show: true, position: 'top', formatter: '{c}%', color: '#1f2937', fontWeight: 700 }
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

const detectionRateHint = computed(() => {
  const platform = quality.platform_detected || 0
  const manual = quality.manual_supplemented || 0
  if (!quality.detection_rate_available) {
    return `平台有效检出 ${platform} 条，人工补录漏检 0 条。检出率需要漏检样本，当前暂无法计算。`
  }
  return `平台有效检出 ${platform} 条 · 人工补录漏检 ${manual} 条`
})

const trendOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['提交', '完成'], bottom: 0 },
  grid: { left: 36, right: 18, top: 32, bottom: 48 },
  xAxis: {
    type: 'category',
    data: trend.dates,
    axisTick: { show: false },
    axisLine: { lineStyle: { color: '#d9e2ec' } },
    axisLabel: { color: '#64748b' }
  },
  yAxis: {
    type: 'value',
    minInterval: 1,
    axisLabel: { color: '#94a3b8' },
    splitLine: { lineStyle: { color: '#edf2f7' } }
  },
  series: [
    { name: '提交', type: 'line', data: trend.submitted, smooth: true, symbol: 'circle' },
    { name: '完成', type: 'line', data: trend.completed, smooth: true, symbol: 'circle' }
  ]
}))

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

function onViewChange() {
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
    Object.assign(trend, { dates: [], submitted: [], completed: [] }, data.trend || {})
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
.review-dashboard { padding: 28px; color: #303133; background: #f8fafc; min-height: 100%; }
.page-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-head h2 { margin: 0 0 6px; font-size: 22px; }
.page-head p { margin: 0; color: #8c8c8c; }
.filter-bar { display: flex; align-items: center; gap: 12px; padding: 14px 18px; margin-bottom: 22px; background: #fff; border-radius: 10px; box-shadow: 0 1px 6px rgba(15,23,42,0.04); }
.filter-bar :deep(.el-tabs__header) { margin: 0; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 18px; margin-bottom: 24px; }
.summary-card { min-height: 158px; }
.kpi-card { padding: 26px 22px; border-radius: 12px; color: #fff; box-shadow: 0 6px 18px rgba(24,144,255,0.10); }
.kpi-card.blue { background: linear-gradient(135deg, #1890ff, #096dd9); }
.kpi-card.soft-blue { background: linear-gradient(135deg, #38bdf8, #0f766e); }
.kpi-label { font-size: 13px; opacity: .9; }
.kpi-value { margin-top: 12px; font-size: 38px; line-height: 1; font-weight: 900; }
.kpi-desc { margin-top: 14px; font-size: 12px; opacity: .78; }
.quality-card { border-radius: 12px; padding: 24px 22px; box-shadow: 0 6px 18px rgba(15,23,42,0.05); border: 1px solid #dfe7f2; background: #fff; }
.quality-card.detection-rate { background: linear-gradient(135deg, #ecfdf5, #fff); }
.quality-card.false-positive-rate { background: linear-gradient(135deg, #fff7ed, #fff); }
.quality-label { color: #64748b; font-size: 13px; font-weight: 700; }
.quality-value { margin-top: 12px; font-size: 38px; font-weight: 900; color: #1f2937; }
.quality-value.is-muted { font-size: 26px; color: #94a3b8; }
.quality-desc { margin-top: 12px; color: #94a3b8; font-size: 12px; line-height: 1.5; }
.quality-subdesc { margin-top: 8px; color: #64748b; font-size: 12px; }
.chart-card { background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 1px 8px rgba(15,23,42,0.05); }
.chart-card.wide { margin-bottom: 16px; }
.table-card { overflow: auto; }
.section-title { display: flex; align-items: baseline; gap: 10px; font-size: 16px; font-weight: 700; margin-bottom: 16px; }
.section-title small { color: #94a3b8; font-size: 12px; font-weight: 500; }
.chart { height: 360px; }
@media (max-width: 768px) { .review-dashboard { padding: 16px; } .filter-bar { flex-wrap: wrap; } }
</style>
