<template>
  <div class="qa-container">
    <h2 class="page-title">知识库问答</h2>

    <div class="qa-layout">
      <aside class="knowledge-panel">
        <div class="panel-header-row">
          <span class="panel-title">文件夹结构</span>
          <el-button text size="small" @click="expandAll">{{ treeExpanded ? '折叠全部' : '展开全部' }}</el-button>
        </div>
        <div v-if="treeLoading" class="tree-loading">加载中...</div>
        <el-tree
          v-else
          ref="treeRef"
          :data="treeData"
          show-checkbox
          node-key="id"
          :props="treeProps"
          :default-expand-all="false"
          :check-strictly="false"
          :expand-on-click-node="true"
          @check="handleTreeCheck"
        >
          <template #default="{ node, data }">
            <span class="tree-node">
              <el-icon class="tree-folder-icon"><Folder /></el-icon>
              <span class="tree-node-label">{{ node.label }}</span>
              <span class="tree-node-count" v-if="data.docCount > 0">{{ data.docCount }}个文档</span>
              <span class="tree-node-count empty" v-else>空</span>
            </span>
          </template>
        </el-tree>
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
          <div
            v-if="checkedLabels.length > 0"
            class="selected-tags"
          >
            <span class="selected-tags-label">已选知识库：</span>
            <el-tag
              v-for="label in checkedLabels"
              :key="label"
              size="small"
              closable
              @close="removeTag(label)"
            >{{ label }}</el-tag>
          </div>
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
            <div class="bubble typing">正在分析知识库内容<span class="dots">...</span></div>
          </div>
        </div>
        <div class="chat-input">
          <el-input
            v-model="question"
            type="textarea"
            :rows="2"
            placeholder="请输入您的问题，按Enter发送..."
            @keydown.enter.exact.prevent="sendQuestion(question)"
          />
          <el-button class="voice-btn" :class="{ recording: isRecording }" @click="toggleVoice">
            <el-icon><Microphone /></el-icon>
          </el-button>
          <el-button type="primary" :loading="loading" @click="sendQuestion(question)">发送</el-button>
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
  </div>
</template>

<script setup>
import { ref, nextTick, computed, onMounted, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { qaAPI, knowledgeAPI } from '@/api'
import { useUserStore } from '@/store/user'
import { User, Folder, Microphone, CopyDocument, Download, ArrowDown } from '@element-plus/icons-vue'

const question = ref('')
const loading = ref(false)
const chatBox = ref(null)
const treeRef = ref(null)
const treeData = ref([])
const treeLoading = ref(false)
const treeExpanded = ref(false)
const checkedIds = ref([])
const checkedLabels = ref([])

const treeProps = { children: 'children', label: 'name' }

const messages = ref([
  { role: 'assistant', content: '您好！我是智能文档助手。请在左侧文件夹树中勾选知识库，然后向我提问。', sources: [], rating: 0 }
])

const feedbackVisible = ref(false)
const feedbackText = ref('')
const currentFeedbackQuestion = ref('')
const currentFeedbackAnswer = ref('')
const currentFeedbackIndex = ref(-1)

const isRecording = ref(false)
let recognition = null

const refreshFeedbackCount = inject('refreshFeedbackCount', null)
const userStore = useUserStore()
const sessionId = ref(null)

onMounted(() => {
  loadKnowledgeTree()
})

async function loadKnowledgeTree() {
  treeLoading.value = true
  try {
    const resp = await knowledgeAPI.getTree()
    const rawTree = resp.data || []
    treeData.value = transformTreeData(rawTree)
  } catch (e) {
    ElMessage.warning('加载知识库失败')
  }
  treeLoading.value = false
}

function countRecursiveDocs(node) {
  let count = (node.files || []).length
  if (node.children && node.children.length) {
    for (const child of node.children) {
      count += countRecursiveDocs(child)
    }
  }
  return count
}

function transformTreeData(nodes) {
  return nodes.map(node => {
    const docCount = countRecursiveDocs(node)
    return {
      id: node.id,
      name: node.name,
      docCount,
      children: node.children && node.children.length ? transformTreeData(node.children) : []
    }
  })
}

function expandAll() {
  treeExpanded.value = !treeExpanded.value
  if (treeExpanded.value) {
    expandAllNodes(treeData.value)
  } else {
    collapseAllNodes(treeData.value)
  }
}

function expandAllNodes(nodes) {
  for (const node of nodes) {
    treeRef.value?.store?.nodesMap?.[node.id]?.expand()
    if (node.children && node.children.length) {
      expandAllNodes(node.children)
    }
  }
}

function collapseAllNodes(nodes) {
  for (const node of nodes) {
    treeRef.value?.store?.nodesMap?.[node.id]?.collapse()
    if (node.children && node.children.length) {
      collapseAllNodes(node.children)
    }
  }
}

function handleTreeCheck() {
  const checked = treeRef.value?.getCheckedNodes(false, false) || []
  const halfChecked = treeRef.value?.getHalfCheckedNodes() || []
  checkedIds.value = [...checked.map(n => n.id), ...halfChecked.map(n => n.id)]
  checkedLabels.value = checked.map(n => getNodePath(n))
}

function getNodePath(node) {
  if (!node) return ''
  let nodeData = node
  const parts = [nodeData.name || nodeData.label]
  let current = node
  while (current.parent && current.parent.level > 0) {
    parts.unshift(current.parent.data?.name || current.parent.label)
    current = current.parent
  }
  return parts.join(' / ')
}

function removeTag(label) {
  const pathParts = label.split(' / ')
  const leafName = pathParts[pathParts.length - 1]
  const nodes = treeRef.value?.getCheckedNodes(false, false) || []
  const target = nodes.find(n => (n.name || n.label) === leafName)
  if (target) {
    treeRef.value?.setChecked(target.id, false, true)
    handleTreeCheck()
  }
}

async function sendQuestion(q) {
  const text = (typeof q === 'string' ? q : question.value).trim()
  if (!text) return
  const checked = treeRef.value?.getCheckedNodes(false, false) || []
  const ids = checked.map(n => n.id)
  if (ids.length === 0) {
    ElMessage.info('请至少选择一个知识库')
    return
  }
  messages.value.push({ role: 'user', content: text, sources: [], rating: 0 })
  question.value = ''
  loading.value = true
  await nextTick()
  scrollToBottom()

  try {
    const resp = await qaAPI.askGeneral(text, ids, sessionId.value)
    const data = resp.data
    if (data.session_id) sessionId.value = data.session_id
    messages.value.push({
      role: 'assistant',
      content: data.answer || '知识库中未找到相关信息。',
      sources: data.sources || [],
      rating: 0
    })
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: '抱歉，查询知识库时出现错误，请稍后重试。',
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
  let md = `# 知识库问答会话 — ${now}

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
  let html = `<html><head><meta charset="utf-8"><title>知识库问答会话</title>
<style>body{font-family:"Microsoft YaHei",sans-serif;max-width:800px;margin:40px auto;line-height:1.8}
h1{border-bottom:2px solid #2563eb;padding-bottom:8px}
.q{margin-top:24px;font-weight:600;color:#1e40af}.a{background:#f8fafc;padding:12px 16px;border-radius:8px;margin:8px 0}
.src{color:#94a3b8;font-size:13px}.bar{color:#94a3b8;margin:24px 0;text-align:center}</style></head><body>
<h1>知识库问答会话 — ${now}</h1>
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
    downloadFile(buildMarkdown(), `QA_会话_${ts}.md`, 'text/markdown')
  } else if (format === 'word') {
    downloadFile(buildHtml(), `QA_会话_${ts}.doc`, 'application/msword')
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

function openFeedbackDialog(idx) {
  currentFeedbackIndex.value = idx
  currentFeedbackQuestion.value = messages.value[idx - 1]?.content || ''
  currentFeedbackAnswer.value = messages.value[idx].content
  feedbackText.value = ''
  feedbackVisible.value = true
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
  if (isRecording.value) { stopVoice(); return }
  startVoice()
}

function startVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SpeechRecognition) { ElMessage.warning('您的浏览器不支持语音输入'); return }
  recognition = new SpeechRecognition()
  recognition.lang = 'zh-CN'
  recognition.interimResults = false
  recognition.continuous = false
  recognition.onresult = (event) => {
    question.value = (question.value + ' ' + event.results[0][0].transcript).trim()
  }
  recognition.onerror = () => { isRecording.value = false; ElMessage.warning('语音识别失败') }
  recognition.onend = () => { isRecording.value = false }
  recognition.start()
  isRecording.value = true
}

function stopVoice() {
  if (recognition) { recognition.stop(); isRecording.value = false }
}

function scrollToBottom() {
  if (chatBox.value) { chatBox.value.scrollTop = chatBox.value.scrollHeight }
}
</script>

<style scoped>
.qa-container { padding: 0; }

.page-title {
  font-size: 20px; font-weight: 600; color: #1f2937; margin-bottom: 20px;
}

.qa-layout {
  display: grid; grid-template-columns: 300px 1fr; gap: 20px; min-height: 600px;
}

.knowledge-panel {
  background: #fff; border-radius: 10px; padding: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  max-height: calc(100vh - 180px); overflow-y: auto;
}

.panel-header-row {
  display: flex; justify-content: space-between; align-items: center;
  padding-bottom: 8px; margin-bottom: 8px; border-bottom: 1px solid #f0f0f0;
}
.panel-title { font-weight: 600; color: #1f2937; }

.tree-loading { color: #94a3b8; padding: 20px; text-align: center; }

.tree-node {
  display: flex; align-items: center; flex: 1; min-width: 0;
  padding-right: 4px;
}
.tree-folder-icon {
  color: #e6a23c; font-size: 16px; margin-right: 6px; flex-shrink: 0;
}
.tree-node-label {
  flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 14px; color: #374151;
}
.tree-node-count {
  font-size: 11px; color: #9ca3af; margin-left: auto; flex-shrink: 0;
  background: #f0f0f0; padding: 1px 6px; border-radius: 8px;
}
.tree-node-count.empty { color: #d1d5db; }

.knowledge-panel :deep(.el-tree) {
  background: transparent;
}
.knowledge-panel :deep(.el-tree-node__content) {
  height: 36px; border-radius: 6px; padding-right: 4px;
}
.knowledge-panel :deep(.el-tree-node__content:hover) {
  background: #f5f7fa;
}
.knowledge-panel :deep(.el-checkbox__label) {
  display: none;
}

.selected-tags {
  padding: 10px 14px; background: #f0f7ff; border-radius: 8px; margin-bottom: 12px;
  display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
}
.selected-tags-label { font-size: 12px; color: #6b7280; font-weight: 500; }

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
  0%,100% { box-shadow: 0 0 0 0 rgba(239,68,68,0.4); }
  50% { box-shadow: 0 0 0 8px rgba(239,68,68,0); }
}

.feedback-preview-text {
  background: #f8fafc; border-radius: 6px; padding: 10px;
  font-size: 13px; color: #475569; max-height: 120px; overflow-y: auto;
}

@media (max-width: 900px) {
  .qa-layout { grid-template-columns: 1fr; }
}
</style>
