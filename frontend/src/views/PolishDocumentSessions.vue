<template>
  <div class="session-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">文档润色详情</h2>
        <div class="page-subtitle">查看文档润色会话与反馈情况</div>
      </div>
      <div class="header-actions">
        <el-button @click="goBack">返回统计面板</el-button>
        <el-button @click="loadData" :loading="loading">刷新</el-button>
      </div>
    </div>

    <div class="filter-bar">
      <el-select v-model="filters.user_name" placeholder="按提交人筛选" clearable filterable class="filter-item">
        <el-option v-for="option in userOptions" :key="option.value" :label="option.label" :value="option.value" />
      </el-select>
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        value-format="YYYY-MM-DD"
        class="filter-item filter-date"
      />
      <el-button type="primary" @click="handleSearch">查询</el-button>
      <el-button @click="handleReset">重置</el-button>
    </div>

    <el-table :data="items" v-loading="loading" border stripe class="session-table" empty-text="暂无文档润色记录">
      <el-table-column prop="created_by" label="提交人" width="120" />
      <el-table-column prop="source_filename" label="提交的文件名" min-width="240" show-overflow-tooltip />
      <el-table-column prop="total_polished_count" label="总润色条数" width="110" align="center" />
      <el-table-column prop="accepted" label="接受数量" width="100" align="center" />
      <el-table-column prop="rejected" label="拒绝数量" width="100" align="center" />
      <el-table-column prop="modified" label="自定义数量" width="110" align="center" />
      <el-table-column prop="accuracy" label="准确度评分" width="110" align="center">
        <template #default="{ row }">{{ formatRate(row.accuracy) }}</template>
      </el-table-column>
      <el-table-column prop="has_corrections" label="是否反馈修正" width="120" align="center">
        <template #default="{ row }">
          <el-tag :type="row.has_corrections ? 'warning' : 'info'" size="small">{{ row.has_corrections ? '是' : '否' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="提交时间" width="180" align="center">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>

    <div class="pager-wrap">
      <el-pagination
        background
        layout="total, prev, pager, next, sizes"
        :total="total"
        :current-page="page"
        :page-size="pageSize"
        :page-sizes="[20, 50, 100]"
        @current-change="handlePageChange"
        @size-change="handleSizeChange"
      />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { polishStatsAPI, userAPI } from '@/api'
import { useUserStore } from '@/store/user'

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = ref({ user_name: '' })
const dateRange = ref([])
const userOptions = ref([])

function formatRate(value) {
  return `${Number(value || 0).toFixed(1)}%`
}

function formatTime(value) {
  if (!value) return '-'
  const raw = String(value).trim()
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/.test(raw) ? raw : `${raw}Z`
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) return raw.slice(0, 19).replace('T', ' ')
  return date.toLocaleString('zh-CN', { hour12: false })
}

function goBack() {
  router.push({ name: 'PolishStats' })
}

async function loadUserOptions() {
  if (!userStore.isAdmin) {
    return
  }
  try {
    const resp = await userAPI.list({ page: 1, page_size: 100 })
    userOptions.value = (resp.data?.items || []).map((item) => ({
      value: item.username,
      label: item.display_name && item.display_name !== item.username
        ? `${item.display_name} (${item.username})`
        : item.username,
    })).filter(item => item.value)
  } catch {
    userOptions.value = []
  }
}

async function loadData() {
  if (!userStore.isAdmin) {
    ElMessage.error('仅管理员可访问此页面')
    return
  }
  loading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
      user_name: filters.value.user_name || undefined,
      start_date: dateRange.value?.[0] || undefined,
      end_date: dateRange.value?.[1] || undefined,
    }
    const resp = await polishStatsAPI.getDocumentSessions(params)
    items.value = resp.data?.items || []
    total.value = resp.data?.total || 0
  } catch (e) {
    if (e.response?.status === 403) {
      ElMessage.error('仅管理员可访问此页面')
    } else {
      ElMessage.error('加载文档润色详情失败')
    }
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  loadData()
}

function handleReset() {
  filters.value.user_name = ''
  dateRange.value = []
  page.value = 1
  loadData()
}

function handlePageChange(value) {
  page.value = value
  loadData()
}

function handleSizeChange(value) {
  pageSize.value = value
  page.value = 1
  loadData()
}

onMounted(() => {
  loadUserOptions()
  loadData()
})
</script>

<style scoped>
.session-page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; gap: 16px; }
.header-actions { display: flex; gap: 12px; flex-wrap: wrap; }
.page-title { margin: 0; font-size: 24px; color: #0f172a; }
.page-subtitle { margin-top: 6px; color: #64748b; }
.filter-bar { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.filter-item { width: 220px; }
.filter-date { width: 320px; }
.session-table { background: #fff; border-radius: 12px; overflow: hidden; }
.pager-wrap { display: flex; justify-content: flex-end; margin-top: 16px; }
</style>
