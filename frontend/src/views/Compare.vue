<template>
  <div class="compare-container">
    <div v-if="currentView === 'upload'">
      <h2 class="page-title">文档对比</h2>

      <div class="panel">
        <div class="panel-header">
          <span>上传两个文档进行对比</span>
          <div class="panel-actions">
            <el-tag size="small" type="info">支持 PDF / DOCX / MD / TXT / DITA / ZIP</el-tag>
          </div>
        </div>

        <div class="upload-grid">
          <div class="upload-slot">
            <div class="slot-label">文档A（原始版本）</div>
            <el-upload
              action="#"
              :auto-upload="false"
              :show-file-list="false"
              :before-upload="(f) => { fileA = f; return false }"
              :on-change="(f) => { fileA = f.raw || f }"
              accept=".pdf,.docx,.doc,.md,.txt,.dita,.xml,.zip"
            >
              <div class="upload-box" :class="{ filled: fileA }">
                <el-icon style="font-size: 36px; color: #3b82f6; margin-bottom: 8px;"><Upload /></el-icon>
                <div v-if="!fileA" class="upload-hint">点击上传文档A</div>
                <div v-else class="upload-name">{{ fileA.name }}</div>
              </div>
            </el-upload>
          </div>

          <div class="vs-badge">VS</div>

          <div class="upload-slot">
            <div class="slot-label">文档B（对比版本）</div>
            <el-upload
              action="#"
              :auto-upload="false"
              :show-file-list="false"
              :before-upload="(f) => { fileB = f; return false }"
              :on-change="(f) => { fileB = f.raw || f }"
              accept=".pdf,.docx,.doc,.md,.txt,.dita,.xml,.zip"
            >
              <div class="upload-box" :class="{ filled: fileB }">
                <el-icon style="font-size: 36px; color: #7c3aed; margin-bottom: 8px;"><Upload /></el-icon>
                <div v-if="!fileB" class="upload-hint">点击上传文档B</div>
                <div v-else class="upload-name">{{ fileB.name }}</div>
              </div>
            </el-upload>
          </div>
        </div>

        <div class="action-row">
          <el-button type="primary" size="large" :loading="loading" :disabled="!fileA || !fileB" @click="doCompare">
            <el-icon><Search /></el-icon> 开始对比
          </el-button>
          <el-button size="large" @click="clearFiles">清空</el-button>
        </div>

        <div v-if="progress > 0 && progress < 100" class="progress-panel">
          <el-progress :percentage="progress" :stroke-width="16" status="success" />
          <div class="progress-text">{{ progressText }}</div>
        </div>
      </div>

      <div v-if="result" class="result-panel">
        <div class="panel-header">
          <span>对比完成</span>
          <div class="panel-actions">
            <el-tag :type="verdictType" size="small">{{ result.verdict }}</el-tag>
            <el-tag type="info" size="small">差异数：{{ result.total_diffs || 0 }}</el-tag>
            <el-button size="small" type="primary" @click="previewReport">预览报告</el-button>
            <el-button size="small" @click="openPdfPreview">PDF页码预览</el-button>
            <el-button size="small" @click="exportCompare">导出报告</el-button>
          </div>
        </div>

        <div v-if="showPreview" class="panel" style="background: #fafafa; margin-top: 12px;">
          <div class="panel-header">
            <span>报告预览</span>
            <el-button size="small" @click="showPreview = false">关闭预览</el-button>
          </div>
          <div class="report-preview-content" style="max-height: 800px; overflow-y: auto; background: #fff; padding: 16px; border-radius: 6px;" v-html="reportContent"></div>
        </div>
      </div>

      <el-dialog
        v-model="showPdfPreviewDialog"
        title="PDF页码预览"
        width="95%"
        top="3vh"
        :close-on-click-modal="false"
        class="pdf-preview-dialog"
      >
        <div class="pdf-preview-wrapper">
          <div class="pdf-preview-pane">
            <div class="pane-header pane-a">
              <span>文档A：{{ fileA?.name || '文档A' }}</span>
            </div>
            <div class="pane-content">
              <PdfPreview
                v-if="pdfUrlA"
                ref="pdfPreviewARef"
                :pdf-url="pdfUrlA"
                :file-name="fileA?.name || 'document_A.pdf'"
                @page-change="onPageAChange"
                @loaded="onPdfALoaded"
              />
              <el-empty v-else description="暂无PDF预览" />
            </div>
          </div>
          <div class="pdf-preview-divider">
            <div class="divider-actions">
              <el-tooltip content="开启后两边同步翻页" placement="top">
                <el-switch
                  v-model="syncScroll"
                  size="small"
                  active-text="同步"
                  inactive-text="独立"
                />
              </el-tooltip>
            </div>
          </div>
          <div class="pdf-preview-pane">
            <div class="pane-header pane-b">
              <span>文档B：{{ fileB?.name || '文档B' }}</span>
            </div>
            <div class="pane-content">
              <PdfPreview
                v-if="pdfUrlB"
                ref="pdfPreviewBRef"
                :pdf-url="pdfUrlB"
                :file-name="fileB?.name || 'document_B.pdf'"
                @page-change="onPageBChange"
                @loaded="onPdfBLoaded"
              />
              <el-empty v-else description="暂无PDF预览" />
            </div>
          </div>
        </div>
      </el-dialog>
    </div>

    <div v-if="currentView === 'tasks'">
      <h2 class="page-title">历史任务</h2>
      <div class="panel">
        <el-empty v-if="history.length === 0" description="暂无历史任务，请先进行文档对比">
          <el-button type="primary" @click="currentView = 'upload'; $router.push('/compare')">去对比</el-button>
        </el-empty>
        <el-table v-else :data="history" border style="width: 100%">
          <el-table-column prop="id" label="任务ID" width="100" />
          <el-table-column prop="file_a_name" label="文档A" />
          <el-table-column prop="file_b_name" label="文档B" />
          <el-table-column prop="similarity" label="相似度" width="120">
            <template #default="scope">
              <span :class="getSimilarityClass(scope.row.similarity)">{{ (scope.row.similarity * 100).toFixed(1) }}%</span>
            </template>
          </el-table-column>
          <el-table-column prop="verdict" label="判定" width="180">
            <template #default="scope">
              <el-tag :type="scope.row.verdict?.includes('通过') ? 'success' : (scope.row.verdict?.includes('强制') ? 'danger' : 'warning')" size="small">{{ scope.row.verdict }}</el-tag>
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
              <el-button size="small" @click="openTaskPdfPreview(scope.row.id)">PDF预览</el-button>
              <el-button size="small" @click="exportTaskReport(scope.row.id)">导出报告</el-button>
              <el-button size="small" type="danger" @click="deleteTask(scope.row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-if="selectedTask" class="result-panel" style="margin-top: 20px;">
        <div class="panel-header">
          <span>任务详情 - {{ selectedTask.id }}</span>
          <div class="panel-actions">
            <el-button size="small" type="primary" @click="previewTaskReport(selectedTask.id)">预览报告</el-button>
            <el-button size="small" @click="exportTaskReport(selectedTask.id)">导出报告</el-button>
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
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { compareAPI } from '@/api'
import { Upload, Search, View } from '@element-plus/icons-vue'
import PdfPreview from '@/components/PdfPreview.vue'

const route = useRoute()
const router = useRouter()
const fileA = ref(null)
const fileB = ref(null)
const loading = ref(false)
const progress = ref(0)
const progressText = ref('')
const result = ref(null)
const history = ref([])
const selectedTask = ref(null)
const showPreview = ref(false)
const reportContent = ref('')
const showPdfPreviewDialog = ref(false)
const pdfUrlA = ref('')
const pdfUrlB = ref('')
const pdfPreviewARef = ref(null)
const pdfPreviewBRef = ref(null)
const syncScroll = ref(true)
const _pageChangingFrom = ref('')

const currentView = computed(() => {
  if (route.path === '/compare/tasks') return 'tasks'
  return 'upload'
})

const verdictType = computed(() => {
  if (!result.value?.verdict) return 'info'
  if (result.value.verdict.includes('通过')) return 'success'
  if (result.value.verdict.includes('强制')) return 'danger'
  return 'warning'
})

onMounted(async () => {
  console.log('[Compare] Component mounted, currentView:', currentView.value, 'route:', route.path)
  if (currentView.value === 'tasks') {
    await loadHistory()
  }
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

function clearFiles() {
  fileA.value = null
  fileB.value = null
  result.value = null
}

function updateProgress(pct, text) {
  return new Promise(resolve => {
    setTimeout(() => {
      progress.value = pct
      progressText.value = text
      resolve()
    }, 200)
  })
}

async function doCompare() {
  if (!fileA.value || !fileB.value) {
    ElMessage.info('请上传两个文档后再进行对比')
    return
  }
  loading.value = true
  progress.value = 0
  progressText.value = ''

  try {
    await updateProgress(5, '正在初始化...')
    await updateProgress(10, '正在上传文件...')
    await updateProgress(15, '正在解析文档A...')

    const respPromise = compareAPI.create(fileA.value, fileB.value)

    for (let p = 20; p < 80; p += 5) {
      await updateProgress(p, `正在处理文档B... ${p}%`)
      await new Promise(r => setTimeout(r, 300))
    }

    await updateProgress(80, '正在对比分析...')

    const resp = await respPromise
    const data = resp.data || {}

    await updateProgress(90, '正在生成结果...')

    result.value = {
      similarity: data.similarity || 0,
      verdict: data.verdict || '',
      total_diffs: data.total_diffs || 0,
      comparison_id: data.comparison_id || data.task_id || 0,
      task_id: data.comparison_id || data.task_id || 0,
    }

    await updateProgress(95, '正在整理报告...')
    await updateProgress(100, '对比完成')

    setTimeout(() => { progress.value = 0 }, 1500)
    ElMessage.success('对比完成')
  } catch (e) {
    progress.value = 0
    ElMessage.error('对比失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function exportCompare() {
  if (!result.value) {
    ElMessage.warning('请先进行对比')
    return
  }

  const taskId = result.value.comparison_id || result.value.task_id
  if (!taskId) {
    ElMessage.warning('无法获取任务ID，请重新对比')
    return
  }

  try {
    const resp = await compareAPI.getReport(taskId, 'html')
    const content = resp.data?.content || ''

    if (!content.trim()) {
      ElMessage.warning('报告内容为空')
      return
    }

    downloadFile(content, `compare_report_${taskId}_${Date.now()}.html`, 'text/html')
    ElMessage.success('对比报告已导出')
  } catch (e) {
    console.error('Export error:', e)
    ElMessage.error('导出失败：' + (e.message || '未知错误'))
  }
}

async function previewReport() {
  if (!result.value) {
    ElMessage.warning('请先进行对比')
    return
  }

  const taskId = result.value.comparison_id || result.value.task_id
  if (!taskId) {
    ElMessage.warning('无法获取任务ID，请重新对比')
    return
  }

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

async function viewTask(taskId) {
  try {
    const resp = await compareAPI.get(taskId)
    const data = resp.data || {}

    selectedTask.value = {
      id: taskId,
      similarity: data.similarity || 0,
      verdict: data.verdict || '',
      file_a_name: data.file_a_name || '',
      file_b_name: data.file_b_name || '',
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

function openPdfPreview() {
  const taskId = result.value?.comparison_id || result.value?.task_id
  if (!taskId) {
    ElMessage.warning('无法获取任务ID')
    return
  }
  pdfUrlA.value = compareAPI.getPreviewFileUrl(taskId, 'a')
  pdfUrlB.value = compareAPI.getPreviewFileUrl(taskId, 'b')
  showPdfPreviewDialog.value = true
}

function openTaskPdfPreview(taskId) {
  if (!taskId) {
    ElMessage.warning('无法获取任务ID')
    return
  }
  pdfUrlA.value = compareAPI.getPreviewFileUrl(taskId, 'a')
  pdfUrlB.value = compareAPI.getPreviewFileUrl(taskId, 'b')
  showPdfPreviewDialog.value = true
}

function onPageAChange(page) {
  if (syncScroll.value && _pageChangingFrom.value !== 'b') {
    _pageChangingFrom.value = 'a'
    nextTick(() => {
      if (pdfPreviewBRef.value?.goToPage) {
        pdfPreviewBRef.value.goToPage(page)
      }
      _pageChangingFrom.value = ''
    })
  }
}

function onPageBChange(page) {
  if (syncScroll.value && _pageChangingFrom.value !== 'a') {
    _pageChangingFrom.value = 'b'
    nextTick(() => {
      if (pdfPreviewARef.value?.goToPage) {
        pdfPreviewARef.value.goToPage(page)
      }
      _pageChangingFrom.value = ''
    })
  }
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
  align-items: flex-start;
  gap: 24px;
  justify-content: center;
}

.upload-slot { flex: 1; max-width: 400px; }

.slot-label {
  font-weight: 600;
  margin-bottom: 12px;
  color: #374151;
}

.upload-box {
  border: 2px dashed #d1d5db;
  border-radius: 8px;
  padding: 30px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s;
}

.upload-box:hover { border-color: #3b82f6; background: #eff6ff; }

.upload-box.filled { border-color: #3b82f6; background: #f0f9ff; }

.upload-hint { color: #6b7280; font-size: 14px; }

.upload-name { color: #3b82f6; font-weight: 600; font-size: 14px; }

.vs-badge {
  font-size: 20px;
  font-weight: 700;
  color: #9ca3af;
  padding: 8px 16px;
}

.action-row {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 24px;
}

.progress-panel {
  margin-top: 20px;
  padding: 16px;
  background: #f8fafc;
  border-radius: 8px;
}

.progress-text {
  text-align: center;
  margin-top: 8px;
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
  height: calc(94vh - 60px);
}

.pdf-preview-wrapper {
  display: flex;
  height: 100%;
  min-height: 600px;
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

.sim-high { color: #10b981; font-weight: 600; }
.sim-medium { color: #f59e0b; font-weight: 600; }
.sim-low { color: #ef4444; font-weight: 600; }
</style>