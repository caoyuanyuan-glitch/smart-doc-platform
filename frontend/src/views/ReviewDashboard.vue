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

    <div class="summary-grid" v-loading="loading">
      <div class="summary-card kpi-card blue">
        <div class="kpi-label">审核任务总数</div>
        <div class="kpi-value">{{ kpi.range_tasks }}</div>
        <div class="kpi-desc">当前筛选范围</div>
      </div>
      <div class="summary-card kpi-card soft-blue">
        <div class="kpi-label">平均单文档问题</div>
        <div class="kpi-value">{{ kpi.avg_issues_per_doc }}</div>
        <div class="kpi-desc">当前筛选范围</div>
      </div>
      <div class="summary-card quality-card detection-rate">
        <div class="quality-label">检出率</div>
        <div class="quality-value">{{ percentText(quality.detection_rate) }}</div>
        <div class="quality-desc">检出率 = 平台检出问题 ÷ (平台检出 + 人工补录) × 100%</div>
        <div class="quality-subdesc">平台检出 {{ quality.platform_detected }} 条 · 人工补录 {{ quality.manual_supplemented }} 条</div>
      </div>
    </div>

    <div class="chart-card wide">
      <div class="section-title">
        <span>Top5 高占比问题</span>
        <small>其余合并为其他细碎问题</small>
      </div>
      <v-chart class="chart" :option="issueBarOption" autoresize />
    </div>
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
import { reviewAPI, getAPIErrorMessage } from '@/api'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const loading = ref(false)
const viewMode = ref('overview')
const filters = reactive({ time_range: '7d', doc_type: 'all' })
const kpi = reactive({ range_tasks: 0, avg_issues_per_doc: 0 })
const quality = reactive({
  platform_detected: 0,
  manual_supplemented: 0,
  expected_issues: 0,
  false_positive_count: 0,
  platform_reported: 0,
  accuracy_rate: 0,
  false_positive_rate: 0,
  detection_rate: 0
})
const issueDistribution = ref([])
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
  if (!Number.isFinite(number)) return '0.0%'
  return `${(number * 100).toFixed(1)}%`
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
    Object.assign(quality, data.quality || {})
    issueDistribution.value = data.issue_distribution || []
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
.review-dashboard { padding: 28px; color: #303133; background: #f8fafc; min-height: 100%; }
.page-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-head h2 { margin: 0 0 6px; font-size: 22px; }
.page-head p { margin: 0; color: #8c8c8c; }
.filter-bar { display: flex; align-items: center; gap: 12px; padding: 14px 18px; margin-bottom: 22px; background: #fff; border-radius: 10px; box-shadow: 0 1px 6px rgba(15,23,42,0.04); }
.filter-bar :deep(.el-tabs__header) { margin: 0; }
.summary-grid { display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 18px; margin-bottom: 24px; }
.summary-card { min-height: 158px; }
.kpi-card { padding: 26px 22px; border-radius: 12px; color: #fff; box-shadow: 0 6px 18px rgba(24,144,255,0.10); }
.kpi-card.blue { background: linear-gradient(135deg, #1890ff, #096dd9); }
.kpi-card.soft-blue { background: linear-gradient(135deg, #38bdf8, #0f766e); }
.kpi-label { font-size: 13px; opacity: .9; }
.kpi-value { margin-top: 12px; font-size: 38px; line-height: 1; font-weight: 900; }
.kpi-desc { margin-top: 14px; font-size: 12px; opacity: .78; }
.quality-card { border-radius: 12px; padding: 24px 22px; box-shadow: 0 6px 18px rgba(15,23,42,0.05); border: 1px solid #dfe7f2; background: #fff; }
.quality-card.detection-rate { background: linear-gradient(135deg, #ecfdf5, #fff); }
.quality-label { color: #64748b; font-size: 13px; font-weight: 700; }
.quality-value { margin-top: 12px; font-size: 38px; font-weight: 900; color: #1f2937; }
.quality-desc { margin-top: 12px; color: #94a3b8; font-size: 12px; line-height: 1.5; }
.quality-subdesc { margin-top: 8px; color: #64748b; font-size: 12px; }
.chart-card { background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 1px 8px rgba(15,23,42,0.05); }
.chart-card.wide { margin-bottom: 16px; }
.section-title { display: flex; align-items: baseline; gap: 10px; font-size: 16px; font-weight: 700; margin-bottom: 16px; }
.section-title small { color: #94a3b8; font-size: 12px; font-weight: 500; }
.chart { height: 360px; }
@media (max-width: 1100px) { .summary-grid { grid-template-columns: repeat(2, minmax(180px, 1fr)); } }
@media (max-width: 768px) { .review-dashboard { padding: 16px; } .filter-bar { flex-wrap: wrap; } .summary-grid { grid-template-columns: 1fr; } }
</style>
