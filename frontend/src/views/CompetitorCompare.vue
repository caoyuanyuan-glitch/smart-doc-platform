<template>
  <div class="compare-page">
    <div class="page-header">
      <h2>竞品对比分析</h2>
      <p class="sub">选择 2-5 份已完成分析的文档（可标记一份为「我方基线」），生成维度矩阵、雷达图与差距洞察。</p>
    </div>

    <el-card shadow="never" class="mb16">
      <template #header><b>新建对比</b></template>
      <el-form label-width="90px">
        <el-form-item label="对比标题">
          <el-input v-model="title" placeholder="例如：Illumina vs 华大智造 操作手册（留空自动命名）" maxlength="120" style="max-width: 420px;" />
        </el-form-item>
      </el-form>
      <el-table :data="tasks" v-loading="loadingTasks" size="small" max-height="360"
                @selection-change="onSelectionChange" ref="taskTable">
        <el-table-column type="selection" width="46" :selectable="(row) => row.status === 'completed'" />
        <el-table-column label="我方基线" width="90">
          <template #default="{ row }">
            <el-radio v-if="selectedIds.includes(row.id)" v-model="baselineTaskId" :value="row.id">{{ '' }}</el-radio>
          </template>
        </el-table-column>
        <el-table-column prop="id" label="ID" width="64" />
        <el-table-column prop="file_name" label="文档名" min-width="220" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'completed' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="分析时间" width="160" />
      </el-table>
      <div class="baseline-tip">
        已选 <b>{{ selectedIds.length }}</b>/5 份；
        基线：
        <el-tag v-if="baselineName" type="primary" size="small">{{ baselineName }}</el-tag>
        <el-tag v-else type="info" size="small">无（仅竞品横向对比）</el-tag>
        <el-button link size="small" @click="baselineTaskId = 0">清除基线</el-button>
      </div>
      <div class="actions">
        <el-button type="primary" :loading="creating" :disabled="selectedIds.length < 2" @click="createComparison">
          生成对比报告
        </el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header><b>历史对比</b></template>
      <el-table :data="comparisons" v-loading="loadingList" size="small">
        <el-table-column prop="id" label="ID" width="64" />
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column label="参与文档" width="100">
          <template #default="{ row }">{{ parseIds(row.task_ids).length }} 份</template>
        </el-table-column>
        <el-table-column label="基线" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.baseline_task_id" type="primary" size="small">#{{ row.baseline_task_id }}</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="160" />
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="viewComparison(row.id)">查看</el-button>
            <el-button link type="danger" size="small" @click="removeComparison(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="detailVisible" :title="detail?.title || '对比详情'" width="92%" top="3vh" destroy-on-close>
      <div v-if="detail" v-loading="loadingDetail">
        <div v-if="radarReady" class="radar-wrap">
          <el-alert v-if="excludedRadarDocs.length" type="warning" :closable="false" class="mb16"
                    :title="`「${excludedRadarDocs.map((d) => d.name).join('、')}」存在缺测维度，未纳入雷达图（详见矩阵中「-」项）`" />
          <VChart :option="radarOption" autoresize style="height: 360px;" />
        </div>
        <el-table :data="matrixRows" size="small" class="mb16">
          <el-table-column label="维度" width="120" fixed>
            <template #default="{ row }">{{ row.label }}</template>
          </el-table-column>
          <el-table-column v-for="col in docColumns" :key="col.task_id" :label="col.label" min-width="140">
            <template #default="{ row }">
              <template v-for="cell in row.cells" :key="cell.tid">
                <span v-if="cell.tid === col.task_id">
                  <b v-if="cell.isWinner" class="win">{{ cell.score }} ▲</b>
                  <span v-else>{{ cell.score }}</span>
                </span>
              </template>
            </template>
          </el-table-column>
        </el-table>
        <div class="report-actions">
          <el-button size="small" type="primary" :disabled="!detail.report_md" @click="downloadReport">下载对比报告 (Markdown)</el-button>
        </div>
        <pre class="report-pre">{{ detail.report_md || '报告生成中…' }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { RadarChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { competitorAPI } from '@/api'

use([RadarChart, TooltipComponent, LegendComponent, CanvasRenderer])

const loadingTasks = ref(false)
const loadingList = ref(false)
const loadingDetail = ref(false)
const creating = ref(false)
const tasks = ref([])
const comparisons = ref([])
const selectedRows = ref([])
const title = ref('')
const baselineTaskId = ref(0)
const detailVisible = ref(false)
const detail = ref(null)
const result = ref(null)
const taskTable = ref(null)

const selectedIds = computed(() => selectedRows.value.map((r) => r.id))
const baselineName = computed(() => {
  if (!baselineTaskId.value) return ''
  const row = selectedRows.value.find((r) => r.id === baselineTaskId.value)
  return row ? `#${row.id} ${row.file_name}` : ''
})

const parseIds = (raw) => {
  try { return JSON.parse(raw || '[]') } catch (e) { return [] }
}

const onSelectionChange = (rows) => {
  if (rows.length > 5) {
    // 超出 5 份：保留前 5，并取消表格中多余的勾选（避免视觉与提交数据不一致）
    ElMessage.warning('最多选择 5 份文档参与对比')
    const kept = rows.slice(0, 5)
    const keptIds = new Set(kept.map((r) => r.id))
    nextTick(() => {
      rows.forEach((row) => {
        if (!keptIds.has(row.id)) taskTable.value?.toggleRowSelection(row, false)
      })
    })
    selectedRows.value = kept
  } else {
    selectedRows.value = rows
  }
  if (baselineTaskId.value && !selectedIds.value.includes(baselineTaskId.value)) {
    baselineTaskId.value = 0
  }
}

const fetchTasks = async () => {
  loadingTasks.value = true
  try {
    const res = await competitorAPI.list({ limit: 200 })
    tasks.value = (res.data || []).filter((t) => t.status === 'completed')
  } catch (e) {
    ElMessage.error('任务列表加载失败')
  } finally {
    loadingTasks.value = false
  }
}

const fetchComparisons = async () => {
  loadingList.value = true
  try {
    const res = await competitorAPI.listComparisons({ limit: 100 })
    comparisons.value = res.data || []
  } catch (e) {
    ElMessage.error('对比列表加载失败')
  } finally {
    loadingList.value = false
  }
}

const createComparison = async () => {
  if (selectedIds.value.length < 2) return
  creating.value = true
  try {
    const payload = { title: title.value, task_ids: selectedIds.value }
    if (baselineTaskId.value) payload.baseline_task_id = baselineTaskId.value
    const res = await competitorAPI.createComparison(payload)
    ElMessage.success('对比报告已生成')
    await fetchComparisons()
    openDetail(res.data)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '对比生成失败')
  } finally {
    creating.value = false
  }
}

const viewComparison = async (id) => {
  loadingDetail.value = true
  detailVisible.value = true
  try {
    const res = await competitorAPI.getComparison(id)
    openDetail(res.data)
  } catch (e) {
    ElMessage.error('对比详情加载失败')
    detailVisible.value = false
  } finally {
    loadingDetail.value = false
  }
}

const openDetail = (data) => {
  detail.value = data
  try {
    result.value = JSON.parse(data.result_json || 'null')
  } catch (err) {
    result.value = null
  }
  detailVisible.value = true
}

const removeComparison = async (id) => {
  try {
    await ElMessageBox.confirm('确认删除该对比记录？（不影响参与任务本身）', '删除确认', { type: 'warning' })
  } catch (e) { return }
  try {
    await competitorAPI.deleteComparison(id)
    ElMessage.success('已删除')
    fetchComparisons()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

// ---------------- 雷达图与矩阵（消费后端 result_json） ----------------
const radarReady = computed(() => Boolean(result.value && result.value.dimension_matrix))

const docColumns = computed(() => {
  if (!result.value) return []
  const docs = result.value.documents || []
  const order = result.value.overall_ranking || docs.map((d) => d.task_id)
  const byId = Object.fromEntries(docs.map((d) => [d.task_id, d]))
  return order.map((tid) => ({
    task_id: tid,
    label: ((byId[tid]?.name || `#${tid}`).slice(0, 18)) + (byId[tid]?.is_baseline ? '（我方）' : '')
  }))
})

const radarOption = computed(() => {
  if (!radarReady.value) return {}
  const labels = result.value.dimension_labels || {}
  const indicators = Object.keys(labels).map((k) => ({ name: labels[k], max: 100 }))
  const docs = result.value.documents || []
  const dimKeys = Object.keys(labels)
  // 含缺测维度（null）的文档不进雷达图（画成 0 会误导），以提示条说明
  const radarDocs = docs.filter((d) => dimKeys.every((k) =>
    (result.value.dimension_matrix[k] || {})[d.task_id] !== null && (result.value.dimension_matrix[k] || {})[d.task_id] !== undefined))
  const seriesData = radarDocs.map((d) => ({
    name: (d.name || `#${d.task_id}`).slice(0, 20) + (d.is_baseline ? '（我方）' : ''),
    value: dimKeys.map((k) => (result.value.dimension_matrix[k] || {})[d.task_id] ?? 0),
    areaStyle: { opacity: 0.08 }
  }))
  return {
    tooltip: {},
    legend: { bottom: 0, type: 'scroll' },
    radar: { indicators, radius: '62%' },
    series: [{ type: 'radar', data: seriesData }]
  }
})

const excludedRadarDocs = computed(() => {
  if (!radarReady.value) return []
  const labels = result.value.dimension_labels || {}
  const dimKeys = Object.keys(labels)
  return (result.value.documents || []).filter((d) => !dimKeys.every((k) =>
    (result.value.dimension_matrix[k] || {})[d.task_id] !== null && (result.value.dimension_matrix[k] || {})[d.task_id] !== undefined))
})

const matrixRows = computed(() => {
  if (!radarReady.value) return []
  const matrix = result.value.dimension_matrix
  const labels = result.value.dimension_labels || {}
  return Object.keys(labels).map((dimKey) => {
    const cells = Object.keys(matrix[dimKey] || {}).map((tid) => ({
      tid: Number(tid),
      score: matrix[dimKey][tid] ?? '-'
    }))
    // 并列最高分均标记（与后端报告口径一致）
    const validScores = cells.filter((c) => typeof c.score === 'number').map((c) => c.score)
    const maxScore = validScores.length ? Math.max(...validScores) : null
    cells.forEach((c) => { c.isWinner = maxScore !== null && c.score === maxScore })
    return { label: labels[dimKey], cells }
  })
})

const downloadReport = () => {
  const md = detail.value?.report_md || ''
  if (!md) return
  const name = (detail.value?.title || 'competitor_comparison').replace(/[\\/:*?"<>|]/g, '_')
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${name}_对比报告.md`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(() => {
  fetchTasks()
  fetchComparisons()
})
</script>

<style scoped>
.compare-page { padding: 16px; max-width: 1200px; margin: 0 auto; }
.page-header h2 { margin: 0 0 4px; font-size: 20px; }
.page-header .sub { margin: 0 0 16px; color: #909399; font-size: 13px; }
.mb16 { margin-bottom: 16px; }
.baseline-tip { margin: 10px 0 0; color: #606266; font-size: 13px; display: flex; align-items: center; gap: 8px; }
.actions { margin-top: 14px; }
.radar-wrap { margin-bottom: 8px; }
.report-actions { margin-bottom: 8px; }
.win { color: #e6a23c; }
.report-pre {
  background: #f5f7fa; border: 1px solid #ebeef5; border-radius: 6px;
  padding: 14px; font-size: 13px; line-height: 1.7;
  max-height: 60vh; overflow: auto; white-space: pre-wrap; word-break: break-word;
}
</style>
