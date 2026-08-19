<template>
  <div class="polish-stats-page">
    <div class="page-head">
      <div>
        <h2 class="page-title">智能润色统计面板</h2>
        <div class="page-subtitle">汇总文本润色与文档润色的准确率、修正分布和文档表现</div>
      </div>
      <el-button :loading="loading" @click="loadStats">刷新</el-button>
    </div>

    <div class="overview-grid" :class="{ 'overview-grid-single': activeTab === 'text' }">
      <template v-if="activeTab === 'text'">
        <button type="button" class="stat-card stat-card-button" @click="openTextSessions">
          <div class="stat-label">文本润色会话</div>
          <div class="stat-value">{{ textStats.overview.total_sessions }}</div>
          <div class="stat-note">最近记录与分类分布</div>
        </button>
      </template>
      <template v-else>
        <button type="button" class="stat-card stat-card-button" @click="openDocumentSessions">
          <div class="stat-label">文档润色数量</div>
          <div class="stat-value">{{ documentStats.overview.total_documents }}</div>
          <div class="stat-note">已统计的文档数量</div>
        </button>
        <div class="stat-card">
          <div class="stat-label">平均准确率</div>
          <div class="stat-value">{{ formatRate(documentStats.overview.average_accuracy) }}</div>
          <div class="stat-note">按文档统计</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">总修正数</div>
          <div class="stat-value">{{ documentStats.overview.total_accepted + documentStats.overview.total_modified + documentStats.overview.total_rejected }}</div>
          <div class="stat-note">接受、修改、拒绝合计</div>
        </div>
      </template>
    </div>

    <el-tabs v-model="activeTab" class="stats-tabs">
      <el-tab-pane label="文本润色" name="text">
        <section class="panel">
          <div class="chart-grid">
            <div class="chart-box wide">
              <div class="chart-toolbar">
                <div class="chart-title">准确率趋势</div>
                <el-date-picker
                  v-model="textAccuracyRange"
                  type="daterange"
                  range-separator="至"
                  start-placeholder="开始日期"
                  end-placeholder="结束日期"
                  value-format="YYYY-MM-DD"
                  clearable
                  class="chart-range"
                />
              </div>
              <v-chart :option="filteredTextAccuracyOption" autoresize class="chart" />
            </div>
            <div class="chart-box">
              <div class="chart-title">修正类别分布</div>
              <v-chart :option="textCategoryPieOption" autoresize class="chart" />
            </div>
          </div>
        </section>
      </el-tab-pane>
      <el-tab-pane label="文档润色" name="document">
        <section class="panel">
          <div class="chart-grid">
            <div class="chart-box wide">
              <div class="chart-toolbar">
                <div class="chart-title">准确率趋势</div>
                <el-date-picker
                  v-model="documentAccuracyRange"
                  type="daterange"
                  range-separator="至"
                  start-placeholder="开始日期"
                  end-placeholder="结束日期"
                  value-format="YYYY-MM-DD"
                  clearable
                  class="chart-range"
                />
              </div>
              <v-chart :option="filteredDocumentAccuracyOption" autoresize class="chart" />
            </div>
            <div class="chart-box">
              <div class="chart-title">处理动作分布</div>
              <v-chart :option="documentDecisionPieOption" autoresize class="chart" />
            </div>
          </div>
          <div class="chart-grid">
            <div class="chart-box">
              <div class="chart-title">修正类别分布</div>
              <v-chart :option="documentCategoryPieOption" autoresize class="chart" />
            </div>
            <div class="chart-box">
              <div class="chart-title">句式库使用效果</div>
              <v-chart :option="guideComparisonOption" autoresize class="chart" />
            </div>
          </div>
        </section>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart, PieChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { polishStatsAPI } from '@/api'
import { useUserStore } from '@/store/user'

use([LineChart, PieChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)
const activeTab = ref('text')
const textAccuracyRange = ref([])
const documentAccuracyRange = ref([])
const textStats = ref({ overview: { total_sessions: 0, average_accuracy: 0, total_corrections: 0, total_accepted: 0 }, accuracy_trend: [], correction_category_pie: [], category_trend: [], recent_sessions: [] })
const documentStats = ref({ overview: { total_documents: 0, total_sessions: 0, average_accuracy: 0, total_accepted: 0, total_modified: 0, total_rejected: 0, total_pending: 0 }, accuracy_trend: [], decision_pie: [], category_distribution: [], guide_comparison: [], documents: [] })

function formatRate(value) {
  const num = Number(value || 0)
  return `${num.toFixed(1)}%`
}

function formatTime(value) {
  if (!value) return '-'
  const raw = String(value).trim()
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/.test(raw) ? raw : `${raw}Z`
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) {
    return raw.slice(0, 19).replace('T', ' ')
  }
  const pad = (num) => String(num).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function toLineSeries(points, key) {
  return points.map(item => Number(item?.[key] || 0))
}

function getProductTypeLabel(item) {
  const value = String(item?.sentence_file_name || '未指定').trim()
  return value.endsWith('（全部文件）') ? value.replace('（全部文件）', '') : value
}

function extractDateKey(value) {
  if (!value) return ''
  const raw = String(value).trim()
  return raw.slice(0, 10)
}

function filterTrendByRange(points, range) {
  const [start, end] = Array.isArray(range) ? range : []
  if (!start && !end) return points
  return points.filter((item) => {
    const dateKey = extractDateKey(item?.created_at)
    if (!dateKey) return false
    if (start && dateKey < start) return false
    if (end && dateKey > end) return false
    return true
  })
}

const filteredTextAccuracyTrend = computed(() => filterTrendByRange(textStats.value.accuracy_trend, textAccuracyRange.value))
const filteredDocumentAccuracyTrend = computed(() => filterTrendByRange(documentStats.value.accuracy_trend, documentAccuracyRange.value))

const filteredTextAccuracyOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'category', data: filteredTextAccuracyTrend.value.map(item => formatTime(item.created_at)), axisLabel: { rotate: 25, fontSize: 10 } },
  yAxis: { type: 'value', max: 100 },
  series: [{ type: 'line', smooth: true, data: toLineSeries(filteredTextAccuracyTrend.value, 'accuracy'), areaStyle: { opacity: 0.12 }, lineStyle: { color: '#3b82f6' }, itemStyle: { color: '#3b82f6' } }]
}))

const textCategoryPieOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [{ type: 'pie', radius: ['40%', '68%'], data: textStats.value.correction_category_pie.map((item, index) => ({ value: item.count, name: item.category, itemStyle: { color: ['#3b82f6', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6'][index % 5] } })) }]
}))

const filteredDocumentAccuracyOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'category', data: filteredDocumentAccuracyTrend.value.map(item => formatTime(item.created_at)), axisLabel: { rotate: 25, fontSize: 10 } },
  yAxis: { type: 'value', max: 100 },
  series: [{ type: 'line', smooth: true, data: toLineSeries(filteredDocumentAccuracyTrend.value, 'accuracy_rate'), areaStyle: { opacity: 0.12 }, lineStyle: { color: '#10b981' }, itemStyle: { color: '#10b981' } }]
}))

const documentDecisionPieOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [{ type: 'pie', radius: ['40%', '68%'], data: documentStats.value.decision_pie.map((item, index) => ({ value: item.count, name: item.action, itemStyle: { color: ['#16a34a', '#f59e0b', '#ef4444', '#64748b'][index % 4] } })) }]
}))

const documentCategoryPieOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [{ type: 'pie', radius: ['40%', '68%'], data: documentStats.value.category_distribution.map((item, index) => ({ value: item.count, name: item.category, itemStyle: { color: ['#0ea5e9', '#8b5cf6', '#f97316', '#14b8a6', '#ef4444'][index % 5] } })) }]
}))

const guideComparisonRows = computed(() => [...documentStats.value.guide_comparison]
  .sort((a, b) => {
    const countDiff = Number(b.session_count || 0) - Number(a.session_count || 0)
    if (countDiff !== 0) return countDiff
    return Number(b.avg_accuracy || 0) - Number(a.avg_accuracy || 0)
  }))

const guideComparisonOption = computed(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
  grid: { left: 48, right: 56, top: 20, bottom: 82 },
  legend: { bottom: 0, data: ['使用次数', '平均准确率'] },
  xAxis: {
    type: 'category',
    data: guideComparisonRows.value.map(item => getProductTypeLabel(item) || '未指定'),
    axisLabel: { rotate: 25, fontSize: 10 }
  },
  yAxis: [
    {
      type: 'value',
      name: '使用次数',
      minInterval: 1
    },
    {
      type: 'value',
      name: '平均准确率',
      min: 0,
      max: 100
    }
  ],
  series: [
    {
      name: '使用次数',
      type: 'bar',
      data: guideComparisonRows.value.map(item => Number(item.session_count || 0)),
      barWidth: 18,
      itemStyle: { color: '#60a5fa' }
    },
    {
      name: '平均准确率',
      type: 'line',
      yAxisIndex: 1,
      smooth: true,
      data: guideComparisonRows.value.map(item => Number(item.avg_accuracy || 0)),
      lineStyle: { color: '#6366f1' },
      itemStyle: { color: '#6366f1' }
    }
  ]
}))

async function loadStats() {
  loading.value = true
  try {
    const [textResp, docResp] = await Promise.all([polishStatsAPI.getTextStats(), polishStatsAPI.getDocumentStats()])
    textStats.value = textResp.data || textStats.value
    documentStats.value = docResp.data || documentStats.value
  } finally {
    loading.value = false
  }
}

function handleTextFeedbackSubmitted() {
  loadStats()
}

function handleDocumentFeedbackSubmitted() {
  loadStats()
}

function ensureAdminAccess() {
  if (userStore.isAdmin) {
    return true
  }
  ElMessage.error('仅管理员可访问此页面')
  return false
}

function openTextSessions() {
  if (!ensureAdminAccess()) return
  router.push({ name: 'PolishTextSessions' })
}

function openDocumentSessions() {
  if (!ensureAdminAccess()) return
  router.push({ name: 'PolishDocumentSessions' })
}

onMounted(() => {
  loadStats()
  window.addEventListener('polish-text-feedback-submitted', handleTextFeedbackSubmitted)
  window.addEventListener('polish-document-feedback-submitted', handleDocumentFeedbackSubmitted)
})

onBeforeUnmount(() => {
  window.removeEventListener('polish-text-feedback-submitted', handleTextFeedbackSubmitted)
  window.removeEventListener('polish-document-feedback-submitted', handleDocumentFeedbackSubmitted)
})
</script>

<style scoped>
.polish-stats-page { padding: 24px; background: linear-gradient(180deg, #f6f8fc 0%, #eef4ff 100%); min-height: 100%; }
.page-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 20px; }
.page-title { margin: 0; font-size: 28px; color: #0f172a; }
.page-subtitle { margin-top: 6px; color: #64748b; }
.overview-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 20px; }
.overview-grid-single { grid-template-columns: minmax(240px, 320px); }
.stat-card, .panel, .table-card { background: rgba(255,255,255,.92); border: 1px solid rgba(148,163,184,.18); border-radius: 18px; box-shadow: 0 12px 30px rgba(15,23,42,.06); }
.stat-card { padding: 18px 20px; }
.stat-card-button { width: 100%; text-align: left; cursor: pointer; transition: transform .18s ease, box-shadow .18s ease; }
.stat-card-button:hover { transform: translateY(-2px); box-shadow: 0 16px 36px rgba(15,23,42,.09); }
.stat-label { font-size: 13px; color: #64748b; }
.stat-value { margin-top: 10px; font-size: 28px; font-weight: 700; color: #0f172a; }
.stat-note { margin-top: 6px; font-size: 12px; color: #94a3b8; }
.stats-grid { display: grid; gap: 20px; }
.stats-tabs { margin-top: 8px; }
.panel { padding: 20px; }
.chart-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 16px; }
.chart-box { padding: 16px; border-radius: 14px; background: #f8fbff; border: 1px solid rgba(148,163,184,.15); }
.chart-box.wide { min-height: 320px; }
.chart-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 10px; }
.chart-title { font-size: 14px; font-weight: 600; color: #1e293b; margin-bottom: 10px; }
.chart-toolbar .chart-title { margin-bottom: 0; }
.chart-range { width: 280px; max-width: 100%; }
.chart { height: 300px; }
@media (max-width: 1200px) {
  .overview-grid, .chart-grid { grid-template-columns: 1fr; }
}
</style>
