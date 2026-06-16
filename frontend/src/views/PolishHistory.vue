<template>
  <div class="polish-history-page">
    <div class="page-header">
      <h2 class="page-title">已润色文档</h2>
      <div class="page-actions">
        <el-upload
          ref="uploadRef"
          action=""
          :auto-upload="false"
          :show-file-list="false"
          :on-change="handleFileChange"
          accept="*"
          multiple
        >
          <el-button type="primary">
            <el-icon><Upload /></el-icon>
            上传文档
          </el-button>
        </el-upload>
      </div>
    </div>

    <div class="content-area">
      <div class="files-section">
        <div class="section-header">
          <span>文档列表</span>
          <span class="file-count">共 {{ documents.length }} 个文档</span>
        </div>

        <el-table
          :data="documents"
          border
          style="width: 100%"
          v-loading="loading"
          empty-text="暂无文档，请上传"
        >
          <el-table-column prop="name" label="文件名" min-width="200" show-overflow-tooltip />
          <el-table-column prop="file_type" label="类型" width="80" align="center" />
          <el-table-column label="大小" width="100" align="center">
            <template #default="{ row }">
              {{ formatFileSize(row.file_size) }}
            </template>
          </el-table-column>
          <el-table-column label="上传时间" width="170">
            <template #default="{ row }">
              {{ formatDateTime(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column prop="has_polished_content" label="类型" width="100" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.name.startsWith('【润色报告】')" type="warning">润色报告</el-tag>
              <el-tag v-else-if="row.name.startsWith('【修订标记版】')" type="primary">修订标记版</el-tag>
              <el-tag v-else type="info">{{ row.file_type || '文档' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="420" fixed="right" align="center">
            <template #default="{ row }">
              <el-button size="small" @click="handlePreview(row)">
                <el-icon><View /></el-icon>
                预览
              </el-button>
              <el-button size="small" @click="handleDownload(row)">
                <el-icon><Download /></el-icon>
                下载
              </el-button>
              <el-button
                v-if="row.report_file_path && !row.name.startsWith('【润色报告】')"
                size="small"
                type="success"
                @click="handleDownloadReport(row)"
              >
                <el-icon><Download /></el-icon>
                下载润色报告
              </el-button>
              <el-button
                size="small"
                type="danger"
                @click="handleDelete(row)"
              >
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
import { Upload, Download, View, Delete, Document } from '@element-plus/icons-vue'
import { polishAPI } from '@/api'

const router = useRouter()
const documents = ref([])
const loading = ref(false)

function formatFileSize(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}

function formatDateTime(dateStr) {
  if (!dateStr) return ''
  try {
    const d = new Date(dateStr)
    if (isNaN(d.getTime())) return dateStr
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    const h = String(d.getHours()).padStart(2, '0')
    const min = String(d.getMinutes()).padStart(2, '0')
    const s = String(d.getSeconds()).padStart(2, '0')
    return `${y}/${m}/${day} ${h}:${min}:${s}`
  } catch (e) {
    return dateStr
  }
}

async function loadDocuments() {
  loading.value = true
  try {
    const resp = await polishAPI.listPolishedDocuments()
    documents.value = resp.data || []
  } catch (e) {
    ElMessage.error('加载文档列表失败')
  } finally {
    loading.value = false
  }
}

async function handleFileChange(file) {
  try {
    await polishAPI.uploadPolishedFile(file.raw)
    ElMessage.success('上传成功')
    loadDocuments()
  } catch (e) {
    ElMessage.error('上传失败：' + (e.response?.data?.detail || e.message))
  }
}

async function handlePreview(doc) {
  router.push({ name: 'PolishPreview', params: { id: doc.id } })
}

async function handleDownload(doc) {
  try {
    await polishAPI.downloadPolishedFile(doc.id, doc.name)
    ElMessage.success('下载已开始')
  } catch (e) {
    ElMessage.error('下载失败')
  }
}

async function handleDownloadReport(doc) {
  if (!doc.report_file_path) {
    ElMessage.warning('暂无润色报告')
    return
  }
  try {
    await polishAPI.downloadPolishedReport(doc.id, `【润色报告】${doc.name.replace(/\.[^.]+$/, '.docx')}`)
    ElMessage.success('润色报告下载已开始')
  } catch (e) {
    ElMessage.error('下载失败')
  }
}

async function handleDelete(doc) {
  try {
    await ElMessageBox.confirm(
      `确定要删除文档 "${doc.name}" 吗？`,
      '确认删除',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await polishAPI.deletePolishedDocument(doc.id)
    ElMessage.success('删除成功')
    loadDocuments()
  } catch (e) {
    if (e !== 'cancel') {
      const msg = e.response?.data?.detail || '未知错误'
      if (msg.includes('仅管理员')) {
        ElMessage.error('您没有权限删除此文件')
      } else {
        ElMessage.error('删除文件失败：' + msg)
      }
    }
  }
}

onMounted(() => {
  loadDocuments()
})
</script>

<style scoped>
.polish-history-page {
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

.content-area {
  flex: 1;
  overflow-y: auto;
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.files-section {
  height: 100%;
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
}

.file-count {
  font-size: 12px;
  color: #9ca3af;
  font-weight: normal;
}
</style>
