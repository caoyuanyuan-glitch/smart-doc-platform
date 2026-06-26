<template>
  <div class="dashboard-page">
    <div class="page-hd">
      <h2>智能问答看板</h2>
      <span class="page-sub">管理员数据分析面板</span>
    </div>

    <div class="overview-cards">
      <div class="stat-card">
        <div class="stat-icon users">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
            <circle cx="9" cy="7" r="4"/>
            <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
            <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
          </svg>
        </div>
        <div class="stat-body">
          <div class="stat-label">
            <span>昨日活跃用户量</span>
            <span class="stat-date">截止昨日</span>
          </div>
          <div class="stat-value-row">
            <span class="stat-value">{{ overview.yesterday_active_users }}</span>
            <span class="stat-unit">人</span>
          </div>
          <div class="stat-trend" :class="overview.active_users_trend >= 0 ? 'up' : 'down'">
            <span class="trend-icon">{{ overview.active_users_trend >= 0 ? '↑' : '↓' }}</span>
            较前一日 {{ overview.active_users_trend >= 0 ? '+' : '' }}{{ overview.active_users_trend }}
          </div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon conv">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            <line x1="9" y1="10" x2="15" y2="10"/>
            <line x1="12" y1="7" x2="12" y2="13"/>
          </svg>
        </div>
        <div class="stat-body">
          <div class="stat-label">
            <span>昨日用户对话量</span>
            <span class="stat-date">截止昨日</span>
          </div>
          <div class="stat-value-row">
            <span class="stat-value">{{ overview.yesterday_conversations }}</span>
            <span class="stat-unit">次</span>
          </div>
          <div class="stat-trend" :class="overview.conversations_trend >= 0 ? 'up' : 'down'">
            <span class="trend-icon">{{ overview.conversations_trend >= 0 ? '↑' : '↓' }}</span>
            较前一日 {{ overview.conversations_trend >= 0 ? '+' : '' }}{{ overview.conversations_trend }}
          </div>
        </div>
      </div>
    </div>

    <div class="charts-row">
      <div class="chart-box">
        <div class="chart-title">活跃用户量趋势</div>
        <v-chart ref="chartUsers" class="chart" :option="chartUsersOption" autoresize />
      </div>
      <div class="chart-box">
        <div class="chart-title">用户对话量趋势</div>
        <v-chart ref="chartConv" class="chart" :option="chartConvOption" autoresize />
      </div>
    </div>

    <div class="detail-section">
      <div class="detail-hd">
        <h3>对话明细</h3>
        <el-button size="small" @click="exportData" :disabled="items.length === 0">导出数据</el-button>
      </div>

      <div class="filter-bar">
        <el-input v-model="filterUser" placeholder="全部人员" clearable size="small" style="width:120px" @change="loadDashboard" />
        <el-select v-model="filterType" placeholder="全部场域" clearable size="small" style="width:130px" @change="loadDashboard">
          <el-option label="知识库问答" value="general" />
          <el-option label="说明书问答" value="manual" />
        </el-select>
        <el-select v-model="filterRating" placeholder="全部反馈" clearable size="small" style="width:120px" @change="loadDashboard">
          <el-option label="有帮助" :value="1" />
          <el-option label="无帮助" :value="-1" />
          <el-option label="未评价" :value="0" />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          size="small"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          @change="loadDashboard"
          style="width:240px"
        />
      </div>

      <el-table :data="items" stripe v-loading="loading" empty-text="暂无对话记录" class="detail-table">
        <el-table-column label="对话人" width="100" prop="user_name" show-overflow-tooltip />
        <el-table-column label="对话场域" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="row.session_type === 'manual' ? 'warning' : ''">{{ row.session_type === 'manual' ? '说明书问答' : '知识库问答' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="对话时间" width="160" prop="created_at" />
        <el-table-column label="交互形态" width="80" align="center">
          <template #default>文本</template>
        </el-table-column>
        <el-table-column label="用户输入" min-width="180" prop="question" show-overflow-tooltip />
        <el-table-column label="结果输出" min-width="200" prop="answer" show-overflow-tooltip />
        <el-table-column label="执行结果" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.rating === 1" size="small" type="success">有帮助</el-tag>
            <el-tag v-else-if="row.rating === -1" size="small" type="danger">无帮助</el-tag>
            <span v-else class="result-none">--</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadDashboard"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { qaAPI } from '@/api'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const loading = ref(false)
const overview = reactive({ yesterday_active_users: 0, yesterday_conversations: 0, active_users_trend: 0, conversations_trend: 0 })
const chartUsersData = ref([])
const chartConvData = ref([])
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const dateRange = ref(null)
const filterUser = ref('')
const filterType = ref('')
const filterRating = ref(null)

const chartUsersOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 16, top: 16, bottom: 28 },
  xAxis: { type: 'category', data: chartUsersData.value.map(d => d.date), axisLabel: { rotate: 30, fontSize: 10 } },
  yAxis: { type: 'value', minInterval: 1 },
  series: [{ type: 'line', data: chartUsersData.value.map(d => d.count), smooth: true, areaStyle: { opacity: 0.15 }, lineStyle: { color: '#3b82f6' }, itemStyle: { color: '#3b82f6' } }],
}))

const chartConvOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 16, top: 16, bottom: 28 },
  xAxis: { type: 'category', data: chartConvData.value.map(d => d.date), axisLabel: { rotate: 30, fontSize: 10 } },
  yAxis: { type: 'value', minInterval: 1 },
  series: [{ type: 'line', data: chartConvData.value.map(d => d.count), smooth: true, areaStyle: { opacity: 0.15 }, lineStyle: { color: '#f59e0b' }, itemStyle: { color: '#f59e0b' } }],
}))

async function loadDashboard() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }
    if (filterUser.value) params.user_name = filterUser.value
    if (filterType.value) params.session_type = filterType.value
    if (filterRating.value !== null && filterRating.value !== '') params.rating = filterRating.value

    const r = await qaAPI.getDashboard(params)
    const data = r.data
    Object.assign(overview, data.overview || {})
    chartUsersData.value = data.charts?.active_users || []
    chartConvData.value = data.charts?.conversations || []
    items.value = data.items || []
    total.value = data.total || 0
  } catch (e) {
    if (e.response?.status === 403) {
      ElMessage.error('仅管理员可访问此页面')
    } else {
      ElMessage.error('加载看板数据失败')
    }
  }
  loading.value = false
}

function exportData() {
  let csv = '\uFEFF对话人,对话场域,对话时间,交互形态,用户输入,结果输出,执行结果\n'
  items.value.forEach(row => {
    const type = row.session_type === 'manual' ? '说明书问答' : '知识库问答'
    const result = row.rating === 1 ? '有帮助' : row.rating === -1 ? '无帮助' : '--'
    const safe = s => '"' + (s || '').replace(/"/g, '""') + '"'
    csv += [safe(row.user_name), safe(type), safe(row.created_at), '文本', safe(row.question), safe(row.answer), safe(result)].join(',') + '\n'
  })
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `问答看板_${new Date().toISOString().slice(0,10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('导出成功')
}

onMounted(loadDashboard)
</script>

<style scoped>
.dashboard-page { padding: 24px; background: #f1f5f9; min-height: 100%; }
.page-hd { margin-bottom: 24px; }
.page-hd h2 { margin: 0; font-size: 20px; color: #1e293b; }
.page-sub { font-size: 13px; color: #94a3b8; }

.overview-cards { display: flex; gap: 20px; margin-bottom: 24px; }
.stat-card {
  flex: 1;
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 1px 3px rgba(0,0,0,.06);
  display: flex;
  align-items: flex-start;
  gap: 16px;
  transition: box-shadow .2s;
}
.stat-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,.08); }

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.stat-icon svg { width: 24px; height: 24px; }
.stat-icon.users { background: #ede9fe; color: #7c3aed; }
.stat-icon.conv { background: #dbeafe; color: #2563eb; }

.stat-body { flex: 1; min-width: 0; }
.stat-label { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; font-size: 13px; color: #64748b; }
.stat-date { font-size: 11px; color: #94a3b8; }
.stat-value-row { display: flex; align-items: baseline; gap: 6px; margin-bottom: 4px; }
.stat-value { font-size: 32px; font-weight: 700; color: #1e293b; line-height: 1; }
.stat-unit { font-size: 14px; color: #94a3b8; }
.stat-trend { font-size: 12px; display: flex; align-items: center; gap: 4px; }
.stat-trend.up { color: #16a34a; }
.stat-trend.down { color: #ef4444; }
.trend-icon { font-size: 14px; font-weight: 700; }

.charts-row { display: flex; gap: 20px; margin-bottom: 24px; }
.chart-box { flex: 1; background: #fff; border-radius: 12px; padding: 20px 24px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.chart-title { font-size: 14px; font-weight: 600; color: #1e293b; margin-bottom: 8px; }
.chart { height: 260px; }

.detail-section { background: #fff; border-radius: 12px; padding: 20px 24px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.detail-hd { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.detail-hd h3 { margin: 0; font-size: 15px; font-weight: 600; }

.filter-bar { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.detail-table { width: 100%; }
.result-none { color: #94a3b8; font-size: 12px; }
.pagination { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
