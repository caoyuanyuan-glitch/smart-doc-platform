<template>
  <div class="translate-container">
    <div class="page-header">
      <h2 class="page-title">文本翻译</h2>
      <p class="page-desc">AI + 记忆库双引擎智能翻译，支持多模型选择</p>
    </div>

    <div class="content-grid">
      <div class="left-panel">
        <el-card class="config-card" shadow="never">
          <template #header>
            <span class="card-header-title">翻译配置</span>
          </template>

          <el-form label-width="90px" label-position="left" size="default">
            <el-form-item label="翻译引擎">
              <el-radio-group v-model="engine" @change="onEngineChange">
                <el-radio-button value="hybrid">AI + 记忆库</el-radio-button>
                <el-radio-button value="ai">仅 AI</el-radio-button>
                <el-radio-button value="memory">仅记忆库</el-radio-button>
              </el-radio-group>
            </el-form-item>

            <el-form-item label="AI 模型" v-if="engine !== 'memory'">
              <el-select v-model="model" placeholder="选择AI模型" style="width: 100%">
                <el-option label="Qwen3.6-Plus" value="qwen" />
                <el-option label="DeepSeek Chat" value="deepseek" />
              </el-select>
            </el-form-item>

            <el-form-item label="源语言">
              <el-select v-model="sourceLang" style="width: 100%">
                <el-option label="中文" value="zh" />
                <el-option label="英文" value="en" />
              </el-select>
            </el-form-item>

            <el-form-item label="目标语言">
              <el-select v-model="targetLang" style="width: 100%">
                <el-option label="英文" value="en" />
                <el-option label="中文" value="zh" />
                <el-option label="日文" value="ja" />
                <el-option label="韩文" value="ko" />
                <el-option label="法文" value="fr" />
                <el-option label="德文" value="de" />
              </el-select>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card class="source-card" shadow="never">
          <template #header>
            <span class="card-header-title">翻译内容</span>
          </template>
          <div class="text-input-area">
            <el-input
              v-model="inputText"
              type="textarea"
              :rows="14"
              placeholder="请输入需要翻译的文本内容..."
              resize="none"
            />
            <div class="input-actions">
              <span class="char-count">{{ inputText.length }} 字符</span>
              <el-button type="primary" :loading="translating" @click="translateText" :disabled="!inputText.trim()">
                <el-icon><Switch /></el-icon>
                开始翻译
              </el-button>
            </div>
          </div>
        </el-card>
      </div>

      <div class="right-panel">
        <el-card class="result-card" shadow="never">
          <template #header>
            <div class="card-header-row">
              <span class="card-header-title">翻译结果</span>
              <div v-if="result" class="result-meta">
                <el-tag v-if="result.from_memory" type="success" size="small">来自记忆库</el-tag>
                <el-tag v-if="result.from_ai" type="warning" size="small">来自AI引擎</el-tag>
              </div>
            </div>
          </template>

          <div v-if="!result && !translating" class="result-empty">
            <el-icon class="empty-icon"><Document /></el-icon>
            <p>翻译结果将显示在这里</p>
            <p class="sub-hint">选择翻译引擎并输入内容后点击开始翻译</p>
          </div>

          <div v-if="translating" class="result-loading">
            <div class="loading-spinner"></div>
            <p>正在翻译中，请稍候...</p>
          </div>

          <div v-if="result && !translating" class="result-content">
            <div class="result-section">
              <h4>原文</h4>
              <div class="result-text original-text">{{ result.original }}</div>
            </div>
            <el-divider />
            <div class="result-section">
              <h4>译文</h4>
              <div class="result-text translated-text">{{ result.translated }}</div>
            </div>
            <div class="result-actions">
              <el-button size="small" @click="copyResult">
                <el-icon><CopyDocument /></el-icon>
                复制译文
              </el-button>
              <el-button size="small" @click="downloadResult">
                <el-icon><Download /></el-icon>
                下载译文
              </el-button>
            </div>
          </div>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Switch, Document, CopyDocument, Download } from '@element-plus/icons-vue'
import { translationAPI } from '@/api'

const engine = ref('hybrid')
const model = ref('qwen')
const sourceLang = ref('zh')
const targetLang = ref('en')
const inputText = ref('')
const translating = ref(false)
const result = ref(null)

function onEngineChange(val) {
  if (val === 'memory') {
    model.value = 'qwen'
  }
}

async function translateText() {
  if (!inputText.value.trim()) {
    ElMessage.warning('请输入翻译内容')
    return
  }
  translating.value = true
  result.value = null
  try {
    const res = await translationAPI.translate({
      content: inputText.value,
      engine: engine.value,
      model: engine.value === 'memory' ? 'qwen' : model.value,
      source_lang: sourceLang.value,
      target_lang: targetLang.value
    })
    result.value = res.data
    ElMessage.success('翻译完成')
  } catch (e) {
    ElMessage.error('翻译失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    translating.value = false
  }
}

function copyResult() {
  if (result.value?.translated) {
    navigator.clipboard.writeText(result.value.translated).then(() => {
      ElMessage.success('已复制到剪贴板')
    }).catch(() => {
      ElMessage.error('复制失败')
    })
  }
}

function downloadResult() {
  if (result.value?.translated) {
    const blob = new Blob([result.value.translated], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `translation_${Date.now()}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }
}
</script>

<style scoped>
.translate-container {
  padding: 0;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 4px;
}

.page-desc {
  font-size: 14px;
  color: #6b7280;
}

.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  align-items: start;
}

.card-header-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.config-card {
  margin-bottom: 16px;
}

.text-input-area :deep(.el-textarea__inner) {
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.7;
}

.input-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}

.char-count {
  font-size: 13px;
  color: #9ca3af;
}

.result-meta {
  display: flex;
  gap: 6px;
}

.result-empty {
  text-align: center;
  padding: 60px 20px;
  color: #9ca3af;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.sub-hint {
  font-size: 13px;
  margin-top: 6px;
  color: #c0c4cc;
}

.result-loading {
  text-align: center;
  padding: 60px 20px;
  color: #6b7280;
}

.loading-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid #dbeafe;
  border-top: 3px solid #2563eb;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.result-content {
  padding: 0;
}

.result-section h4 {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 10px;
}

.result-text {
  background: #f8fafc;
  border-radius: 8px;
  padding: 16px;
  font-size: 14px;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}

.original-text {
  color: #64748b;
}

.translated-text {
  color: #1f2937;
}

.result-actions {
  display: flex;
  gap: 10px;
  margin-top: 16px;
}

@media (max-width: 1024px) {
  .content-grid {
    grid-template-columns: 1fr;
  }
}
</style>
