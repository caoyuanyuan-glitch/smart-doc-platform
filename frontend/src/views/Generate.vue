<template>
  <div class="gen-container">
    <div v-if="currentView === 'generate'">
      <h2 class="page-title">内容生成</h2>

      <div class="panel">
        <div class="panel-header">
          <span>填写参数</span>
        </div>

        <el-form :model="form" label-width="120px" style="max-width: 800px;">
          <el-form-item label="产品名称">
            <el-input v-model="form.productName" placeholder="例如：智能检测试剂X-200" />
          </el-form-item>
          <el-form-item label="产品型号">
            <el-input v-model="form.productModel" placeholder="例如：X-200 / X-300 / Pro-Max" />
          </el-form-item>
          <el-form-item label="文档类型">
            <el-select v-model="form.docType" style="width: 100%;">
              <el-option label="用户手册" value="user_manual" />
              <el-option label="技术规格" value="spec" />
              <el-option label="安装指南" value="install" />
              <el-option label="操作说明" value="operation" />
            </el-select>
          </el-form-item>
          <el-form-item label="目标章节">
            <el-checkbox-group v-model="form.chapters">
              <el-checkbox label="简介" />
              <el-checkbox label="安装" />
              <el-checkbox label="操作" />
              <el-checkbox label="维护" />
              <el-checkbox label="故障排除" />
            </el-checkbox-group>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" size="large" :loading="loading" @click="doGenerate">生成文档</el-button>
            <el-button size="large" @click="reset">重置</el-button>
          </el-form-item>
        </el-form>
      </div>

      <div v-if="result" class="panel">
        <div class="panel-header">
          <span>生成结果</span>
          <div class="panel-actions">
            <el-tag type="info" size="small" v-if="result.sections && result.sections.length">共 {{ result.sections.length }} 个章节</el-tag>
            <el-button size="small" @click="copyGen">复制</el-button>
            <el-button size="small" type="primary" @click="downloadGen">下载</el-button>
          </div>
        </div>
        <div class="gen-content">
          <pre>{{ result.content }}</pre>
          <el-divider v-if="result.sections && result.sections.length" />
          <div v-if="result.sections && result.sections.length" class="sections-title">章节结构：</div>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item v-for="(s, i) in result.sections" :key="i" :label="'第' + (i+1) + '章'">{{ s }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </div>
    </div>

    <div v-if="currentView === 'templates'">
      <h2 class="page-title">模板管理</h2>
      <div class="panel">
        <el-table :data="templates" border>
          <el-table-column prop="name" label="模板名称" />
          <el-table-column prop="type" label="类型" width="120" />
          <el-table-column prop="lang" label="语言" width="100" />
          <el-table-column prop="fields" label="字段数" width="100" />
          <el-table-column prop="updated_at" label="更新时间" width="180" />
          <el-table-column label="操作" width="180">
            <template #default>
              <el-button size="small">使用</el-button>
              <el-button size="small">编辑</el-button>
              <el-button size="small" type="danger">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { generateAPI } from '@/api'

const route = useRoute()
const loading = ref(false)
const result = ref(null)

const form = ref({
  productName: '智能检测试剂',
  productModel: 'X-200',
  docType: 'user_manual',
  chapters: ['简介', '操作', '维护']
})

const templates = ref([
  { name: '标准产品说明书模板', type: 'manual', lang: '中文', fields: 15, updated_at: '2025-01-10 10:30' },
  { name: '技术规格文档模板', type: 'spec', lang: '中英文', fields: 22, updated_at: '2025-01-09 14:20' },
  { name: '用户操作手册模板', type: 'user', lang: '中文', fields: 18, updated_at: '2025-01-08 09:15' }
])

const currentView = computed(() => (route.path === '/generate/templates' ? 'templates' : 'generate'))

function buildExampleContent() {
  const chapterText = (form.value.chapters && form.value.chapters.length ? form.value.chapters : ['简介', '操作']).join('、')
  return `${form.value.productName}（型号：${form.value.productModel}）文档

【文档类型】${docTypeLabel(form.value.docType)}
【目标章节】${chapterText}

一、产品简介
${form.value.productName}（型号：${form.value.productModel}）是基于先进免疫层析技术开发的新一代体外诊断产品，适用于医疗机构和临床实验室。本产品采用标准化工艺生产，确保批次间一致性和稳定性。

二、产品规格
- 产品型号：${form.value.productModel}
- 检测原理：免疫层析法
- 样本类型：血清 / 血浆 / 全血
- 检测时间：15 分钟
- 储存条件：2 ~ 25°C，避光保存
- 有效期：24 个月（未开封）

三、操作说明
1. 取出检测卡，平放于桌面
2. 加入 100μL 样本至加样孔
3. 计时 15 分钟后读取结果
4. 请严格按照说明书步骤操作

四、维护与保养
- 定期检查试剂有效期
- 保持设备清洁，避免灰尘污染
- 按照使用手册进行日常维护操作

五、故障排除
- 无显示 → 检查试剂是否过期，操作是否规范
- 信号偏低 → 确认样本采集方式与体积
- 设备报错 → 重新启动，若持续请联系技术支持

—— 本文档由智能技术文档平台自动生成 ——`
}

function docTypeLabel(type) {
  const map = {
    user_manual: '用户手册',
    spec: '技术规格',
    install: '安装指南',
    operation: '操作说明'
  }
  return map[type] || type
}

async function doGenerate() {
  if (!form.value.productName || !form.value.productModel) {
    ElMessage.info('请填写产品名称和型号')
    return
  }
  loading.value = true
  try {
    const resp = await generateAPI.create(form.value.productName, form.value.productModel, form.value.docType, form.value.chapters.join(','))
    const data = resp.data || {}
    result.value = {
      content: data.content || buildExampleContent(),
      sections: data.sections || (form.value.chapters && form.value.chapters.length ? form.value.chapters : ['简介', '产品规格', '操作说明', '维护保养', '故障排除'])
    }
    ElMessage.success('生成完成')
  } catch (e) {
    result.value = {
      content: buildExampleContent(),
      sections: form.value.chapters && form.value.chapters.length ? form.value.chapters : ['简介', '产品规格', '操作说明', '维护保养', '故障排除']
    }
    ElMessage.info('接口调用失败，已展示示例生成结果')
  } finally {
    loading.value = false
  }
}

function reset() {
  form.value = { productName: '', productModel: '', docType: 'user_manual', chapters: [] }
  result.value = null
}

function copyGen() {
  navigator.clipboard.writeText(result.value.content).then(() => ElMessage.success('已复制')).catch(() => ElMessage.info('复制失败，请手动复制'))
}

function downloadGen() {
  const blob = new Blob([result.value.content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${form.value.productName}_${form.value.productModel}_${docTypeLabel(form.value.docType)}.txt`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('下载已开始')
}
</script>

<style>
.gen-container { padding: 0; }

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

.gen-content {
  background: #f8fafc;
  padding: 24px;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
}

.gen-content pre {
  line-height: 1.8;
  color: #374151;
  font-size: 14px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  margin: 0;
  background: #fff;
  padding: 16px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

.sections-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 12px;
}
</style>
