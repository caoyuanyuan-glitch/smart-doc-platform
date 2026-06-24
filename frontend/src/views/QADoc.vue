<template>
  <div class="qa-container">
    <h2 class="page-title">文档对话</h2>

    <div class="qa-layout">
      <aside class="knowledge-panel">
        <div class="panel-title">上传文档</div>
        <div class="upload-area" @click="triggerUpload" @dragover.prevent @drop.prevent="handleDrop">
          <el-icon class="upload-icon"><UploadFilled /></el-icon>
          <p v-if="uploadedFiles.length === 0">点击或拖拽文件到此处上传</p>
          <p v-else class="upload-hint">点击继续添加文件</p>
          <p class="upload-formats">支持 PDF、DOCX、TXT、Excel 格式</p>
          <input ref="fileInput" type="file" multiple accept=".pdf,.docx,.txt,.xlsx,.xls,.md" style="display:none" @change="handleFileChange" />
        </div>
        <div v-if="uploadedFiles.length > 0" class="file-list">
          <div class="file-list-title">已上传文档 ({{ uploadedFiles.length }})</div>
          <div v-for="(f, i) in uploadedFiles" :key="i" class="file-item">
            <el-icon :style="{ color: fileIconColor(f.name) }"><Document /></el-icon>
            <span class="file-name" @click="previewFile(i)" :title="'点击预览: ' + f.name">{{ f.name }}</span>
            <el-icon class="file-remove" @click="removeFile(i)"><Close /></el-icon>
          </div>
          <el-button class="clear-btn" size="small" text type="danger" @click="clearFiles">清空全部</el-button>
        </div>
        <div v-if="uploadedFiles.length === 0" class="upload-hint-text">上传文档后即可开始对话，AI 将仅基于您上传的文档内容回答。</div>
      </aside>

      <section class="chat-panel">
        <div class="chat-toolbar">
          <el-button size="small" text @click="copyAll" :disabled="messages.length <= 1">
            <el-icon><CopyDocument /></el-icon> 复制全文
          </el-button>
          <el-dropdown @command="handleExport">
            <el-button size="small" text :disabled="messages.length <= 1">
              <el-icon><Download /></el-icon> 导出
              <el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="md">Markdown (.md)</el-dropdown-item>
                <el-dropdown-item command="word">Word (.doc)</el-dropdown-item>
                <el-dropdown-item command="pdf">PDF (.pdf)</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <div class="chat-messages" ref="chatBox">
          <div v-for="(msg, i) in messages" :key="i" class="message" :class="msg.role">
            <div class="avatar" :class="msg.role">
              <el-icon v-if="msg.role === 'user'"><User /></el-icon>
              <el-icon v-else>
                <svg viewBox="0 0 32 32" fill="none" style="width:18px;height:18px">
                  <line x1="16" y1="2" x2="16" y2="6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                  <circle cx="16" cy="1.5" r="1.5" fill="#f59e0b"/>
                  <rect x="5" y="6" width="22" height="19" rx="6" stroke="currentColor" stroke-width="1.5"/>
                  <circle cx="11" cy="14" r="2.5" stroke="currentColor" stroke-width="1.2" fill="#1e40af"/>
                  <circle cx="21" cy="14" r="2.5" stroke="currentColor" stroke-width="1.2" fill="#1e40af"/>
                  <circle cx="11" cy="14" r="1.2" fill="currentColor"/>
                  <circle cx="21" cy="14" r="1.2" fill="currentColor"/>
                  <path d="M11 21 Q16 24 21 21" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" fill="none"/>
                </svg>
              </el-icon>
            </div>
            <div class="bubble-wrap">
              <div class="bubble">{{ msg.content }}</div>
              <div v-if="msg.sources && msg.sources.length" class="sources">
                <div class="sources-title">参考来源：</div>
                <div v-for="(s, si) in msg.sources" :key="si" class="source-item">{{ s.title || s }}</div>
              </div>
              <div v-if="msg.role === 'assistant' && i > 0" class="feedback-row">
                <div class="feedback-actions">
                  <span class="feedback-label">评价：</span>
                  <el-button :type="msg.rating === 1 ? 'primary' : 'default'" size="small" circle @click="rateAnswer(i, 1)">👍</el-button>
                  <el-button :type="msg.rating === -1 ? 'danger' : 'default'" size="small" circle @click="rateAnswer(i, -1)">👎</el-button>
                </div>
                <el-divider direction="vertical" />
                <el-button size="small" text type="warning" @click="openFeedbackDialog(i)">内容有误？点此反馈</el-button>
              </div>
            </div>
          </div>
          <div v-if="loading" class="message assistant">
            <div class="avatar assistant">
              <el-icon>
                <svg viewBox="0 0 32 32" fill="none" style="width:18px;height:18px">
                  <line x1="16" y1="2" x2="16" y2="6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                  <circle cx="16" cy="1.5" r="1.5" fill="#f59e0b"/>
                  <rect x="5" y="6" width="22" height="19" rx="6" stroke="currentColor" stroke-width="1.5"/>
                  <circle cx="11" cy="14" r="2.5" stroke="currentColor" stroke-width="1.2" fill="#1e40af"/>
                  <circle cx="21" cy="14" r="2.5" stroke="currentColor" stroke-width="1.2" fill="#1e40af"/>
                  <circle cx="11" cy="14" r="1.2" fill="currentColor"/>
                  <circle cx="21" cy="14" r="1.2" fill="currentColor"/>
                  <path d="M11 21 Q16 24 21 21" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" fill="none"/>
                </svg>
              </el-icon>
            </div>
            <div class="bubble typing">正在分析文档内容<span class="dots">...</span></div>
          </div>
        </div>
        <div class="chat-input">
          <el-input
            v-model="question"
            type="textarea"
            :rows="2"
            placeholder="请输入您的问题，按Enter发送..."
            :disabled="uploadedFiles.length === 0"
            @keydown.enter.exact.prevent="sendQuestion(question)"
          />
          <el-button class="voice-btn" :class="{ recording: isRecording }" @click="toggleVoice" :disabled="uploadedFiles.length === 0">
            <el-icon><Microphone /></el-icon>
          </el-button>
          <el-button type="primary" :loading="loading" @click="sendQuestion(question)" :disabled="uploadedFiles.length === 0">发送</el-button>
        </div>
      </section>
    </div>

    <el-dialog v-model="feedbackVisible" title="反馈内容有误" width="500px">
      <el-form label-position="top">
        <el-form-item label="问题">
          <div class="feedback-preview-text">{{ currentFeedbackQuestion }}</div>
        </el-form-item>
        <el-form-item label="AI回答">
          <div class="feedback-preview-text">{{ currentFeedbackAnswer }}</div>
        </el-form-item>
        <el-form-item label="错误描述">
          <el-input v-model="feedbackText" type="textarea" :rows="4" placeholder="请描述回答中的错误之处..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="feedbackVisible = false">取消</el-button>
        <el-button type="primary" @click="submitFeedback">提交反馈</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" :title="'预览: ' + previewFilename" width="700px" top="5vh">
      <div class="preview-content" v-loading="previewLoading">
        <div v-if="previewHtml" class="doc-preview-rendered" v-html="previewHtml"></div>
        <div v-else-if="!previewLoading" class="preview-empty">无法读取该文件内容</div>
        <div v-if="previewTruncated" class="preview-truncated-notice">（内容较长，仅显示前 10000 字符）</div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, nextTick, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { qaAPI } from '@/api'
import { useUserStore } from '@/store/user'
import { User, UploadFilled, Document, Close, Microphone, CopyDocument, Download, ArrowDown } from '@element-plus/icons-vue'

const question = ref('')
const loading = ref(false)
const chatBox = ref(null)
const fileInput = ref(null)
const uploadedFiles = ref([])

const messages = ref([
  { role: 'assistant', content: '您好！请先上传您想要提问的文档，上传后即可针对文档内容进行对话。AI 将仅基于您上传的文档回答，不会使用外部知识。', sources: [], rating: 0 }
])

const feedbackVisible = ref(false)
const feedbackText = ref('')
const currentFeedbackQuestion = ref('')
const currentFeedbackAnswer = ref('')
const currentFeedbackIndex = ref(-1)

const isRecording = ref(false)
let recognition = null

const previewVisible = ref(false)
const previewContent = ref('')
const previewHtml = ref('')
const previewFilename = ref('')
const previewLoading = ref(false)
const previewTruncated = ref(false)

const refreshFeedbackCount = inject('refreshFeedbackCount', null)
const userStore = useUserStore()
const sessionId = ref(null)

function triggerUpload() {
  fileInput.value?.click()
}

function handleFileChange(e) {
  const files = Array.from(e.target.files || [])
  addFiles(files)
  e.target.value = ''
}

function handleDrop(e) {
  const files = Array.from(e.dataTransfer.files || [])
  addFiles(files)
}

function addFiles(files) {
  const allowed = ['.pdf', '.docx', '.txt', '.xlsx', '.xls', '.md']
  for (const f of files) {
    const ext = '.' + f.name.split('.').pop().toLowerCase()
    if (allowed.includes(ext)) {
      if (!uploadedFiles.value.find(u => u.name === f.name && u.size === f.size)) {
        uploadedFiles.value.push(f)
      }
    } else {
      ElMessage.warning(`不支持的文件格式: ${f.name}`)
    }
  }
  if (uploadedFiles.value.length > 0) {
    ElMessage.success(`已添加 ${uploadedFiles.value.length} 个文件`)
  }
}

function removeFile(i) {
  uploadedFiles.value.splice(i, 1)
}

function clearFiles() {
  uploadedFiles.value = []
  messages.value = [
    { role: 'assistant', content: '您好！请先上传您想要提问的文档，上传后即可针对文档内容进行对话。AI 将仅基于您上传的文档回答，不会使用外部知识。', sources: [], rating: 0 }
  ]
}

async function previewFile(i) {
  const file = uploadedFiles.value[i]
  if (!file) return
  previewVisible.value = true
  previewFilename.value = file.name
  previewContent.value = ''
  previewHtml.value = ''
  previewLoading.value = true
  try {
    const resp = await qaAPI.previewDoc(file)
    previewContent.value = resp.data.content || ''
    previewHtml.value = resp.data.preview_html || ''
    previewTruncated.value = resp.data.truncated || false
  } catch {
    previewContent.value = ''
    previewHtml.value = ''
    ElMessage.warning('预览失败，请重试')
  }
  previewLoading.value = false
}

function fileIconColor(name) {
  const ext = name.split('.').pop()?.toLowerCase()
  const colors = { pdf: '#ef4444', docx: '#3b82f6', txt: '#6b7280', xlsx: '#10b981', xls: '#10b981', md: '#7c3aed' }
  return colors[ext] || '#6b7280'
}

async function sendQuestion(q) {
  const text = (typeof q === 'string' ? q : question.value).trim()
  if (!text) return
  if (uploadedFiles.value.length === 0) {
    ElMessage.info('请先上传文档')
    return
  }
  messages.value.push({ role: 'user', content: text, sources: [], rating: 0 })
  question.value = ''
  loading.value = true
  await nextTick()
  scrollToBottom()

  try {
    const resp = await qaAPI.askDocs(text, uploadedFiles.value, sessionId.value)
    const data = resp.data
    if (data.session_id) sessionId.value = data.session_id
    messages.value.push({
      role: 'assistant',
      content: data.answer || '未能从文档中找到相关信息。',
      sources: data.sources || data.files?.map(f => ({ title: f })) || [],
      rating: 0
    })
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: '抱歉，处理文档时出现错误，请稍后重试。',
      sources: [],
      rating: 0
    })
  }
  loading.value = false
  await nextTick()
  scrollToBottom()
}

function buildMarkdown() {
  const now = new Date().toLocaleString('zh-CN')
  let md = `# 文档对话会话 — ${now}

> 共 ${Math.floor(messages.value.length / 2)} 轮对话

`
  for (let i = 0; i < messages.value.length; i++) {
    const msg = messages.value[i]
    if (msg.role === 'user') {
      md += `## Q: ${msg.content}\n\n**AI 回答：**\n`
    } else if (msg.role === 'assistant') {
      md += msg.content + '\n'
      if (msg.sources && msg.sources.length) {
        md += '\n> 参考来源：' + msg.sources.map(s => s.title || s).join('、') + '\n'
      }
      if (msg.rating === 1) md += '> 评价：👍 有帮助\n'
      if (msg.rating === -1) md += '> 评价：👎 无帮助\n'
      md += '\n---\n\n'
    }
  }
  return md
}

function buildHtml() {
  const now = new Date().toLocaleString('zh-CN')
  let html = `<html><head><meta charset="utf-8"><title>文档对话会话</title>
<style>body{font-family:"Microsoft YaHei",sans-serif;max-width:800px;margin:40px auto;line-height:1.8}
h1{border-bottom:2px solid #2563eb;padding-bottom:8px}
.q{margin-top:24px;font-weight:600;color:#1e40af}.a{background:#f8fafc;padding:12px 16px;border-radius:8px;margin:8px 0}
.src{color:#94a3b8;font-size:13px}.bar{color:#94a3b8;margin:24px 0;text-align:center}</style></head><body>
<h1>文档对话会话 — ${now}</h1>
<p class="src">共 ${Math.floor(messages.value.length / 2)} 轮对话</p>
`
  for (let i = 0; i < messages.value.length; i++) {
    const msg = messages.value[i]
    if (msg.role === 'user') {
      html += `<div class="q">Q: ${escapeHtml(msg.content)}</div>`
    } else if (msg.role === 'assistant') {
      html += `<div class="a">${escapeHtml(msg.content)}</div>`
      if (msg.sources && msg.sources.length) {
        html += `<p class="src">参考来源：${escapeHtml(msg.sources.map(s => s.title || s).join('、'))}</p>`
      }
      if (msg.rating === 1) html += '<p class="src">评价：👍 有帮助</p>'
      if (msg.rating === -1) html += '<p class="src">评价：👎 无帮助</p>'
      html += '<div class="bar">———</div>'
    }
  }
  html += '</body></html>'
  return html
}

function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

function downloadFile(content, filename, mime) {
  const blob = new Blob(['\uFEFF' + content], { type: mime + ';charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function copyAll() {
  try {
    await navigator.clipboard.writeText(buildMarkdown())
    ElMessage.success('全文已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请重试')
  }
}

function handleExport(format) {
  if (messages.value.length <= 1) return
  const ts = new Date().toISOString().replace(/[:.]/g, '').substring(0, 15)
  if (format === 'md') {
    downloadFile(buildMarkdown(), `QA_文档对话_${ts}.md`, 'text/markdown')
  } else if (format === 'word') {
    downloadFile(buildHtml(), `QA_文档对话_${ts}.doc`, 'application/msword')
  } else if (format === 'pdf') {
    const w = window.open('', '_blank')
    w.document.write(buildHtml())
    w.document.close()
    w.onload = () => w.print()
  }
}

function rateAnswer(idx, rating) {
  const msg = messages.value[idx]
  msg.rating = msg.rating === rating ? 0 : rating
  qaAPI.submitFeedback({
    question: messages.value[idx - 1]?.content || '',
    answer: msg.content,
    rating: msg.rating,
    feedback_text: ''
  }).then(() => {
    if (userStore.isAdmin && userStore.isLoggedIn && refreshFeedbackCount) refreshFeedbackCount()
  }).catch(() => {})
}

async function submitFeedback() {
  try {
    await qaAPI.submitFeedback({
      question: currentFeedbackQuestion.value,
      answer: currentFeedbackAnswer.value,
      rating: -1,
      feedback_text: feedbackText.value
    })
    ElMessage.success('感谢您的反馈，管理员会尽快处理')
    feedbackVisible.value = false
    if (userStore.isAdmin && userStore.isLoggedIn && refreshFeedbackCount) refreshFeedbackCount()
  } catch (e) {
    ElMessage.error('反馈提交失败')
  }
}

function toggleVoice() {
  if (isRecording.value) {
    stopVoice()
    return
  }
  startVoice()
}

function startVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SpeechRecognition) {
    ElMessage.warning('您的浏览器不支持语音输入')
    return
  }
  recognition = new SpeechRecognition()
  recognition.lang = 'zh-CN'
  recognition.interimResults = false
  recognition.continuous = false
  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript
    question.value = (question.value + ' ' + transcript).trim()
  }
  recognition.onerror = () => {
    isRecording.value = false
    ElMessage.warning('语音识别失败，请重试')
  }
  recognition.onend = () => { isRecording.value = false }
  recognition.start()
  isRecording.value = true
}

function stopVoice() {
  if (recognition) {
    recognition.stop()
    isRecording.value = false
  }
}

function scrollToBottom() {
  if (chatBox.value) {
    chatBox.value.scrollTop = chatBox.value.scrollHeight
  }
}
</script>

<style scoped>
.qa-container { padding: 0; }

.page-title {
  font-size: 20px; font-weight: 600; color: #1f2937; margin-bottom: 20px;
}

.qa-layout {
  display: grid; grid-template-columns: 320px 1fr; gap: 20px; min-height: 600px;
}

.knowledge-panel {
  background: #fff; border-radius: 10px; padding: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  max-height: calc(100vh - 180px); overflow-y: auto;
}

.panel-title {
  font-weight: 600; color: #1f2937; margin-bottom: 12px;
  padding-bottom: 8px; border-bottom: 1px solid #f0f0f0;
}

.upload-area {
  border: 2px dashed #d1d5db; border-radius: 10px;
  padding: 24px 16px; text-align: center; cursor: pointer;
  transition: all 0.2s; color: #6b7280; font-size: 13px;
}
.upload-area:hover { border-color: #3b82f6; background: #f0f7ff; }
.upload-icon { font-size: 32px; color: #3b82f6; margin-bottom: 8px; }
.upload-formats { font-size: 12px; color: #9ca3af; margin-top: 6px; }
.upload-hint { color: #3b82f6; }
.upload-hint-text { margin-top: 16px; font-size: 13px; color: #94a3b8; line-height: 1.6; }

.file-list { margin-top: 16px; }
.file-list-title { font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 8px; }
.file-item {
  display: flex; align-items: center; padding: 8px 10px;
  background: #f8fafc; border-radius: 6px; margin-bottom: 4px;
}
.file-name { flex: 1; font-size: 13px; color: #374151; margin-left: 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
.file-name:hover { color: #3b82f6; text-decoration: underline; }
.file-remove { color: #ef4444; cursor: pointer; flex-shrink: 0; }
.clear-btn { margin-top: 8px; }

.chat-panel {
  background: #fff; border-radius: 10px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  display: flex; flex-direction: column; overflow: hidden;
}

.chat-toolbar {
  display: flex; gap: 8px; padding: 8px 16px;
  border-bottom: 1px solid #f0f0f0; justify-content: flex-end;
}

.chat-messages {
  flex: 1; padding: 20px; overflow-y: auto; background: #f8fafc;
  min-height: 500px; max-height: calc(100vh - 300px);
}

.message { display: flex; margin-bottom: 20px; gap: 10px; }
.message.user { flex-direction: row-reverse; }

.avatar {
  width: 36px; height: 36px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  color: #fff; flex-shrink: 0;
}
.avatar.user { background: #3b82f6; }
.avatar.assistant { background: #409EFF; }

.bubble-wrap { max-width: 70%; }

.bubble {
  padding: 12px 16px; border-radius: 12px;
  line-height: 1.7; color: #374151; font-size: 14px; white-space: pre-wrap;
}
.message.user .bubble { background: #3b82f6; color: #fff; border-bottom-right-radius: 4px; }
.message.assistant .bubble { background: #fff; border: 1px solid #e5e7eb; border-bottom-left-radius: 4px; }

.sources {
  margin-top: 8px; padding: 10px 12px;
  background: #f1f5f9; border-radius: 8px; font-size: 12px;
}
.sources-title { color: #64748b; margin-bottom: 4px; font-weight: 500; }
.source-item { color: #475569; padding: 2px 0; }

.feedback-row {
  display: flex; align-items: center; gap: 6px; margin-top: 10px;
  padding-top: 8px; border-top: 1px solid #f0f0f0;
}

.feedback-actions {
  display: flex; align-items: center; gap: 4px;
}

.feedback-label {
  font-size: 12px; color: #94a3b8; margin-right: 2px;
}

.typing { color: #94a3b8; font-style: italic; }

.chat-input {
  display: flex; gap: 10px; padding: 16px;
  border-top: 1px solid #e5e7eb; background: #fff; align-items: flex-end;
}
.chat-input .el-textarea { flex: 1; }
.voice-btn {
  width: 40px; height: 40px; border-radius: 50%; padding: 0;
}
.voice-btn.recording {
  background: #ef4444; color: #fff; border-color: #ef4444;
  animation: pulse 1.2s infinite;
}
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0.4); }
  50% { box-shadow: 0 0 0 8px rgba(239,68,68,0); }
}

.feedback-preview-text {
  background: #f8fafc; border-radius: 6px; padding: 10px;
  font-size: 13px; color: #475569; max-height: 120px; overflow-y: auto;
}

.preview-content { min-height: 200px; }
.doc-preview,
:deep(.doc-preview) {
  background: #f8fafc; padding: 16px; border-radius: 8px;
  font-size: 13px; line-height: 1.8; color: #374151;
  max-height: 60vh; overflow-y: auto; white-space: pre-wrap; word-break: break-all;
}
.preview-empty { text-align: center; color: #94a3b8; padding: 40px; }
.preview-truncated-notice { margin-top: 10px; font-size: 12px; color: #f59e0b; }

.doc-preview-rendered {
  max-height: 70vh; overflow-y: auto; background: #f8fafc;
  border-radius: 8px; padding: 16px; color: #374151; line-height: 1.8;
}

:deep(.doc-preview-html p) { margin: 0 0 10px; }
:deep(.doc-preview-inline-image) {
  display: block; max-width: 100%; max-height: 420px; object-fit: contain;
  margin: 10px 0; border-radius: 6px; background: #fff;
  border: 1px solid #e5e7eb;
}
:deep(.doc-preview-table) {
  width: 100%; border-collapse: collapse; margin: 10px 0; background: #fff;
}
:deep(.doc-preview-table td) {
  border: 1px solid #e5e7eb; padding: 8px; vertical-align: top;
}
:deep(.doc-preview-page) {
  margin: 0 0 16px; padding: 10px; border: 1px solid #e5e7eb;
  border-radius: 8px; background: #fff;
}
:deep(.doc-preview-page img) { width: 100%; display: block; }
:deep(.doc-preview-page figcaption) {
  margin-top: 8px; text-align: center; color: #64748b; font-size: 12px;
}
:deep(.doc-preview-sheet h4) { margin: 12px 0 8px; color: #1e40af; }

@media (max-width: 900px) {
  .qa-layout { grid-template-columns: 1fr; }
}
</style>
