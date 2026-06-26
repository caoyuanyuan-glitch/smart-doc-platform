<template>
  <div class="qa-history-page">
    <div class="page-header">
      <h2 class="page-title">{{ activeTab === 'general' ? '知识库问答历史' : '说明书问答历史' }}</h2>
      <div class="page-tabs">
        <el-radio-group :model-value="activeTab" size="small" @change="handleTabChange">
          <el-radio-button value="general">知识库问答历史</el-radio-button>
          <el-radio-button value="doc">说明书问答历史</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <div class="content-area">
      <div class="sessions-panel">
        <div class="panel-header">
          <span class="panel-title">会话列表</span>
          <span class="session-count">共 {{ sessions.length }} 个会话</span>
        </div>
        <div class="session-list" v-loading="loading">
          <div
            v-for="sess in sessions"
            :key="sess.id"
            class="session-item"
            :class="{ active: selectedSession?.id === sess.id }"
            @click="selectSession(sess)"
          >
            <div class="session-title">{{ sess.title }}</div>
            <div class="session-meta">
              <span class="session-time">{{ formatTime(sess.updated_at) }}</span>
              <span class="session-msgs">{{ sess.message_count }} 条消息</span>
            </div>
            <el-button
              class="session-delete"
              size="small"
              type="danger"
              text
              @click.stop="handleDelete(sess.id)"
            >
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
          <div v-if="!loading && sessions.length === 0" class="empty-hint">暂无历史记录</div>
        </div>
      </div>

      <div class="messages-panel" :class="{ expanded: selectedSession }">
        <template v-if="selectedSession">
          <div class="panel-header">
            <span class="panel-title">{{ selectedSession.title }}</span>
            <div class="panel-header-right">
              <el-dropdown @command="handleExport">
                <el-button size="small" text :disabled="messages.length === 0">
                  <el-icon><Download /></el-icon> 导出
                  <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="md">Markdown (.md)</el-dropdown-item>
                    <el-dropdown-item command="word">Word (.doc)</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <span class="session-time">{{ formatTime(selectedSession.created_at) }}</span>
            </div>
          </div>
          <div class="messages-box" ref="msgBox">
            <div
              v-for="msg in messages"
              :key="msg.id"
              class="msg-item"
              :class="'msg-' + msg.role"
            >
              <div class="msg-role">{{ msg.role === 'user' ? '你' : 'AI' }}</div>
              <div class="msg-content">{{ msg.content }}</div>
              <div v-if="msg.sources && msg.sources.length" class="msg-sources">
                <span class="sources-label">参考来源：</span>
                <template v-for="(s, si) in msg.sources" :key="si">
                  <el-tag size="small" type="info" class="source-tag">{{ s.title || s }}</el-tag>
                </template>
              </div>
            </div>
          </div>
        </template>
        <div v-else class="no-selection">
          <el-icon :size="48"><ChatDotRound /></el-icon>
          <p>选择一个会话查看详情</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { qaAPI } from '@/api'
import { ChatDotRound, Delete, Download, ArrowDown } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const activeTab = computed(() => route.path.includes('/qa/history/doc') ? 'doc' : 'general')
const sessions = ref([])
const selectedSession = ref(null)
const messages = ref([])
const loading = ref(false)
const msgBox = ref(null)

function formatTime(t) {
  if (!t) return ''
  return t.replace('T', ' ').substring(0, 19)
}

function handleTabChange(tab) {
  const targetPath = tab === 'doc' ? '/qa/history/doc' : '/qa/history/general'
  if (route.path !== targetPath) {
    router.push(targetPath)
  }
}

async function loadSessions() {
  loading.value = true
  try {
    const resp = await qaAPI.getSessions(activeTab.value)
    sessions.value = resp.data.sessions || []
    if (selectedSession.value) {
      const found = sessions.value.find(s => s.id === selectedSession.value.id)
      if (!found) {
        selectedSession.value = null
        messages.value = []
      }
    }
  } catch {
    sessions.value = []
  }
  loading.value = false
}

async function selectSession(sess) {
  selectedSession.value = sess
  try {
    const resp = await qaAPI.getSessionDetail(sess.id)
    messages.value = resp.data.messages || []
    await nextTick()
    if (msgBox.value) {
      msgBox.value.scrollTop = msgBox.value.scrollHeight
    }
  } catch {
    messages.value = []
  }
}

async function handleDelete(id) {
  try {
    await ElMessageBox.confirm('确定要删除此历史记录吗？', '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await qaAPI.deleteSession(id)
    ElMessage.success('已删除')
    if (selectedSession.value?.id === id) {
      selectedSession.value = null
      messages.value = []
    }
    await loadSessions()
  } catch {
    ElMessage.error('删除失败')
  }
}

function handleExport(format) {
  if (messages.value.length === 0) return
  const title = (selectedSession.value?.title || '会话').replace(/[\\/:*?"<>|]/g, '_')
  if (format === 'md') {
    downloadFile(buildMarkdown(), `${title}.md`, 'text/markdown')
  } else if (format === 'word') {
    downloadFile(buildHtml(), `${title}.doc`, 'application/msword')
  }
}

function buildMarkdown() {
  let md = `# ${selectedSession.value?.title || '问答会话'}\n\n`
  for (const msg of messages.value) {
    if (msg.role === 'user') {
      md += `## Q: ${msg.content}\n\n**AI 回答：**\n`
    } else if (msg.role === 'assistant') {
      md += msg.content + '\n'
      if (msg.sources && msg.sources.length) {
        md += '\n> 参考来源：' + msg.sources.map(s => s.title || s).join('、') + '\n'
      }
      md += '\n---\n\n'
    }
  }
  return md
}

function buildHtml() {
  const title = selectedSession.value?.title || '问答会话'
  let html = `<html><head><meta charset="utf-8"><title>${title}</title>
<style>body{font-family:"Microsoft YaHei",sans-serif;max-width:800px;margin:40px auto;line-height:1.8}
h1{border-bottom:2px solid #2563eb;padding-bottom:8px}
.q{margin-top:24px;font-weight:600;color:#1e40af}.a{background:#f8fafc;padding:12px 16px;border-radius:8px;margin:8px 0}
.src{color:#94a3b8;font-size:13px}.bar{color:#94a3b8;margin:24px 0;text-align:center}</style></head><body>
<h1>${escapeHtml(title)}</h1>
`
  for (const msg of messages.value) {
    if (msg.role === 'user') {
      html += `<div class="q">Q: ${escapeHtml(msg.content)}</div>`
    } else if (msg.role === 'assistant') {
      html += `<div class="a">${escapeHtml(msg.content)}</div>`
      if (msg.sources && msg.sources.length) {
        html += `<p class="src">参考来源：${escapeHtml(msg.sources.map(s => s.title || s).join('、'))}</p>`
      }
      html += '<div class="bar">---</div>'
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

watch(() => route.path, () => {
  selectedSession.value = null
  messages.value = []
  loadSessions()
}, { immediate: true })
</script>

<style scoped>
.qa-history-page {
  display: flex; flex-direction: column; height: 100%; padding: 20px;
}

.page-header {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px;
}

.page-title { font-size: 18px; font-weight: 600; margin: 0; }

.content-area {
  display: flex; gap: 16px; flex: 1; overflow: hidden;
}

.sessions-panel {
  width: 340px; min-width: 280px; border: 1px solid #e5e7eb; border-radius: 8px;
  display: flex; flex-direction: column; overflow: hidden; background: #fff;
}

.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; border-bottom: 1px solid #f0f0f0;
}

.panel-title { font-weight: 600; font-size: 14px; }

.session-count { font-size: 12px; color: #94a3b8; }

.session-list {
  flex: 1; overflow-y: auto; padding: 8px;
}

.session-item {
  display: flex; align-items: center; padding: 10px 12px; border-radius: 6px;
  cursor: pointer; margin-bottom: 4px; position: relative;
  transition: background .15s;
}

.session-item:hover { background: #f8fafc; }

.session-item.active { background: #eff6ff; }

.session-title {
  flex: 1; font-size: 13px; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; margin-right: 8px;
}

.session-meta {
  display: flex; flex-direction: column; align-items: flex-end; gap: 2px; flex-shrink: 0;
}

.session-time { font-size: 11px; color: #94a3b8; }

.session-msgs { font-size: 11px; color: #94a3b8; }

.session-delete { flex-shrink: 0; margin-left: 4px; opacity: 0; transition: opacity .15s; }

.session-item:hover .session-delete { opacity: 1; }

.empty-hint {
  text-align: center; padding: 40px 0; color: #94a3b8; font-size: 14px;
}

.messages-panel {
  flex: 1; border: 1px solid #e5e7eb; border-radius: 8px;
  display: flex; flex-direction: column; overflow: hidden; background: #fff;
}

.no-selection {
  flex: 1; display: flex; flex-direction: column; align-items: center;
  justify-content: center; color: #94a3b8; gap: 12px;
}

.no-selection p { font-size: 14px; }

.panel-header-right { display: flex; align-items: center; gap: 8px; }

.panel-header .session-time { font-size: 12px; color: #94a3b8; }

.messages-box {
  flex: 1; overflow-y: auto; padding: 16px;
}

.msg-item { margin-bottom: 16px; }

.msg-role { font-size: 12px; color: #94a3b8; margin-bottom: 4px; }

.msg-content {
  white-space: pre-wrap; word-break: break-word; line-height: 1.6;
  font-size: 14px; background: #f8fafc; padding: 10px 14px; border-radius: 8px;
}

.msg-assistant .msg-content { background: #eff6ff; }

.msg-sources { margin-top: 6px; display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }

.sources-label { font-size: 12px; color: #94a3b8; }

.source-tag { font-size: 11px; }
</style>
