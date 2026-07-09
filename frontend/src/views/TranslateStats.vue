<template>
  <div class="stats-container">
    <h2 class="stats-title">翻译统计面板</h2>

    <div class="stats-layout">
      <div class="stats-section">
        <div class="section-header">
          <h3 class="section-title">累计统计</h3>
        </div>
        <div class="stats-cards">
          <div class="stat-card card-text">
            <div class="stat-label">文本翻译字数</div>
            <div class="stat-value">{{ stats.text_word_count.toLocaleString() }}</div>
            <div class="stat-unit">字</div>
          </div>
          <div class="stat-card card-doc">
            <div class="stat-label">已翻译文档数</div>
            <div class="stat-value">{{ stats.doc_count.toLocaleString() }}</div>
            <div class="stat-unit">个</div>
          </div>
          <div class="stat-card card-ai">
            <div class="stat-label">AI大模型翻译字数</div>
            <div class="stat-value">{{ stats.ai_word_count.toLocaleString() }}</div>
            <div class="stat-unit">字</div>
          </div>
          <div class="stat-card card-memory">
            <div class="stat-label">记忆库匹配字数</div>
            <div class="stat-value">{{ stats.memory_word_count.toLocaleString() }}</div>
            <div class="stat-unit">字</div>
          </div>
        </div>
        <div class="chart-section" v-if="hasOverallChartData">
          <h3 class="chart-title">累计翻译来源占比</h3>
          <div class="chart-wrapper">
            <v-chart :option="overallPieOption" autoresize style="height: 380px" />
          </div>
        </div>
        <div class="chart-section empty-chart" v-else>
          <p>当前还没有累计翻译来源统计数据</p>
        </div>
      </div>

      <div class="stats-section">
        <div class="section-header">
          <h3 class="section-title">本次上传统计</h3>
          <span v-if="stats.current_upload.batch_id" class="section-meta">批次 {{ stats.current_upload.batch_id }}</span>
        </div>
        <div class="stats-cards batch-cards">
          <div class="stat-card card-doc">
            <div class="stat-label">本次翻译文档数</div>
            <div class="stat-value">{{ stats.current_upload.doc_count.toLocaleString() }}</div>
            <div class="stat-unit">个</div>
          </div>
          <div class="stat-card card-text">
            <div class="stat-label">本次文档总字数</div>
            <div class="stat-value">{{ stats.current_upload.doc_word_count.toLocaleString() }}</div>
            <div class="stat-unit">字</div>
          </div>
          <div class="stat-card card-ai">
            <div class="stat-label">本次 AI 翻译字数</div>
            <div class="stat-value">{{ stats.current_upload.ai_word_count.toLocaleString() }}</div>
            <div class="stat-unit">字</div>
          </div>
          <div class="stat-card card-memory">
            <div class="stat-label">本次记忆库匹配字数</div>
            <div class="stat-value">{{ stats.current_upload.memory_word_count.toLocaleString() }}</div>
            <div class="stat-unit">字</div>
          </div>
        </div>
        <div class="chart-section" v-if="hasCurrentUploadChartData">
          <h3 class="chart-title">本次上传翻译来源占比</h3>
          <div class="chart-wrapper">
            <v-chart :option="currentUploadPieOption" autoresize style="height: 380px" />
          </div>
        </div>
        <div class="chart-section empty-chart" v-else>
          <p>当前还没有本次上传的文档翻译统计数据</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { translationAPI } from '@/api'

const TRANSLATION_BATCH_STORAGE_KEY = 'translation:lastUploadBatchId'
const TRANSLATION_BATCH_EVENT = 'translation-batch-updated'
const TRANSLATION_STATS_EVENT = 'translation-stats-updated'

use([PieChart, TitleComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const stats = ref({
  text_word_count: 0,
  doc_count: 0,
  doc_word_count: 0,
  ai_word_count: 0,
  memory_word_count: 0,
  current_upload: {
    batch_id: '',
    doc_count: 0,
    doc_word_count: 0,
    ai_word_count: 0,
    memory_word_count: 0
  }
})

const loading = ref(false)
let refreshTimer = null

const hasOverallChartData = computed(() => {
  return ((stats.value.ai_word_count || 0) + (stats.value.memory_word_count || 0)) > 0
})

const hasCurrentUploadChartData = computed(() => {
  const currentUpload = stats.value.current_upload || {}
  return ((currentUpload.ai_word_count || 0) + (currentUpload.memory_word_count || 0)) > 0
})

const overallPieOption = computed(() => ({
  tooltip: {
    trigger: 'item',
    formatter: '{b}: {c} 字 ({d}%)'
  },
  legend: {
    bottom: 10
  },
  series: [
    {
      name: '翻译来源',
      type: 'pie',
      radius: ['45%', '72%'],
      center: ['50%', '48%'],
      avoidLabelOverlap: false,
      itemStyle: {
        borderRadius: 6,
        borderColor: '#fff',
        borderWidth: 3
      },
      label: {
        show: true,
        position: 'outside',
        formatter: '{b}\n{d}%'
      },
      emphasis: {
        label: {
          show: true,
          fontSize: 16,
          fontWeight: 'bold'
        }
      },
      data: [
        {
          value: stats.value.ai_word_count,
          name: 'AI大模型翻译',
          itemStyle: { color: '#409EFF' }
        },
        {
          value: stats.value.memory_word_count,
          name: '记忆库匹配',
          itemStyle: { color: '#67C23A' }
        }
      ]
    }
  ]
}))

const currentUploadPieOption = computed(() => ({
  tooltip: {
    trigger: 'item',
    formatter: '{b}: {c} 字 ({d}%)'
  },
  legend: {
    bottom: 10
  },
  series: [
    {
      name: '翻译来源',
      type: 'pie',
      radius: ['45%', '72%'],
      center: ['50%', '48%'],
      avoidLabelOverlap: false,
      itemStyle: {
        borderRadius: 6,
        borderColor: '#fff',
        borderWidth: 3
      },
      label: {
        show: true,
        position: 'outside',
        formatter: '{b}\n{d}%'
      },
      emphasis: {
        label: {
          show: true,
          fontSize: 16,
          fontWeight: 'bold'
        }
      },
      data: [
        {
          value: stats.value.current_upload.ai_word_count,
          name: 'AI大模型翻译',
          itemStyle: { color: '#409EFF' }
        },
        {
          value: stats.value.current_upload.memory_word_count,
          name: '记忆库匹配',
          itemStyle: { color: '#67C23A' }
        }
      ]
    }
  ]
}))

async function loadStats() {
  loading.value = true
  try {
    const batchId = sessionStorage.getItem(TRANSLATION_BATCH_STORAGE_KEY) || localStorage.getItem(TRANSLATION_BATCH_STORAGE_KEY) || ''
    const res = await translationAPI.getStats(batchId)
    if (res.data) {
      stats.value = res.data
    }
  } catch (e) {
    console.error('加载统计数据失败', e)
  } finally {
    loading.value = false
  }
}

function handleBatchUpdated(event) {
  const batchId = event?.detail?.batchId || ''
  if (batchId) {
    sessionStorage.setItem(TRANSLATION_BATCH_STORAGE_KEY, batchId)
    localStorage.setItem(TRANSLATION_BATCH_STORAGE_KEY, batchId)
  }
  loadStats()
}

function handleVisibilityChange() {
  if (document.visibilityState === 'visible') {
    loadStats()
  }
}

onMounted(() => {
  loadStats()
  window.addEventListener(TRANSLATION_BATCH_EVENT, handleBatchUpdated)
  window.addEventListener(TRANSLATION_STATS_EVENT, loadStats)
  window.addEventListener('storage', loadStats)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  refreshTimer = window.setInterval(loadStats, 5000)
})

onBeforeUnmount(() => {
  window.removeEventListener(TRANSLATION_BATCH_EVENT, handleBatchUpdated)
  window.removeEventListener(TRANSLATION_STATS_EVENT, loadStats)
  window.removeEventListener('storage', loadStats)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<style scoped>
.stats-container {
  padding: 24px;
  max-width: 1600px;
}

.stats-layout {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 24px;
  align-items: start;
}

.stats-section {
  min-width: 0;
}

.stats-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 20px 0;
  color: #303133;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
  color: #303133;
}

.section-meta {
  font-size: 12px;
  color: #909399;
}

.stats-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 32px;
}

.batch-cards {
  margin-bottom: 20px;
}

.stat-card {
  padding: 20px 16px;
  border-radius: 8px;
  text-align: center;
  color: #fff;
}

.card-text {
  background: linear-gradient(135deg, #409EFF, #337ECC);
}

.card-doc {
  background: linear-gradient(135deg, #E6A23C, #CF9236);
}

.card-ai {
  background: linear-gradient(135deg, #67C23A, #529B2E);
}

.card-memory {
  background: linear-gradient(135deg, #909399, #6B6E73);
}

.stat-label {
  font-size: 13px;
  opacity: 0.9;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
}

.stat-unit {
  font-size: 12px;
  opacity: 0.75;
  margin-top: 4px;
}

.chart-section {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.chart-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 16px 0;
  color: #303133;
}

.chart-wrapper {
  display: flex;
  justify-content: center;
}

.empty-chart {
  text-align: center;
  color: #909399;
  padding: 48px 20px;
}

@media (max-width: 768px) {
  .stats-layout {
    grid-template-columns: 1fr;
  }

  .stats-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
