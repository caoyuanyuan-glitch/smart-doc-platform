<template>
  <div class="knowledge-page">
    <div class="page-header">
      <h2 class="page-title">
        <el-breadcrumb separator="/">
          <template v-if="currentFolder">
            <el-breadcrumb-item>{{ currentFolder.name }}</el-breadcrumb-item>
          </template>
          <span v-else class="no-folder-hint">请选择左侧知识库文件夹</span>
        </el-breadcrumb>
      </h2>
      <div class="page-actions" v-if="currentFolder">
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
            上传文件
          </el-button>
        </el-upload>
      </div>
    </div>

    <div class="content-area">
      <div v-if="!currentFolder" class="empty-state">
        <el-icon :size="80" color="#9ca3af"><FolderOpened /></el-icon>
        <p class="empty-text">请在左侧选择一个文件夹</p>
        <p class="empty-subtext">或在侧边栏点击 + 新建文件夹</p>
      </div>

      <div v-else class="files-section">
        <div class="section-header">
          <span>文件列表</span>
          <span class="file-count">共 {{ currentFiles.length }} 个文件</span>
        </div>

        <el-table
          :data="currentFiles"
          border
          style="width: 100%"
          v-loading="fileLoading"
          empty-text="暂无文件，请上传"
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
          <el-table-column label="操作" width="320" fixed="right" align="center">
            <template #default="{ row }">
              <el-button size="small" @click="handlePreviewFile(row)">
                <el-icon><View /></el-icon>
                预览
              </el-button>
              <el-button size="small" @click="handleDownloadFile(row)">
                <el-icon><Download /></el-icon>
                下载
              </el-button>
              <el-button
                size="small"
                type="danger"
                @click="handleDeleteFile(row)"
              >
                <el-icon><Delete /></el-icon>
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 文件预览对话框 -->
    <el-dialog
      v-model="previewDialogVisible"
      :title="`预览：${previewFileName}`"
      width="80%"
      top="5vh"
    >
      <div class="preview-container">
        <!-- 文本文件预览 -->
        <div v-if="previewType === 'text'" class="text-preview">
          <pre>{{ previewContent }}</pre>
        </div>
        <!-- 图片预览 -->
        <div v-if="previewType === 'image'" class="image-preview">
          <img :src="previewFileUrl" alt="预览图片" />
        </div>
        <!-- PDF 预览 -->
        <div v-if="previewType === 'pdf'" class="pdf-preview">
          <iframe :src="previewFileUrl" frameborder="0" class="preview-frame"></iframe>
        </div>
        <!-- DOCX 预览 -->
        <div v-if="previewType === 'docx'" class="docx-preview">
          <pre>{{ previewContent }}</pre>
        </div>
        <!-- 不支持的类型 -->
        <div v-if="previewType === 'unsupported' || previewType === 'error'" class="unsupported-preview">
          <el-icon :size="50" color="#9ca3af"><Document /></el-icon>
          <p>{{ previewContent }}</p>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, Download, View, Delete, FolderOpened, Document } from '@element-plus/icons-vue'
import { knowledgeAPI } from '@/api'
import { useUserStore } from '@/store/user'

const route = useRoute()
const userStore = useUserStore()
const currentFiles = ref([])
const fileLoading = ref(false)
const currentFolder = ref(null)

const currentUser = computed(() => userStore.user)

const previewDialogVisible = ref(false)
const previewContent = ref('')
const previewType = ref('text')
const previewFileName = ref('')
const previewFileUrl = ref('')

const folderId = computed(() => {
  const id = route.params.id
  return id ? parseInt(id) : null
})

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

async function loadFolderContent(id) {
  if (!id) {
    currentFolder.value = null
    currentFiles.value = []
    return
  }
  
  fileLoading.value = true
  try {
    const resp = await knowledgeAPI.getFolderContent(id)
    currentFolder.value = resp.data.folder
    currentFiles.value = resp.data.files || []
  } catch (e) {
    ElMessage.error('加载文件列表失败')
    currentFiles.value = []
  } finally {
    fileLoading.value = false
  }
}

async function handleFileChange(file) {
  if (!folderId.value) {
    ElMessage.warning('请先选择文件夹')
    return
  }
  try {
    await knowledgeAPI.uploadFile(folderId.value, file.raw)
    ElMessage.success('上传成功')
    loadFolderContent(folderId.value)
  } catch (e) {
    ElMessage.error('上传失败：' + (e.response?.data?.detail || e.message))
  }
}

async function handlePreviewFile(file) {
  try {
    const resp = await knowledgeAPI.previewFile(file.id)
    const data = resp.data
    previewFileName.value = data.file_name
    previewType.value = data.type
    previewContent.value = data.content || ''
    previewFileUrl.value = data.file_path || ''
    previewDialogVisible.value = true
  } catch (e) {
    ElMessage.error('预览失败')
  }
}

async function handleDownloadFile(file) {
  try {
    await knowledgeAPI.downloadFile(file.id, file.name)
    ElMessage.success('下载已开始')
  } catch (e) {
    ElMessage.error('下载失败')
  }
}

async function handleDeleteFile(file) {
  try {
    await ElMessageBox.confirm(
      `确定要删除文件 "${file.name}" 吗？`,
      '确认删除',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await knowledgeAPI.deleteFile(file.id)
    ElMessage.success('删除成功')
    loadFolderContent(folderId.value)
  } catch (e) {
    if (e !== 'cancel') {
      const msg = e.response?.data?.detail || '未知错误'
      if (msg.includes('仅管理员') || msg.includes('创建者')) {
        ElMessage.error('您没有权限删除此文件')
      } else {
        ElMessage.error('删除文件失败：' + msg)
      }
    }
  }
}

watch(() => route.params.id, (newId) => {
  if (newId) {
    loadFolderContent(parseInt(newId))
  } else {
    currentFolder.value = null
    currentFiles.value = []
  }
})

onMounted(() => {
  if (folderId.value) {
    loadFolderContent(folderId.value)
  }
})
</script>

<style scoped>
.knowledge-page {
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

.no-folder-hint {
  color: #9ca3af;
  font-size: 16px;
}

.content-area {
  flex: 1;
  overflow-y: auto;
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.empty-text {
  color: #6b7280;
  font-size: 16px;
  margin-top: 16px;
}

.empty-subtext {
  color: #9ca3af;
  font-size: 14px;
  margin-top: 8px;
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

.preview-container {
  max-height: 70vh;
  overflow: auto;
}

.text-preview pre {
  white-space: pre-wrap;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 14px;
  line-height: 1.6;
  margin: 0;
}

.image-preview img {
  max-width: 100%;
  max-height: 70vh;
  display: block;
  margin: 0 auto;
}

.pdf-preview,
.docx-preview {
  width: 100%;
  height: 70vh;
}

.preview-frame {
  width: 100%;
  height: 100%;
  border: none;
}

.unsupported-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: #6b7280;
  font-size: 16px;
  padding: 40px;
}
</style>
