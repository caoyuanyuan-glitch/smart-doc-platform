<template>
  <div class="polish-stats-page">
    <div class="page-head">
      <div>
        <h2 class="page-title">智能润色统计面板</h2>
        <div class="page-subtitle">汇总文本润色与文档润色的准确率、修正分布和文档表现</div>
      </div>
      <el-button :loading="loading" @click="loadStats">刷新</el-button>
    </div>

    <div class="overview-grid">
      <div class="stat-card">
        <div class="stat-label">文本润色会话</div>
        <div class="stat-value">{{ textStats.overview.total_sessions }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">文档润色文档</div>
        <div class="stat-value">{{ documentStats.overview.total_documents }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">平均准确率</div>
        <div class="stat-value">{{ formatRate(documentStats.overview.average_accuracy) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">总修正数</div>
        <div class="stat-value">{{ documentStats.overview.total_accepted + documentStats.overview.total_modified + documentStats.overview.total_rejected }}</div>
      </div>
    </div>

    <div class="stats-grid">
      <section class="panel">
        <div class="panel-head">
          <h3>文本润色</h3>
          <span>句式和术语反馈</span>
        </div>
        <div class="chart-grid">
          <div class="chart-box wide">
            <div class="chart-title">准确率趋势</div>
            <v-chart :option="textAccuracyOption" autoresize class="chart" />
          </div>
          <div class="chart-box">
            <div class="chart-title">修正类别分布</div>
            <v-chart :option="textCategoryPieOption" autoresize class="chart" />
          </div>
        </div>
        <div class="table-card">
          <div class="table-title">最近会话</div>
          <div v-if="!textStats.recent_sessions.length" class="empty-state">暂无文本润色记录</div>
          <div v-else class="simple-table">
            <div v-for="item in textStats.recent_sessions" :key="item.session_id" class="table-row">
              <span>{{ formatTime(item.created_at) }}</span>
              <span>准确率 {{ formatRate(item.accuracy) }}</span>
              <span>修正 {{ item.correction_count }} 条</span>
            </div>
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h3>文档润色</h3>
          <span>CAT 结果和文档分布</span>
        </div>
        <div class="chart-grid">
          <div class="chart-box wide">
            <div class="chart-title">文档准确率趋势</div>
            <v-chart :option="documentAccuracyOption" autoresize class="chart" />
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
            <div class="chart-title">句式库对比</div>
            <v-chart :option="guideComparisonOption" autoresize class="chart" />
          </div>
        </div>
        <div class="table-card">
          <div class="table-title">最近文档</div>
          <div v-if="!documentStats.documents.length" class="empty-state">暂无文档润色记录</div>
          <div v-else class="simple-table doc-table">
            <div v-for="item in documentStats.documents" :key="item.source_filename" class="table-row table-row-doc">
              <span class="doc-name">{{ item.source_filename }}</span>
              <span>准确率 {{ formatRate(item.latest_accuracy) }}</span>
              <span>句式库 {{ item.sentence_file_name || '未指定' }}</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart, PieChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { polishStatsAPI } from '@/api'

use([LineChart, PieChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const loading = ref(false)
const textStats = ref({ overview: { total_sessions: 0, average_accuracy: 0, total_corrections: 0, total_accepted: 0 }, accuracy_trend: [], correction_category_pie: [], category_trend: [], recent_sessions: [] })
const documentStats = ref({ overview: { total_documents: 0, total_sessions: 0, average_accuracy: 0, total_accepted: 0, total_modified: 0, total_rejected: 0, total_pending: 0 }, accuracy_trend: [], decision_pie: [], category_distribution: [], guide_comparison: [], documents: [] })

function formatRate(value) {
  const num = Number(value || 0)
  return `${num.toFixed(1)}%`
}

function formatTime(value) {
  if (!value) return '-'
  return String(value).slice(0, 19).replace('T', ' ')
}

function toLineSeries(points, key) {
  return points.map(item => Number(item?.[key] || 0))
}

const textAccuracyOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'category', data: textStats.value.accuracy_trend.map(item => formatTime(item.created_at)), axisLabel: { rotate: 25, fontSize: 10 } },
  yAxis: { type: 'value', max: 100 },
  series: [{ type: 'line', smooth: true, data: toLineSeries(textStats.value.accuracy_trend, 'accuracy'), areaStyle: { opacity: 0.12 }, lineStyle: { color: '#3b82f6' }, itemStyle: { color: '#3b82f6' } }]
}))

const textCategoryPieOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0 },
  series: [{ type: 'pie', radius: ['40%', '68%'], data: textStats.value.correction_category_pie.map((item, index) => ({ value: item.count, name: item.category, itemStyle: { color: ['#3b82f6', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6'][index % 5] } })) }]
}))

const documentAccuracyOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'category', data: documentStats.value.accuracy_trend.map(item => formatTime(item.created_at)), axisLabel: { rotate: 25, fontSize: 10 } },
  yAxis: { type: 'value', max: 100 },
  series: [{ type: 'line', smooth: true, data: toLineSeries(documentStats.value.accuracy_trend, 'accuracy_rate'), areaStyle: { opacity: 0.12 }, lineStyle: { color: '#10b981' }, itemStyle: { color: '#10b981' } }]
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

const guideComparisonOption = computed(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 50, right: 20, top: 20, bottom: 40 },
  xAxis: { type: 'value', max: 100 },
  yAxis: { type: 'category', data: documentStats.value.guide_comparison.map(item => item.sentence_file_name || '未指定'), axisLabel: { width: 120, overflow: 'truncate' } },
  series: [{ type: 'bar', data: documentStats.value.guide_comparison.map(item => Number(item.avg_accuracy || 0)), barWidth: 18, itemStyle: { color: '#6366f1' } }]
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

onMounted(loadStats)
</script>

<style scoped>
.polish-stats-page { padding: 24px; background: linear-gradient(180deg, #f6f8fc 0%, #eef4ff 100%); min-height: 100%; }
.page-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 20px; }
.page-title { margin: 0; font-size: 28px; color: #0f172a; }
.page-subtitle { margin-top: 6px; color: #64748b; }
.overview-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 20px; }
.stat-card, .panel, .table-card { background: rgba(255,255,255,.92); border: 1px solid rgba(148,163,184,.18); border-radius: 18px; box-shadow: 0 12px 30px rgba(15,23,42,.06); }
.stat-card { padding: 18px 20px; }
.stat-label { font-size: 13px; color: #64748b; }
.stat-value { margin-top: 10px; font-size: 28px; font-weight: 700; color: #0f172a; }
.stats-grid { display: grid; gap: 20px; }
.panel { padding: 20px; }
.panel-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16px; }
.panel-head h3 { margin: 0; font-size: 18px; color: #0f172a; }
.panel-head span { color: #64748b; font-size: 13px; }
.chart-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 16px; }
.chart-box { padding: 16px; border-radius: 14px; background: #f8fbff; border: 1px solid rgba(148,163,184,.15); }
.chart-box.wide { min-height: 320px; }
.chart-title { font-size: 14px; font-weight: 600; color: #1e293b; margin-bottom: 10px; }
.chart { height: 300px; }
.table-card { padding: 16px 18px; }
.table-title { font-size: 14px; font-weight: 600; color: #1e293b; margin-bottom: 12px; }
.simple-table { display: grid; gap: 10px; }
.table-row { display: grid; grid-template-columns: 1.2fr 1fr 1fr; gap: 12px; padding: 10px 12px; border-radius: 12px; background: #f8fbff; color: #334155; }
.table-row-doc { grid-template-columns: 2fr 1fr 1fr; }
.doc-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty-state { padding: 24px 0; color: #94a3b8; text-align: center; }
@media (max-width: 1200px) {
  .overview-grid, .chart-grid { grid-template-columns: 1fr; }
}
</style>
