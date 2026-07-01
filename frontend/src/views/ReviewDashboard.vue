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
        <div class="kpi-label">审核任务数</div>
        <div class="kpi-value">{{ kpi.range_tasks }}</div>
        <div class="kpi-desc">当前筛选范围</div>
      </div>
      <div class="summary-card kpi-card soft-blue">
        <div class="kpi-label">平均问题数/文档</div>
        <div class="kpi-value">{{ kpi.avg_issues_per_doc }}</div>
        <div class="kpi-desc">当前筛选范围</div>
      </div>
      <div class="summary-card quality-card false-rate">
        <div class="quality-label">误报率</div>
        <div class="quality-value">{{ percentText(quality.false_positive_rate) }}</div>
        <div class="quality-desc">误报问题数 {{ quality.false_positive_count }} / 平台上报 {{ quality.platform_reported }}</div>
      </div>
      <div class="summary-card quality-card detection-rate">
        <div class="quality-label">检出率</div>
        <div class="quality-value">{{ percentText(quality.detection_rate) }}</div>
        <div class="quality-desc">平台检出 {{ quality.platform_detected }} / 应检出 {{ quality.expected_issues }}</div>
        <div class="quality-subdesc">补充上报 {{ quality.manual_supplemented }} 条</div>
      </div>
    </div>

    <div class="chart-card wide">
      <div class="section-title">问题类型占比</div>
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
  false_positive_rate: 0,
  detection_rate: 0
})
const issueDistribution = ref([])
let refreshTimer = null

const issueRows = computed(() => issueDistribution.value
  .map(item => ({ ...item, percent: Math.round((Number(item.percentage || 0) * 100) * 10) / 10 }))
  .sort((left, right) => left.percent - right.percent))

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
  grid: { left: 45, right: 24, top: 24, bottom: 70 },
  xAxis: { type: 'category', data: issueRows.value.map(item => item.type), axisLabel: { interval: 0, rotate: 25 } },
  yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
  series: [
    {
      name: '问题占比',
      type: 'bar',
      data: issueRows.value.map(item => item.percent),
      barMaxWidth: 42,
      itemStyle: { color: '#2563eb', borderRadius: [4, 4, 0, 0] },
      label: { show: true, position: 'top', formatter: '{c}%', color: '#303133' }
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
.review-dashboard { padding: 24px; color: #303133; }
.page-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-head h2 { margin: 0 0 6px; font-size: 22px; }
.page-head p { margin: 0; color: #8c8c8c; }
.filter-bar { display: flex; align-items: center; gap: 12px; padding: 12px 16px; margin-bottom: 16px; background: #fff; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.04); }
.filter-bar :deep(.el-tabs__header) { margin: 0; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(180px, 1fr)); gap: 14px; margin-bottom: 16px; }
.summary-card { min-height: 148px; }
.kpi-card { padding: 22px 18px; border-radius: 14px; color: #fff; box-shadow: 0 8px 22px rgba(24,144,255,0.12); }
.kpi-card.blue { background: linear-gradient(135deg, #1890ff, #096dd9); }
.kpi-card.soft-blue { background: linear-gradient(135deg, #38bdf8, #0f766e); }
.kpi-label { font-size: 13px; opacity: .9; }
.kpi-value { margin-top: 10px; font-size: 30px; line-height: 1; font-weight: 800; }
.kpi-desc { margin-top: 12px; font-size: 12px; opacity: .82; }
.quality-card { border-radius: 12px; padding: 18px 20px; box-shadow: 0 8px 22px rgba(15,23,42,0.06); border: 1px solid #dfe7f2; background: #fff; }
.quality-card.false-rate { background: linear-gradient(135deg, #fff7ed, #fff); }
.quality-card.detection-rate { background: linear-gradient(135deg, #ecfdf5, #fff); }
.quality-label { color: #64748b; font-size: 13px; font-weight: 700; }
.quality-value { margin-top: 10px; font-size: 32px; font-weight: 800; color: #1f2937; }
.quality-desc { margin-top: 10px; color: #475569; font-size: 13px; }
.quality-subdesc { margin-top: 6px; color: #64748b; font-size: 12px; }
.chart-card { background: #fff; border-radius: 12px; padding: 18px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); }
.chart-card.wide { margin-bottom: 16px; }
.section-title { font-size: 16px; font-weight: 700; margin-bottom: 12px; }
.chart { height: 320px; }
@media (max-width: 1100px) { .summary-grid { grid-template-columns: repeat(2, minmax(180px, 1fr)); } }
@media (max-width: 768px) { .review-dashboard { padding: 16px; } .filter-bar { flex-wrap: wrap; } .summary-grid { grid-template-columns: 1fr; } }
</style>
