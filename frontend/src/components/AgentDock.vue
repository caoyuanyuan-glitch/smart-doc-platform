<template>
  <div class="agent-dock" v-if="isAuthenticated">
    <transition name="agent-panel">
      <section class="agent-panel" v-show="open" aria-label="智能助手">
        <header class="agent-header">
          <div class="agent-title">
            <span class="agent-title-dot"></span>
            <span>智能助手</span>
            <span class="agent-title-sub">一句话调用平台功能</span>
          </div>
          <div class="agent-header-actions">
            <el-tooltip content="清空对话" placement="bottom">
              <button class="agent-icon-btn" @click="clearMessages" aria-label="清空对话">
                <el-icon><Delete /></el-icon>
              </button>
            </el-tooltip>
            <button class="agent-icon-btn" @click="open = false" aria-label="收起">
              <el-icon><Close /></el-icon>
            </button>
          </div>
        </header>

        <div class="agent-body" ref="bodyRef">
          <div v-if="messages.length === 0" class="agent-welcome">
            <p class="agent-welcome-title">你好，我是平台智能助手</p>
            <p class="agent-welcome-desc">告诉我你想做什么，我帮你调用对应模块，或带你到对应页面。</p>
            <div class="agent-chips">
              <button
                v-for="c in quickPrompts"
                :key="c"
                class="agent-chip"
                @click="sendText(c)"
              >{{ c }}</button>
            </div>
          </div>

          <div v-for="(msg, idx) in messages" :key="idx" class="agent-msg" :class="msg.role">
            <div class="agent-bubble">{{ msg.content }}</div>
            <button
              v-if="msg.role === 'assistant' && msg.action && msg.action.type === 'navigate' && msg.action.path"
              class="agent-jump"
              @click="goTo(msg.action)"
            >
              前往{{ msg.moduleName || '对应页面' }} <span aria-hidden="true">→</span>
            </button>
          </div>

          <div v-if="sending" class="agent-msg assistant">
            <div class="agent-bubble agent-thinking">正在理解你的意图<span class="agent-dots">…</span></div>
          </div>
        </div>

        <footer class="agent-footer">
          <el-input
            v-model="input"
            type="textarea"
            :rows="2"
            resize="none"
            placeholder="例如：帮我润色这段话 / 审核文档"
            @keydown.enter.exact.prevent="send"
            :disabled="sending"
          />
          <div class="agent-footer-bar">
            <span class="agent-hint">Enter 发送 · Shift+Enter 换行</span>
            <el-button type="primary" size="small" :loading="sending" @click="send">发送</el-button>
          </div>
        </footer>
      </section>
    </transition>

    <button
      class="agent-fab"
      :class="{ active: open }"
      @click="open = !open"
      :aria-label="open ? '收起智能助手' : '打开智能助手'"
      :title="open ? '收起智能助手' : '打开智能助手'"
    >
      <el-icon v-if="!open" :size="24"><ChatDotRound /></el-icon>
      <el-icon v-else :size="24"><Close /></el-icon>
    </button>
  </div>
</template>

<script setup>
import { ref, nextTick, computed } from 'vue'
import { useRouter } from 'vue-router'
import { agentAPI } from '@/api'
import { ChatDotRound, Close, Delete } from '@element-plus/icons-vue'

const router = useRouter()
const open = ref(false)
const input = ref('')
const sending = ref(false)
const messages = ref([])
const bodyRef = ref(null)
const quickPrompts = ['帮我润色一段文本', '生成一篇使用说明书', '审核这份文档', '对比两个版本']
const isAuthenticated = computed(() => !!localStorage.getItem('token'))

function scrollToBottom() {
  nextTick(() => {
    if (bodyRef.value) bodyRef.value.scrollTop = bodyRef.value.scrollHeight
  })
}

function clearMessages() {
  messages.value = []
}

function historyPayload() {
  return messages.value.slice(-6).map(m => ({ role: m.role, content: m.content }))
}

async function sendText(text) {
  const message = (text ?? input.value).trim()
  if (!message || sending.value) return
  input.value = ''
  messages.value.push({ role: 'user', content: message })
  sending.value = true
  scrollToBottom()
  try {
    const res = await agentAPI.chat(message, historyPayload())
    const data = res.data || {}
    messages.value.push({
      role: 'assistant',
      content: data.reply || '抱歉，我暂时无法处理，请稍后重试。',
      action: data.action || null,
      moduleName: data.module_name || null,
      intent: data.intent || null
    })
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: '调用失败，请检查后端服务是否已启动，或直接点击左侧菜单使用对应模块。',
      action: null,
      moduleName: null
    })
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

function send() {
  sendText(input.value)
}

function goTo(action) {
  const query = { ...(action.params || {}) }
  router.push({ path: action.path, query })
  open.value = false
}
</script>

<style scoped>
.agent-dock { position: fixed; right: 24px; bottom: 24px; z-index: 3000; }
.agent-fab {
  width: 56px; height: 56px; border-radius: 50%; border: none; cursor: pointer;
  background: #409eff; color: #fff; display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 20px rgba(64, 158, 255, .4); margin-left: auto; transition: transform .2s, background .2s;
}
.agent-fab:hover { transform: translateY(-2px); background: #337ecc; }
.agent-fab.active { background: #5a5a5a; box-shadow: 0 4px 14px rgba(0, 0, 0, .2); }
.agent-panel {
  width: 360px; height: 540px; max-height: calc(100vh - 120px); margin-bottom: 12px; margin-left: auto;
  background: #fff; border: 1px solid #e4e7ed; border-radius: 14px; overflow: hidden;
  box-shadow: 0 10px 40px rgba(0, 0, 0, .16); display: flex; flex-direction: column;
}
.agent-header {
  height: 52px; flex: 0 0 52px; padding: 0 14px; display: flex; align-items: center; justify-content: space-between;
  background: #f5f7fa; border-bottom: 1px solid #e4e7ed;
}
.agent-title { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: #303133; }
.agent-title-dot { width: 8px; height: 8px; border-radius: 50%; background: #409eff; }
.agent-title-sub { font-size: 12px; font-weight: 400; color: #909399; }
.agent-header-actions { display: flex; gap: 4px; }
.agent-icon-btn {
  width: 28px; height: 28px; border: none; background: transparent; color: #606266; cursor: pointer;
  border-radius: 6px; display: flex; align-items: center; justify-content: center;
}
.agent-icon-btn:hover { background: #e9e9eb; }
.agent-body { flex: 1 1 auto; overflow-y: auto; padding: 14px; background: #fafafa; }
.agent-welcome { padding: 12px 4px; }
.agent-welcome-title { margin: 0 0 6px; font-size: 15px; font-weight: 600; color: #303133; }
.agent-welcome-desc { margin: 0 0 14px; font-size: 13px; color: #909399; line-height: 1.6; }
.agent-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.agent-chip {
  border: 1px solid #dcdfe6; background: #fff; color: #409eff; border-radius: 16px;
  padding: 6px 12px; font-size: 12px; cursor: pointer; transition: all .2s;
}
.agent-chip:hover { background: #ecf5ff; border-color: #409eff; }
.agent-msg { display: flex; flex-direction: column; margin-bottom: 14px; align-items: flex-start; }
.agent-msg.user { align-items: flex-end; }
.agent-bubble {
  max-width: 86%; padding: 10px 12px; border-radius: 10px; font-size: 13px; line-height: 1.6;
  white-space: pre-wrap; word-break: break-word; background: #fff; color: #303133; border: 1px solid #e4e7ed;
}
.agent-msg.user .agent-bubble { background: #409eff; color: #fff; border-color: #409eff; border-bottom-right-radius: 2px; }
.agent-msg.assistant .agent-bubble { border-bottom-left-radius: 2px; }
.agent-jump {
  margin-top: 6px; border: none; background: transparent; color: #409eff; font-size: 12px;
  cursor: pointer; padding: 2px 0;
}
.agent-jump:hover { text-decoration: underline; }
.agent-thinking { color: #909399; }
.agent-dots { letter-spacing: 2px; }
.agent-footer { flex: 0 0 auto; padding: 10px 12px 12px; border-top: 1px solid #e4e7ed; background: #fff; }
.agent-footer-bar { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; }
.agent-hint { font-size: 11px; color: #a8abb2; }
.agent-panel-enter-active, .agent-panel-leave-active { transition: opacity .18s, transform .18s; }
.agent-panel-enter-from, .agent-panel-leave-to { opacity: 0; transform: translateY(12px); }
</style>
