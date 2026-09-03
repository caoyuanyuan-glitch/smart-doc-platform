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
      <div class="summary-card kpi-card">
        <div class="kpi-label">{{ isPersonalView ? '我的审核任务' : '全员审核任务' }}</div>
        <div class="kpi-value-row">
          <span class="kpi-value">{{ kpi.range_tasks }}</span>
          <span class="kpi-unit">个</span>
        </div>
        <div class="kpi-desc">已完成 {{ kpi.range_completed || 0 }} 个</div>
      </div>
      <div class="summary-card kpi-card">
        <div class="kpi-label">平均单文档问题</div>
        <div class="kpi-value-row">
          <span class="kpi-value">{{ kpi.avg_issues_per_doc }}</span>
          <span class="kpi-unit">条</span>
        </div>
        <div class="kpi-desc">平均耗时 {{ formatMinutes(kpi.avg_review_time) }}</div>
      </div>
      <div class="summary-card quality-card">
        <div class="quality-label">检出率</div>
        <div class="kpi-value-row">
          <span class="quality-value" :class="{ 'is-muted': !quality.detection_rate_available }">{{ detectionRateText }}</span>
          <span v-if="quality.detection_rate_available" class="kpi-unit">%</span>
        </div>
        <div v-if="!quality.detection_rate_available" class="quality-subdesc">需漏检样本数据</div>
        <el-tooltip placement="top">
          <template #content>
            <div>平台有效检出 / (平台有效检出 + 人工补录漏检)</div>
            <div>{{ detectionRateHint }}</div>
          </template>
          <span class="metric-help">i</span>
        </el-tooltip>
      </div>
      <div v-if="!isPersonalView" class="summary-card quality-card">
        <div class="quality-label">误报率</div>
        <div class="kpi-value-row">
          <span class="quality-value">{{ percentNumber(quality.false_positive_rate) }}</span>
          <span class="kpi-unit">%</span>
        </div>
        <el-tooltip placement="top">
          <template #content>
            <div>人工标记误报 / 平台上报问题</div>
            <div>误报 {{ quality.false_positive_count || 0 }} 条 · 平台上报 {{ quality.platform_reported || 0 }} 条</div>
          </template>
          <span class="metric-help">i</span>
        </el-tooltip>
      </div>
    </div>

    <div class="chart-row" :class="{ single: !otherIssueRows.length }">
      <div class="chart-card">
        <div class="section-title">
          <span>{{ isPersonalView ? '我的高占比问题 Top5' : '全员高占比问题 Top5' }}</span>
        </div>
        <v-chart class="chart" :option="issueBarOption" autoresize />
      </div>
      <div v-if="otherIssueRows.length" class="chart-card">
        <div class="section-title">
          <span>其他组研问题</span>
        </div>
        <v-chart class="chart" :option="issuePieOption" autoresize />
      </div>
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
import { use, graphic } from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { reviewAPI, userAPI, getAPIErrorMessage } from '@/api'
import { useUserStore } from '@/store/user'

use([BarChart, LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

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

const rankedIssueRows = computed(() => (
  issueDistribution.value
    .map(item => ({ ...item, percent: Math.round((Number(item.percentage || 0) * 100) * 10) / 10 }))
    .sort((left, right) => right.percent - left.percent)
))

const issueRows = computed(() => rankedIssueRows.value.slice(0, 5))

const RING_COLORS = ['#4F8CF7', '#8FB0F0', '#B5CCF5', '#D6E3FA', '#E8EFFC']

const otherIssueRows = computed(() => {
  const restRows = rankedIssueRows.value.slice(5)
  if (restRows.length <= 5) return restRows
  const visible = restRows.slice(0, 4)
  const merged = restRows.slice(4)
  const count = merged.reduce((sum, item) => sum + Number(item.count || 0), 0)
  const percent = Math.round(merged.reduce((sum, item) => sum + item.percent, 0) * 10) / 10
  return [...visible, { type: '其他', count, percent }]
})

const barGradient = new graphic.LinearGradient(0, 0, 0, 1, [
  { offset: 0, color: '#4F8CF7' },
  { offset: 1, color: '#7AA3F9' }
])

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
    axisLabel: {
      interval: 0,
      rotate: issueRows.value.some(item => String(item.type || '').length > 8) ? 30 : 0,
      width: 118,
      overflow: 'truncate',
      color: '#5A6B87',
      fontSize: 12
    }
  },
  yAxis: {
    type: 'value',
    axisLabel: { formatter: '{value}%', color: '#8C9AB7' },
    splitLine: { lineStyle: { color: '#edf2f7' } }
  },
  series: [
    {
      name: '问题占比',
      type: 'bar',
      data: issueRows.value.map(item => item.percent),
      barMaxWidth: 46,
      itemStyle: { color: barGradient, borderRadius: [5, 5, 0, 0] },
      label: {
        show: true,
        position: 'top',
        formatter: params => issueRows.value[params.dataIndex]?.count ?? params.value,
        color: '#1A2D4D',
        fontSize: 12,
        fontWeight: 600
      }
    }
  ]
}))

function percentNumber(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '--'
  return (number * 100).toFixed(1)
}

const detectionRateText = computed(() => {
  if (!quality.detection_rate_available) return '--'
  return percentNumber(quality.detection_rate)
})

const detectionRateHint = computed(() => {
  const platform = quality.platform_detected || 0
  const manual = quality.manual_supplemented || 0
  if (!quality.detection_rate_available) {
    return `平台有效检出 ${platform} 条，人工补录漏检 0 条。检出率需要漏检样本，当前暂无法计算。`
  }
  return `平台有效检出 ${platform} 条 · 人工补录漏检 ${manual} 条`
})

const issuePieOption = computed(() => ({
  tooltip: {
    trigger: 'item',
    formatter: params => `${params.name}<br/>数量: ${params.value}<br/>占比: ${params.percent}%`
  },
  legend: {
    orient: 'vertical',
    left: 0,
    top: 0,
    itemWidth: 10,
    itemHeight: 10,
    itemGap: 8,
    icon: 'circle',
    textStyle: { color: '#5A6B87', fontSize: 13 }
  },
  series: [
    {
      name: '其他组研问题',
      type: 'pie',
      radius: ['48%', '72%'],
      center: ['68%', '52%'],
      avoidLabelOverlap: true,
      label: { show: false },
      labelLine: { show: false },
      data: otherIssueRows.value.map((item, index) => ({
        name: item.type,
        value: Number(item.count || 0),
        itemStyle: { color: RING_COLORS[index % RING_COLORS.length] }
      }))
    }
  ]
}))

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
.review-dashboard { padding: 28px; color: #1A2D4D; background: #F7F9FC; min-height: 100%; font-size: 14px; font-family: "PingFang SC", "Microsoft YaHei", system-ui, sans-serif; line-height: 1.6; }
.page-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-head h2 { margin: 0 0 6px; font-size: 22px; color: #1A2D4D; font-weight: 700; line-height: 1.3; }
.page-head p { margin: 0; color: #5A6B87; font-size: 13px; }
.filter-bar { display: flex; align-items: center; gap: 12px; padding: 14px 18px; margin-bottom: 16px; background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.filter-bar :deep(.el-tabs__header) { margin: 0; }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 16px; }
.summary-card { min-height: 158px; }
.kpi-card, .quality-card { position: relative; padding: 20px 24px; border-radius: 8px; color: #1A2D4D; background: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.kpi-label, .quality-label { font-size: 14px; color: #5A6B87; font-weight: 500; }
.kpi-value-row { display: flex; align-items: baseline; gap: 6px; margin-top: 12px; }
.kpi-value, .quality-value { font-size: 32px; line-height: 1; font-weight: 700; color: #1A2D4D; }
.kpi-unit { font-size: 14px; color: #8C9AB7; }
.kpi-desc { margin-top: 14px; font-size: 12px; color: #8C9AB7; }
.metric-help { position: absolute; right: 16px; bottom: 14px; display: inline-flex; width: 16px; height: 16px; align-items: center; justify-content: center; border-radius: 50%; border: 1px solid #c5d0de; color: #8C9AB7; font-size: 11px; font-style: italic; cursor: help; background: #fff; }
.quality-value.is-muted { color: #8C9AB7; }
.quality-subdesc { margin-top: 12px; color: #8C9AB7; font-size: 12px; line-height: 1.6; }
.chart-row { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(280px, 0.9fr); gap: 16px; margin-bottom: 16px; }
.chart-row.single { grid-template-columns: 1fr; }
.chart-card { background: #fff; border-radius: 8px; padding: 20px 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.chart-card.wide { margin-bottom: 16px; }
.table-card { overflow: auto; }
.section-title { display: flex; align-items: baseline; gap: 10px; font-size: 16px; font-weight: 700; margin-bottom: 16px; color: #1A2D4D; }
.section-title small { color: #94a3b8; font-size: 12px; font-weight: 500; }
.chart { height: 360px; }
@media (max-width: 1100px) { .chart-row { grid-template-columns: 1fr; } }
@media (max-width: 768px) { .review-dashboard { padding: 16px; } .filter-bar { flex-wrap: wrap; } }
</style>
