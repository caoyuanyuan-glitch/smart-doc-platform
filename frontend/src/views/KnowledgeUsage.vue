<template>
  <div class="usage-page">
    <div class="page-head">
      <div>
        <h2 class="page-title">知识库调用统计</h2>
        <div class="page-subtitle">记录智能润色、智能问答、AI 翻译读取知识库文件的次数、耗时和账号</div>
      </div>
      <el-button :loading="loading" @click="loadSummary">刷新</el-button>
    </div>

    <div class="filter-bar">
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        value-format="YYYY-MM-DD"
        clearable
        class="date-range"
      />
      <el-select v-model="moduleFilter" placeholder="全部模块" clearable class="module-select">
        <el-option label="智能润色" value="polish" />
        <el-option label="智能问答" value="qa" />
        <el-option label="AI翻译" value="translation" />
      </el-select>
      <el-input v-model="keyword" placeholder="搜索文件名" clearable class="keyword-input" @keyup.enter="loadSummary" />
      <el-button type="primary" :loading="loading" @click="loadSummary">查询</el-button>
    </div>

    <div class="chart-grid">
      <div class="chart-card">
        <div class="chart-head">
          <div class="chart-title">模块调用次数</div>
          <div class="chart-note">按模块统计文件调用次数</div>
        </div>
        <VChart
          :option="moduleCountOption"
          :style="{ height: chartHeight }"
          autoresize
          @click="onModuleChartClick"
        />
      </div>
      <div class="chart-card">
        <div class="chart-head">
          <div class="chart-title">文件调用次数</div>
          <div class="chart-note">合计 {{ summary.total_calls }} 次 · {{ summary.file_count }} 个文件</div>
        </div>
        <VChart
          :option="callCountOption"
          :style="{ height: chartHeight }"
          autoresize
          @click="onCallChartClick"
        />
      </div>
    </div>

    <div class="table-card">
      <el-table :data="pagedItems" v-loading="loading" stripe empty-text="暂无调用记录" @row-click="openDetails">
        <el-table-column prop="file_name" label="文件" min-width="220" show-overflow-tooltip />
        <el-table-column prop="folder_path" label="所在目录" min-width="180" show-overflow-tooltip />
        <el-table-column prop="call_count" label="调用次数" width="110" />
        <el-table-column label="调用模块" min-width="180">
          <template #default="{ row }">
            <span v-for="label in row.module_labels" :key="label" class="module-chip">{{ label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计耗时" width="120">
          <template #default="{ row }">{{ formatDuration(row.total_duration_ms) }}</template>
        </el-table-column>
        <el-table-column prop="account_count" label="账号数" width="90" />
        <el-table-column label="最近调用" width="190">
          <template #default="{ row }">{{ formatTime(row.last_called_at) }}</template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next"
          :total="tableTotal"
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[20, 30, 50]"
          @size-change="handleSizeChange"
        />
      </div>
    </div>

    <el-drawer v-model="detailVisible" :title="detailTitle" size="520px">
      <el-table :data="details.items" v-loading="detailLoading" empty-text="暂无明细">
        <el-table-column label="调用时间" min-width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="module_label" label="模块" width="100" />
        <el-table-column prop="username" label="账号" width="110" />
        <el-table-column label="耗时" width="90">
          <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
        </el-table-column>
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { knowledgeAPI } from '@/api'

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const loading = ref(false)
const detailLoading = ref(false)
const detailVisible = ref(false)
const dateRange = ref([])
const moduleFilter = ref('')
const keyword = ref('')
const selectedFile = ref(null)
const page = ref(1)
const pageSize = ref(20)
const summary = ref({ file_count: 0, total_calls: 0, total_duration_ms: 0, items: [] })
const details = ref({ items: [] })

const detailTitle = computed(() => selectedFile.value?.file_name || '调用明细')
const tableTotal = computed(() => (summary.value.items || []).length)
const pagedItems = computed(() => {
  const items = summary.value.items || []
  const start = (page.value - 1) * pageSize.value
  return items.slice(start, start + pageSize.value)
})

function handleSizeChange(value) {
  pageSize.value = value
  page.value = 1
}

function queryParams() {
  const params = {}
  if (moduleFilter.value) params.module = moduleFilter.value
  if (keyword.value.trim()) params.q = keyword.value.trim()
  if (dateRange.value?.length === 2) {
    params.start = dateRange.value[0]
    params.end = dateRange.value[1]
  }
  return params
}

function formatDuration(ms) {
  const value = Number(ms || 0)
  if (value < 1000) return `${value} ms`
  return `${(value / 1000).toFixed(1)} s`
}

function formatTime(iso) {
  if (!iso) return '-'
  return String(iso).replace('T', ' ').replace('+08:00', '')
}

function shortenLabel(text) {
  const value = String(text || '')
  return value.length > 18 ? `${value.slice(0, 17)}...` : value
}

function sortedChartItems(key) {
  return [...(summary.value.items || [])]
    .sort((left, right) => Number(right?.[key] || 0) - Number(left?.[key] || 0))
    .slice(0, 12)
}

function barOption(rows, valueKey, color, tooltipFormatter) {
  const names = rows.map(item => shortenLabel(item.file_name))
  const values = rows.map(item => Number(item?.[valueKey] || 0))
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: params => {
        const item = rows[params?.[0]?.dataIndex || 0]
        return item ? tooltipFormatter(item) : ''
      }
    },
    grid: { left: 132, right: 56, top: 8, bottom: 8 },
    xAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: '#a8a29e' },
      splitLine: { lineStyle: { color: 'rgba(120, 113, 108, 0.12)' } }
    },
    yAxis: {
      type: 'category',
      data: names,
      inverse: true,
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { color: '#57534e', fontSize: 11 }
    },
    series: [
      {
        type: 'bar',
        data: values,
        barMaxWidth: 16,
        itemStyle: { color, borderRadius: [0, 8, 8, 0] },
        label: { show: true, position: 'right', color: '#44403c', fontSize: 11 }
      }
    ]
  }
}

const callChartRows = computed(() => sortedChartItems('call_count'))
const chartHeight = computed(() => {
  const count = Math.max(callChartRows.value.length, moduleChartRows.value.length, 1)
  return `${Math.max(240, count * 36 + 24)}px`
})
const callCountOption = computed(() => barOption(
  callChartRows.value,
  'call_count',
  '#0f766e',
  item => `${item.file_name}<br/>调用 ${item.call_count} 次`
))
const MODULE_COLORS = {
  polish: '#0f766e',
  qa: '#1d4ed8',
  translation: '#b45309',
}
const moduleChartRows = computed(() => [...(summary.value.module_stats || [])]
  .sort((left, right) => Number(right?.call_count || 0) - Number(left?.call_count || 0)))
const moduleCountOption = computed(() => {
  const rows = moduleChartRows.value
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: params => {
        const item = rows[params?.[0]?.dataIndex || 0]
        return item ? `${item.module_label}<br/>调用 ${item.call_count} 次 · ${item.file_count} 个文件` : ''
      }
    },
    grid: { left: 108, right: 56, top: 8, bottom: 8 },
    xAxis: {
      type: 'value',
      minInterval: 1,
      axisLabel: { color: '#a8a29e' },
      splitLine: { lineStyle: { color: 'rgba(120, 113, 108, 0.12)' } }
    },
    yAxis: {
      type: 'category',
      data: rows.map(item => item.module_label),
      inverse: true,
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { color: '#57534e', fontSize: 12 }
    },
    series: [
      {
        type: 'bar',
        data: rows.map(item => ({
          value: Number(item.call_count || 0),
          itemStyle: { color: MODULE_COLORS[item.module] || '#78716c', borderRadius: [0, 8, 8, 0] }
        })),
        barMaxWidth: 18,
        label: { show: true, position: 'right', color: '#44403c', fontSize: 11 }
      }
    ]
  }
})

function onCallChartClick(params) {
  const row = callChartRows.value[params?.dataIndex]
  if (row) openDetails(row)
}

function onModuleChartClick(params) {
  const row = moduleChartRows.value[params?.dataIndex]
  if (row?.module) moduleFilter.value = row.module
}

async function loadSummary() {
  loading.value = true
  page.value = 1
  try {
    const resp = await knowledgeAPI.getUsageSummary(queryParams())
    summary.value = resp.data || summary.value
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '加载调用统计失败')
  } finally {
    loading.value = false
  }
}

async function openDetails(row) {
  selectedFile.value = row
  detailVisible.value = true
  detailLoading.value = true
  try {
    const resp = await knowledgeAPI.getUsageFileDetails(row.file_id, queryParams())
    details.value = resp.data || { items: [] }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '加载调用明细失败')
  } finally {
    detailLoading.value = false
  }
}

watch([dateRange, moduleFilter], () => {
  loadSummary()
})

onMounted(loadSummary)
</script>

<style scoped>
.usage-page {
  padding: 24px;
  min-height: 100%;
  background:
    radial-gradient(1200px 420px at 0% -10%, rgba(14, 116, 144, 0.10), transparent 55%),
    linear-gradient(180deg, #f4f1ea 0%, #eef2f0 100%);
}
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 18px;
}
.page-title {
  margin: 0;
  font-size: 28px;
  color: #1c1917;
}
.page-subtitle {
  margin-top: 6px;
  color: #78716c;
}
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}
.date-range { width: 280px; }
.module-select { width: 160px; }
.keyword-input { width: 220px; }
.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}
.chart-card, .table-card {
  background: rgba(255, 252, 247, 0.92);
  border: 1px solid rgba(120, 113, 108, 0.16);
  border-radius: 16px;
  box-shadow: 0 10px 28px rgba(28, 25, 23, 0.05);
}
.chart-card { padding: 16px 18px 8px; }
.chart-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 8px;
}
.chart-title { font-size: 15px; font-weight: 600; color: #1c1917; }
.chart-note { font-size: 12px; color: #78716c; }
.table-card { padding: 8px; }
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  padding: 12px 8px 4px;
}
.module-chip {
  display: inline-flex;
  margin-right: 6px;
  padding: 2px 8px;
  border-radius: 999px;
  background: #ecfdf3;
  color: #0f766e;
  font-size: 12px;
}
.table-card :deep(.el-table__row) { cursor: pointer; }
@media (max-width: 900px) {
  .chart-grid { grid-template-columns: 1fr; }
}
</style>
