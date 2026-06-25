<template>
  <div class="feedback-page">
    <div class="page-header">
      <div class="header-left">
        <h2 class="page-title">反馈管理</h2>
        <span class="page-subtitle">共 {{ items.length }} 条反馈，{{ unresolvedCount }} 条待处理</span>
      </div>
      <div class="header-actions">
        <el-button :type="filter === 'all' ? 'primary' : 'default'" size="small" @click="filter = 'all'">全部</el-button>
        <el-button :type="filter === 'unresolved' ? 'primary' : 'default'" size="small" @click="filter = 'unresolved'">未处理</el-button>
        <el-button :type="filter === 'resolved' ? 'primary' : 'default'" size="small" @click="filter = 'resolved'">已处理</el-button>
      </div>
    </div>

    <el-table :data="filteredItems" stripe class="feedback-table" v-loading="loading" empty-text="暂无反馈记录">
      <el-table-column type="index" label="序号" width="60" />
      <el-table-column prop="question" label="问题" min-width="160">
        <template #default="{ row }">
          <div class="text-cell">{{ row.question }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="answer" label="AI回答" min-width="200">
        <template #default="{ row }">
          <div class="text-cell">{{ row.answer }}</div>
        </template>
      </el-table-column>
      <el-table-column label="反馈类型" width="110" align="center">
        <template #default="{ row }">
          <template v-if="row.feedback_text">
            <el-tag type="warning" size="small">内容有误</el-tag>
          </template>
          <template v-else-if="row.rating === 1">
            <el-tag type="success" size="small">赞</el-tag>
          </template>
          <template v-else-if="row.rating === -1">
            <el-tag type="danger" size="small">踩</el-tag>
          </template>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="feedback_text" label="反馈描述" min-width="160">
        <template #default="{ row }">
          <div class="text-cell">{{ row.feedback_text || '-' }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="resolved" label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.resolved ? 'success' : 'warning'" size="small">
            {{ row.resolved ? '已处理' : '未处理' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="提交时间" width="170" align="center">
        <template #default="{ row }">
          <span class="time-cell">{{ row.created_at ? row.created_at.replace('T', ' ').substring(0, 19) : '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!row.resolved"
            type="primary"
            size="small"
            text
            @click="handleResolve(row.id)"
          >标记已处理</el-button>
          <span v-else class="resolved-label">-</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { qaAPI } from '@/api'

const loading = ref(false)
const items = ref([])
const filter = ref('unresolved')

const filteredItems = computed(() => {
  if (filter.value === 'all') return items.value
  if (filter.value === 'unresolved') return items.value.filter(i => !i.resolved)
  return items.value.filter(i => i.resolved)
})

const unresolvedCount = computed(() => items.value.filter(i => !i.resolved).length)

async function fetchFeedbacks() {
  loading.value = true
  try {
    const resp = await qaAPI.getFeedbacks()
    items.value = resp.data?.items || []
  } catch (e) {
    if (e.response?.status === 403) {
      ElMessage.warning('仅管理员可查看反馈列表')
    } else {
      ElMessage.error('获取反馈列表失败')
    }
  }
  loading.value = false
}

async function handleResolve(id) {
  try {
    await qaAPI.resolveFeedback(id)
    ElMessage.success('已标记为已处理')
    const item = items.value.find(i => i.id === id)
    if (item) item.resolved = true
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

onMounted(() => {
  fetchFeedbacks()
})
</script>

<style scoped>
.feedback-page { padding: 0; }

.page-header {
  display: flex; justify-content: space-between; align-items: flex-start;
  margin-bottom: 20px;
}

.header-left { display: flex; flex-direction: column; gap: 4px; }

.page-title {
  font-size: 20px; font-weight: 600; color: #1f2937; margin: 0;
}

.page-subtitle {
  font-size: 13px; color: #94a3b8;
}

.header-actions { display: flex; gap: 8px; align-self: center; }

.feedback-table {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  overflow: hidden;
}

.feedback-table :deep(.el-table__header-wrapper th) {
  background: #f8fafc;
  color: #1f2937;
  font-weight: 600;
}

.feedback-table :deep(.el-table__header-wrapper th .cell) {
  color: #1f2937;
  font-weight: 600;
}

.text-cell {
  overflow: hidden; text-overflow: ellipsis;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  line-height: 1.5; font-size: 13px;
}

.time-cell {
  font-size: 12px; color: #64748b;
}

.resolved-label { color: #94a3b8; }
</style>
