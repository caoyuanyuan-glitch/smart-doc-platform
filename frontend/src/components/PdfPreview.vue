<template>
  <div class="pdf-preview">
    <div class="pdf-toolbar">
      <div class="toolbar-left">
        <el-button
          size="small"
          :icon="ArrowLeft"
          :disabled="currentPage <= 1 || loading"
          @click="prevPage"
        />
        <span class="page-info">
          <el-input-number
            v-model="inputPage"
            :min="1"
            :max="totalPages || 1"
            size="small"
            :disabled="loading || !totalPages"
            @change="jumpToPage"
            controls-position="right"
            style="width: 100px"
          />
          <span class="page-total">/ {{ totalPages || 0 }}</span>
        </span>
        <el-button
          size="small"
          :icon="ArrowRight"
          :disabled="currentPage >= totalPages || loading"
          @click="nextPage"
        />
      </div>
      <div class="toolbar-center">
        <span class="file-name" :title="fileName">{{ fileName }}</span>
      </div>
      <div class="toolbar-right">
        <el-button
          size="small"
          :icon="ZoomOut"
          :disabled="loading || scale <= 0.5"
          @click="zoomOut"
        />
        <span class="scale-text">{{ Math.round(scale * 100) }}%</span>
        <el-button
          size="small"
          :icon="ZoomIn"
          :disabled="loading || scale >= 3"
          @click="zoomIn"
        />
        <el-button
          size="small"
          :disabled="loading"
          @click="fitWidth"
        >
          适应宽度
        </el-button>
      </div>
    </div>

    <div class="pdf-container" ref="containerRef">
      <div v-if="loading" class="pdf-loading">
        <el-icon class="loading-icon" :size="32"><Loading /></el-icon>
        <span>加载中...</span>
      </div>
      <div v-else-if="error" class="pdf-error">
        <el-icon :size="32" color="#f56c6c"><Warning /></el-icon>
        <span>{{ error }}</span>
      </div>
      <canvas v-show="!loading && !error" ref="canvasRef" class="pdf-canvas" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, nextTick } from 'vue'
import { ArrowLeft, ArrowRight, ZoomIn, ZoomOut, Loading, Warning } from '@element-plus/icons-vue'
import * as pdfjsLib from 'pdfjs-dist'

const props = defineProps({
  pdfUrl: {
    type: String,
    required: true
  },
  fileName: {
    type: String,
    default: 'document.pdf'
  },
  initialPage: {
    type: Number,
    default: 1
  }
})

const emit = defineEmits(['page-change', 'loaded'])

const containerRef = ref(null)
const canvasRef = ref(null)
const currentPage = ref(1)
const inputPage = ref(1)
const totalPages = ref(0)
const scale = ref(1.2)
const loading = ref(false)
const error = ref('')
let pdfDoc = null
let currentRenderTask = null

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url
).toString()

async function loadPdf() {
  if (!props.pdfUrl) return
  loading.value = true
  error.value = ''
  try {
    const loadingTask = pdfjsLib.getDocument(props.pdfUrl)
    pdfDoc = await loadingTask.promise
    totalPages.value = pdfDoc.numPages
    emit('loaded', { totalPages: totalPages.value })
    if (props.initialPage && props.initialPage <= totalPages.value) {
      currentPage.value = props.initialPage
      inputPage.value = props.initialPage
    }
    await renderPage(currentPage.value)
  } catch (e) {
    console.error('PDF load error:', e)
    error.value = 'PDF加载失败: ' + (e.message || e)
  } finally {
    loading.value = false
  }
}

async function renderPage(pageNum) {
  if (!pdfDoc || !canvasRef.value) return
  if (currentRenderTask) {
    try {
      await currentRenderTask.cancel()
    } catch (e) {}
  }
  try {
    const page = await pdfDoc.getPage(pageNum)
    const viewport = page.getViewport({ scale: scale.value })
    const canvas = canvasRef.value
    const context = canvas.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    canvas.width = viewport.width * dpr
    canvas.height = viewport.height * dpr
    canvas.style.width = viewport.width + 'px'
    canvas.style.height = viewport.height + 'px'
    context.scale(dpr, dpr)
    const renderContext = {
      canvasContext: context,
      viewport: viewport
    }
    currentRenderTask = page.render(renderContext)
    await currentRenderTask.promise
    currentPage.value = pageNum
    inputPage.value = pageNum
    emit('page-change', pageNum)
  } catch (e) {
    if (e.name !== 'RenderingCancelledException') {
      console.error('Page render error:', e)
    }
  }
}

function prevPage() {
  if (currentPage.value > 1) {
    renderPage(currentPage.value - 1)
  }
}

function nextPage() {
  if (currentPage.value < totalPages.value) {
    renderPage(currentPage.value + 1)
  }
}

function jumpToPage(val) {
  const page = parseInt(val)
  if (page >= 1 && page <= totalPages.value && page !== currentPage.value) {
    renderPage(page)
  }
}

function zoomIn() {
  if (scale.value < 3) {
    scale.value = Math.min(3, scale.value + 0.2)
    renderPage(currentPage.value)
  }
}

function zoomOut() {
  if (scale.value > 0.5) {
    scale.value = Math.max(0.5, scale.value - 0.2)
    renderPage(currentPage.value)
  }
}

async function fitWidth() {
  if (!pdfDoc || !containerRef.value) return
  const page = await pdfDoc.getPage(1)
  const containerWidth = containerRef.value.clientWidth - 20
  const viewport = page.getViewport({ scale: 1 })
  const newScale = containerWidth / viewport.width
  scale.value = Math.max(0.5, Math.min(3, newScale))
  renderPage(currentPage.value)
}

function goToPage(pageNum) {
  if (pageNum >= 1 && pageNum <= totalPages.value && pageNum !== currentPage.value) {
    renderPage(pageNum)
  }
}

watch(() => props.pdfUrl, (newUrl) => {
  if (newUrl) {
    loadPdf()
  }
})

onMounted(() => {
  if (props.pdfUrl) {
    nextTick(() => {
      loadPdf()
    })
  }
})

defineExpose({
  goToPage,
  currentPage,
  totalPages
})
</script>

<style scoped>
.pdf-preview {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f5f7fa;
  border-radius: 8px;
  overflow: hidden;
}

.pdf-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  flex-shrink: 0;
}

.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-center {
  flex: 1;
  text-align: center;
}

.file-name {
  font-size: 13px;
  color: #606266;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
}

.page-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #606266;
}

.page-total {
  font-size: 13px;
  color: #909399;
}

.scale-text {
  font-size: 12px;
  color: #606266;
  min-width: 45px;
  text-align: center;
}

.pdf-container {
  flex: 1;
  overflow: auto;
  display: flex;
  justify-content: center;
  padding: 16px;
  position: relative;
}

.pdf-canvas {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  background: #fff;
}

.pdf-loading,
.pdf-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #909399;
  font-size: 14px;
  height: 300px;
}

.loading-icon {
  animation: rotate 1.5s linear infinite;
  color: #409eff;
}

@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
