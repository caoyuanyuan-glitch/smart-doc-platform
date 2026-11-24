<template>
  <div class="qa-container">
    <header class="qa-hero">
      <div>
        <h2 class="page-title">说明书问答</h2>
        <p class="page-subtitle">直接提问，系统会打开所选电子说明书库并检索对应手册</p>
      </div>
      <div class="hero-actions">
        <el-button v-if="inChat" class="back-home-btn" @click="backHome">
          <el-icon><ArrowLeft /></el-icon>
          返回主页
        </el-button>
      </div>
    </header>

    <div v-if="!inChat" class="qa-home">
      <section class="home-main">
        <div class="home-ask">
        <div class="ask-meta">
          <el-input
            v-model="product"
            class="product-input"
            clearable
            placeholder="可输入多个型号 / 货号，用逗号分隔，例如 T1+, T7"
          />
          <el-radio-group v-model="siteLang" size="small" class="site-switch">
            <el-radio-button value="zh">中文说明书</el-radio-button>
            <el-radio-button value="en">英文说明书</el-radio-button>
          </el-radio-group>
        </div>
        <div class="chat-input home-input">
          <el-input
            v-model="question"
            type="textarea"
            :rows="2"
            placeholder="直接输入问题，例如：T1+ 开机前要检查哪些项目？"
            @keydown.enter.exact.prevent="sendQuestion(question)"
          />
          <el-button type="primary" :loading="loading" @click="sendQuestion(question)">发送</el-button>
        </div>
        </div>

        <div class="recent-ask">
          <div class="side-head">
            <span>最近问答</span>
            <el-button v-if="sessionList.length" size="small" text @click="historyVisible = true">全部</el-button>
          </div>
          <div v-if="!sessionList.length" class="side-empty">提问后，会话会显示在这里</div>
          <div v-else class="recent-ask-list">
            <button
              v-for="s in sessionList.slice(0, 8)"
              :key="s.id"
              class="side-item"
              type="button"
              @click="loadSession(s.id)"
            >
              <span class="side-item-title">{{ s.title }}</span>
              <span class="side-item-time">{{ formatTime(s.updated_at) }}</span>
            </button>
          </div>
        </div>
      </section>
    </div>

    <section v-else class="chat-panel">
      <div class="chat-toolbar">
        <div class="selected-tags">
          <span class="selected-tags-label">本次依据：</span>
          <template v-if="currentTitles.length">
            <el-tag v-for="t in currentTitles" :key="t" size="small">{{ t }}</el-tag>
            <el-button v-if="candidates.length > 1" size="small" text type="primary" @click="switchVisible = true">更换</el-button>
          </template>
          <span v-else class="scope-hint">{{ loading ? '正在说明书库检索' : '尚未定位说明书' }}</span>
        </div>
        <div class="chat-toolbar-actions">
          <el-button size="small" text @click="backHome"><el-icon><Plus /></el-icon> 新建会话</el-button>
          <el-button size="small" text @click="copyAll" :disabled="messages.length <= 1"><el-icon><CopyDocument /></el-icon> 复制全文</el-button>
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
      </div>

      <div class="chat-messages" ref="chatBox">
        <div v-for="(msg, i) in messages" :key="i" class="message" :class="msg.role">
          <div class="avatar" :class="msg.role">
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
          <div class="bubble-wrap">
            <div v-if="msg.role === 'assistant'" class="bubble bubble-md" v-html="renderAnswerHtml(msg.content)"></div>
            <div v-else class="bubble">{{ msg.content }}</div>
            <div v-if="msg.sources && msg.sources.length" class="sources">
              <div class="sources-title">信息来源：</div>
              <div v-for="(s, si) in uniqSources(msg.sources)" :key="si" class="source-item">
                <span>《{{ s.title }}》第 {{ s.page }} 页</span>
                <span v-if="s.content" class="src-quote">{{ s.content }}</span>
                <el-button
                  v-if="s.file_id"
                  size="small"
                  text
                  type="primary"
                  :loading="previewingKey === sourceKey(s)"
                  @click="previewSource(s)"
                >{{ previewingKey === sourceKey(s) ? '正在打开原文' : '查看原文' }}</el-button>
                <a v-if="officialUrl" class="official-link" :href="officialUrl" target="_blank" rel="noopener">去官网核对</a>
              </div>
            </div>
            <div v-if="msg.miss" class="miss-box">
              <el-upload drag accept=".pdf" :auto-upload="false" :show-file-list="false" :on-change="onMissFile">
                <p>补充说明书后继续问（仅本会话）</p>
              </el-upload>
            </div>
            <div v-if="msg.role === 'assistant' && i > 0 && !msg.miss && !msg.choose" class="feedback-row">
              <div class="feedback-actions">
                <span class="feedback-label">评价：</span>
                <el-button class="rate-btn" :type="msg.rating === 1 ? 'primary' : 'default'" size="small" circle title="有帮助" @click="rateMsg(i, 1)">
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 10v12"/><path d="M15 5.88L14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88z"/></svg>
                </el-button>
                <el-button class="rate-btn" :type="msg.rating === -1 ? 'danger' : 'default'" size="small" circle title="无帮助" @click="rateMsg(i, -1)">
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 14V2"/><path d="M9 18.12L10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88z"/></svg>
                </el-button>
              </div>
              <el-divider direction="vertical" />
              <el-button size="small" text type="warning" @click="openFeedbackDialog(i)">内容有误？点此反馈</el-button>
            </div>
          </div>
        </div>

        <div v-if="loading" class="message assistant">
          <div class="avatar assistant"><el-icon><svg viewBox="0 0 32 32" fill="none" style="width:18px;height:18px"><circle cx="16" cy="1.5" r="1.5" fill="#f59e0b"/><rect x="5" y="6" width="22" height="19" rx="6" stroke="currentColor" stroke-width="1.5"/></svg></el-icon></div>
          <div class="bubble typing">{{ loadingText }}</div>
        </div>
      </div>

      <div class="chat-composer">
        <el-radio-group v-model="siteLang" size="small" class="site-switch">
          <el-radio-button value="zh">中文说明书</el-radio-button>
          <el-radio-button value="en">英文说明书</el-radio-button>
        </el-radio-group>
        <div class="chat-input">
          <el-input v-model="question" type="textarea" :rows="2" placeholder="继续追问，或换一个型号再问" @keydown.enter.exact.prevent="sendQuestion(question)" />
          <el-button type="primary" :loading="loading" @click="sendQuestion(question)">发送</el-button>
        </div>
      </div>
    </section>

    <el-dialog v-model="feedbackVisible" title="反馈内容有误" width="500px">
      <el-form label-position="top">
        <el-form-item label="问题"><div class="fb-preview-text">{{ currentFeedbackQuestion }}</div></el-form-item>
        <el-form-item label="AI回答"><div class="fb-preview-text">{{ currentFeedbackAnswer }}</div></el-form-item>
        <el-form-item label="错误描述"><el-input v-model="feedbackText" type="textarea" :rows="4" placeholder="请描述回答中的错误之处..." /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="feedbackVisible = false">取消</el-button>
        <el-button type="primary" @click="submitFeedback">提交反馈</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="switchVisible" :title="currentTitles.length ? '更换说明书' : '请选择说明书'" width="640px">
      <div class="candidate-list">
        <label v-for="c in candidates" :key="c.official_id" class="candidate-item" :class="{ active: pickedOfficialIds.includes(c.official_id) }">
          <input type="checkbox" :value="c.official_id" v-model="pickedOfficialIds" />
          <div>
            <div class="candidate-title">{{ c.title }}</div>
            <div class="candidate-meta">版本 {{ c.docuversion || '-' }} · {{ c.create_time || '-' }} · {{ c.size || '-' }}</div>
          </div>
        </label>
      </div>
      <template #footer>
        <el-button @click="switchVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!pickedOfficialIds.length" @click="confirmSwitch">{{ currentTitles.length ? '用所选重新作答' : '用所选说明书作答' }}</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="historyVisible" title="最近问答" size="360px">
      <div v-if="!sessionList.length" class="empty-hint">暂无历史会话</div>
      <div v-for="s in sessionList" :key="s.id" class="hst-item" @click="loadSession(s.id)">
        <span class="hst-title">{{ s.title }}</span>
        <el-button text type="danger" @click.stop="deleteSession(s.id)">删除</el-button>
      </div>
    </el-drawer>

    <el-drawer v-model="previewVisible" title="查看原文" size="55%" @closed="resetPreview">
      <div class="preview-body">
        <div v-if="previewBusy" class="preview-loading">
          <el-icon class="is-loading preview-spinner"><Loading /></el-icon>
          <p>{{ previewLoading ? '正在获取说明书原文...' : '正在定位到参考页...' }}</p>
        </div>
        <iframe
          v-if="previewUrl"
          class="preview-frame"
          :class="{ 'is-ready': previewReady }"
          :src="previewUrl"
          title="说明书原文"
          @load="onPreviewFrameLoad"
        />
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown, ArrowLeft, CopyDocument, Download, Loading, Plus, User } from '@element-plus/icons-vue'
import { manualAPI, qaAPI } from '@/api/index.js'

function formatTime(iso) {
  if (!iso) return ''
  return String(iso).replace('T', ' ').slice(0, 16)
}

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function formatAnswerHtml(escaped) {
  const lines = String(escaped || '').split(/\n/)
  const html = []
  let i = 0
  const listItem = /^\s*(?:[-*]|\d+[\.、])\s+/
  const orderedItem = /^\s*\d+[\.、]\s+/
  const bulletItem = /^\s*[-*]\s+/
  while (i < lines.length) {
    const line = lines[i]
    if (/^\s*#{1,3}\s+/.test(line)) {
      const hashes = line.trim().match(/^#+/)[0]
      const level = Math.min(hashes.length + 1, 4)
      const text = line.replace(/^\s*#{1,3}\s+/, '').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      html.push(`<h${level} class="qa-md-h">${text}</h${level}>`)
      i += 1
      continue
    }
    if (/^\s*\|.+\|\s*$/.test(line)) {
      const rows = []
      while (i < lines.length && /^\s*\|.+\|\s*$/.test(lines[i])) {
        const cells = lines[i].split('|').slice(1, -1).map(cell => cell.trim())
        if (!cells.every(cell => /^:?-{3,}:?$/.test(cell))) rows.push(cells)
        i += 1
      }
      if (rows.length) {
        html.push('<table class="qa-md-table">')
        rows.forEach((cells, idx) => {
          const tag = idx === 0 ? 'th' : 'td'
          html.push('<tr>' + cells.map(cell => `<${tag}>${cell}</${tag}>`).join('') + '</tr>')
        })
        html.push('</table>')
      }
      continue
    }
    if (orderedItem.test(line) || bulletItem.test(line)) {
      const ordered = orderedItem.test(line)
      html.push(ordered ? '<ol class="qa-md-list">' : '<ul class="qa-md-list">')
      while (i < lines.length && (ordered ? orderedItem.test(lines[i]) : bulletItem.test(lines[i]))) {
        let item = lines[i].replace(listItem, '')
        i += 1
        while (i < lines.length && lines[i].trim() && !listItem.test(lines[i]) && !/^\s*\|.+\|\s*$/.test(lines[i])) {
          item += '<br>' + lines[i].trim()
          i += 1
        }
        html.push(`<li>${item.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')}</li>`)
      }
      html.push(ordered ? '</ol>' : '</ul>')
      continue
    }
    const withBold = line.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    if (withBold.trim()) html.push(`<p>${withBold}</p>`)
    i += 1
  }
  return html.join('') || `<p>${escaped}</p>`
}

function renderAnswerHtml(text) {
  return formatAnswerHtml(escapeHtml(text))
}
const loadingStages = ['正在电子说明书库检索...', '已定位目标手册...', '正在解析 PDF...', '正在作答...']

const product = ref('')
const siteLang = ref('zh')
const question = ref('')
const loading = ref(false)
const loadingText = ref(loadingStages[0])
const sessionId = ref(null)
const currentTitle = ref('说明书问答')
const currentTitles = ref([])
const candidates = ref([])
const messages = ref([])
const sessionList = ref([])
const chatBox = ref(null)
const inChat = computed(() => messages.value.length > 0 || loading.value)

const refreshFeedbackCount = inject('refreshFeedbackCount', null)
const feedbackVisible = ref(false)
const feedbackText = ref('')
const currentFeedbackQuestion = ref('')
const currentFeedbackAnswer = ref('')
const currentFeedbackIndex = ref(-1)
const switchVisible = ref(false)
const pickedOfficialIds = ref([])
const historyVisible = ref(false)
const previewVisible = ref(false)
const previewUrl = ref('')
const lastUserQuestion = ref('')
let stageTimer = null
const previewLoading = ref(false)
const previewReady = ref(false)
const previewingKey = ref('')
const previewBusy = computed(() => previewVisible.value && !previewReady.value)
let lastObjectUrl = ''
let previewTimer = null

const officialUrl = computed(() => {
  const hit = candidates.value.find(c => currentTitles.value.includes(c.title))
  if (hit?.library_url) return hit.library_url
  return siteLang.value === 'en'
    ? 'https://global-mgitech.com/resources/manual-library/'
    : 'https://mgi-tech.com/manual'
})

function startLoadingStages() {
  let i = 0
  loadingText.value = loadingStages[0]
  clearInterval(stageTimer)
  stageTimer = setInterval(() => {
    i = Math.min(i + 1, loadingStages.length - 1)
    loadingText.value = loadingStages[i]
  }, 2200)
}

function stopLoadingStages() {
  clearInterval(stageTimer)
  stageTimer = null
}

function scrollToBottom() {
  if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
}

function uniqSources(arr) {
  if (!arr || !arr.length) return []
  const seen = new Set()
  return arr.filter(s => {
    const key = (s.title || '') + '_' + (s.page || '')
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

async function sendQuestion(text, extra = {}) {
  const q = (text || '').trim()
  if (!q || loading.value) return
  lastUserQuestion.value = q
  if (!extra.file_ids && !extra.official_ids) {
    messages.value.push({ role: 'user', content: q, sources: [], rating: 0 })
  }
  question.value = ''
  loading.value = true
  startLoadingStages()
  await nextTick(); scrollToBottom()
  try {
    const resp = await manualAPI.query({
      question: q,
      product: product.value,
      session_id: sessionId.value,
      official_ids: extra.official_ids || undefined,
      file_ids: extra.file_ids || undefined,
      site: siteLang.value,
    })
    const data = resp.data || {}
    sessionId.value = data.session_id
    if (data.site === 'en' || data.site === 'zh') siteLang.value = data.site
    currentTitles.value = data.titles || (data.selected || []).map(s => s.title)
    currentTitle.value = currentTitles.value[0] || q.slice(0, 40)
    candidates.value = data.candidates || []
    pickedOfficialIds.value = (data.selected || []).map(s => s.official_id).filter(Boolean)
    if (data.status === 'choose') {
      pickedOfficialIds.value = (data.selected || []).map(s => s.official_id).filter(Boolean)
      switchVisible.value = true
    }
    messages.value.push({
      role: 'assistant',
      content: data.answer || data.message || '未能找到相关信息',
      sources: data.sources || [],
      rating: 0,
      miss: data.status === 'miss',
      choose: data.status === 'choose',
    })
    loadSessionList()
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: e.response?.data?.detail || '查询出错，请稍后重试',
      sources: [],
      rating: 0,
      miss: true,
    })
  }
  loading.value = false
  stopLoadingStages()
  await nextTick(); scrollToBottom()
}

async function onMissFile(file) {
  if (!file?.raw) return
  try {
    const resp = await manualAPI.upload([file.raw])
    const ok = (resp.data.uploaded || []).filter(i => i.status === 'ok')
    if (!ok.length) {
      ElMessage.warning('上传失败')
      return
    }
    await sendQuestion(lastUserQuestion.value || question.value, { file_ids: ok.map(i => i.file_id) })
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '上传失败')
  }
}

async function confirmSwitch() {
  switchVisible.value = false
  if (!pickedOfficialIds.value.length) return
  await sendQuestion(lastUserQuestion.value, { official_ids: pickedOfficialIds.value })
}

function backHome() {
  sessionId.value = null
  currentTitle.value = '说明书问答'
  currentTitles.value = []
  candidates.value = []
  messages.value = []
  question.value = ''
  lastUserQuestion.value = ''
}

function rateMsg(i, v) {
  const msg = messages.value[i]
  msg.rating = msg.rating === v ? 0 : v
  qaAPI.submitFeedback({
    question: messages.value[i - 1]?.content || '',
    answer: msg.content,
    rating: msg.rating,
    feedback_text: ''
  }).then(() => { if (refreshFeedbackCount) refreshFeedbackCount() }).catch(() => {})
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

async function previewSource(s) {
  if (!s?.file_id) return
  const key = sourceKey(s)
  previewingKey.value = key
  previewVisible.value = true
  previewLoading.value = true
  previewReady.value = false
  previewUrl.value = ''
  clearTimeout(previewTimer)
  try {
    const resp = await manualAPI.previewBlob(s.file_id)
    if (previewingKey.value !== key) return
    if (lastObjectUrl) URL.revokeObjectURL(lastObjectUrl)
    lastObjectUrl = URL.createObjectURL(resp.data)
    previewUrl.value = lastObjectUrl + '#page=' + (s.page || 1)
    previewTimer = setTimeout(() => {
      previewReady.value = true
      if (previewingKey.value === key) previewingKey.value = ''
    }, 8000)
  } catch {
    ElMessage.warning('原文打开失败')
    previewVisible.value = false
    previewingKey.value = ''
  } finally {
    if (previewingKey.value === key) {
      previewLoading.value = false
    }
  }
}

function sourceKey(s) {
  return `${s.file_id}-${s.page || 1}`
}

function onPreviewFrameLoad() {
  previewReady.value = true
  clearTimeout(previewTimer)
  previewingKey.value = ''
}

function resetPreview() {
  previewLoading.value = false
  previewReady.value = false
  previewingKey.value = ''
  previewUrl.value = ''
  clearTimeout(previewTimer)
  if (lastObjectUrl) {
    URL.revokeObjectURL(lastObjectUrl)
    lastObjectUrl = ''
  }
}

async function loadSessionList() {
  try {
    const r = await manualAPI.getSessions()
    sessionList.value = r.data || []
  } catch {}
}

async function loadSession(id) {
  try {
    const r = await manualAPI.getSessionDetail(id)
    const d = r.data
    sessionId.value = id
    currentTitle.value = d.session?.title || ''
    currentTitles.value = d.session?.titles || []
    candidates.value = d.session?.candidates || []
    messages.value = (d.messages || []).map(m => ({
      role: m.role,
      content: m.content,
      sources: (m.sources || []).map(s => ({ title: s.title || '', page: s.page || '?', content: s.content || '', file_id: s.file_id })),
      rating: 0,
      miss: false,
    }))
    historyVisible.value = false
    await nextTick(); scrollToBottom()
  } catch {
    ElMessage.warning('加载失败')
  }
}

async function deleteSession(id) {
  try {
    await manualAPI.deleteSession(id)
    sessionList.value = sessionList.value.filter(s => s.id !== id)
    if (sessionId.value === id) backHome()
  } catch {
    ElMessage.warning('删除失败')
  }
}

function copyAll() {
  let t = ''
  messages.value.forEach(m => { t += (m.role === 'user' ? 'Q: ' : 'A: ') + m.content + '\n\n' })
  navigator.clipboard.writeText(t).then(() => ElMessage.success('已复制'))
}

function buildHtml() {
  let h = '<!DOCTYPE html><html><head><meta charset="utf-8"><title>说明书问答</title></head><body><h1>' + escapeHtml(currentTitle.value) + '</h1>'
  messages.value.forEach(m => {
    if (m.role === 'user') h += '<p><b>Q:</b> ' + escapeHtml(m.content) + '</p>'
    else h += '<p><b>A:</b> ' + escapeHtml(m.content) + '</p>'
  })
  return h + '</body></html>'
}

function handleExport(cmd) {
  const title = currentTitle.value || '说明书问答'
  if (cmd === 'md') {
    let md = '# ' + title + '\n\n'
    messages.value.forEach(m => {
      md += (m.role === 'user' ? '## Q: ' : '**A:** ') + m.content + '\n\n'
    })
    const b = new Blob(['\uFEFF' + md], { type: 'text/markdown;charset=utf-8' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = title + '.md'; a.click()
  } else if (cmd === 'word') {
    const b = new Blob(['\uFEFF' + buildHtml()], { type: 'application/msword;charset=utf-8' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = title + '.doc'; a.click()
  } else {
    const w = window.open('', '_blank'); w.document.write(buildHtml()); w.document.close(); w.print()
  }
}

onMounted(() => { loadSessionList() })
onBeforeUnmount(() => { stopLoadingStages(); resetPreview() })
</script>

<style scoped>
.qa-container {
  padding: 0;
  min-height: calc(100vh - 108px);
  display: flex;
  flex-direction: column;
}
.qa-hero { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 14px; }
.page-title { font-size: 26px; font-weight: 650; color: #111827; margin: 0 0 6px; }
.page-subtitle { margin: 0; color: #6b7280; font-size: 14px; line-height: 1.6; }
.hero-actions { display: flex; gap: 8px; }
.back-home-btn { height: 36px; padding: 0 14px; border: 1px solid #d7dee8; background: #fff; color: #334155; border-radius: 8px; }
.back-home-btn:hover, .back-home-btn:focus { border-color: #93c5fd; color: #1d4ed8; background: #f8fbff; }
.qa-home {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.home-main {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}
.recent-ask {
  background: #fff;
  border: 1px solid #efe8dc;
  border-radius: 14px;
  padding: 10px 14px 12px;
  display: flex;
  flex-direction: column;
}
.recent-ask-list {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 28px;
}
.side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 650;
  color: #1e293b;
  margin-bottom: 8px;
}
.side-empty { color: #94a3b8; font-size: 13px; padding: 8px 4px; line-height: 1.6; }
.side-item {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  text-align: left;
  border: 0;
  border-bottom: 1px solid #f1f5f9;
  background: transparent;
  padding: 12px 4px;
  cursor: pointer;
}
.side-item:hover { background: #f8fbff; }
.side-item-title {
  font-size: 13px;
  color: #334155;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}
.side-item-time { font-size: 12px; color: #94a3b8; }
.home-ask {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ask-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.ask-meta .product-input {
  flex: 1;
  min-width: 240px;
}
.site-switch :deep(.el-radio-button__inner) {
  padding: 7px 12px;
}
.chat-composer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 16px 0;
  background: #fff;
  border-top: 1px solid #e5e7eb;
}
.chat-composer .chat-input {
  border-top: 0;
  padding: 0 0 16px;
}
.product-input { margin-bottom: 0; }
.chat-input {
  display: flex;
  gap: 10px;
  padding: 16px;
  border-top: 1px solid #e5e7eb;
  background: #fff;
  align-items: flex-end;
}
.home-input {
  border: 1px solid #e7e0d6;
  border-radius: 14px;
  padding: 8px 8px 8px 12px;
  background: #fff;
  box-shadow: 0 8px 20px rgba(28, 25, 23, 0.04);
}
.chat-input .el-textarea { flex: 1; }
.chat-panel { background: #fff; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); display: flex; flex-direction: column; overflow: hidden; }
.chat-toolbar {
  display: flex;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid #f0f0f0;
  justify-content: space-between;
  align-items: center;
}
.chat-toolbar-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
}
.chat-messages { flex: 1; padding: 20px; overflow-y: auto; background: #f8fafc; min-height: 420px; max-height: calc(100vh - 300px); }
.selected-tags {
  padding: 0;
  background: transparent;
  border-radius: 0;
  margin-bottom: 0;
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.selected-tags-label { font-size: 12px; color: #6b7280; font-weight: 500; }
.scope-hint {
  font-size: 12px;
  color: #2563eb;
  background: #eff6ff;
  border-radius: 999px;
  padding: 2px 8px;
}
.message { display: flex; margin-bottom: 20px; gap: 10px; }
.message.user { flex-direction: row-reverse; }
.avatar { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; flex-shrink: 0; }
.avatar.user { background: #3b82f6; }
.avatar.assistant { background: #409EFF; }
.bubble-wrap { max-width: 74%; }
.message.assistant .bubble-wrap { max-width: 86%; }
.bubble { padding: 12px 16px; border-radius: 12px; line-height: 1.7; color: #374151; font-size: 14px; white-space: pre-wrap; }
.message.user .bubble { background: #3b82f6; color: #fff; border-bottom-right-radius: 4px; }
.message.assistant .bubble { background: #fff; border: 1px solid #e5e7eb; border-bottom-left-radius: 4px; }
.bubble-md {
  white-space: normal;
}
.bubble-md p {
  margin: 0 0 10px;
}
.bubble-md p:last-child {
  margin-bottom: 0;
}
.bubble-md .qa-md-h {
  margin: 12px 0 8px;
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
}
.bubble-md .qa-md-list {
  margin: 4px 0 8px;
  padding-left: 1.4em;
}
.bubble-md ol.qa-md-list {
  list-style: decimal;
}
.bubble-md .qa-md-list li {
  margin: 8px 0;
  line-height: 1.7;
}
.bubble-md .qa-md-table {
  border-collapse: collapse;
  width: 100%;
  margin-top: 6px;
  font-size: 13px;
}
.bubble-md .qa-md-table th,
.bubble-md .qa-md-table td {
  border: 1px solid #e5e7eb;
  padding: 6px 8px;
  text-align: left;
}
.bubble-md .qa-md-table th {
  background: #f8fafc;
}
.sources { margin-top: 8px; padding: 10px 12px; background: #f1f5f9; border-radius: 8px; font-size: 12px; }
.sources-title { color: #64748b; margin-bottom: 4px; font-weight: 500; }
.source-item { color: #475569; padding: 4px 0; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.src-quote { color: #94a3b8; max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.official-link { color: #2563eb; font-size: 12px; }
.miss-box { margin-top: 10px; }
.feedback-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 10px; padding-top: 8px; border-top: 1px solid #f0f0f0; }
.feedback-actions { display: flex; align-items: center; gap: 4px; }
.feedback-label { font-size: 12px; color: #94a3b8; }
.rate-btn { width: 28px; height: 28px; padding: 0; }
.typing { color: #94a3b8; font-style: italic; }
.fb-preview-text { padding: 10px 12px; background: #f8fafc; border-radius: 6px; font-size: 13px; color: #475569; max-height: 120px; overflow-y: auto; }
.candidate-list { display: flex; flex-direction: column; gap: 8px; max-height: 420px; overflow-y: auto; }
.candidate-item { display: flex; gap: 10px; padding: 10px; border: 1px solid #e5e7eb; border-radius: 8px; cursor: pointer; }
.candidate-item.active { border-color: #93c5fd; background: #f8fbff; }
.candidate-title { font-size: 13px; color: #1e293b; }
.candidate-meta { font-size: 12px; color: #94a3b8; margin-top: 4px; }
.hst-item { display: flex; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid #f1f5f9; cursor: pointer; }
.hst-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty-hint { color: #94a3b8; font-size: 13px; }
.preview-body { position: relative; min-height: calc(100vh - 120px); }
.preview-loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: #f8fafc;
  color: #475569;
  z-index: 2;
}
.preview-loading p { margin: 0; font-size: 14px; }
.preview-spinner { font-size: 28px; color: #2563eb; }
.preview-frame { width: 100%; height: calc(100vh - 120px); border: 0; opacity: 0; }
.preview-frame.is-ready { opacity: 1; }
@media (max-width: 980px) {
  .recent-ask-list { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .qa-hero { align-items: flex-start; flex-direction: column; }
}
</style>
