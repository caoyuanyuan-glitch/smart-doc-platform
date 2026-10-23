<template>
  <div class="translate-history-page">
    <div class="page-header">
      <h2 class="page-title">已翻译文档</h2>
      <div class="page-actions">
        <el-button type="danger" :disabled="selectedIds.length === 0" @click="batchDelete">
          批量删除 ({{ selectedIds.length }})
        </el-button>
      </div>
    </div>

    <div class="content-area">
      <div class="files-section">
        <div class="section-header">
          <span>文档列表</span>
          <div class="section-header-right">
            <span class="file-count">共 {{ documents.length }} 个文档</span>
            <el-button size="small" @click="loadDocuments" :loading="loading">刷新</el-button>
          </div>
        </div>

        <el-table
          :data="documents"
          border
          style="width: 100%"
          v-loading="loading"
          empty-text="暂无已翻译文档"
          @selection-change="handleSelectionChange"
        >
          <el-table-column type="selection" width="50" />
          <el-table-column prop="filename" label="原文件名" min-width="200" show-overflow-tooltip />
          <el-table-column prop="translated_filename" label="译文文件名" min-width="200" show-overflow-tooltip />
          <el-table-column prop="file_type" label="类型" width="90" align="center">
            <template #default="{ row }">
              <el-tag type="info">{{ formatFileType(row.file_type, row.filename) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="大小" width="110" align="center">
            <template #default="{ row }">
              {{ formatFileSize(row.file_size) }}
            </template>
          </el-table-column>
          <el-table-column label="翻译耗时" width="120" align="center">
            <template #default="{ row }">
              {{ formatDuration(row.duration_ms) }}
            </template>
          </el-table-column>
          <el-table-column label="上传时间" width="180">
            <template #default="{ row }">
              {{ formatDateTime(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="280" fixed="right" align="center">
            <template #default="{ row }">
              <el-button size="small" @click="handlePreview(row)">
                <el-icon><View /></el-icon>
                预览
              </el-button>
              <el-button size="small" @click="handleDownload(row)">
                <el-icon><Download /></el-icon>
                下载
              </el-button>
              <el-button size="small" type="danger" @click="handleDelete(row)">
                <el-icon><Delete /></el-icon>
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, View, Delete } from '@element-plus/icons-vue'
import { getBlobErrorMessage, translationAPI } from '@/api'

const router = useRouter()
const documents = ref([])
const selectedIds = ref([])
const loading = ref(false)

function handleSelectionChange(selection) {
  selectedIds.value = selection.map(row => row.id)
}

function formatFileType(fileType, filename) {
  const rawType = String(fileType || '').replace('.', '').trim()
  if (rawType) return rawType.toLowerCase()
  const ext = String(filename || '').split('.').pop()
  return ext && ext !== filename ? ext.toLowerCase() : '文档'
}

function formatFileSize(bytes) {
  const size = Number(bytes || 0)
  if (!size) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1)
  const value = size / Math.pow(1024, index)
  return `${Math.round(value * 100) / 100} ${units[index]}`
}

function formatDuration(durationMs) {
  const ms = Number(durationMs || 0)
  if (!ms || ms < 0) return '-'
  const totalSeconds = Math.max(1, Math.round(ms / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  if (hours > 0) return `${hours}小时${String(minutes).padStart(2, '0')}分${String(seconds).padStart(2, '0')}秒`
  if (minutes > 0) return `${minutes}分${String(seconds).padStart(2, '0')}秒`
  return `${seconds}秒`
}

function formatDateTime(dateStr) {
  if (!dateStr) return '-'
  try {
    const raw = String(dateStr).trim()
    const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/.test(raw) ? raw : `${raw}Z`
    const date = new Date(normalized)
    if (Number.isNaN(date.getTime())) return raw.slice(0, 19).replace('T', ' ')
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const hour = String(date.getHours()).padStart(2, '0')
    const minute = String(date.getMinutes()).padStart(2, '0')
    const second = String(date.getSeconds()).padStart(2, '0')
    return `${year}/${month}/${day} ${hour}:${minute}:${second}`
  } catch (e) {
    return String(dateStr)
  }
}

async function loadDocuments() {
  loading.value = true
  try {
    const resp = await translationAPI.getDocs(0, 500, '', true)
    documents.value = resp.data || []
  } catch (e) {
    ElMessage.error('加载已翻译文档失败')
  } finally {
    loading.value = false
  }
}

function handlePreview(doc) {
  if (!doc?.id) return
  router.push({ name: 'TranslatePreview', params: { id: String(doc.id) } })
}

async function handleDownload(doc) {
  try {
    await translationAPI.downloadTranslatedDoc(doc.id, doc.translated_filename || doc.filename)
    ElMessage.success('下载已开始')
  } catch (error) {
    const message = await getBlobErrorMessage(error, '下载译文失败')
    ElMessage.error(message)
  }
}

async function handleDelete(doc) {
  try {
    await ElMessageBox.confirm(
      `确定要删除文档 "${doc.filename}" 吗？`,
      '确认删除',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await translationAPI.deleteDoc(doc.id)
    ElMessage.success('删除成功')
    loadDocuments()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.detail || '删除失败')
    }
  }
}

async function batchDelete() {
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedIds.value.length} 个文档吗？`,
      '批量删除',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    for (const id of selectedIds.value) {
      await translationAPI.deleteDoc(id)
    }
    ElMessage.success('批量删除成功')
    selectedIds.value = []
    loadDocuments()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.detail || '批量删除失败')
    }
  }
}

onMounted(() => {
  loadDocuments()
})
</script>

<style scoped>
.translate-history-page {
  height: calc(100vh - 108px);
  display: flex;
  flex-direction: column;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-shrink: 0;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #1f2937;
}

.page-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.content-area {
  flex: 1;
  overflow: hidden;
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  display: flex;
  flex-direction: column;
}

.files-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
  font-weight: 600;
  color: #1f2937;
  flex-shrink: 0;
}

.section-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.file-count {
  font-size: 12px;
  color: #9ca3af;
  font-weight: normal;
}

.preview-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
  color: #4b5563;
  font-size: 13px;
}

.preview-content {
  max-height: 60vh;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  background: #f8fafc;
  border-radius: 8px;
  padding: 16px;
  font-size: 13px;
  line-height: 1.6;
  color: #111827;
}

:deep(.el-table__header-wrapper th) {
  background: #f8fafc;
  color: #111827;
  font-weight: 700;
}
</style>
