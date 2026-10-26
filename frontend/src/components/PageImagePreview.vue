<template>
  <div class="pdf-preview">
    <div class="pdf-toolbar">
      <div class="toolbar-left">
        <el-button
          size="small"
          :icon="ArrowLeft"
          :disabled="currentPage <= 1"
          @click="prevPage"
        />
        <span class="page-info">
          <el-input-number
            v-model="inputPage"
            :min="1"
            :max="totalPages || 1"
            size="small"
            :disabled="!totalPages"
            @change="jumpToPage"
            controls-position="right"
            style="width: 100px"
          />
          <span class="page-total">/ {{ totalPages || 0 }}</span>
        </span>
        <el-button
          size="small"
          :icon="ArrowRight"
          :disabled="currentPage >= totalPages"
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
          :disabled="loading || scale <= 0.25"
          @click="zoomOut"
        />
        <span class="scale-text">{{ Math.round(scale * 100) }}%</span>
        <el-button
          size="small"
          :icon="ZoomIn"
          :disabled="loading || scale >= 3"
          @click="zoomIn"
        />
        <el-button size="small" :disabled="loading" @click="fitWidth">适应宽度</el-button>
        <el-button size="small" :disabled="loading" @click="fitPage">适应整页</el-button>
      </div>
    </div>

    <div class="pdf-container" ref="containerRef">
      <div v-if="loading && !pageUrl" class="pdf-loading">
        <el-icon class="loading-icon" :size="32"><Loading /></el-icon>
        <span>加载中...</span>
      </div>
      <div v-else-if="error" class="pdf-error">
        <el-icon :size="32" color="#f56c6c"><Warning /></el-icon>
        <span>{{ error }}</span>
      </div>
      <img
        v-show="pageUrl && !error"
        :src="pageUrl"
        class="pdf-page-image"
        :style="{ width: Math.round(scale * 100) + '%' }"
        alt="pdf-page"
        @load="onImageLoad"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { ArrowLeft, ArrowRight, ZoomIn, ZoomOut, Loading, Warning } from '@element-plus/icons-vue'
import { compareAPI } from '@/api'

const props = defineProps({
  taskId: { type: Number, required: true },
  side: { type: String, default: 'a' },
  fileName: { type: String, default: 'document.pdf' },
  totalPages: { type: Number, default: 0 },
  initialPage: { type: Number, default: 1 },
  highlight: { type: Boolean, default: true },
  peerPage: { type: Number, default: 0 }
})

const emit = defineEmits(['page-change', 'loaded'])

const containerRef = ref(null)
const currentPage = ref(1)
const inputPage = ref(1)
const scale = ref(1)
const loading = ref(false)
const error = ref('')
const pageUrl = ref('')
let loadSeq = 0
const imgNatural = ref({ w: 0, h: 0 })
const fitMode = ref('page')
let resizeObserver = null

function revokePageUrl() {
  if (pageUrl.value) {
    URL.revokeObjectURL(pageUrl.value)
    pageUrl.value = ''
  }
}

async function loadPage(pageNum, opts = {}) {
  if (!props.taskId || !props.totalPages) {
    error.value = '无法读取页数'
    return
  }
  const page = Math.max(1, Math.min(Number(pageNum) || 1, props.totalPages))
  const silent = !!opts.silent
  const changed = page !== currentPage.value
  currentPage.value = page
  inputPage.value = page
  if (changed && !silent) emit('page-change', page)
  const seq = ++loadSeq
  loading.value = true
  error.value = ''
  try {
    const resp = await compareAPI.getPreviewPage(props.taskId, props.side, page, {
      highlight: props.highlight,
      peerPage: 0,
    })
    if (seq !== loadSeq) return
    revokePageUrl()
    pageUrl.value = URL.createObjectURL(resp.data)
  } catch (e) {
    if (seq !== loadSeq) return
    error.value = '页面加载失败: ' + (e.message || e)
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function prevPage() {
  if (currentPage.value > 1) loadPage(currentPage.value - 1)
}

function nextPage() {
  if (currentPage.value < props.totalPages) loadPage(currentPage.value + 1)
}

function jumpToPage(val) {
  const page = parseInt(val, 10)
  if (page >= 1 && page <= props.totalPages && page !== currentPage.value) {
    loadPage(page)
  }
}

function zoomIn() {
  if (scale.value < 3) {
    fitMode.value = 'manual'
    scale.value = Math.min(3, +(scale.value + 0.2).toFixed(1))
  }
}

function zoomOut() {
  if (scale.value > 0.25) {
    fitMode.value = 'manual'
    scale.value = Math.max(0.25, +(scale.value - 0.2).toFixed(1))
  }
}

function fitWidth() {
  fitMode.value = 'width'
  scale.value = 1
}

function fitPage() {
  fitMode.value = 'page'
  const el = containerRef.value
  const { w, h } = imgNatural.value
  if (!el || !w || !h) return
  const pad = 32
  const cw = el.clientWidth - pad
  const ch = el.clientHeight - pad
  if (cw <= 0 || ch <= 0) return
  const heightAtFullWidth = cw * (h / w)
  const next = heightAtFullWidth > ch ? ch / heightAtFullWidth : 1
  scale.value = Math.max(0.25, Math.min(3, Math.round(next * 100) / 100))
}

function onImageLoad(e) {
  const img = e?.target
  if (!img) return
  imgNatural.value = { w: img.naturalWidth, h: img.naturalHeight }
  if (fitMode.value === 'page') {
    fitPage()
  }
}

function goToPage(pageNum, silent = false) {
  const page = parseInt(pageNum, 10)
  if (page >= 1 && page <= props.totalPages && page !== currentPage.value) {
    loadPage(page, { silent: !!silent })
  }
}

watch(
  () => [props.taskId, props.side, props.totalPages],
  () => {
    if (props.taskId && props.totalPages) {
      emit('loaded', { totalPages: props.totalPages })
      loadPage(props.initialPage || 1)
    }
  }
)

watch(
  () => props.highlight,
  () => {
    if (props.taskId && props.totalPages && currentPage.value) {
      loadPage(currentPage.value, { silent: true })
    }
  }
)

onMounted(() => {
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      if (fitMode.value === 'page') fitPage()
    })
    if (containerRef.value) resizeObserver.observe(containerRef.value)
  }
  if (props.taskId && props.totalPages) {
    emit('loaded', { totalPages: props.totalPages })
    loadPage(props.initialPage || 1)
  }
})

onBeforeUnmount(() => {
  loadSeq += 1
  revokePageUrl()
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
})

defineExpose({
  goToPage,
  currentPage,
  totalPages: props.totalPages
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

.pdf-page-image {
  display: block;
  height: auto;
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
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
