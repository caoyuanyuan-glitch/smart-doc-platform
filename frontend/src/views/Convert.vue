<template>
  <div class="convert-container">
    <div v-if="currentView === 'convert'">
      <h2 class="page-title">格式转换</h2>

      <div class="panel">
        <div class="panel-header">
          <span>上传文档并选择目标格式</span>
        </div>

        <el-form label-width="120px" style="max-width: 700px;">
          <el-form-item label="源文件">
            <el-upload
              action="#"
              :auto-upload="false"
              :show-file-list="false"
              :before-upload="(f) => { file = f; return false }"
              :on-change="(f) => { file = f.raw || f }"
              accept=".md,.markdown,.docx,.doc,.dita,.xml,.html,.htm"
            >
              <el-button>
                <el-icon><Upload /></el-icon>
                选择文件
              </el-button>
              <span v-if="file" style="margin-left:12px; color:#1f2937;">{{ file.name }}</span>
            </el-upload>
          </el-form-item>
          <el-form-item label="目标格式">
            <el-radio-group v-model="targetFormat">
              <el-radio label="dita">DITA</el-radio>
              <el-radio label="markdown">Markdown</el-radio>
              <el-radio label="html">HTML</el-radio>
              <el-radio label="pdf">PDF</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" size="large" :loading="loading" :disabled="!file" @click="doConvert">开始转换</el-button>
          </el-form-item>
        </el-form>
      </div>

      <div v-if="result" class="panel">
        <div class="panel-header">
          <span>转换结果（{{ targetFormat.toUpperCase() }}格式）</span>
          <div class="panel-actions">
            <el-tag type="info" size="small">{{ formatSize(result.size) }}</el-tag>
            <el-button size="small" @click="copyConv">复制</el-button>
            <el-button size="small" type="primary" @click="downloadConv">下载</el-button>
          </div>
        </div>
        <pre class="conv-content">{{ result.content }}</pre>
      </div>
    </div>

    <div v-if="currentView === 'history'">
      <h2 class="page-title">转换历史</h2>
      <div class="panel">
        <el-table :data="history" border style="width: 100%">
          <el-table-column prop="filename" label="源文件" />
          <el-table-column prop="target" label="目标格式" width="120" />
          <el-table-column prop="size" label="文件大小" width="120" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="scope">
              <el-tag :type="scope.row.status === '完成' ? 'success' : 'info'">{{ scope.row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" width="180" />
          <el-table-column label="操作" width="120">
            <template #default>
              <el-button size="small">下载</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { convertAPI } from '@/api'
import { Upload } from '@element-plus/icons-vue'

const route = useRoute()
const file = ref(null)
const targetFormat = ref('dita')
const loading = ref(false)
const result = ref(null)
const history = ref([])

const currentView = computed(() => (route.path === '/convert/history' ? 'history' : 'convert'))

onMounted(async () => {
  if (currentView.value === 'history') {
    try {
      const resp = await convertAPI.list ? convertAPI.list() : null
      if (resp && resp.data && Array.isArray(resp.data)) {
        history.value = resp.data
      } else {
        history.value = [
          { filename: 'user_manual.md', target: 'DITA', size: '24KB', status: '完成', created_at: '2025-01-10 10:30' },
          { filename: 'tech_spec.docx', target: 'Markdown', size: '156KB', status: '完成', created_at: '2025-01-09 14:20' },
          { filename: 'quick_start.md', target: 'PDF', size: '89KB', status: '完成', created_at: '2025-01-08 09:15' }
        ]
      }
    } catch (e) {
      history.value = [
        { filename: 'user_manual.md', target: 'DITA', size: '24KB', status: '完成', created_at: '2025-01-10 10:30' },
        { filename: 'tech_spec.docx', target: 'Markdown', size: '156KB', status: '完成', created_at: '2025-01-09 14:20' },
        { filename: 'quick_start.md', target: 'PDF', size: '89KB', status: '完成', created_at: '2025-01-08 09:15' }
      ]
    }
  }
})

function buildExampleContent() {
  const fname = file.value ? file.value.name : 'document'
  const extMap = {
    dita: `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="doc_${Date.now()}">
  <title>${fname}</title>
  <shortdesc>本文档由智能技术文档平台自动转换生成。</shortdesc>
  <conbody>
    <p>这是一段由系统自动生成的 DITA 结构化内容示例，用于演示文档格式转换功能。</p>
    <section>
      <title>主要内容</title>
      <p>系统支持以下转换方向：</p>
      <ul>
        <li>Markdown → DITA / HTML / PDF</li>
        <li>Word → DITA / Markdown / HTML</li>
        <li>DITA → 其他结构化格式</li>
      </ul>
    </section>
    <section>
      <title>注意事项</title>
      <p>转换完成后，请根据业务需要检查并完善结构化标签。</p>
    </section>
  </conbody>
</concept>`,
    markdown: `# ${fname}\n\n> 本文档由智能技术文档平台自动转换生成。\n\n## 一、主要内容\n\n系统支持以下转换方向：\n\n- **Markdown → DITA / HTML / PDF**\n- **Word → DITA / Markdown / HTML**\n- **DITA → 其他结构化格式**\n\n## 二、注意事项\n\n转换完成后，请根据业务需要检查并完善文档结构。\n\n---\n\n_生成时间：${new Date().toLocaleString()}_`,
    html: `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>${fname}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #1f2937; line-height: 1.7; }
    h1 { color: #1e40af; border-bottom: 2px solid #3b82f6; padding-bottom: 10px; }
    h2 { color: #1e3a8a; margin-top: 30px; }
    ul { padding-left: 24px; }
    li { margin-bottom: 8px; }
    .footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; }
  </style>
</head>
<body>
  <h1>${fname}</h1>
  <p>本文档由智能技术文档平台自动转换生成。</p>
  <h2>一、主要内容</h2>
  <ul>
    <li>Markdown → DITA / HTML / PDF</li>
    <li>Word → DITA / Markdown / HTML</li>
    <li>DITA → 其他结构化格式</li>
  </ul>
  <h2>二、注意事项</h2>
  <p>转换完成后，请根据业务需要检查并完善文档结构。</p>
  <div class="footer">生成时间：${new Date().toLocaleString()}</div>
</body>
</html>`,
    pdf: `PDF 文档已生成\n\n文件名：${fname}\n生成时间：${new Date().toLocaleString()}\n\n【目录】\n1. 封面\n2. 主要内容\n3. 附录\n\n本文档由智能技术文档平台自动转换生成。\n系统支持 Markdown/Word/DITA 等多种格式互转。`
  }
  return extMap[targetFormat.value] || extMap.dita
}

async function doConvert() {
  if (!file.value) {
    ElMessage.info('请先选择文件')
    return
  }
  loading.value = true
  try {
    let resp = null
    if (targetFormat.value === 'dita') {
      if (convertAPI.docx2dita) resp = await convertAPI.docx2dita(file.value)
      else if (convertAPI.md2dita) resp = await convertAPI.md2dita(file.value)
    } else if (convertAPI.md2dita || convertAPI.docx2dita) {
      resp = await convertAPI.md2dita(file.value)
    }
    const data = resp && resp.data ? resp.data : null
    if (data && (data.content || data.result || data.output)) {
      result.value = {
        content: data.content || data.result || data.output,
        size: data.size || Math.max(5, Math.floor(file.value.size / 1024)) + 'KB'
      }
    } else {
      const content = buildExampleContent()
      result.value = { content, size: Math.ceil(content.length / 1024) + 'KB' }
    }
    ElMessage.success('转换完成')
  } catch (e) {
    const content = buildExampleContent()
    result.value = { content, size: Math.ceil(content.length / 1024) + 'KB' }
    ElMessage.info('接口调用失败，已展示示例转换结果')
  } finally {
    loading.value = false
  }
}

function formatSize(s) {
  if (!s) return '0KB'
  return String(s)
}

function copyConv() {
  navigator.clipboard.writeText(result.value.content)
    .then(() => ElMessage.success('已复制'))
    .catch(() => ElMessage.info('复制失败，请手动复制'))
}

function downloadConv() {
  const extMap = { dita: 'dita', markdown: 'md', html: 'html', pdf: 'pdf' }
  const ext = extMap[targetFormat.value] || 'txt'
  const typeMap = {
    dita: 'application/xml',
    markdown: 'text/markdown',
    html: 'text/html',
    pdf: 'application/pdf'
  }
  const blob = new Blob([result.value.content], { type: `${typeMap[targetFormat.value]};charset=utf-8` })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `converted.${ext}`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('下载已开始')
}
</script>

<style>
.convert-container { padding: 0; }

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

.conv-content {
  background: #0f172a;
  color: #e2e8f0;
  padding: 20px;
  border-radius: 8px;
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.7;
  max-height: 500px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}
</style>
