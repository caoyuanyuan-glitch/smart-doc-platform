<template>
  <div class="review-dashboard">
    <div class="page-head">
      <div>
        <h2>文档审核统计看板</h2>
        <p>查看审核任务状态、问题分布和审核效率</p>
      </div>
      <el-button size="small" @click="loadDashboard" :loading="loading">刷新</el-button>
    </div>

    <div class="filter-bar">
      <el-tabs v-model="viewMode" @tab-change="loadDashboard">
        <el-tab-pane label="管理视图" name="overview" />
        <el-tab-pane label="个人视图" name="personal" />
      </el-tabs>
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
    </div>

    <div class="kpi-grid" v-loading="loading">
      <div class="kpi-card blue">
        <div class="kpi-label">今日审核任务数</div>
        <div class="kpi-value">{{ kpi.today_tasks }}</div>
        <div class="kpi-desc">当天提交审核</div>
      </div>
      <div class="kpi-card orange">
        <div class="kpi-label">待处理任务</div>
        <div class="kpi-value">{{ kpi.pending_tasks }}</div>
        <div class="kpi-desc">待审核/审核中</div>
      </div>
      <div class="kpi-card green">
        <div class="kpi-label">今日完成数</div>
        <div class="kpi-value">{{ kpi.today_completed }}</div>
        <div class="kpi-desc">当天完成审核</div>
      </div>
      <div class="kpi-card red">
        <div class="kpi-label">平均问题数/文档</div>
        <div class="kpi-value">{{ kpi.avg_issues_per_doc }}</div>
        <div class="kpi-desc">当前筛选范围</div>
      </div>
      <div class="kpi-card gray">
        <div class="kpi-label">平均审核耗时</div>
        <div class="kpi-value">{{ kpi.avg_review_time }}</div>
        <div class="kpi-desc">分钟</div>
      </div>
    </div>

    <div class="chart-card wide">
      <div class="section-title">审核任务趋势</div>
      <v-chart class="chart" :option="trendOption" autoresize />
    </div>

    <div class="chart-grid">
      <div class="chart-card">
        <div class="section-title">问题类型分布</div>
        <v-chart class="chart" :option="issueOption" autoresize />
      </div>
      <div class="chart-card">
        <div class="section-title">文档类型审核分布</div>
        <v-chart class="chart" :option="docTypeOption" autoresize />
      </div>
    </div>

    <div class="table-card">
      <div class="section-title">{{ viewMode === 'personal' ? '我的审核任务列表' : '近期审核任务列表' }}</div>
      <el-table :data="taskList" stripe empty-text="暂无审核任务" size="small">
        <el-table-column prop="document_name" label="文档名称" min-width="220" show-overflow-tooltip />
        <el-table-column prop="document_type" label="文档类型" width="100" />
        <el-table-column prop="submitted_at" label="提交时间" width="170">
          <template #default="{ row }">{{ formatDate(row.submitted_at) }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="issue_count" label="问题数" width="90" align="center" />
        <el-table-column prop="priority" label="优先级" width="90" align="center" />
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart, PieChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { reviewAPI, getAPIErrorMessage } from '@/api'

use([LineChart, PieChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const loading = ref(false)
const viewMode = ref('overview')
const filters = reactive({ time_range: '7d', doc_type: 'all' })
const kpi = reactive({ today_tasks: 0, pending_tasks: 0, today_completed: 0, avg_issues_per_doc: 0, avg_review_time: 0 })
const trend = ref({ dates: [], submitted: [], completed: [], avg_issues: [] })
const issueDistribution = ref([])
const docTypeDistribution = ref([])
const taskList = ref([])
let refreshTimer = null

const trendOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { top: 0 },
  grid: { left: 45, right: 45, top: 48, bottom: 32 },
  xAxis: { type: 'category', data: trend.value.dates },
  yAxis: [{ type: 'value', minInterval: 1 }, { type: 'value' }],
  series: [
    { name: '提交审核数', type: 'line', smooth: true, data: trend.value.submitted, itemStyle: { color: '#1890ff' } },
    { name: '完成审核数', type: 'line', smooth: true, data: trend.value.completed, lineStyle: { type: 'dashed' }, itemStyle: { color: '#52c41a' } },
    { name: '平均问题数/文档', type: 'line', yAxisIndex: 1, smooth: true, data: trend.value.avg_issues, lineStyle: { type: 'dotted' }, itemStyle: { color: '#fa8c16' } }
  ]
}))

const issueOption = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  legend: { bottom: 0 },
  series: [{ type: 'pie', radius: ['45%', '68%'], center: ['50%', '45%'], data: issueDistribution.value.map(item => ({ name: item.type, value: item.count })) }]
}))

const docTypeOption = computed(() => {
  const rows = docTypeDistribution.value
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0 },
    grid: { left: 45, right: 20, top: 48, bottom: 35 },
    xAxis: { type: 'category', data: rows.map(item => item.type) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '通过', type: 'bar', stack: 'total', data: rows.map(item => item.passed), itemStyle: { color: '#52c41a' } },
      { name: '有问题', type: 'bar', stack: 'total', data: rows.map(item => item.issues), itemStyle: { color: '#f5222d' } },
      { name: '需确认', type: 'bar', stack: 'total', data: rows.map(item => item.confirm), itemStyle: { color: '#faad14' } }
    ]
  }
})

function formatDate(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 16)
}

function statusText(status) {
  return { completed: '已完成', running: '审核中', pending: '待处理', failed: '失败' }[status] || status || '-'
}

function statusType(status) {
  return { completed: 'success', running: 'warning', pending: 'info', failed: 'danger' }[status] || 'info'
}

async function loadDashboard() {
  loading.value = true
  try {
    const params = { time_range: filters.time_range, doc_type: filters.doc_type }
    const response = viewMode.value === 'personal'
      ? await reviewAPI.getDashboardPersonal(params)
      : await reviewAPI.getDashboardOverview(params)
    const data = response.data || {}
    Object.assign(kpi, data.kpi || {})
    trend.value = data.trend || { dates: [], submitted: [], completed: [], avg_issues: [] }
    issueDistribution.value = data.issue_distribution || []
    docTypeDistribution.value = data.doc_type_distribution || []
    taskList.value = data.task_list || []
  } catch (error) {
    ElMessage.error(`加载审核看板失败: ${getAPIErrorMessage(error)}`)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadDashboard()
  refreshTimer = setInterval(loadDashboard, 5 * 60 * 1000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
.review-dashboard { padding: 24px; color: #303133; }
.page-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-head h2 { margin: 0 0 6px; font-size: 22px; }
.page-head p { margin: 0; color: #8c8c8c; }
.filter-bar { display: flex; align-items: center; gap: 12px; padding: 12px 16px; margin-bottom: 16px; background: #fff; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.04); }
.filter-bar :deep(.el-tabs__header) { margin: 0; }
.kpi-grid { display: grid; grid-template-columns: repeat(6, minmax(140px, 1fr)); gap: 14px; margin-bottom: 16px; }
.kpi-card { padding: 18px 16px; border-radius: 14px; color: #fff; min-height: 126px; box-shadow: 0 8px 22px rgba(24,144,255,0.12); }
.kpi-card.blue { background: linear-gradient(135deg, #1890ff, #096dd9); }
.kpi-card.orange { background: linear-gradient(135deg, #faad14, #d48806); }
.kpi-card.green { background: linear-gradient(135deg, #52c41a, #389e0d); }
.kpi-card.red { background: linear-gradient(135deg, #f5222d, #cf1322); }
.kpi-card.purple { background: linear-gradient(135deg, #722ed1, #531dab); }
.kpi-card.gray { background: linear-gradient(135deg, #8c8c8c, #595959); }
.kpi-label { font-size: 13px; opacity: .9; }
.kpi-value { margin-top: 10px; font-size: 30px; line-height: 1; font-weight: 800; }
.kpi-desc { margin-top: 12px; font-size: 12px; opacity: .82; }
.chart-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-bottom: 16px; }
.chart-card, .table-card { background: #fff; border-radius: 12px; padding: 18px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); }
.chart-card.wide { margin-bottom: 16px; }
.section-title { font-size: 16px; font-weight: 700; margin-bottom: 12px; }
.chart { height: 320px; }
.table-card { margin-top: 16px; }
@media (max-width: 1200px) { .kpi-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 768px) { .review-dashboard { padding: 16px; } .filter-bar { flex-wrap: wrap; } .kpi-grid, .chart-grid { grid-template-columns: 1fr; } }
</style>
