<template>
  <div class="qa-layout" @mousemove="onDrag" @mouseup="stopDrag" @mouseleave="stopDrag">
    <!-- 左侧：MGI 说明书网站 -->
    <aside class="left-panel" :style="{ width: leftW + 'px' }">
      <div class="panel-hd">
        <h3>华大智造说明书库</h3>
        <span class="hd-desc">在此搜索和下载说明书 PDF</span>
      </div>

      <div class="steps-bar">
        <div class="step"><span class="sn">1</span> 搜索说明书</div>
        <div class="step"><span class="sn">2</span> 下载 PDF 到本地</div>
        <div class="step"><span class="sn">3</span> 在右侧上传并问答</div>
      </div>

      <div class="iframe-wrapper">
        <iframe
          ref="siteIframe"
          src="https://www.mgi-tech.com/manual"
          frameborder="0"
          class="site-iframe"
          title="华大智造说明书库"
        ></iframe>
      </div>
    </aside>

    <!-- 拖拽分隔条 -->
    <div class="drag-handle" @mousedown.prevent="startDrag">
      <div class="drag-line"></div>
    </div>

    <!-- 右侧：上传 + 问答 -->
    <section class="right-panel">
      <div v-if="!sessionId" class="setup-view">
        <div class="upload-zone">
          <div class="upload-label">上传说明书 PDF</div>
          <el-upload
            ref="uploadRef"
            drag
            multiple
            accept=".pdf"
            :auto-upload="false"
            :on-change="onFileChange"
            :show-file-list="false"
            class="upload-dragger"
          >
            <div class="upload-inner">
              <el-icon class="upload-icon"><UploadFilled /></el-icon>
              <p>将 PDF 文件拖拽到此处，或点击上传</p>
              <p class="upload-hint">支持多份说明书同时上传</p>
            </div>
          </el-upload>

          <div v-if="pendingFiles.length > 0" class="upload-actions">
            <el-button type="primary" @click="doUpload" :loading="uploading">
              上传 {{ pendingFiles.length }} 个文件
            </el-button>
            <el-button @click="clearPending" :disabled="uploading">取消</el-button>
          </div>
        </div>

        <div v-if="uploadedFiles.length > 0" class="file-section">
          <div class="section-hd">
            <h4>已上传文件</h4>
            <div class="section-hd-right">
              <el-button size="small" text @click="selectAll">全选</el-button>
              <el-button size="small" text @click="deselectAll">取消</el-button>
            </div>
          </div>

          <div class="file-list">
            <div
              v-for="f in uploadedFiles"
              :key="f.file_id"
              class="file-item"
              :class="{ selected: selectedIds.has(f.file_id) }"
            >
              <el-checkbox
                :model-value="selectedIds.has(f.file_id)"
                @change="toggleFile(f.file_id)"
              />
              <el-icon class="file-icon"><Document /></el-icon>
              <div class="file-info">
                <div class="file-name">{{ f.title || f.filename }}</div>
                <div class="file-meta">{{ f.total_pages }} 页 · {{ formatSize(f.file_size) }}</div>
              </div>
              <div class="file-actions">
                <el-button size="small" text @click.stop="previewFile(f.file_id)">
                  <el-icon><View /></el-icon>
                </el-button>
                <el-button size="small" text type="danger" @click.stop="removeFile(f.file_id)">
                  <el-icon><Delete /></el-icon>
                </el-button>
              </div>
            </div>
          </div>

          <div class="file-actions-bottom">
            <el-button
              type="primary"
              size="large"
              @click="startSession"
              :loading="starting"
              :disabled="selectedIds.size === 0"
              style="width:100%"
            >
              开始问答（已选 {{ selectedIds.size }} 份说明书）
            </el-button>
          </div>
        </div>

        <div v-if="sessionList.length > 0" class="history-section">
          <div class="section-hd"><h4>最近问答</h4></div>
          <div
            v-for="s in sessionList"
            :key="s.id"
            class="hst-item"
            @click="loadSession(s.id)"
          >
            <el-icon><ChatDotRound /></el-icon>
            <span class="hst-title">{{ s.title }}</span>
            <el-icon class="hst-del" @click.stop="deleteSession(s.id)"><Close /></el-icon>
          </div>
        </div>
      </div>

      <!-- 问答视图 -->
      <template v-else>
        <div class="chat-hd">
          <div class="chat-hd-left">
            <span class="chat-title">{{ currentTitle }}</span>
          </div>
          <div class="chat-hd-right">
            <el-button size="small" text type="primary" @click="newSession">新建会话</el-button>
          </div>
        </div>

        <div class="chat-scope" v-if="currentTitles.length > 0">
          <span class="scope-label">知识范围：</span>
          <el-tag v-for="(t, i) in currentTitles" :key="i" size="small" effect="plain" round>{{ t }}</el-tag>
        </div>

        <div class="chat-tools">
          <el-button size="small" text @click="copyAll" :disabled="messages.length <= 1"><el-icon><CopyDocument /></el-icon> 复制</el-button>
          <el-dropdown @command="handleExport">
            <el-button size="small" text :disabled="messages.length <= 1"><el-icon><Download /></el-icon> 导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="md">Markdown</el-dropdown-item>
                <el-dropdown-item command="word">Word</el-dropdown-item>
                <el-dropdown-item command="pdf">PDF</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <div class="chat-msgs" ref="chatBox">
          <div v-for="(msg, i) in messages" :key="i" class="msg-row" :class="msg.role">
            <div class="msg-avatar" :class="msg.role">
              <el-icon v-if="msg.role === 'user'"><User /></el-icon>
              <el-icon v-else>
                <svg viewBox="0 0 32 32" fill="none" style="width:18px;height:18px">
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
            <div class="msg-body">
              <div class="msg-bubble">{{ msg.content }}</div>
              <div v-if="msg.sources && msg.sources.length" class="msg-sources">
                <div class="src-label">信息来源：</div>
                <div v-for="(s, si) in msg.sources" :key="si" class="src-item">
                  <el-icon><Document /></el-icon>
                  <span>《{{ s.title }}》第 {{ s.page }} 页</span>
                  <span v-if="s.content" class="src-quote">"{{ s.content }}"</span>
                </div>
              </div>
              <div v-if="msg.role === 'assistant' && i > 0" class="msg-fb">
                <div class="fb-actions">
                  <span class="fb-label">评价：</span>
                  <el-button :type="msg.rating === 1 ? 'primary' : 'default'" size="small" circle @click="rateMsg(i, 1)">👍</el-button>
                  <el-button :type="msg.rating === -1 ? 'danger' : 'default'" size="small" circle @click="rateMsg(i, -1)">👎</el-button>
                </div>
                <el-divider direction="vertical" />
                <el-button size="small" text type="warning" @click="openFeedbackDialog(i)">内容有误？点此反馈</el-button>
              </div>
            </div>
          </div>
          <div v-if="loading" class="msg-row assistant">
            <div class="msg-avatar assistant">
              <el-icon><svg viewBox="0 0 32 32" fill="none" style="width:18px;height:18px"><circle cx="16" cy="1.5" r="1.5" fill="#f59e0b"/><rect x="5" y="6" width="22" height="19" rx="6" stroke="currentColor" stroke-width="1.5"/><circle cx="11" cy="14" r="2.5" stroke="currentColor" stroke-width="1.2" fill="#1e40af"/><circle cx="21" cy="14" r="2.5" stroke="currentColor" stroke-width="1.2" fill="#1e40af"/><path d="M11 21 Q16 24 21 21" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" fill="none"/></svg></el-icon>
            </div>
            <div class="msg-body"><div class="msg-bubble typing">检索回答中...</div></div>
          </div>
        </div>

        <div class="chat-input">
          <el-input
            v-model="question"
            placeholder="基于已选说明书提问，例如：这款仪器的规格参数是多少？"
            @keyup.enter="sendQuestion()"
            :disabled="loading"
          >
            <template #append>
              <el-button type="primary" @click="sendQuestion()" :disabled="loading || !question.trim()" :loading="loading">发送</el-button>
            </template>
          </el-input>
        </div>
      </template>
        <el-dialog v-model="feedbackVisible" title="反馈内容有误" width="500px">
          <el-form label-position="top">
            <el-form-item label="问题">
              <div class="fb-preview-text">{{ currentFeedbackQuestion }}</div>
            </el-form-item>
            <el-form-item label="AI回答">
              <div class="fb-preview-text">{{ currentFeedbackAnswer }}</div>
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
      </section>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Document, View, Delete, User, CopyDocument, Download, ArrowDown, Close, ChatDotRound } from '@element-plus/icons-vue'
import { manualAPI, qaAPI } from '@/api/index.js'

const leftW = ref(420)
const dragging = ref(false)
const startX = ref(0)
const startW = ref(0)

const pendingFiles = ref([])
const uploading = ref(false)
const uploadedFiles = ref([])
const selectedIds = ref(new Set())
const starting = ref(false)
const sessionId = ref(null)
const currentTitle = ref('')
const currentTitles = ref([])
const messages = ref([])
const question = ref('')
const loading = ref(false)
const sessionList = ref([])
const chatBox = ref(null)

const refreshFeedbackCount = inject('refreshFeedbackCount', null)

const feedbackVisible = ref(false)
const feedbackText = ref('')
const currentFeedbackQuestion = ref('')
const currentFeedbackAnswer = ref('')
const currentFeedbackIndex = ref(-1)

function startDrag(e) { dragging.value = true; startX.value = e.clientX; startW.value = leftW.value; document.body.style.cursor = 'col-resize'; document.body.style.userSelect = 'none' }
function onDrag(e) { if (!dragging.value) return; leftW.value = Math.max(340, Math.min(startW.value + e.clientX - startX.value, Math.round(window.innerWidth * 0.65))) }
function stopDrag() { dragging.value = false; document.body.style.cursor = ''; document.body.style.userSelect = '' }

function onFileChange(file) {
  if (file.raw) pendingFiles.value.push(file.raw)
}

function clearPending() {
  pendingFiles.value = []
}

async function doUpload() {
  if (pendingFiles.value.length === 0) return
  uploading.value = true
  try {
    const resp = await manualAPI.upload(pendingFiles.value)
    const items = resp.data.uploaded || []
    for (const item of items) {
      if (item.status === 'ok') {
        uploadedFiles.value.push(item)
      } else {
        ElMessage.warning(item.filename + ': ' + (item.error || '上传失败'))
      }
    }
    pendingFiles.value = []
    ElMessage.success(`成功上传 ${items.filter(i => i.status === 'ok').length} 个文件`)
  } catch (e) {
    ElMessage.error('上传失败: ' + (e.response?.data?.detail || e.message))
  }
  uploading.value = false
}

function toggleFile(id) {
  const s = new Set(selectedIds.value)
  if (s.has(id)) s.delete(id); else s.add(id)
  selectedIds.value = s
}
function selectAll() { selectedIds.value = new Set(uploadedFiles.value.map(f => f.file_id)) }
function deselectAll() { selectedIds.value = new Set() }

async function removeFile(id) {
  try {
    await manualAPI.deleteUpload(id)
    uploadedFiles.value = uploadedFiles.value.filter(f => f.file_id !== id)
    const s = new Set(selectedIds.value); s.delete(id); selectedIds.value = s
  } catch { ElMessage.warning('删除失败') }
}

function previewFile(id) { window.open(manualAPI.getPreviewUrl(id), '_blank') }

function formatSize(bytes) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0; let s = bytes
  while (s >= 1024 && i < units.length - 1) { s /= 1024; i++ }
  return s.toFixed(1) + ' ' + units[i]
}

async function startSession() {
  if (selectedIds.value.size === 0) { ElMessage.warning('请先选择说明书'); return }
  starting.value = true
  try {
    const resp = await manualAPI.start([...selectedIds.value])
    const data = resp.data
    sessionId.value = data.session_id
    currentTitle.value = data.title
    currentTitles.value = data.titles || []
    messages.value = [{ role: 'assistant', content: data.message, sources: [], rating: 0 }]
    loadSessionList()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '启动失败')
  }
  starting.value = false
}

async function sendQuestion() {
  const text = question.value.trim()
  if (!text || !sessionId.value || loading.value) return
  messages.value.push({ role: 'user', content: text, sources: [], rating: 0 })
  question.value = ''
  loading.value = true
  await nextTick(); scrollToBottom()
  try {
    const resp = await manualAPI.ask(sessionId.value, text)
    messages.value.push({
      role: 'assistant',
      content: resp.data.answer || '未能找到相关信息',
      sources: resp.data.sources || [],
      rating: 0,
    })
  } catch {
    messages.value.push({ role: 'assistant', content: '查询出错，请稍后重试', sources: [], rating: 0 })
  }
  loading.value = false
  await nextTick(); scrollToBottom()
}

function scrollToBottom() { if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight }
function rateMsg(i, v) {
  const msg = messages.value[i]
  msg.rating = msg.rating === v ? 0 : v
  qaAPI.submitFeedback({
    question: messages.value[i - 1]?.content || '',
    answer: msg.content,
    rating: msg.rating,
    feedback_text: ''
  }).then(() => {
    if (refreshFeedbackCount) refreshFeedbackCount()
  }).catch(() => {})
}

function openFeedbackDialog(i) {
  currentFeedbackIndex.value = i
  currentFeedbackQuestion.value = messages.value[i - 1]?.content || ''
  currentFeedbackAnswer.value = messages.value[i].content
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
    if (refreshFeedbackCount) refreshFeedbackCount()
  } catch {
    ElMessage.error('反馈提交失败')
  }
}

async function loadSessionList() {
  try { const r = await manualAPI.getSessions(); sessionList.value = r.data || [] } catch {}
}

async function loadSession(id) {
  try {
    const r = await manualAPI.getSessionDetail(id)
    const d = r.data
    sessionId.value = id
    currentTitle.value = d.session?.title || ''
    currentTitles.value = d.session?.titles || []
    messages.value = (d.messages || []).map(m => ({
      role: m.role, content: m.content,
      sources: (m.sources || []).map(s => ({ title: s.title || '', page: s.page || '?', content: '' })),
      rating: 0,
    }))
    await nextTick(); scrollToBottom()
  } catch { ElMessage.warning('加载失败') }
}

async function deleteSession(id) {
  try {
    await manualAPI.deleteSession(id)
    sessionList.value = sessionList.value.filter(s => s.id !== id)
    if (sessionId.value === id) newSession()
  } catch { ElMessage.warning('删除失败') }
}

function newSession() { sessionId.value = null; currentTitle.value = ''; currentTitles.value = []; messages.value = []; question.value = '' }

function copyAll() {
  let t = ''; messages.value.forEach(m => { t += (m.role === 'user' ? 'Q: ' : 'A: ') + m.content + '\n\n' })
  navigator.clipboard.writeText(t).then(() => ElMessage.success('已复制'))
}

function escapeHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML }

function buildHtml() {
  let h = '<!DOCTYPE html><html><head><meta charset="utf-8"><title>说明书问答</title><style>*{box-sizing:border-box}body{font-family:"Microsoft YaHei",sans-serif;max-width:860px;margin:40px auto;padding:0 20px;line-height:1.8;color:#1f2937}h1{font-size:20px;border-bottom:2px solid #2563eb;padding-bottom:10px;margin-bottom:20px}.q{margin-top:28px;padding:10px 14px;background:#eff6ff;border-radius:8px;font-weight:600;color:#1e40af}.a{padding:10px 14px;background:#f8fafc;border-radius:8px;margin:6px 0 16px;border-left:3px solid #2563eb}.src{color:#94a3b8;font-size:12px;margin-top:6px}.src i{font-style:normal;color:#3b82f6}</style></head><body><h1>'+escapeHtml(currentTitle.value)+'</h1>'
  messages.value.forEach(m => {
    if (m.role === 'user') h += '<div class="q">Q: ' + escapeHtml(m.content) + '</div>'
    else {
      h += '<div class="a">' + escapeHtml(m.content) + '</div>'
      if (m.sources && m.sources.length) {
        h += '<div class="src">来源：' + m.sources.map(s => '《'+escapeHtml(s.title||'')+'》第'+(s.page||'?')+'页').join('、') + '</div>'
      }
    }
  })
  return h + '</body></html>'
}

function handleExport(cmd) {
  const title = currentTitle.value || '说明书问答'
  if (cmd === 'md') {
    let md = '# ' + title + '\n\n'
    messages.value.forEach(m => {
      if (m.role === 'user') md += '## Q: ' + m.content + '\n\n'
      else {
        md += '**A:** ' + m.content + '\n'
        if (m.sources && m.sources.length) md += '> 来源：' + m.sources.map(s => '《'+s.title+'》第'+s.page+'页').join('、') + '\n'
        md += '\n---\n\n'
      }
    })
    const b = new Blob(['\uFEFF'+md],{type:'text/markdown;charset=utf-8'})
    const a = document.createElement('a'); a.href=URL.createObjectURL(b); a.download=title+'.md'; a.click()
  } else if (cmd === 'word') {
    const b = new Blob(['\uFEFF'+buildHtml()],{type:'application/msword;charset=utf-8'})
    const a = document.createElement('a'); a.href=URL.createObjectURL(b); a.download=title+'.doc'; a.click()
  } else if (cmd === 'pdf') {
    const w = window.open('','_blank'); w.document.write(buildHtml()); w.document.close(); w.print()
  }
}

onMounted(loadSessionList)
</script>

<style scoped>
.qa-layout { height: calc(100vh - 60px); display: flex; overflow: hidden; background: #f1f5f9; }

/* 左侧面板 */
.left-panel { flex-shrink:0; display:flex; flex-direction:column; background:#fff; border-right:1px solid #e5e7eb; min-width:340px; }
.panel-hd { padding:14px 16px 10px; border-bottom:1px solid #f1f5f9; display:flex; align-items:baseline; gap:8px; }
.panel-hd h3 { margin:0; font-size:14px; font-weight:700; }
.hd-desc { font-size:11px; color:#94a3b8; }
.steps-bar { display:flex; gap:0; padding:8px 12px; border-bottom:1px solid #f1f5f9; font-size:11px; color:#64748b; }
.step { flex:1; text-align:center; display:flex; flex-direction:column; align-items:center; gap:2px; }
.sn { width:18px; height:18px; border-radius:50%; background:#eff6ff; color:#2563eb; font-size:10px; font-weight:700; display:flex; align-items:center; justify-content:center; }
.iframe-wrapper { flex:1; overflow:hidden; }
.site-iframe { width:100%; height:100%; border:none; }

/* 拖拽 */
.drag-handle { width:10px; flex-shrink:0; cursor:col-resize; display:flex; align-items:center; justify-content:center; background:transparent; transition:background .15s; z-index:10; }
.drag-handle:hover { background:rgba(37,99,235,.06); }
.drag-line { width:2px; height:48px; border-radius:1px; background:#cbd5e1; transition:all .15s; }
.drag-handle:hover .drag-line { background:#2563eb; height:64px; }

/* 右侧面板 */
.right-panel { flex:1; display:flex; flex-direction:column; overflow:hidden; background:#fff; min-width:0; }

.setup-view { flex:1; overflow-y:auto; padding:24px; }

/* 上传区 */
.upload-zone { margin-bottom:24px; }
.upload-label { font-size:15px; font-weight:700; margin-bottom:12px; color:#1e293b; }
.upload-dragger { width:100%; }
.upload-inner { padding:32px 16px; text-align:center; }
.upload-icon { font-size:40px; color:#94a3b8; }
.upload-hint { font-size:12px; color:#b0b7c3; margin-top:4px; }
.upload-actions { margin-top:12px; display:flex; justify-content:center; gap:8px; }

/* 文件列表 */
.file-section { margin-bottom:24px; }
.section-hd { display:flex; align-items:center; justify-content:space-between; padding:8px 0; border-bottom:1px solid #f1f5f9; margin-bottom:8px; }
.section-hd h4 { margin:0; font-size:13px; font-weight:600; }
.section-hd-right { display:flex; gap:4px; }
.file-list { max-height:360px; overflow-y:auto; }
.file-item { display:flex; align-items:center; gap:10px; padding:10px 12px; border-radius:8px; border:1px solid transparent; transition:all .15s; }
.file-item:hover { background:#f8fafc; }
.file-item.selected { background:#eff6ff; border-color:#bfdbfe; }
.file-icon { color:#2563eb; font-size:22px; flex-shrink:0; }
.file-info { flex:1; min-width:0; }
.file-name { font-size:13px; font-weight:500; color:#1e293b; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.file-meta { font-size:11px; color:#94a3b8; margin-top:2px; }
.file-actions { display:flex; gap:2px; flex-shrink:0; }
.file-actions-bottom { margin-top:12px; }

/* 历史 */
.history-section { margin-top:24px; }
.hst-item { display:flex; align-items:center; gap:8px; padding:7px 12px; border-radius:6px; cursor:pointer; font-size:13px; color:#475569; }
.hst-item:hover { background:#eff6ff; }
.hst-title { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.hst-del { opacity:0; font-size:12px; color:#94a3b8; }
.hst-item:hover .hst-del { opacity:1; }
.hst-del:hover { color:#ef4444; }

/* 问答 */
.chat-hd { display:flex; align-items:center; justify-content:space-between; padding:10px 24px; border-bottom:1px solid #e5e7eb; background:#fafbfc; flex-shrink:0; }
.chat-title { font-weight:600; font-size:14px; }
.chat-hd-right { display:flex; gap:4px; }
.chat-scope { display:flex; align-items:center; flex-wrap:wrap; gap:6px; padding:8px 24px; border-bottom:1px solid #f1f5f9; background:#fafbfc; flex-shrink:0; }
.scope-label { font-size:12px; color:#64748b; }
.chat-tools { display:flex; gap:8px; padding:6px 24px; border-bottom:1px solid #f1f5f9; flex-shrink:0; }
.chat-msgs { flex:1; overflow-y:auto; padding:20px 24px; background:#f8fafc; }
.msg-row { display:flex; gap:12px; margin-bottom:24px; }
.msg-row.user { flex-direction:row-reverse; }
.msg-avatar { width:36px; height:36px; border-radius:50%; display:flex; align-items:center; justify-content:center; flex-shrink:0; font-size:16px; }
.msg-avatar.user { background:#2563eb; color:#fff; }
.msg-avatar.assistant { background:#f59e0b; color:#fff; }
.msg-body { max-width:72%; }
.msg-bubble { padding:11px 15px; border-radius:12px; font-size:14px; line-height:1.65; white-space:pre-wrap; word-break:break-word; }
.msg-row.user .msg-bubble { background:#2563eb; color:#fff; border-bottom-right-radius:4px; }
.msg-row.assistant .msg-bubble { background:#fff; color:#1e293b; border:1px solid #e2e8f0; border-bottom-left-radius:4px; box-shadow:0 1px 2px rgba(0,0,0,.04); }
.msg-bubble.typing { opacity:.6; }
.msg-sources { margin-top:8px; padding:8px 12px; background:#f8fafc; border-radius:8px; border:1px solid #e2e8f0; }
.src-label { font-size:12px; font-weight:600; color:#64748b; margin-bottom:4px; }
.src-item { display:flex; align-items:center; gap:4px; font-size:12px; color:#475569; padding:2px 0; }
.src-quote { color:#94a3b8; font-size:11px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:300px; }
.msg-fb { margin-top:8px; display:flex; align-items:center; gap:4px; }
.fb-actions { display:flex; align-items:center; gap:4px; }
.fb-label { font-size:12px; color:#64748b; }
.fb-preview-text { padding:10px 12px; background:#f8fafc; border-radius:6px; font-size:13px; color:#475569; line-height:1.6; max-height:120px; overflow-y:auto; }
.chat-input { padding:12px 24px 16px; border-top:1px solid #e5e7eb; flex-shrink:0; background:#fff; }
</style>
