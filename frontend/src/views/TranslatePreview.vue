<template>
  <div class="preview-page">
    <div v-if="loading" class="loading-container">
      <el-icon class="is-loading" :size="40"><Loading /></el-icon>
      <p>加载中...</p>
    </div>

    <div v-else-if="error" class="error-container">
      <el-icon :size="60" color="#9ca3af"><WarningFilled /></el-icon>
      <p class="error-text">{{ error }}</p>
      <el-button @click="goBack">返回已翻译文档列表</el-button>
    </div>

    <div v-else class="preview-content">
      <div class="preview-header">
        <el-button @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          返回列表
        </el-button>
        <div class="header-title">
          <h3>{{ preview.translated_filename || preview.filename || '译文预览' }}</h3>
          <el-tag type="info">{{ preview.file_type || '文档' }}</el-tag>
        </div>
        <div class="header-actions">
          <el-button type="primary" @click="handleDownload">
            <el-icon><Download /></el-icon>
            下载文档
          </el-button>
        </div>
      </div>

      <div class="preview-body">
        <div v-if="preview.type === 'text'" class="text-preview-wrapper">
          <pre class="text-content">{{ preview.content || '暂无可预览内容' }}</pre>
        </div>
        <div v-else-if="preview.type === 'image'" class="image-preview-wrapper">
          <img v-if="objectUrl" :src="objectUrl" alt="译文预览" class="preview-image" />
        </div>
        <div v-else-if="preview.type === 'pdf'" class="pdf-preview-wrapper">
          <iframe v-if="objectUrl" :src="objectUrl" class="pdf-frame" frameborder="0"></iframe>
        </div>
        <div v-else class="unsupported-preview">
          <el-icon :size="60" color="#9ca3af"><Document /></el-icon>
          <p>{{ preview.content || '该文件类型暂不支持在线预览，请下载查看' }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Download, Loading, WarningFilled, Document } from '@element-plus/icons-vue'
import { getBlobErrorMessage, translationAPI } from '@/api'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const error = ref('')
const preview = ref({})
const objectUrl = ref('')

function goBack() {
  router.push({ name: 'TranslateHistory' })
}

function clearObjectUrl() {
  if (objectUrl.value) {
    URL.revokeObjectURL(objectUrl.value)
    objectUrl.value = ''
  }
}

async function loadPreview() {
  const id = route.params.id
  if (!id) {
    error.value = '未提供文档 ID'
    loading.value = false
    return
  }

  loading.value = true
  error.value = ''
  clearObjectUrl()
  try {
    const resp = await translationAPI.previewTranslatedDoc(id)
    preview.value = resp.data || {}
    if (preview.value.type === 'image' || preview.value.type === 'pdf') {
      const raw = await translationAPI.previewTranslatedDocRaw(id)
      objectUrl.value = URL.createObjectURL(raw.data)
    }
  } catch (e) {
    error.value = e.response?.data?.detail || '加载预览数据失败'
  } finally {
    loading.value = false
  }
}

async function handleDownload() {
  const id = route.params.id
  if (!id) return
  try {
    await translationAPI.downloadTranslatedDoc(id, preview.value.translated_filename || preview.value.filename)
    ElMessage.success('下载已开始')
  } catch (error) {
    const message = await getBlobErrorMessage(error, '下载译文失败')
    ElMessage.error(message)
  }
}

onMounted(() => {
  loadPreview()
})

onBeforeUnmount(() => {
  clearObjectUrl()
})
</script>

<style scoped>
.preview-page {
  height: calc(100vh - 108px);
  display: flex;
  flex-direction: column;
  background: #f9fafb;
}

.loading-container,
.error-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: #6b7280;
}

.error-container {
  text-align: center;
}

.error-text {
  font-size: 14px;
  margin-top: 8px;
  color: #ef4444;
}

.preview-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.preview-header {
  display: flex;
  align-items: center;
  padding: 12px 20px;
  border-bottom: 1px solid #e5e7eb;
  background: #fff;
  flex-shrink: 0;
  gap: 12px;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.header-title h3 {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}

.header-actions {
  margin-left: auto;
}

.preview-body {
  flex: 1;
  overflow: auto;
}

.text-preview-wrapper {
  height: 100%;
  padding: 20px;
}

.text-content {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  min-height: 100%;
  font-size: 14px;
  line-height: 1.7;
  color: #111827;
}

.image-preview-wrapper,
.pdf-preview-wrapper,
.unsupported-preview {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.preview-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  background: #fff;
}

.pdf-frame {
  width: 100%;
  height: 100%;
  background: #fff;
}

.unsupported-preview {
  flex-direction: column;
  gap: 12px;
  color: #6b7280;
}
</style>
