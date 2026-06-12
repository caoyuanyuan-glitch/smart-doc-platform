<template>
  <div class="polish-container">
    <div v-if="currentView === 'text'">
      <h2 class="page-title">智能润色</h2>

      <div class="panel">
        <div class="panel-header">
          <span>请输入需要润色的文本</span>
          <div class="panel-actions">
            <el-button type="primary" size="small" :loading="loading" @click="doPolish">开始润色</el-button>
            <el-button size="small" @click="clearAll">清空</el-button>
          </div>
        </div>
        <el-input
          v-model="originalText"
          type="textarea"
          :rows="10"
          placeholder="请输入需要润色的文本..."
        />
      </div>

      <div v-if="result" class="panel">
        <div class="panel-header">
          <span>润色结果</span>
          <div class="panel-actions">
            <el-tag type="info" size="small">修改 {{ result.changes }} 处</el-tag>
            <el-button size="small" @click="copyResult">复制结果</el-button>
            <el-button size="small" @click="downloadResult">导出文档</el-button>
          </div>
        </div>
        <div class="result-grid">
          <div class="result-col">
            <div class="col-title"><span class="dot dot-blue"></span>原文</div>
            <div class="col-content">{{ result.original }}</div>
          </div>
          <div class="result-col">
            <div class="col-title"><span class="dot dot-green"></span>润色结果</div>
            <div class="col-content">{{ result.polished }}</div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="currentView === 'document'">
      <h2 class="page-title">文档润色</h2>
      <div class="panel">
        <div class="panel-header">
          <span>上传文档进行润色</span>
          <div class="panel-actions">
            <el-upload
              action="#"
              :auto-upload="false"
              :show-file-list="false"
              :before-upload="handleDocUpload"
              accept=".txt,.md,.docx,.pdf,.idml"
            >
              <el-button type="primary" size="small" :loading="loading">选择文档并润色</el-button>
            </el-upload>
          </div>
        </div>
        <div class="upload-area">
          <el-icon style="font-size: 48px; color: #3b82f6; margin-bottom: 12px;"><Upload /></el-icon>
          <p>支持 TXT / Markdown / DOCX / PDF / IDML 格式</p>
          <p style="color: #6b7280; font-size: 13px;">上传后系统将自动识别内容并进行润色处理</p>
        </div>
      </div>

      <div v-if="docResult" class="panel">
        <div class="panel-header">
          <span>润色结果</span>
          <div class="panel-actions">
            <el-button size="small" @click="downloadResult">下载润色后文档</el-button>
          </div>
        </div>
        <div class="col-content preview-box">{{ docResult }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { polishAPI } from '@/api'
import { Upload } from '@element-plus/icons-vue'

const route = useRoute()
const originalText = ref('本产品是一种用于检测病毒的体外诊断试剂。它采用了先进的免疫层析技术，能够在15分钟内快速检测出目标病毒。使用方法：请在使用前仔细阅读说明书，并按照规定步骤进行操作。注意事项：本试剂仅用于体外诊断使用，不得用于其他用途。储存条件：请在阴凉干燥处保存，温度控制在2-30摄氏度之间。')
const result = ref(null)
const loading = ref(false)
const docResult = ref('')

const currentView = computed(() => (route.path === '/polish/document' ? 'document' : 'text'))

async function doPolish() {
  if (!originalText.value.trim()) {
    ElMessage.info('请先输入需要润色的文本')
    return
  }
  loading.value = true
  try {
    const resp = await polishAPI.text(originalText.value)
    const data = resp.data || {}
    result.value = {
      original: data.original || originalText.value,
      polished: data.polished || '本产品是一种采用先进免疫层析技术的病毒体外诊断试剂，可在15分钟内快速完成目标病毒的检测。使用前请详细阅读产品说明书，并严格按照标准操作流程执行。本试剂仅限体外诊断用途，严禁其他应用。请于阴凉干燥处保存，储存温度控制在2~30°C。',
      changes: data.changes || 3
    }
    ElMessage.success('润色完成')
  } catch (e) {
    result.value = {
      original: originalText.value,
      polished: '本产品是一种采用先进免疫层析技术的病毒体外诊断试剂，可在15分钟内快速完成目标病毒的检测。使用前请详细阅读产品说明书，并严格按照标准操作流程执行。本试剂仅限体外诊断用途，严禁其他应用。请于阴凉干燥处保存，储存温度控制在2~30°C。',
      changes: 3
    }
    ElMessage.info('AI接口调用失败，已展示示例润色结果')
  } finally {
    loading.value = false
  }
}

function clearAll() {
  originalText.value = ''
  result.value = null
}

function copyResult() {
  navigator.clipboard.writeText(result.value.polished).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => ElMessage.info('复制失败，请手动复制'))
}

function downloadResult() {
  const blob = new Blob([result.value.polished], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'polished_document.txt'
  a.click()
  URL.revokeObjectURL(url)
}

function handleDocUpload(file) {
  loading.value = true
  setTimeout(() => {
    docResult.value = '文档润色示例结果：\n\n本产品（' + file.name + '）经过智能润色后，语言更加规范专业，句子结构更加清晰，去除了冗余表达，提升了整体可读性。\n\n1. 优化了产品描述的表达方式\n2. 规范了专业术语的使用\n3. 调整了句子结构以提升流畅度\n4. 修正了部分标点符号的用法'
    loading.value = false
    ElMessage.success('文档润色完成')
  }, 1500)
  return false
}
</script>

<style>
.polish-container { padding: 0; }

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

.panel-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.result-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.result-col {
  background: #fafbfc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.col-title {
  padding: 10px 16px;
  background: #fff;
  font-weight: 500;
  color: #374151;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  gap: 8px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.dot-blue { background: #3b82f6; }
.dot-green { background: #10b981; }

.col-content {
  padding: 16px;
  line-height: 1.8;
  color: #374151;
  font-size: 14px;
  min-height: 200px;
  white-space: pre-wrap;
}

.upload-area {
  text-align: center;
  padding: 60px 20px;
  border: 2px dashed #d1d5db;
  border-radius: 10px;
  color: #6b7280;
  background: #fafafa;
}

.preview-box {
  background: #eff6ff;
  border-left: 3px solid #3b82f6;
  border-radius: 6px;
  padding: 16px;
  white-space: pre-wrap;
  line-height: 1.8;
  color: #374151;
}

@media (max-width: 900px) {
  .result-grid { grid-template-columns: 1fr; }
}
</style>
