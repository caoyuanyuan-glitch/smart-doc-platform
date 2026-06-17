<template>
  <div class="preview-page">
    <div v-if="loading" class="loading-container">
      <el-icon class="is-loading" :size="40"><Loading /></el-icon>
      <p>加载中...</p>
    </div>

    <div v-else-if="error" class="error-container">
      <el-icon :size="60" color="#9ca3af"><WarningFilled /></el-icon>
      <p class="error-text">{{ error }}</p>
      <el-button @click="$router.push('/polish/history')">返回已润色文档列表</el-button>
    </div>

    <div v-else class="preview-content" v-loading="previewLoading">
      <div class="preview-header">
        <el-button @click="$router.push('/polish/history')">
          <el-icon><ArrowLeft /></el-icon>
          返回列表
        </el-button>
        <div class="header-title">
          <h3>{{ docInfo.name }}</h3>
          <el-tag v-if="docInfo.name.startsWith('【润色报告】')" type="warning">润色报告</el-tag>
          <el-tag v-else-if="docInfo.name.startsWith('【修订标记版】')" type="primary">修订标记版</el-tag>
          <el-tag v-else type="info">{{ docInfo.file_type }}</el-tag>
        </div>
        <div class="header-actions">
          <el-button v-if="docInfo.report_file_path" type="success" @click="handleDownloadReport">
            <el-icon><Download /></el-icon>
            下载润色报告
          </el-button>
          <el-button type="primary" @click="handleDownload">
            <el-icon><Download /></el-icon>
            下载文档
          </el-button>
        </div>
      </div>

      <div class="preview-body">
        <div v-if="preview.type === 'text' || preview.type === 'docx'" class="type-text-or-docx">
          <div v-if="preview.polished_content" class="preview-tabs">
            <el-tabs v-model="activeTab" class="text-tabs">
              <el-tab-pane label="原文内容" name="original"></el-tab-pane>
              <el-tab-pane :label="docInfo.name.startsWith('【修订标记版】') ? '修订标记版' : '润色后内容'" name="polished">
              </el-tab-pane>
            </el-tabs>
          </div>
          <div class="text-content-wrapper">
            <pre class="text-content">{{ activeTab === 'original' ? (preview.content || '') : (preview.polished_content || '') }}</pre>
          </div>
        </div>

        <div v-if="preview.type === 'image'" class="image-preview-wrapper">
          <img :src="preview.file_path" alt="预览图片" class="preview-image" />
        </div>

        <div v-if="preview.type === 'pdf'" class="pdf-preview-wrapper">
          <iframe :src="preview.file_path" class="pdf-frame" frameborder="0"></iframe>
        </div>

        <div v-if="preview.type === 'unsupported' || preview.type === 'error'" class="unsupported-preview">
          <el-icon :size="60" color="#9ca3af"><Document /></el-icon>
          <p>{{ preview.content || '该文件类型暂不支持在线预览，请下载查看' }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Download, Loading, WarningFilled, Document } from '@element-plus/icons-vue'
import { polishAPI } from '@/api'

const route = useRoute()
const loading = ref(true)
const error = ref('')
const previewLoading = ref(false)
const docInfo = ref(null)
const preview = ref({})
const activeTab = ref('original')

async function loadPreview() {
  const id = route.params.id
  if (!id) {
    error.value = '未提供文档 ID'
    loading.value = false
    return
  }

  loading.value = true
  try {
    const docResp = await polishAPI.getPolishedDocument(id)
    docInfo.value = docResp.data

    previewLoading.value = true
    const previewResp = await polishAPI.previewPolishedFile(id)
    preview.value = previewResp.data
  } catch (e) {
    error.value = e.response?.data?.detail || '加载预览数据失败'
  } finally {
    loading.value = false
    previewLoading.value = false
  }
}

function handleDownload() {
  if (!docInfo.value) return
  polishAPI.downloadPolishedFile(docInfo.value.id, docInfo.value.filename)
  ElMessage.success('已开始下载')
}

async function handleDownloadReport() {
  if (!docInfo.value) return
  try {
    const name = docInfo.value.name.replace('【修订标记版】', '【润色报告】').replace(/\.[^.]+$/, '.docx')
    await polishAPI.downloadPolishedReport(docInfo.value.id, name)
    ElMessage.success('润色报告下载已开始')
  } catch (e) {
    ElMessage.error('下载失败')
  }
}

onMounted(() => {
  loadPreview()
})
</script>

<style scoped>
.preview-page {
  height: calc(100vh - 108px);
  display: flex;
  flex-direction: column;
  background: #f9fafb;
}

.loading-container, .error-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: #6b7280;
}

.error-container { text-align: center; }

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
}

.header-title h3 {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}

.header-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}

.preview-body {
  flex: 1;
  overflow: auto;
}

.type-text-or-docx {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
}

.preview-tabs {
  padding: 0 16px;
}

.text-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
  margin-top: 8px;
}

.text-content-wrapper {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.text-content {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: system-ui, -apple-system, sans-serif;
  font-size: 14px;
  line-height: 1.6;
  color: #1f2937;
}

.image-preview-wrapper {
  height: 100%;
  display: flex;
  justify-content: center;
  padding: 16px;
  background: #fff;
  overflow: auto;
}

.preview-image {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.pdf-preview-wrapper {
  height: 100%;
  background: #fff;
  overflow: auto;
}

.pdf-frame {
  width: 100%;
  height: 100%;
  border: none;
}

.unsupported-preview {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #fff;
  color: #6b7280;
  gap: 16px;
}
</style>
