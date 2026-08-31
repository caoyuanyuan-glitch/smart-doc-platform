<template>
  <div class="qa-container">
    <header class="qa-hero">
      <div>
        <h2 class="page-title">知识库问答</h2>
        <p class="page-subtitle">点一张意向卡片框定检索范围，或直接提问检索写作规范与资源库</p>
      </div>
      <el-button v-if="inChat" class="back-home-btn" @click="backToScenes">
        <el-icon><ArrowLeft /></el-icon>
        返回主页
      </el-button>
    </header>

    <div v-if="!inChat" class="qa-home">
      <section class="home-main">
        <div class="scene-grid">
          <button
            v-for="card in SCENE_CARDS"
            :key="card.key"
            class="scene-card"
            :style="{ '--accent': card.accent }"
            type="button"
            :disabled="treeLoading"
            @click="enterScene(card)"
          >
            <span class="scene-mark" aria-hidden="true"></span>
            <span class="scene-kicker">{{ card.kicker }}</span>
            <h3 class="scene-title">{{ card.title }}</h3>
            <p class="scene-desc">{{ card.desc }}</p>
            <span class="scene-meta">{{ sceneDocLabel(card) }}</span>
          </button>
        </div>

        <div class="quick-ask">
          <div class="quick-ask-head">快捷问法</div>
          <button
            v-for="item in GLOBAL_SUGGESTIONS"
            :key="item"
            class="quick-ask-item"
            type="button"
            :disabled="loading"
            @click="sendQuestion(item)"
          >
            {{ item }}
          </button>
        </div>

        <div class="chat-input home-input">
          <el-input
            v-model="question"
            type="textarea"
            :rows="2"
            placeholder="不选卡片将在「写作规范」和「资源库」中全局检索..."
            @keydown.enter.exact.prevent="sendQuestion(question)"
          />
          <el-button class="voice-btn" :class="{ recording: isRecording }" @click="toggleVoice">
            <el-icon><Microphone /></el-icon>
          </el-button>
          <el-button type="primary" :loading="loading" @click="sendQuestion(question)">发送</el-button>
        </div>
      </section>

      <aside class="home-side">
        <div class="side-head">
          <span>最近问答</span>
          <el-button v-if="sessionList.length" size="small" text @click="goHistory">全部</el-button>
        </div>
        <div v-if="!sessionList.length" class="side-empty">提问后，会话会显示在这里</div>
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
      </aside>
    </div>

    <section v-else class="chat-panel">
      <div class="chat-toolbar">
        <el-button size="small" text @click="newConversation" :disabled="messages.length <= 1">
          <el-icon><Plus /></el-icon> 新建会话
        </el-button>
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
        <div class="selected-tags">
          <span class="selected-tags-label">当前范围：</span>
          <template v-if="activeScene">
            <el-tag size="small" closable @close="backToScenes">{{ activeScene.title }}</el-tag>
          </template>
          <template v-else>
            <el-tag size="small">写作规范</el-tag>
            <el-tag size="small">资源库</el-tag>
            <span class="scope-hint">全局检索</span>
          </template>
        </div>
        <div v-if="showInitialSuggestions" class="recommendations">
          <div v-if="initialSuggestionsLoading" class="recommendations-loading">
            <span v-for="n in 4" :key="n" class="skeleton-line"></span>
          </div>
          <div v-else class="suggestion-list">
            <div
              v-for="(q, i) in displaySuggestions"
              :key="i"
              class="suggestion-item"
              @click="clickSuggestion(q)"
            >
              <span class="suggestion-dot"></span>
              <span class="suggestion-text">"{{ stripQuotes(q) }}"</span>
            </div>
          </div>
          <span
            v-if="suggestionsRefreshable && displaySuggestions.length"
            class="refresh-btn"
            @click="refreshInitialSuggestions"
          >
            换一批
          </span>
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
              <div v-for="(s, si) in uniqSources(msg.sources)" :key="si" class="source-item">{{ s.title || s }}</div>
            </div>
            <div v-if="msg.role === 'assistant' && i > 0" class="feedback-row">
              <div class="feedback-actions">
                <span class="feedback-label">评价：</span>
                <el-button
                  class="rate-btn"
                  :type="msg.rating === 1 ? 'primary' : 'default'"
                  size="small"
                  circle
                  title="有帮助"
                  @click="rateAnswer(i, 1)"
                >
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M7 10v12"/>
                    <path d="M15 5.88L14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88z"/>
                  </svg>
                </el-button>
                <el-button
                  class="rate-btn"
                  :type="msg.rating === -1 ? 'danger' : 'default'"
                  size="small"
                  circle
                  title="无帮助"
                  @click="rateAnswer(i, -1)"
                >
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M17 14V2"/>
                    <path d="M9 18.12L10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88z"/>
                  </svg>
                </el-button>
              </div>
              <el-divider direction="vertical" />
              <el-button size="small" text type="warning" @click="openFeedbackDialog(i)">内容有误？点此反馈</el-button>
              <button
                v-if="msg.suggestions && msg.suggestions.length"
                class="followup-toggle"
                type="button"
                @click="toggleFollowup(i)"
              >
                <span class="followup-label">你可能还想问</span>
                <span class="followup-count">{{ msg.suggestions.length }}</span>
                <el-icon class="followup-arrow" :class="{ open: isFollowupOpen(i) }"><ArrowDown /></el-icon>
              </button>
            </div>
            <div
              v-if="msg.role === 'assistant' && i > 0 && msg.suggestions && msg.suggestions.length"
              class="followup-panel"
            >
              <div v-show="isFollowupOpen(i)" class="followup-body">
                <button
                  v-for="(sug, si) in msg.suggestions"
                  :key="si"
                  class="followup-item"
                  :class="{ 'followup-item--expired': i !== lastAssistantIndex }"
                  type="button"
                  :disabled="i !== lastAssistantIndex"
                  @click="i === lastAssistantIndex && clickSuggestion(sug)"
                >
                  {{ stripQuotes(sug) }}
                </button>
              </div>
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
          :placeholder="inputPlaceholder"
          @keydown.enter.exact.prevent="sendQuestion(question)"
        />
        <el-button class="voice-btn" :class="{ recording: isRecording }" @click="toggleVoice">
          <el-icon><Microphone /></el-icon>
        </el-button>
        <el-button type="primary" :loading="loading" @click="sendQuestion(question)">发送</el-button>
      </div>
    </section>

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
import { ref, nextTick, computed, onMounted, inject, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { qaAPI, knowledgeAPI, getKnowledgeLoadErrorMessage } from '@/api'
import { useUserStore } from '@/store/user'
import { User, Microphone, CopyDocument, Download, ArrowDown, ArrowLeft, Plus } from '@element-plus/icons-vue'

const AGENT_KB_NAME = 'AI agent知识库'

const SCENE_CARDS = [
  {
    key: 'style',
    kicker: '写作规范',
    title: '查写作规范与风格',
    desc: '中英文技术文档的语气、用词、标题与版式约定',
    accent: '#1d4ed8',
    paths: [['写作规范', '写作风格指南']],
    suggestions: [
      '中文技术文档标题和术语该怎么写',
      '英文说明书的语气和句式有哪些要求',
      '风格指南里最容易忽略的点是什么'
    ]
  },
  {
    key: 'sentence',
    kicker: '句式清单',
    title: '找表达句式',
    desc: '建库试剂、自动化等说明书里可直接套用的表达',
    accent: '#0f766e',
    paths: [['写作规范', '句式清单']],
    suggestions: [
      '建库试剂说明书常用句式有哪些',
      '自动化说明书里操作步骤该怎么写',
      '平台反馈过哪些需要统一的句式'
    ]
  },
  {
    key: 'review',
    kicker: '审核自检',
    title: '内容审核与自检',
    desc: '常见错误、审核规则、Checklist 与发布前核对项',
    accent: '#b45309',
    paths: [
      ['写作规范', '常见错误清单'],
      ['写作规范', '技术文档审核规则库'],
      ['写作规范', '说明书自检checklist'],
      ['写作规范', '审核依据汇总']
    ],
    suggestions: [
      '发布前我应该按哪些项做自检',
      '技术文档常见错误有哪些',
      '说明书审核时要重点核对什么'
    ]
  },
  {
    key: 'term',
    kicker: '术语库',
    title: '查术语',
    desc: '产品、模块与流程的标准译名和对照表',
    accent: '#be123c',
    paths: [['资源库', '术语库']],
    suggestions: [
      '这个术语的标准译名是什么',
      '自动化相关术语有哪些对照',
      '平台反馈过哪些术语需要统一'
    ]
  },
  {
    key: 'tm',
    kicker: '记忆库',
    title: '中英互译',
    desc: '已审核语料和记忆库条目，用来对照既有译法',
    accent: '#6d28d9',
    paths: [['资源库', '记忆库']],
    suggestions: [
      '这段中文在记忆库里有没有现成译法',
      'T7 相关语料是怎么翻译的',
      '记忆库里有哪些可复用的句对'
    ]
  },
  {
    key: 'files',
    kicker: '文件资料',
    title: '找文件资料',
    desc: '说明书、手册和产品介绍等原始资料',
    accent: '#334155',
    paths: [['资源库', '文件资料']],
    suggestions: [
      '这份说明书的主要内容是什么',
      '产品介绍里强调了哪些功能',
      '培训手册应该从哪一节开始读'
    ]
  }
]

const GLOBAL_SUGGESTIONS = [
  '中文技术文档写作有哪些必须遵守的规范',
  '说明书发布前要做哪些自检',
  '常用术语的标准译名在哪里查',
  '记忆库里有没有可复用的中英句对'
]

const route = useRoute()
const router = useRouter()
const question = ref('')
const loading = ref(false)
const chatBox = ref(null)
const treeData = ref([])
const treeLoading = ref(false)
const activeScene = ref(null)
const askedUnscoped = ref(false)

const messages = ref([])
const initialSuggestionsLoading = ref(false)
const suggestionsRefreshable = ref(false)
const displaySuggestions = ref([])
const openFollowups = ref({})

const inChat = computed(() => Boolean(activeScene.value) || askedUnscoped.value)
const scopeLabel = computed(() => {
  if (activeScene.value) return activeScene.value.title
  return '写作规范、资源库（全局）'
})
const inputPlaceholder = computed(() => {
  if (activeScene.value) return `在「${activeScene.value.title}」范围内提问，按 Enter 发送...`
  return '将在「写作规范」和「资源库」中全局检索，按 Enter 发送...'
})

const showInitialSuggestions = computed(() => {
  return inChat.value && !messages.value.some(m => m.role === 'user')
})

const lastAssistantIndex = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    if (messages.value[i].role === 'assistant') return i
  }
  return -1
})

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
const sessionList = ref([])

function findNodeByPath(nodes, parts) {
  let list = nodes || []
  let node = null
  for (const part of parts) {
    node = list.find(item => item.name === part) || null
    if (!node) return null
    list = node.children || []
  }
  return node
}

function resolveSceneFolderIds(card) {
  const ids = []
  for (const path of card.paths) {
    const node = findNodeByPath(treeData.value, path)
    if (node) ids.push(node.id)
  }
  return ids
}

function sceneDocCount(card) {
  let count = 0
  for (const path of card.paths) {
    const node = findNodeByPath(treeData.value, path)
    count += node?.docCount || 0
  }
  return count
}

function sceneDocLabel(card) {
  if (treeLoading.value) return '正在读取知识库...'
  const count = sceneDocCount(card)
  return count > 0 ? `${count} 份资料` : '目录待同步'
}

function currentKnowledgeIds() {
  if (!activeScene.value) return []
  return resolveSceneFolderIds(activeScene.value)
}

function greetingForScope() {
  if (activeScene.value) {
  return `已进入「${activeScene.value.title}」。我会只检索该范围内的资料。`
  }
  return '将在「写作规范」和「资源库」中全局检索。'
}

function resetMessages(withGreeting = true) {
  messages.value = withGreeting
    ? [{ role: 'assistant', content: greetingForScope(), sources: [], rating: 0 }]
    : []
  sessionId.value = null
  openFollowups.value = {}
}

async function fetchInitialSuggestions() {
  if (!showInitialSuggestions.value) return
  const ids = currentKnowledgeIds()
  if (activeScene.value) {
    displaySuggestions.value = [...activeScene.value.suggestions]
  } else {
    displaySuggestions.value = [...GLOBAL_SUGGESTIONS]
  }
  suggestionsRefreshable.value = Boolean(ids.length)
  if (!ids.length) return
  initialSuggestionsLoading.value = false
  try {
    const resp = await qaAPI.getInitialSuggestions(ids, 4)
    const data = resp.data?.data
    if (data?.suggestions?.length) {
      displaySuggestions.value = data.suggestions
      suggestionsRefreshable.value = data.refreshable === true
    }
  } catch {
    suggestionsRefreshable.value = false
  }
}

function refreshInitialSuggestions() {
  fetchInitialSuggestions()
}

function stripQuotes(text) {
  return String(text || '').replace(/[\u201c\u201d\u2018\u2019\u201a\u201b\u201e\u201f\u0022\u0027\u0060\u300c\u300d\u300e\u300f\uff02\uff07\u00ab\u00bb]/g, '')
}

function clickSuggestion(text) {
  if (loading.value) return
  sendQuestion(text)
}

function isFollowupOpen(index) {
  return Boolean(openFollowups.value[index])
}

function toggleFollowup(index) {
  openFollowups.value = {
    ...openFollowups.value,
    [index]: !openFollowups.value[index]
  }
}

function enterScene(card) {
  if (treeLoading.value) {
    ElMessage.info('知识库目录加载中，请稍候')
    return
  }
  const ids = resolveSceneFolderIds(card)
  if (!ids.length) {
    ElMessage.warning('该场景对应的知识目录暂不可用，请先同步知识库')
    return
  }
  activeScene.value = card
  askedUnscoped.value = false
  resetMessages(true)
  displaySuggestions.value = [...card.suggestions]
  fetchInitialSuggestions()
  nextTick(() => scrollToBottom())
}

function backToScenes() {
  if (loading.value) return
  activeScene.value = null
  askedUnscoped.value = false
  messages.value = []
  sessionId.value = null
  displaySuggestions.value = []
  question.value = ''
  openFollowups.value = {}
  loadSessionList()
}

function newConversation() {
  if (loading.value) return
  resetMessages(true)
  displaySuggestions.value = []
  fetchInitialSuggestions()
  nextTick(() => scrollToBottom())
}

function formatTime(iso) {
  if (!iso) return ''
  return String(iso).replace('T', ' ').slice(0, 16)
}

function goHistory() {
  router.push('/qa/history/general')
}

async function loadSessionList() {
  try {
    const r = await qaAPI.getSessions('general')
    sessionList.value = r.data?.sessions || []
  } catch {
    sessionList.value = []
  }
}

async function loadSession(id) {
  try {
    const r = await qaAPI.getSessionDetail(id)
    const d = r.data
    sessionId.value = id
    activeScene.value = null
    askedUnscoped.value = true
    messages.value = (d.messages || []).map(m => ({
      role: m.role,
      content: m.content,
      sources: m.sources || [],
      rating: m.rating || 0,
      suggestions: []
    }))
    await nextTick()
    scrollToBottom()
  } catch {
    ElMessage.warning('加载失败')
  }
}

onMounted(() => {
  loadKnowledgeTree()
  loadSessionList()
})

watch(() => route.path, () => {
  loadKnowledgeTree()
})

async function loadKnowledgeTree() {
  treeLoading.value = true
  try {
    const resp = await knowledgeAPI.getTree()
    const rawTree = (resp.data || []).filter(node => node.name !== AGENT_KB_NAME)
    treeData.value = transformTreeData(rawTree)
  } catch (e) {
    ElMessage.warning(getKnowledgeLoadErrorMessage(e))
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
  return (nodes || []).map(node => {
    const docCount = countRecursiveDocs(node)
    return {
      id: node.id,
      name: node.name,
      docCount,
      children: node.children && node.children.length ? transformTreeData(node.children) : []
    }
  })
}

async function sendQuestion(q) {
  const text = (typeof q === 'string' ? q : question.value).trim()
  if (!text) return
  const ids = currentKnowledgeIds()
  if (activeScene.value && ids.length === 0) {
    ElMessage.warning('该场景对应的知识目录暂不可用')
    return
  }
  if (!inChat.value) {
    askedUnscoped.value = true
    resetMessages(false)
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
      rating: 0,
      suggestions: data.suggestions || []
    })
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: '抱歉，查询知识库时出现错误，请稍后重试。',
      sources: [],
      rating: 0,
      suggestions: []
    })
  }
  loading.value = false
  await nextTick()
  scrollToBottom()
}

function uniqSources(arr) {
  if (!arr || !arr.length) return []
  const seen = new Set()
  return arr.filter(s => {
    const key = typeof s === 'string' ? s : (s.title || '') + '_' + (s.page || '')
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
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
        md += '\n> 参考来源：' + uniqSources(msg.sources).map(s => s.title || s).join('、') + '\n'
      }
      if (msg.rating === 1) md += '> 评价：有帮助\n'
      if (msg.rating === -1) md += '> 评价：无帮助\n'
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
        html += `<p class="src">参考来源：${escapeHtml(uniqSources(msg.sources).map(s => s.title || s).join('、'))}</p>`
      }
      if (msg.rating === 1) html += '<p class="src">评价：有帮助</p>'
      if (msg.rating === -1) html += '<p class="src">评价：无帮助</p>'
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
.qa-container {
  padding: 0;
  min-height: calc(100vh - 108px);
  display: flex;
  flex-direction: column;
}

.qa-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 14px;
}

.page-title {
  font-size: 26px;
  font-weight: 650;
  color: #111827;
  margin: 0 0 6px;
  letter-spacing: 0.01em;
}

.page-subtitle {
  margin: 0;
  color: #6b7280;
  font-size: 14px;
  line-height: 1.6;
}

.back-home-btn {
  height: 36px;
  padding: 0 14px;
  border: 1px solid #d7dee8;
  background: #fff;
  color: #334155;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.back-home-btn:hover,
.back-home-btn:focus {
  border-color: #93c5fd;
  color: #1d4ed8;
  background: #f8fbff;
}

.qa-home {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 16px;
  min-height: 0;
  align-items: stretch;
}

.home-main {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.scene-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.scene-card {
  position: relative;
  display: flex;
  flex-direction: column;
  text-align: left;
  background: #fffaf3;
  border: 1px solid #efe4d4;
  border-radius: 14px;
  padding: 14px 14px 12px 20px;
  cursor: pointer;
  overflow: hidden;
  box-shadow: 0 8px 18px rgba(28, 25, 23, 0.04);
  transition: transform 0.16s ease, box-shadow 0.16s ease, border-color 0.16s ease;
}

.scene-card:hover {
  transform: translateY(-3px);
  border-color: var(--accent);
  box-shadow: 0 16px 32px rgba(28, 25, 23, 0.08);
}

.scene-card:disabled {
  cursor: wait;
  opacity: 0.7;
  transform: none;
}

.scene-mark {
  position: absolute;
  left: 0;
  top: 14px;
  width: 6px;
  height: 28px;
  border-radius: 0 6px 6px 0;
  background: var(--accent);
}

.scene-kicker {
  display: inline-block;
  font-size: 11px;
  letter-spacing: 0.12em;
  color: var(--accent);
  font-weight: 700;
  margin-bottom: 4px;
}

.scene-title {
  margin: 0 0 4px;
  font-size: 16px;
  color: #1c1917;
  font-weight: 700;
}

.scene-desc {
  margin: 0 0 8px;
  color: #57534e;
  font-size: 13px;
  line-height: 1.5;
}

.scene-meta {
  font-size: 12px;
  color: #a8a29e;
  margin-top: auto;
}

.quick-ask {
  flex: 1;
  min-height: 0;
  background: #fff;
  border: 1px solid #efe8dc;
  border-radius: 14px;
  padding: 10px 14px 12px;
  display: flex;
  flex-direction: column;
}
.quick-ask-head {
  font-size: 12px;
  color: #94a3b8;
  padding: 4px 2px 8px;
}
.quick-ask-item {
  width: 100%;
  text-align: left;
  border: 0;
  border-bottom: 1px solid #f1f5f9;
  background: transparent;
  padding: 10px 6px;
  font-size: 13px;
  color: #334155;
  cursor: pointer;
  line-height: 1.5;
}
.quick-ask-item:hover { background: #f8fbff; color: #1d4ed8; }
.quick-ask-item:disabled { cursor: wait; opacity: 0.6; }

.home-side {
  background: #fff;
  border: 1px solid #e8eef5;
  border-radius: 14px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  min-height: 100%;
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
.side-empty { color: #94a3b8; font-size: 13px; padding: 20px 4px; line-height: 1.6; }
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

.selected-tags {
  padding: 10px 14px;
  background: #f0f7ff;
  border-radius: 8px;
  margin-bottom: 12px;
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

.chat-panel {
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex: 1;
}

.chat-toolbar {
  display: flex;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid #f0f0f0;
  justify-content: flex-end;
  align-items: center;
}

.chat-messages {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  background: #f8fafc;
  min-height: 500px;
  max-height: calc(100vh - 300px);
}

.message { display: flex; margin-bottom: 20px; gap: 10px; }
.message.user { flex-direction: row-reverse; }

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}
.avatar.user { background: #3b82f6; }
.avatar.assistant { background: #409EFF; }

.bubble-wrap { max-width: 70%; }

.bubble {
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.7;
  color: #374151;
  font-size: 14px;
  white-space: pre-wrap;
}
.message.user .bubble { background: #3b82f6; color: #fff; border-bottom-right-radius: 4px; }
.message.assistant .bubble { background: #fff; border: 1px solid #e5e7eb; border-bottom-left-radius: 4px; }

.sources {
  margin-top: 8px;
  padding: 10px 12px;
  background: #f1f5f9;
  border-radius: 8px;
  font-size: 12px;
}
.sources-title { color: #64748b; margin-bottom: 4px; font-weight: 500; }
.source-item { color: #475569; padding: 2px 0; }

.feedback-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid #f0f0f0;
}

.feedback-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.feedback-label {
  font-size: 12px;
  color: #94a3b8;
  margin-right: 2px;
}

.rate-btn {
  width: 28px;
  height: 28px;
  padding: 0;
}
.rate-btn :deep(span) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.typing { color: #94a3b8; font-style: italic; }

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
  box-shadow: 0 8px 20px rgba(28, 25, 23, 0.04);
}
.chat-input .el-textarea { flex: 1; }
.voice-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  padding: 0;
}
.voice-btn.recording {
  background: #ef4444;
  color: #fff;
  border-color: #ef4444;
  animation: pulse 1.2s infinite;
}
@keyframes pulse {
  0%,100% { box-shadow: 0 0 0 0 rgba(239,68,68,0.4); }
  50% { box-shadow: 0 0 0 8px rgba(239,68,68,0); }
}

.feedback-preview-text {
  background: #f8fafc;
  border-radius: 6px;
  padding: 10px;
  font-size: 13px;
  color: #475569;
  max-height: 120px;
  overflow-y: auto;
}

.recommendations {
  margin-bottom: 12px;
  margin-top: 4px;
}
.recommendations-loading {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.skeleton-line {
  height: 20px;
  background: #f0f0f0;
  border-radius: 4px;
  width: 80%;
  animation: skeleton-pulse 1.4s ease-in-out infinite;
}
.skeleton-line:nth-child(2) { width: 66%; }
.skeleton-line:nth-child(3) { width: 74%; }
.skeleton-line:nth-child(4) { width: 56%; }
@keyframes skeleton-pulse {
  0%,100% { opacity: 1; } 50% { opacity: 0.4; }
}
.suggestion-list {
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
}
.suggestion-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  cursor: pointer;
  transition: background 0.15s;
  border-bottom: 1px solid #f0f0f0;
}
.suggestion-item:last-child { border-bottom: none; }
.suggestion-item:hover { background: #f8fafc; }
.suggestion-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #3b82f6;
  flex-shrink: 0;
  margin-top: 8px;
}
.suggestion-text {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  line-height: 1.6;
}
.refresh-btn {
  display: inline-block;
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  cursor: pointer;
  user-select: none;
}
.refresh-btn:hover { color: #3b82f6; }

.followup-panel {
  margin-top: 0;
}
.followup-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 10px 0 12px;
  border: 1px solid #e6edf5;
  border-radius: 999px;
  background: #f8fafc;
  color: #64748b;
  font-size: 12px;
  cursor: pointer;
  flex-shrink: 0;
  margin-left: 4px;
}
.followup-toggle:hover {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
}
.followup-label {
  line-height: 1;
}
.followup-count {
  min-width: 16px;
  height: 16px;
  padding: 0 5px;
  border-radius: 999px;
  background: #e2e8f0;
  color: #475569;
  font-size: 11px;
  line-height: 16px;
  text-align: center;
}
.followup-toggle:hover .followup-count {
  background: #dbeafe;
  color: #1d4ed8;
}
.followup-arrow {
  font-size: 11px;
  transition: transform 0.18s ease;
}
.followup-arrow.open { transform: rotate(180deg); }
.followup-body {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}
.followup-item {
  text-align: left;
  border: 1px solid #e8eef5;
  background: #fff;
  border-radius: 8px;
  padding: 7px 11px;
  font-size: 13px;
  color: #334155;
  line-height: 1.5;
  cursor: pointer;
  max-width: 100%;
}
.followup-item:hover {
  border-color: #93c5fd;
  background: #f8fbff;
  color: #1d4ed8;
}
.followup-item--expired,
.followup-item:disabled {
  cursor: default;
  opacity: 0.45;
}
.followup-item--expired:hover,
.followup-item:disabled:hover {
  border-color: #e8eef5;
  background: #fff;
  color: #334155;
}

@media (max-width: 980px) {
  .qa-home { grid-template-columns: 1fr; }
  .scene-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 640px) {
  .scene-grid { grid-template-columns: 1fr; }
  .qa-hero { align-items: flex-start; flex-direction: column; }
}
</style>
