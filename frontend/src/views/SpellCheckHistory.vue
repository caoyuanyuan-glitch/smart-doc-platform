<template>
  <div class="history-container">
    <div class="header-section">
      <h2>拼写检查历史</h2>
      <p class="subtitle">查看历史拼写检查任务的结果</p>
    </div>

    <div class="toolbar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索文件名/错误描述"
        clearable
        style="width: 300px;"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-select v-model="filterType" placeholder="筛选类型" size="default" style="width: 140px; margin-left: 8px;">
        <el-option label="全部" value="all"></el-option>
        <el-option label="有错误" value="has_error"></el-option>
        <el-option label="无错误" value="no_error"></el-option>
      </el-select>
      <el-button type="danger" plain style="margin-left: 8px;" @click="clearAll" :disabled="historyList.length === 0">
        <el-icon><Delete /></el-icon>
        清空历史
      </el-button>
      <el-button type="primary" @click="loadHistory" style="margin-left: 8px;">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <div class="table-section">
      <el-table
        :data="filteredHistory"
        border
        stripe
        v-loading="loading"
        empty-text="暂无历史记录，请先到「拼写检查」页面进行一次检查"
      >
        <el-table-column type="expand">
          <template #default="scope">
            <div class="detail-content">
              <div class="detail-section" v-if="scope.row.text">
                <h4>原文摘要</h4>
                <pre class="text-preview">{{ scope.row.text }}</pre>
              </div>
              <div class="detail-section">
                <h4>错误列表 ({{ scope.row.errors?.length || 0 }})</h4>
                <el-table :data="scope.row.errors" border size="small" max-height="400">
                  <el-table-column type="index" label="#" width="50" />
                  <el-table-column prop="type" label="类型" width="80">
                    <template #default="errScope">
                      <el-tag :type="getErrorTagType(errScope.row.type)" size="small">
                        {{ getErrorTypeLabel(errScope.row.type) }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="message" label="错误描述" width="140" />
                  <el-table-column prop="word" label="问题单词" width="140">
                    <template #default="errScope">
                      <span v-if="errScope.row.word" class="problem-word">{{ errScope.row.word }}</span>
                      <span v-else>-</span>
                    </template>
                  </el-table-column>
                  <el-table-column label="建议" min-width="200">
                    <template #default="errScope">
                      <el-tag
                        v-for="(s, idx) in (errScope.row.suggestions || [])"
                        :key="idx"
                        size="small"
                        style="margin-right: 4px; margin-bottom: 4px;"
                      >{{ s }}</el-tag>
                      <span v-if="!errScope.row.suggestions || errScope.row.suggestions.length === 0">-</span>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="filename" label="文件/来源" min-width="220" show-overflow-tooltip>
          <template #default="scope">
            <el-icon style="vertical-align: middle; margin-right: 4px;">
              <Document v-if="scope.row.filename !== '文本输入'" />
              <EditPen v-else />
            </el-icon>
            {{ scope.row.filename }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="检查时间" width="180">
          <template #default="scope">
            {{ formatTime(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="spell_count" label="拼写错误" width="100" align="center">
          <template #default="scope">
            <el-tag type="danger" size="small" effect="plain">{{ scope.row.spell_count }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="grammar_count" label="语法错误" width="100" align="center">
          <template #default="scope">
            <el-tag type="warning" size="small" effect="plain">{{ scope.row.grammar_count }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_count" label="总问题数" width="100" align="center">
          <template #default="scope">
            <el-tag :type="scope.row.total_count > 0 ? 'danger' : 'success'" size="small">
              {{ scope.row.total_count }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="scope">
            <el-button size="small" type="primary" plain @click="reapplyResult(scope.row)">
              重新加载
            </el-button>
            <el-button size="small" type="danger" plain @click="deleteItem(scope.row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="historyList.length === 0 && !loading" class="empty-tip">
      <el-empty description="还没有历史检查记录" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Delete, Refresh, Document, EditPen } from '@element-plus/icons-vue'

const router = useRouter()
const historyList = ref([])
const searchKeyword = ref('')
const filterType = ref('all')
const loading = ref(false)

const STORAGE_KEY = 'spell_check_history'

const filteredHistory = computed(() => {
  let result = historyList.value
  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase()
    result = result.filter(item => {
      if (item.filename?.toLowerCase().includes(kw)) return true
      if (item.errors?.some(e => e.message?.toLowerCase().includes(kw))) return true
      if (item.errors?.some(e => e.word?.toLowerCase().includes(kw))) return true
      return false
    })
  }
  if (filterType.value === 'has_error') {
    result = result.filter(item => item.total_count > 0)
  } else if (filterType.value === 'no_error') {
    result = result.filter(item => item.total_count === 0)
  }
  return result
})

function formatTime(iso) {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch (e) {
    return iso
  }
}

function loadHistory() {
  loading.value = true
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    historyList.value = stored ? JSON.parse(stored) : []
  } catch (e) {
    console.error('加载历史失败:', e)
    historyList.value = []
  } finally {
    loading.value = false
  }
}

function getErrorTypeLabel(type) {
  if (type === 'spell') return '拼写'
  if (type === 'style') return '风格'
  if (type === 'unit') return '单位'
  if (type === 'grammar') return '语法'
  return type || '其他'
}

function getErrorTagType(type) {
  if (type === 'spell') return 'danger'
  if (type === 'style') return 'info'
  if (type === 'unit') return 'success'
  return 'warning'
}

async function clearAll() {
  try {
    await ElMessageBox.confirm('确定要清空所有拼写检查历史吗？', '提示', {
      type: 'warning',
      confirmButtonText: '清空',
      cancelButtonText: '取消'
    })
    localStorage.removeItem(STORAGE_KEY)
    historyList.value = []
    ElMessage.success('已清空历史')
  } catch (e) {
    // 用户取消
  }
}

async function deleteItem(row) {
  try {
    await ElMessageBox.confirm(`确定要删除「${row.filename}」的检查记录吗？`, '提示', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
    const idx = historyList.value.findIndex(h => h.id === row.id)
    if (idx >= 0) {
      historyList.value.splice(idx, 1)
      localStorage.setItem(STORAGE_KEY, JSON.stringify(historyList.value))
      ElMessage.success('已删除')
    }
  } catch (e) {
    // 用户取消
  }
}

function reapplyResult(row) {
  // 通过 sessionStorage 传递给拼写检查页面
  sessionStorage.setItem('spell_check_reapply', JSON.stringify(row))
  router.push('/review/spell-check')
}

onMounted(() => {
  loadHistory()
})
</script>

<style scoped>
.history-container {
  max-width: 1400px;
  margin: 0 auto;
}

.header-section {
  margin-bottom: 24px;
}

.header-section h2 {
  font-size: 24px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 4px;
}

.subtitle {
  font-size: 14px;
  color: #6b7280;
}

.toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 4px;
}

.table-section {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  padding: 20px;
}

.detail-content {
  padding: 12px 20px;
  background: #f9fafb;
}

.detail-section {
  margin-bottom: 20px;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.detail-section h4 {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 10px;
}

.text-preview {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 12px;
  font-size: 13px;
  line-height: 1.6;
  color: #374151;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
}

.problem-word {
  color: #dc2626;
  font-weight: 600;
  background: #fef3c7;
  padding: 1px 4px;
  border-radius: 3px;
}

.empty-tip {
  margin-top: 40px;
}
</style>
