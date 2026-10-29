<template>
  <div class="compare-container">
    <div v-if="currentView === 'upload'">
      <h2 class="page-title">文档对比</h2>

      <div class="panel">
        <div class="panel-header">
          <span>上传文档进行对比</span>
          <div class="panel-actions">
            <el-tag size="small" type="info">支持 PDF / Word / Excel / MD / TXT / DITA / ZIP</el-tag>
          </div>
        </div>

        <div class="upload-grid">
          <div class="upload-slot">
            <div class="slot-label">基准文档</div>
            <label class="upload-box" :class="{ filled: files[0] }">
              <input type="file" accept=".pdf,.docx,.doc,.md,.markdown,.txt,.dita,.xml,.zip,.xlsx,.xls" @change="pickFile(0, $event)" />
              <el-icon style="font-size: 36px; color: #3b82f6; margin-bottom: 8px;"><Upload /></el-icon>
              <div v-if="!files[0]" class="upload-hint">点击上传基准文档</div>
              <div v-else class="upload-name">{{ files[0].name }}</div>
            </label>
            <div class="slot-hint">对照标准，如旧版</div>
          </div>
          <div class="vs-col">
            <div class="slot-label vs-spacer-label" aria-hidden="true">&nbsp;</div>
            <div class="vs-badge">VS</div>
            <div class="slot-hint vs-spacer-hint" aria-hidden="true">&nbsp;</div>
          </div>
          <div class="upload-slot">
            <div class="slot-label">待比文档</div>
            <label class="upload-box" :class="{ filled: files[1] }">
              <input type="file" accept=".pdf,.docx,.doc,.md,.markdown,.txt,.dita,.xml,.zip,.xlsx,.xls" @change="pickFile(1, $event)" />
              <el-icon style="font-size: 36px; color: #7c3aed; margin-bottom: 8px;"><Upload /></el-icon>
              <div v-if="!files[1]" class="upload-hint">点击上传待比文档</div>
              <div v-else class="upload-name">{{ files[1].name }}</div>
            </label>
            <div class="slot-hint">要检查的版本，如新版</div>
          </div>
        </div>

        <div class="action-row">
          <el-button type="primary" size="large" :loading="loading" :disabled="!files[0] || !files[1]" @click="doCompare">
            <el-icon><Search /></el-icon> 开始对比
          </el-button>
          <el-button size="large" @click="clearFiles">清空</el-button>
        </div>

        <div v-if="progress > 0 && progress < 100" class="progress-panel">
          <el-progress
            :percentage="progress"
            :stroke-width="8"
            :show-text="false"
            color="#3b82f6"
          />
          <div class="progress-text">{{ progressText }} {{ progress }}%</div>
        </div>
      </div>

      <div v-if="allResults.length > 0" class="result-panel">
        <div class="panel-header">
          <span>对比完成（{{ allResults.length }} 组结果）</span>
          <div class="panel-actions">
            <el-button size="small" @click="clearFiles">重新对比</el-button>
          </div>
        </div>

        <el-tabs v-model="activeResultTab" type="border-card" class="result-tabs">
          <el-tab-pane
            v-for="(r, ri) in allResults"
            :key="ri"
            :label="'对比 ' + (ri + 1) + ': ' + (r.file_b_name || '文档')"
            :name="ri"
          >
            <div class="pair-header">
              <span class="pair-label">
                {{ r.file_a_name }} <strong>VS</strong> {{ r.file_b_name }}
              </span>
              <div class="pair-tags">
                <el-tag :type="getVerdictTagType(r.verdict)" size="small">{{ r.verdict }}</el-tag>
                <el-tag type="info" size="small">差异数：{{ r.total_diffs || 0 }}</el-tag>
                <el-tag type="warning" size="small">相似度：{{ ((r.similarity || 0) * 100).toFixed(1) }}%</el-tag>
              </div>
            </div>
            <div class="pair-actions">
              <el-button size="small" type="primary" @click="previewPairReport(r.task_id)">预览报告</el-button>
              <el-button size="small" @click="exportPairReport(r.task_id)">导出报告</el-button>
              <el-button size="small" @click="openPairPdfPreview(r.task_id)">文档预览</el-button>
            </div>

            <div v-if="showPreview && activePreviewTask === r.task_id" class="panel" style="background: #fafafa; margin-top: 12px;">
              <div class="panel-header">
                <span>报告预览 - {{ r.file_a_name }} vs {{ r.file_b_name }}</span>
                <el-button size="small" @click="showPreview = false; activePreviewTask = null">关闭预览</el-button>
              </div>
              <div class="report-preview-content" style="max-height: 800px; overflow-y: auto; background: #fff; padding: 16px; border-radius: 6px;" v-html="reportContent"></div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>

      <el-dialog
        v-model="showPdfPreviewDialog"
        title="文档预览"
        :width="previewFullscreen ? '100%' : '98%'"
        :top="previewFullscreen ? '0' : '1vh'"
        :fullscreen="previewFullscreen"
        :close-on-click-modal="false"
        class="pdf-preview-dialog"
        header-class="pdf-preview-dialog-header"
        body-class="pdf-preview-dialog-body"
        modal-class="pdf-preview-overlay"
        :class="{ 'is-preview-fullscreen': previewFullscreen }"
        @closed="onPreviewDialogClosed"
      >
        <template #header>
          <div class="pdf-preview-header">
            <span class="pdf-preview-title">文档预览</span>
            <el-button type="primary" size="small" @click.stop="togglePreviewFullscreen">
              <el-icon><FullScreen /></el-icon>
              {{ previewFullscreen ? '退出全屏' : '全屏' }}
            </el-button>
          </div>
        </template>
        <TextDiffPreview
          v-if="isTextDiffPreview"
          :file-a-name="previewNameA || files[0]?.name || '基准文档'"
          :file-b-name="previewNameB || compareFiles[activePdfSide]?.name || '待比文档'"
          :rows="textDiffRows"
          :diff-sections="textDiffSections"
          :diff-count="textDiffCount"
        />
        <div v-else class="pdf-preview-wrapper">
          <div class="pdf-preview-pane">
            <div class="pane-header pane-a">
              <span>基准文档：{{ previewNameA || files[0]?.name || '基准文档' }}</span>
            </div>
            <div class="pane-content">
              <PageImagePreview
                v-if="previewKindA === 'pdf-pages' && previewTaskId"
                ref="pdfPreviewARef"
                :task-id="previewTaskId"
                side="a"
                :file-name="previewNameA || files[0]?.name || 'document_A.pdf'"
                :total-pages="previewPagesA"
                :highlight="highlightDiff"
                @page-change="onPageAChange"
                @loaded="onPdfALoaded"
              />
              <PdfPreview
                v-else-if="previewKindA === 'pdf' && pdfUrlA"
                ref="pdfPreviewARef"
                :pdf-url="pdfUrlA"
                :file-name="previewNameA || files[0]?.name || 'document_A.pdf'"
                @page-change="onPageAChange"
                @loaded="onPdfALoaded"
              />
              <div v-else-if="previewKindA === 'html' || previewKindA === 'textdiff'" class="html-preview-scroll" v-html="htmlPreviewA" />
              <el-empty v-else description="暂无文档预览" />
            </div>
          </div>
          <div class="pdf-preview-divider">
            <div class="divider-actions">
              <el-button type="primary" size="small" class="fs-side-btn" @click="togglePreviewFullscreen">
                {{ previewFullscreen ? '退出' : '全屏' }}
              </el-button>
              <el-tooltip v-if="isPdfPreviewKind(previewKindA) && isPdfPreviewKind(previewKindB)" content="按相同章节同步翻页" placement="top">
                <el-switch
                  v-model="syncScroll"
                  size="small"
                  active-text="同步"
                  inactive-text="独立"
                />
              </el-tooltip>
              <el-tooltip v-if="canHighlightPreview" content="标出文本增删改、图片和格式差异" placement="top">
                <el-switch
                  v-model="highlightDiff"
                  size="small"
                  active-text="高亮"
                  inactive-text="原文"
                />
              </el-tooltip>
              <div v-if="alignLabel" class="align-label" :title="alignLabel">{{ alignLabel }}</div>
              <div v-if="highlightDiff && canHighlightPreview" class="hl-legend">
                <span class="hl-del">删</span>
                <span class="hl-ins">增</span>
                <span class="hl-chg">改</span>
                <span v-if="isPdfPreviewKind(previewKindA) && isPdfPreviewKind(previewKindB)" class="hl-img">图</span>
                <span v-if="isPdfPreviewKind(previewKindA) && isPdfPreviewKind(previewKindB)" class="hl-fmt">格式</span>
              </div>
            </div>
          </div>
          <div class="pdf-preview-pane">
            <div class="pane-header pane-b">
              <span>待比文档：{{ previewNameB || compareFiles[activePdfSide]?.name || '待比文档' }}</span>
            </div>
            <div class="pane-content">
              <PageImagePreview
                v-if="previewKindB === 'pdf-pages' && previewTaskId"
                ref="pdfPreviewBRef"
                :task-id="previewTaskId"
                side="b"
                :file-name="previewNameB || compareFiles[activePdfSide]?.name || 'document_B.pdf'"
                :total-pages="previewPagesB"
                :highlight="highlightDiff"
                :initial-page="mapPeerPage('a', 1) || 1"
                @page-change="onPageBChange"
                @loaded="onPdfBLoaded"
              />
              <PdfPreview
                v-else-if="previewKindB === 'pdf' && pdfUrlB"
                ref="pdfPreviewBRef"
                :pdf-url="pdfUrlB"
                :file-name="previewNameB || compareFiles[activePdfSide]?.name || 'document_B.pdf'"
                @page-change="onPageBChange"
                @loaded="onPdfBLoaded"
              />
              <div v-else-if="previewKindB === 'html' || previewKindB === 'textdiff'" class="html-preview-scroll" v-html="htmlPreviewB" />
              <el-empty v-else description="暂无文档预览" />
            </div>
          </div>
        </div>
      </el-dialog>
    </div>

    <div v-if="currentView === 'tasks'">
      <h2 class="page-title">历史任务</h2>
      <div class="panel">
        <el-empty v-if="history.length === 0" description="暂无历史任务，请先进行文档对比或参数对比">
          <el-button type="primary" @click="currentView = 'upload'; $router.push('/compare')">去对比</el-button>
        </el-empty>
        <el-table v-else :data="history" border style="width: 100%">
          <el-table-column prop="id" label="任务ID" width="100" />
          <el-table-column label="类型" width="100">
            <template #default="scope">
              <el-tag :type="scope.row.task_type === 'param' ? 'success' : 'primary'" size="small">
                {{ scope.row.task_type === 'param' ? '参数对比' : '文档对比' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="file_a_name" label="文档A" />
          <el-table-column prop="file_b_name" label="文档B" />
          <el-table-column prop="similarity" label="相似度" width="120">
            <template #default="scope">
              <span :class="getSimilarityClass(scope.row.similarity)">{{ (scope.row.similarity * 100).toFixed(1) }}%</span>
            </template>
          </el-table-column>
          <el-table-column prop="verdict" label="判定" width="220">
            <template #default="scope">
              <el-tag :type="scope.row.verdict?.includes('通过') || scope.row.verdict?.includes('一致') ? 'success' : (scope.row.verdict?.includes('强制') || scope.row.verdict?.includes('差异较大') ? 'danger' : 'warning')" size="small">{{ scope.row.verdict }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="total_diffs" label="差异数" width="100" />
          <el-table-column prop="created_at" label="创建时间" width="180">
            <template #default="scope">
              {{ formatTime(scope.row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="280">
            <template #default="scope">
              <el-button size="small" @click="viewTask(scope.row.id)">查看</el-button>
              <el-button v-if="scope.row.task_type !== 'param'" size="small" @click="openTaskPdfPreview(scope.row.id)">文档预览</el-button>
              <el-button v-if="scope.row.task_type !== 'param'" size="small" @click="exportTaskReport(scope.row.id)">导出报告</el-button>
              <el-button size="small" type="danger" @click="deleteTask(scope.row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="selectedTask" class="result-panel" style="margin-top: 20px;">
        <div class="panel-header">
          <span>任务详情 - {{ selectedTask.id }} ({{ selectedTask.task_type === 'param' ? '参数对比' : '文档对比' }})</span>
          <div class="panel-actions">
            <el-button v-if="selectedTask.task_type !== 'param'" size="small" type="primary" @click="previewTaskReport(selectedTask.id)">预览报告</el-button>
            <el-button v-if="selectedTask.task_type !== 'param'" size="small" @click="exportTaskReport(selectedTask.id)">导出报告</el-button>
            <el-button size="small" @click="selectedTask = null">关闭</el-button>
          </div>
        </div>

        <div v-if="showPreview" class="panel" style="background: #fafafa; margin-top: 12px;">
          <div class="panel-header">
            <span>报告预览 - 任务 {{ selectedTask.id }}</span>
            <el-button size="small" @click="showPreview = false">关闭预览</el-button>
          </div>
          <div class="report-preview-content" style="max-height: 800px; overflow-y: auto; background: #fff; padding: 16px; border-radius: 6px;" v-html="reportContent"></div>
        </div>

        <div v-if="selectedTask.task_type === 'param' && paramTaskResults.length > 0" style="margin-top: 16px;">
          <div class="param-stats-row" style="display:flex; gap:16px; margin-bottom:16px;">
            <el-statistic title="总参数" :value="paramStats.total" />
            <el-statistic title="一致" :value="paramStats.match" />
            <el-statistic title="不一致" :value="paramStats.diff" />
            <el-statistic title="仅基准有" :value="paramStats.onlyA" />
            <el-statistic title="仅待比有" :value="paramStats.onlyB" />
          </div>
          <el-table :data="paramTaskResults" border stripe max-height="500" style="width:100%">
            <el-table-column prop="param" label="参数名" width="200" fixed />
            <el-table-column label="所在章节" min-width="160">
              <template #default="scope">
                {{ chapterLabel(scope.row) }}
              </template>
            </el-table-column>
            <el-table-column prop="value_a" label="基准文档值" min-width="180" />
            <el-table-column prop="value_b" label="待比文档值" min-width="180" />
            <el-table-column label="匹配" width="100">
              <template #default="scope">
                <el-tag :type="scope.row.match === '一致' ? 'success' : (scope.row.match === '不一致' ? 'danger' : 'info')" size="small">
                  {{ scope.row.match }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="source_a" label="来源A" width="120" />
            <el-table-column prop="source_b" label="来源B" width="120" />
          </el-table>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { compareAPI } from '@/api'
import { Upload, Search, View, FullScreen } from '@element-plus/icons-vue'
import PdfPreview from '@/components/PdfPreview.vue'
import PageImagePreview from '@/components/PageImagePreview.vue'
import TextDiffPreview from '@/components/TextDiffPreview.vue'

const route = useRoute()
const router = useRouter()
const files = ref([null, null])
const compareFiles = ref([])
const loading = ref(false)
const progress = ref(0)
const progressText = ref('')
const allResults = ref([])
const activeResultTab = ref(0)
const history = ref([])
const selectedTask = ref(null)
const showPreview = ref(false)
const activePreviewTask = ref(null)
const reportContent = ref('')
const showPdfPreviewDialog = ref(false)
const previewFullscreen = ref(false)
const pdfUrlA = ref('')
const pdfUrlB = ref('')
const pdfPreviewARef = ref(null)
const pdfPreviewBRef = ref(null)
const previewKindA = ref('')
const previewKindB = ref('')
const htmlPreviewA = ref('')
const htmlPreviewB = ref('')
const previewNameA = ref('')
const previewNameB = ref('')
const previewTaskId = ref(0)
const previewPagesA = ref(0)
const previewPagesB = ref(0)
const syncScroll = ref(true)
const highlightDiff = ref(true)
const previewAlignPairs = ref([])
const previewPageA = ref(1)
const previewPageB = ref(1)
const textDiffRows = ref([])
const textDiffSections = ref([])
const textDiffCount = ref(0)
const _pageChangingFrom = ref('')
const activePdfSide = ref(1)
const paramTaskResults = ref([])
const paramStats = ref({ total: 0, match: 0, diff: 0, onlyA: 0, onlyB: 0 })

const currentView = computed(() => {
  if (route.path === '/compare/tasks') return 'tasks'
  return 'upload'
})

function isPdfPreviewKind(kind) {
  return kind === 'pdf' || kind === 'pdf-pages'
}

const canHighlightPreview = computed(() => {
  const pdfPair = isPdfPreviewKind(previewKindA.value) && isPdfPreviewKind(previewKindB.value)
  const htmlPair = previewKindA.value === 'html' && previewKindB.value === 'html'
  return pdfPair || htmlPair
})

const isTextDiffPreview = computed(() => {
  return previewKindA.value === 'textdiff' && previewKindB.value === 'textdiff'
})

function togglePreviewFullscreen() {
  previewFullscreen.value = !previewFullscreen.value
  nextTick(() => {
    const overlay = document.querySelector('.pdf-preview-overlay')
    if (previewFullscreen.value) {
      const target = overlay || document.querySelector('.pdf-preview-dialog')
      if (target && target.requestFullscreen && !document.fullscreenElement) {
        target.requestFullscreen().catch(() => {})
      }
    } else if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {})
    }
  })
}

function onPreviewDialogClosed() {
  previewFullscreen.value = false
  if (document.fullscreenElement) {
    document.exitFullscreen().catch(() => {})
  }
}

function onNativeFullscreenChange() {
  if (!document.fullscreenElement) {
    previewFullscreen.value = false
  }
}

function mapPeerPage(fromSide, page) {
  const pairs = previewAlignPairs.value || []
  const sa = fromSide === 'b' ? 'b' : 'a'
  const sb = fromSide === 'b' ? 'a' : 'b'
  const containing = pairs.filter((item) => {
    const start = item[`page_start_${sa}`] || 0
    const end = item[`page_end_${sa}`] || 0
    const peerStart = item[`page_start_${sb}`] || 0
    return start && end && peerStart && page >= start && page <= end
  })
  if (!containing.length) {
    const firstA = Math.min(...pairs.map((p) => p.page_start_a).filter(Boolean))
    const firstB = Math.min(...pairs.map((p) => p.page_start_b).filter(Boolean))
    if (!Number.isFinite(firstA) || !Number.isFinite(firstB)) return 0
    if (fromSide !== 'b' && page < firstA && firstA > 1) {
      const spanA = firstA - 1
      const spanB = Math.max(1, firstB - 1)
      return Math.min(spanB, Math.max(1, Math.round(((page - 1) * spanB) / spanA) + 1))
    }
    if (fromSide === 'b' && page < firstB && firstB > 1) {
      const spanB = firstB - 1
      const spanA = Math.max(1, firstA - 1)
      return Math.min(spanA, Math.max(1, Math.round(((page - 1) * spanA) / spanB) + 1))
    }
    return 0
  }
  containing.sort((x, y) => {
    const rx = (x[`page_end_${sa}`] || 0) - (x[`page_start_${sa}`] || 0)
    const ry = (y[`page_end_${sa}`] || 0) - (y[`page_start_${sa}`] || 0)
    return rx - ry || (y.level || 0) - (x.level || 0)
  })
  const item = containing[0]
  const offset = page - (item[`page_start_${sa}`] || page)
  const start = item[`page_start_${sb}`] || 0
  const end = item[`page_end_${sb}`] || start
  return Math.min(end, Math.max(start, start + offset))
}

const alignLabel = computed(() => {
  const pairs = previewAlignPairs.value || []
  const page = previewPageA.value
  const containing = pairs.filter((item) => {
    const start = item.page_start_a || 0
    const end = item.page_end_a || 0
    return start && end && page >= start && page <= end
  })
  if (!containing.length) return ''
  containing.sort((x, y) => {
    const rx = (x.page_end_a || 0) - (x.page_start_a || 0)
    const ry = (y.page_end_a || 0) - (y.page_start_a || 0)
    return rx - ry || (y.level || 0) - (x.level || 0)
  })
  return containing[0].heading_a || containing[0].heading_b || ''
})

onMounted(async () => {
  console.log('[Compare] Component mounted, currentView:', currentView.value, 'route:', route.path)
  document.addEventListener('fullscreenchange', onNativeFullscreenChange)
  if (currentView.value === 'tasks') {
    await loadHistory()
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', onNativeFullscreenChange)
})

watch(() => route.path, async (newPath) => {
  if (newPath === '/compare/tasks') {
    await loadHistory()
  }
})

async function loadHistory() {
  console.log('[History] loadHistory called, current route:', route.path)
  try {
    const resp = await compareAPI.list()
    console.log('[History] API response:', resp)
    console.log('[History] resp.data:', resp.data)
    if (resp.data && Array.isArray(resp.data)) {
      history.value = resp.data
      console.log('[History] Loaded', history.value.length, 'tasks')
    } else {
      console.warn('[History] Unexpected response format:', resp.data)
      history.value = []
    }
  } catch (e) {
    console.error('[History] Load failed:', e)
    history.value = []
  }
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  if (typeof timestamp === 'object') return timestamp.toLocaleString()
  if (typeof timestamp === 'string') {
    return new Date(timestamp).toLocaleString()
  }
  return new Date(timestamp * 1000).toLocaleString()
}

function getSimilarityClass(similarity) {
  if (similarity >= 0.8) return 'sim-high'
  if (similarity >= 0.6) return 'sim-medium'
  return 'sim-low'
}

function getVerdictTagType(verdict) {
  if (!verdict) return 'info'
  if (verdict.includes('通过') || verdict.includes('80')) return 'success'
  if (verdict.includes('强制') || verdict.includes('60')) return 'danger'
  return 'warning'
}

function pickFile(idx, ev) {
  const f = ev.target.files && ev.target.files[0]
  if (f) files.value[idx] = f
  ev.target.value = ''
}

function clearFiles() {
  files.value = [null, null]
  allResults.value = []
  compareFiles.value = []
  activeResultTab.value = 0
  showPreview.value = false
  activePreviewTask.value = null
}

function updateProgress(pct, text) {
  progress.value = pct
  progressText.value = text
}

async function doCompare() {
  const validFiles = files.value.filter(f => f)
  if (validFiles.length < 2) {
    ElMessage.info('请至少上传2个文档后再进行对比')
    return
  }
  compareFiles.value = [...validFiles]
  loading.value = true
  progress.value = 0
  progressText.value = ''

  try {
    updateProgress(15, '正在上传文件')

    const respPromise = compareAPI.create(validFiles)
    updateProgress(55, '正在对比分析')

    const resp = await respPromise
    const data = resp.data || {}

    updateProgress(90, '正在生成结果')

    allResults.value = (data.results || []).map(r => ({
      ...r,
      task_id: r.task_id || r.comparison_id || 0,
    }))

    updateProgress(100, '对比完成')

    setTimeout(() => { progress.value = 0 }, 600)
    ElMessage.success(`对比完成，共 ${allResults.value.length} 组结果`)
  } catch (e) {
    progress.value = 0
    ElMessage.error('对比失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function previewPairReport(taskId) {
  if (!taskId) return
  try {
    const resp = await compareAPI.getReport(taskId, 'html')
    reportContent.value = resp.data?.content || ''
    if (!reportContent.value.trim()) {
      ElMessage.warning('报告内容为空')
      return
    }
    showPreview.value = true
    activePreviewTask.value = taskId
    ElMessage.success('报告已加载')
  } catch (e) {
    console.error('Preview error:', e)
    ElMessage.error('预览失败：' + (e.message || '未知错误'))
  }
}

async function exportPairReport(taskId) {
  if (!taskId) return
  try {
    const resp = await compareAPI.getReport(taskId, 'html')
    const content = resp.data?.content || ''
    downloadFile(content, `compare_report_${taskId}_${Date.now()}.html`, 'text/html')
    ElMessage.success('对比报告已导出')
  } catch (e) {
    console.error('Export error:', e)
    ElMessage.error('导出失败：' + (e.message || '未知错误'))
  }
}

function resetPreviewState() {
  pdfUrlA.value = ''
  pdfUrlB.value = ''
  previewKindA.value = ''
  previewKindB.value = ''
  htmlPreviewA.value = ''
  htmlPreviewB.value = ''
  previewNameA.value = ''
  previewNameB.value = ''
  previewTaskId.value = 0
  previewPagesA.value = 0
  previewPagesB.value = 0
  previewAlignPairs.value = []
  previewPageA.value = 1
  previewPageB.value = 1
  textDiffRows.value = []
  textDiffSections.value = []
  textDiffCount.value = 0
}

async function loadSidePreview(taskId, side) {
  try {
    const resp = await compareAPI.getPreviewContent(taskId, side, { highlight: highlightDiff.value })
    const data = resp.data || {}
    const name = data.file_name || ''
    let kind = ''
    if (data.type === 'pdf-pages') kind = 'pdf-pages'
    else if (data.type === 'pdf') kind = 'pdf'
    else if (data.type === 'textdiff') kind = 'textdiff'
    else if (data.content) kind = 'html'
    if (side === 'a') {
      previewKindA.value = kind
      previewNameA.value = name
      previewPagesA.value = data.total_pages || 0
      if (kind === 'pdf-pages') {
        pdfUrlA.value = ''
        htmlPreviewA.value = ''
      } else if (kind === 'pdf') {
        pdfUrlA.value = compareAPI.getPreviewFileUrl(taskId, 'a')
        htmlPreviewA.value = ''
      } else {
        pdfUrlA.value = ''
        htmlPreviewA.value = data.content || ''
      }
    } else {
      previewKindB.value = kind
      previewNameB.value = name
      previewPagesB.value = data.total_pages || 0
      if (kind === 'pdf-pages') {
        pdfUrlB.value = ''
        htmlPreviewB.value = ''
      } else if (kind === 'pdf') {
        pdfUrlB.value = compareAPI.getPreviewFileUrl(taskId, 'b')
        htmlPreviewB.value = ''
      } else {
        pdfUrlB.value = ''
        htmlPreviewB.value = data.content || ''
      }
    }
  } catch (e) {
    if (side === 'a') {
      previewKindA.value = ''
      pdfUrlA.value = ''
      htmlPreviewA.value = ''
    } else {
      previewKindB.value = ''
      pdfUrlB.value = ''
      htmlPreviewB.value = ''
    }
  }
}

async function loadPairPreview(taskId) {
  resetPreviewState()
  previewTaskId.value = taskId
  try {
    const resp = await compareAPI.getPreviewAlign(taskId)
    previewAlignPairs.value = resp.data?.pairs || []
  } catch (e) {
    previewAlignPairs.value = []
  }
  try {
    const infoResp = await compareAPI.getPreviewInfo(taskId)
    const info = infoResp.data || {}
    previewNameA.value = info.file_a_name || previewNameA.value
    previewNameB.value = info.file_b_name || previewNameB.value
    if (info.type_a === 'textdiff' && info.type_b === 'textdiff') {
      previewKindA.value = 'textdiff'
      previewKindB.value = 'textdiff'
      await loadTextDiff(taskId)
      return
    }
  } catch (e) {
    /* fall through to per-side preview */
  }
  await Promise.all([loadSidePreview(taskId, 'a'), loadSidePreview(taskId, 'b')])
}

async function loadTextDiff(taskId) {
  try {
    const resp = await compareAPI.getPreviewTextDiff(taskId)
    const data = resp.data || {}
    textDiffRows.value = data.rows || []
    textDiffSections.value = data.diff_sections || []
    textDiffCount.value = data.diff_count || 0
    if (data.file_a_name) previewNameA.value = data.file_a_name
    if (data.file_b_name) previewNameB.value = data.file_b_name
  } catch (e) {
    textDiffRows.value = []
    textDiffSections.value = []
    textDiffCount.value = 0
    ElMessage.error('文本对比预览失败：' + (e.message || '未知错误'))
  }
}

watch(highlightDiff, () => {
  if (!showPdfPreviewDialog.value || !previewTaskId.value) return
  if (previewKindA.value !== 'html' && previewKindB.value !== 'html') return
  Promise.all([
    loadSidePreview(previewTaskId.value, 'a'),
    loadSidePreview(previewTaskId.value, 'b'),
  ])
})

function openPairPdfPreview(taskId) {
  if (!taskId) {
    ElMessage.warning('无法获取任务ID')
    return
  }
  const idx = allResults.value.findIndex(r => r.task_id === taskId)
  activePdfSide.value = idx >= 0 ? (idx + 1) : 1
  showPdfPreviewDialog.value = true
  loadPairPreview(taskId)
}

async function viewTask(taskId) {
  try {
    const resp = await compareAPI.get(taskId)
    const data = resp.data || {}

    selectedTask.value = {
      id: taskId,
      task_type: data.task_type || 'doc',
      similarity: data.similarity || 0,
      verdict: data.verdict || '',
      file_a_name: data.file_a_name || '',
      file_b_name: data.file_b_name || '',
    }

    if (data.task_type === 'param') {
      const matched = Array.isArray(data.matched_pairs) ? data.matched_pairs : []
      const onlyA = Array.isArray(data.only_a) ? data.only_a : []
      const onlyB = Array.isArray(data.only_b) ? data.only_b : []
      paramTaskResults.value = [
        ...matched,
        ...onlyA.map(r => ({ ...r, match: '仅A有', value_b: '-' })),
        ...onlyB.map(r => ({ ...r, match: '仅B有', value_a: '-' })),
      ]
      const stats = data.diff_stats || data.stats || {}
      paramStats.value = {
        total: (stats.params_a || 0) + (stats.params_b || 0),
        match: stats.match || 0,
        diff: stats.diff || 0,
        onlyA: stats.only_a || onlyA.length,
        onlyB: stats.only_b || onlyB.length,
      }
    } else {
      paramTaskResults.value = []
    }
  } catch (e) {
    ElMessage.error('查看失败：' + (e.message || '未知错误'))
  }
}

async function exportTaskReport(taskId) {
  try {
    const resp = await compareAPI.getReport(taskId, 'html')
    const content = resp.data?.content || ''
    downloadFile(content, `compare_report_${taskId}.html`, 'text/html')
    ElMessage.success('对比报告已导出')
  } catch (e) {
    ElMessage.error('导出失败：' + (e.message || '未知错误'))
  }
}

async function previewTaskReport(taskId) {
  try {
    const resp = await compareAPI.getReport(taskId, 'html')
    reportContent.value = resp.data?.content || ''

    if (!reportContent.value.trim()) {
      ElMessage.warning('报告内容为空')
      return
    }

    showPreview.value = true
    ElMessage.success('报告已加载')
  } catch (e) {
    console.error('Preview error:', e)
    ElMessage.error('预览失败：' + (e.message || '未知错误'))
  }
}

async function deleteTask(taskId) {
  try {
    await compareAPI.delete(taskId)
    await loadHistory()
    if (selectedTask.value?.id === taskId) {
      selectedTask.value = null
    }
    ElMessage.success('任务已删除')
  } catch (e) {
    ElMessage.error('删除失败：' + (e.message || '未知错误'))
  }
}

function downloadFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

async function saveConfig() {
  try {
    await compareAPI.updateConfig(config.value)
    ElMessage.success('配置已保存')
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

function openTaskPdfPreview(taskId) {
  if (!taskId) {
    ElMessage.warning('无法获取任务ID')
    return
  }
  activePdfSide.value = 1
  showPdfPreviewDialog.value = true
  loadPairPreview(taskId)
}

function onPageAChange(page) {
  previewPageA.value = page
  if (!syncScroll.value || _pageChangingFrom.value === 'b') return
  _pageChangingFrom.value = 'a'
  const peer = mapPeerPage('a', page)
  if (peer && pdfPreviewBRef.value?.goToPage) {
    pdfPreviewBRef.value.goToPage(peer, true)
  }
  _pageChangingFrom.value = ''
}

function onPageBChange(page) {
  previewPageB.value = page
  if (!syncScroll.value || _pageChangingFrom.value === 'a') return
  _pageChangingFrom.value = 'b'
  const peer = mapPeerPage('b', page)
  if (peer && pdfPreviewARef.value?.goToPage) {
    pdfPreviewARef.value.goToPage(peer, true)
  }
  _pageChangingFrom.value = ''
}

function onPdfALoaded(info) {
  console.log('PDF A loaded, total pages:', info.totalPages)
}

function onPdfBLoaded(info) {
  console.log('PDF B loaded, total pages:', info.totalPages)
}
</script>

<style>
.compare-container { padding: 0; }

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 20px;
}

.panel {
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.result-panel {
  background: #fff;
  border-radius: 10px;
  padding: 24px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.result-tabs {
  margin-top: 16px;
}

.pair-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding: 12px 16px;
  background: #f8fafc;
  border-radius: 6px;
}

.pair-label {
  font-size: 15px;
  color: #1f2937;
}

.pair-label strong {
  color: #3b82f6;
  margin: 0 8px;
}

.pair-tags {
  display: flex;
  gap: 8px;
}

.pair-actions {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
  font-weight: 600;
  color: #1f2937;
}

.panel-actions { display: flex; align-items: center; gap: 10px; }

.upload-grid {
  display: flex;
  justify-content: center;
  align-items: stretch;
  gap: 16px;
}

.upload-slot,
.vs-col {
  width: 240px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.vs-col {
  width: 64px;
}

.slot-label {
  font-weight: 600;
  color: #374151;
  text-align: center;
  width: 240px;
  line-height: 22px;
  margin-bottom: 10px;
}

.slot-hint {
  margin-top: 10px;
  font-weight: 400;
  font-size: 12px;
  color: #6b7280;
  text-align: center;
  width: 240px;
  line-height: 18px;
}

.vs-spacer-label,
.vs-spacer-hint {
  visibility: hidden;
}

.upload-box {
  position: relative;
  border: 2px dashed #d1d5db;
  border-radius: 8px;
  padding: 30px 16px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s;
  width: 240px;
  min-height: 160px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.upload-box input[type="file"] {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.upload-box:hover { border-color: #3b82f6; background: #eff6ff; }

.upload-box.filled { border-color: #3b82f6; background: #f0f9ff; }

.upload-hint { color: #6b7280; font-size: 14px; }

.upload-name { color: #3b82f6; font-weight: 600; font-size: 14px; word-break: break-all; }

.vs-badge {
  flex: 1;
  font-size: 20px;
  font-weight: 700;
  color: #9ca3af;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0;
}

.action-row {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 24px;
}

.progress-panel {
  max-width: 320px;
  margin: 16px auto 0;
  padding: 0;
}

.progress-text {
  text-align: center;
  margin-top: 6px;
  font-size: 12px;
  color: #6b7280;
}

.cards { display:flex;gap:16px;flex-wrap:wrap;margin-bottom:28px; }
.card { background:#fff;border-radius:10px;padding:18px 22px;box-shadow:0 1px 3px rgba(0,0,0,.08);min-width:140px; }
.card.primary { background:linear-gradient(135deg,#1976d2,#2c3e50);color:#fff;min-width:180px; }
.card.primary .lbl { color:rgba(255,255,255,.85); }
.card.primary .num { font-size:32px; }
.card .num { font-size:24px;font-weight:700; }
.card .lbl { color:#777;font-size:12px;margin-top:4px; }

.explain { background:#fffbea;border-left:4px solid #f9a825;padding:14px 18px;border-radius:6px;font-size:13px;line-height:1.8;color:#444;margin-bottom:22px; }

.file-info { background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.08);padding:16px 18px;margin:0 0 22px; }
.file-info h3 { margin:0 0 12px;font-size:16px;color:#2c3e50; }
.file-info-grid { display:grid;grid-template-columns:120px 1fr;gap:8px 12px;font-size:13px;line-height:1.7; }
.file-info-grid .label { color:#666;font-weight:600; }
.file-info-grid .value { word-break:break-word;overflow-wrap:anywhere; }

.report-preview-content table { width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08);table-layout:fixed; }
.report-preview-content th,.report-preview-content td { padding:10px 12px;text-align:left;font-size:13px;border-bottom:1px solid #eee;vertical-align:top;word-break:break-word;overflow-wrap:anywhere; }
.report-preview-content th { background:#2c3e50;color:#fff;font-weight:600;white-space:normal;font-size:12px; }
.report-preview-content tr:hover { background:#f9fafb; }
.report-preview-content code { background:#eef1f4;padding:1px 6px;border-radius:4px;font-size:12px; }

.report-preview-content .tag { background:#e3f2fd;color:#1565c0;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:500; }
.report-preview-content .tag.ok { background:#e8f5e9;color:#2e7d32; }
.report-preview-content .tag.warn { background:#fff3e0;color:#e65100; }
.report-preview-content .tag.danger { background:#ffebee;color:#c62828; }
.report-preview-content .tag.only-a { background:#fff4f4;color:#c62828; }
.report-preview-content .tag.only-b { background:#f4faf4;color:#2e7d32; }

.report-preview-content .bar { position:relative;background:#eee;border-radius:10px;height:18px;width:100%;min-width:80px;overflow:hidden; }
.report-preview-content .bar .fill { height:100%;border-radius:10px; }
.report-preview-content .bar span { position:absolute;left:0;right:0;top:0;line-height:18px;text-align:center;font-size:11px;color:#000;font-weight:600; }

.report-preview-content h2 { margin-top:32px;font-size:18px;border-left:4px solid #1976d2;padding-left:10px;color:#2c3e50;font-weight:600; }

.report-preview-content .row-main { cursor:pointer; }
.report-preview-content .row-main:hover { background:#f0f4f9; }
.report-preview-content .row-main .diff-cell { color:#c62828;font-weight:600; }
.report-preview-content .row-diff { display:none; }
.report-preview-content .row-diff.open { display:table-row; }
.report-preview-content .row-diff > td { background:#fafbfc;padding:0; }

.report-preview-content .diffs { padding:12px 16px; }
.report-preview-content .diff-empty { padding:14px 16px;color:#2e7d32;font-size:13px;background:#eaf6ec;border-radius:6px; }
.report-preview-content .diff-row { display:flex;align-items:flex-start;gap:10px;padding:8px 10px;margin:6px 0;border-radius:6px;font-size:13px;line-height:1.6; }
.report-preview-content .diff-row.changed { background:#fff8e1;border-left:3px solid #f9a825; }
.report-preview-content .diff-row .text { flex:1;word-break:break-word; }
.report-preview-content .diff-row .side-a,.report-preview-content .diff-row .side-b { padding:4px 0; }
.report-preview-content .diff-row .side-a::before { content:"A: ";color:#c62828;font-weight:600; }
.report-preview-content .diff-row .side-b::before { content:"B: ";color:#2e7d32;font-weight:600; }

.report-preview-content .tag-c { font-size:11px;padding:2px 8px;border-radius:10px;white-space:nowrap;font-weight:600;background:#f9a825;color:#fff;min-width:50px;text-align:center; }

.report-preview-content .del { background:#ffd6d6;text-decoration:line-through;color:#a31515;padding:0 2px;border-radius:2px; }
.report-preview-content .ins { background:#d6f5d6;color:#1a5e1a;padding:0 2px;border-radius:2px; }

.report-preview-content table.summary td { vertical-align:top;font-size:13px;line-height:1.55; }
.report-preview-content table.summary td:nth-child(1) { width:60px;text-align:center; }
.report-preview-content table.summary td:nth-child(2) { width:120px;color:#666; }
.report-preview-content table.summary td:nth-child(3) { font-weight:600;max-width:300px; }
.report-preview-content table.summary td:nth-child(4) { width:80px; }
.report-preview-content table.summary td:nth-child(5) { width:120px; }
.report-preview-content table.summary td:nth-child(6) { width:80px;text-align:center;color:#888; }
.report-preview-content table.summary td:nth-child(7) { width:100px;text-align:center;font-weight:600; }
.report-preview-content table.summary td:nth-child(8) { width:80px;text-align:center;font-weight:600;color:#c62828; }

.report-preview-content tr.ok-row td:nth-child(7) { color:#2e7d32; }
.report-preview-content tr.high-row td:nth-child(7) { color:#558b2f; }
.report-preview-content tr.mid-row td:nth-child(7) { color:#ef6c00; }
.report-preview-content tr.low-row td:nth-child(7) { color:#c62828; }
.report-preview-content tr.only-a-row { background:#fff4f4; }
.report-preview-content tr.only-b-row { background:#f4faf4; }
.report-preview-content tr.only-a-row td:nth-child(7), .report-preview-content tr.only-b-row td:nth-child(7) { color:#666; }

.report-preview-content .small { color:#888;font-size:12px; }

.report-preview-content .diff-list { max-height: 600px; overflow-y: auto; }

.report-preview-content .diff-item {
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  border-left: 4px solid;
}

.report-preview-content .diff-item.add, .report-preview-content .diff-item.only_b { background: #f0fdf4; border-left-color: #22c55e; }
.report-preview-content .diff-item.delete, .report-preview-content .diff-item.only_a { background: #fef2f2; border-left-color: #ef4444; }
.report-preview-content .diff-item.modify { background: #fffbeb; border-left-color: #f59e0b; }

.report-preview-content .diff-item.severity-critical { border-left-width: 6px; }
.report-preview-content .diff-item.severity-high { border-left-width: 5px; }

.report-preview-content .diff-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.report-preview-content .diff-index {
  background: #e5e7eb;
  color: #6b7280;
  font-size: 12px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

.report-preview-content .diff-type { font-weight: 600; }

.report-preview-content .severity-tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
}

.report-preview-content .severity-tag.critical { background: #fee2e2; color: #dc2626; }
.report-preview-content .severity-tag.high { background: #fef3c7; color: #d97706; }
.report-preview-content .severity-tag.medium { background: #dbeafe; color: #2563eb; }
.report-preview-content .severity-tag.low { background: #dcfce7; color: #16a34a; }

.report-preview-content .similarity-tag {
  font-size: 12px;
  background: #f3f4f6;
  color: #374151;
  padding: 2px 8px;
  border-radius: 4px;
  margin-left: auto;
}

.report-preview-content .diff-content { margin-top: 8px; }

.report-preview-content .diff-text {
  padding: 8px 12px;
  border-radius: 4px;
  margin-bottom: 8px;
}

.report-preview-content .diff-text:last-child { margin-bottom: 0; }

.report-preview-content .diff-text-a { background: #f3f4f6; }
.report-preview-content .diff-text-b { background: #e0f2fe; }

.report-preview-content .text-label {
  font-weight: 600;
  color: #6b7280;
  margin-right: 8px;
}

.report-preview-content .empty-state {
  text-align: center;
  padding: 40px;
  color: #9ca3af;
}

.report-preview-content .similarity-high { color: #86efac; }
.report-preview-content .similarity-medium { color: #fcd34d; }
.report-preview-content .similarity-low { color: #fca5a5; }

.pdf-preview-dialog :deep(.el-dialog__body) {
  padding: 0;
  height: calc(98vh - 54px);
  overflow: hidden;
}

.pdf-preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: calc(100% - 36px);
}

.pdf-preview-title {
  font-size: 16px;
  font-weight: 600;
}

.pdf-preview-wrapper {
  display: flex;
  height: 100%;
  min-height: 0;
}

.fs-side-btn {
  width: 42px;
  padding: 8px 0;
}

.pdf-preview-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.pane-header {
  padding: 10px 16px;
  font-weight: 600;
  font-size: 14px;
  border-bottom: 1px solid #e4e7ed;
  flex-shrink: 0;
}

.pane-a {
  background: #fef2f2;
  color: #dc2626;
  border-right: 1px solid #fecaca;
}

.pane-b {
  background: #f0fdf4;
  color: #16a34a;
  border-left: 1px solid #bbf7d0;
}

.pane-content {
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

.html-preview-scroll {
  height: 100%;
  overflow: auto;
  background: #fff;
  padding: 16px 20px;
  font-size: 14px;
  line-height: 1.7;
  color: #1f2937;
}

.html-preview-scroll pre {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  margin: 0;
}

.html-preview-scroll img {
  max-width: 100%;
}

.html-preview-scroll table {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0 16px;
}

.html-preview-scroll td,
.html-preview-scroll th {
  border: 1px solid #e5e7eb;
  padding: 6px 8px;
  vertical-align: top;
}

.html-preview-scroll ul {
  padding-left: 20px;
}

.html-preview-scroll h1,
.html-preview-scroll h2,
.html-preview-scroll h3,
.html-preview-scroll h4,
.html-preview-scroll h5,
.html-preview-scroll h6 {
  margin: 14px 0 8px;
  font-weight: 700;
  line-height: 1.3;
  color: #111827;
}

.html-preview-scroll h1 { font-size: 22px; }
.html-preview-scroll h2 { font-size: 18px; }
.html-preview-scroll h3 { font-size: 16px; }
.html-preview-scroll h4 { font-size: 15px; }

.html-preview-scroll pre.md-code {
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px 12px;
  margin: 8px 0 12px;
  overflow-x: auto;
  white-space: pre-wrap;
}

.html-preview-scroll pre.md-code code {
  background: transparent;
  padding: 0;
}

.html-preview-scroll code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  background: #f3f4f6;
  padding: 1px 4px;
  border-radius: 3px;
}

.html-preview-scroll blockquote {
  margin: 8px 0 12px;
  padding: 6px 12px;
  border-left: 4px solid #93c5fd;
  background: #eff6ff;
  color: #1e3a8a;
}

.html-preview-scroll ul.md-loose-list,
.html-preview-scroll ol.md-loose-list {
  margin: 0;
  padding-left: 22px;
}

.html-preview-scroll .doc-preview-md p {
  margin: 0 0 10px;
}

.pdf-preview-divider {
  width: 50px;
  background: #f3f4f6;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-left: 1px solid #e5e7eb;
  border-right: 1px solid #e5e7eb;
}

.divider-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
}

.hl-legend {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 11px;
  color: #4b5563;
}

.align-label {
  max-width: 72px;
  font-size: 11px;
  line-height: 1.3;
  color: #1d4ed8;
  text-align: center;
  word-break: break-all;
}

.hl-del,
.hl-ins,
.hl-chg {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 600;
}

.hl-del { background: rgba(255, 76, 76, 0.35); }
.hl-ins { background: rgba(46, 184, 92, 0.35); }
.hl-chg { background: rgba(255, 196, 0, 0.45); }

.hl-img,
.hl-fmt {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 600;
}

.hl-img { background: rgba(59, 130, 246, 0.35); }
.hl-fmt { background: rgba(168, 85, 247, 0.35); }

.sim-high { color: #10b981; font-weight: 600; }
.sim-medium { color: #f59e0b; font-weight: 600; }
.sim-low { color: #ef4444; font-weight: 600; }
</style>

<style>
.pdf-preview-overlay {
  overflow: hidden !important;
}
.pdf-preview-overlay:fullscreen,
.pdf-preview-overlay:-webkit-full-screen {
  background: #fff;
}
.pdf-preview-dialog.el-dialog {
  display: flex !important;
  flex-direction: column;
  margin-bottom: 0;
}
.pdf-preview-dialog .pdf-preview-dialog-header,
.pdf-preview-dialog .el-dialog__header {
  flex: 0 0 auto !important;
  padding: 10px 16px 8px !important;
}
.pdf-preview-dialog .pdf-preview-dialog-body,
.pdf-preview-dialog .el-dialog__body {
  flex: 1 1 auto !important;
  min-height: 0 !important;
  padding: 0 !important;
  overflow: hidden !important;
  height: calc(98vh - 54px);
  display: flex !important;
  flex-direction: column !important;
}
.pdf-preview-dialog.is-fullscreen,
.pdf-preview-dialog.is-preview-fullscreen {
  width: 100% !important;
  max-width: 100% !important;
  height: 100vh !important;
  max-height: 100vh !important;
  margin: 0 !important;
  top: 0 !important;
  overflow: hidden !important;
}
.pdf-preview-dialog.is-fullscreen .pdf-preview-dialog-body,
.pdf-preview-dialog.is-fullscreen .el-dialog__body,
.pdf-preview-dialog.is-preview-fullscreen .pdf-preview-dialog-body,
.pdf-preview-dialog.is-preview-fullscreen .el-dialog__body {
  height: auto !important;
}
</style>

<style>
.html-preview-scroll .hl-del,
.html-preview-scroll td.hl-del {
  background: rgba(255, 76, 76, 0.28);
}
.html-preview-scroll .hl-ins,
.html-preview-scroll td.hl-ins {
  background: rgba(46, 184, 92, 0.28);
}
.html-preview-scroll .hl-chg,
.html-preview-scroll td.hl-chg {
  background: rgba(255, 196, 0, 0.35);
}
.html-preview-scroll .hl-block {
  border-radius: 4px;
  padding: 2px 4px;
}
</style>
