<template>
  <div class="false-positive-memory-page">
    <div class="page-header">
      <div>
        <h2 class="page-title">误报记忆库</h2>
        <p class="page-subtitle">管理已写入数据库的误报抑制条目。</p>
      </div>
      <el-button @click="loadEntries">刷新</el-button>
    </div>

    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索签名、规则、分类、原文、文档名"
        clearable
        style="width: 360px"
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      />
      <el-button type="primary" @click="handleSearch">搜索</el-button>
    </div>

    <el-table :data="entries" border stripe v-loading="loading">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="document_name" label="来源文档" min-width="180" show-overflow-tooltip />
      <el-table-column prop="category" label="分类" width="140" show-overflow-tooltip />
      <el-table-column prop="rule" label="规则" width="140" show-overflow-tooltip />
      <el-table-column prop="original_text" label="原文片段" min-width="220" show-overflow-tooltip />
      <el-table-column prop="signature" label="命中签名" min-width="260" show-overflow-tooltip />
      <el-table-column prop="created_at" label="创建时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button text type="danger" size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-row">
      <el-pagination
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadEntries"
      />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { reviewAPI } from '@/api'

const loading = ref(false)
const entries = ref([])
const keyword = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

function formatTime(value) {
  if (!value) return ''
  return String(value).replace('T', ' ').slice(0, 19)
}

async function loadEntries() {
  loading.value = true
  try {
    const { data } = await reviewAPI.listFalsePositiveMemory({
      keyword: keyword.value.trim(),
      skip: (page.value - 1) * pageSize.value,
      limit: pageSize.value,
    })
    entries.value = data.items || []
    total.value = data.total || 0
  } catch {
    entries.value = []
    total.value = 0
    ElMessage.error('加载误报记忆库失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  loadEntries()
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除误报记忆 #${row.id} 吗？`, '确认删除', { type: 'warning' })
  } catch {
    return
  }

  try {
    await reviewAPI.deleteFalsePositiveMemory(row.id)
    ElMessage.success('已删除')
    if (entries.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    await loadEntries()
  } catch {
    ElMessage.error('删除失败')
  }
}

onMounted(() => {
  loadEntries()
})
</script>

<style scoped>
.false-positive-memory-page {
  padding: 20px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  font-size: 24px;
}

.page-subtitle {
  margin: 6px 0 0;
  color: #6b7280;
  font-size: 14px;
}

.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
