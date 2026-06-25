<template>
  <div class="stats-container">
    <h2 class="stats-title">翻译统计面板</h2>

    <div class="stats-cards">
      <div class="stat-card card-text">
        <div class="stat-label">文本翻译字数</div>
        <div class="stat-value">{{ stats.text_char_count.toLocaleString() }}</div>
        <div class="stat-unit">字符</div>
      </div>
      <div class="stat-card card-doc">
        <div class="stat-label">已翻译文档数</div>
        <div class="stat-value">{{ stats.doc_count.toLocaleString() }}</div>
        <div class="stat-unit">个</div>
      </div>
      <div class="stat-card card-ai">
        <div class="stat-label">AI大模型翻译字数</div>
        <div class="stat-value">{{ stats.ai_char_count.toLocaleString() }}</div>
        <div class="stat-unit">字符</div>
      </div>
      <div class="stat-card card-memory">
        <div class="stat-label">记忆库匹配字数</div>
        <div class="stat-value">{{ stats.memory_char_count.toLocaleString() }}</div>
        <div class="stat-unit">字符</div>
      </div>
    </div>

    <div class="chart-section" v-if="hasChartData">
      <h3 class="chart-title">翻译来源占比</h3>
      <div class="chart-wrapper">
        <v-chart :option="pieOption" autoresize style="height: 380px" />
      </div>
    </div>
    <div class="chart-section empty-chart" v-else>
      <p>暂无翻译数据，开始翻译后将展示来源占比饼图</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { translationAPI } from '@/api'

use([PieChart, TitleComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const stats = ref({
  text_char_count: 0,
  doc_count: 0,
  doc_char_count: 0,
  ai_char_count: 0,
  memory_char_count: 0
})

const loading = ref(false)

const hasChartData = computed(() => {
  return (stats.value.ai_char_count + stats.value.memory_char_count) > 0
})

const pieOption = computed(() => ({
  tooltip: {
    trigger: 'item',
    formatter: '{b}: {c} 字符 ({d}%)'
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
          value: stats.value.ai_char_count,
          name: 'AI大模型翻译',
          itemStyle: { color: '#409EFF' }
        },
        {
          value: stats.value.memory_char_count,
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
    const res = await translationAPI.getStats()
    if (res.data) {
      stats.value = res.data
    }
  } catch (e) {
    console.error('加载统计数据失败', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadStats()
})
</script>

<style scoped>
.stats-container {
  padding: 24px;
  max-width: 960px;
}

.stats-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 20px 0;
  color: #303133;
}

.stats-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 32px;
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
  .stats-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
