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

            <div
              v-if="msg.role === 'assistant' && msg.sources && msg.sources.length"
              class="agent-sources"
            >
              <span class="agent-sources-label">参考来源</span>
              <span
                v-for="(src, sidx) in msg.sources"
                :key="sidx"
                class="agent-source-tag"
                :title="src.snippet || ''"
              >{{ src.title }}</span>
            </div>

            <div v-if="msg.role === 'assistant' && msg.upload" class="agent-upload">
              <div v-if="msg.upload.intent === 'convert'" class="agent-convert-format">
                <span class="agent-upload-hint">转成</span>
                <select v-model="msg.upload.targetFormat" class="agent-format-select">
                  <option value="markdown">Markdown</option>
                  <option value="dita">DITA</option>
                  <option value="csv">CSV</option>
                </select>
              </div>
              <input
                :ref="el => setUploadInput(el, idx)"
                type="file"
                :multiple="msg.upload.multiple"
                :accept="msg.upload.accept || ''"
                class="agent-file-input"
                @change="onFileSelected($event, idx, msg)"
              />
              <button class="agent-upload-btn" :disabled="sending || msg.task?.running" @click="triggerUpload(idx)">
                <span class="agent-upload-icon">＋</span>
                {{ uploadButtonText(msg.upload) }}
              </button>
              <span class="agent-upload-hint">{{ msg.upload.hint }}</span>
            </div>

            <div v-if="msg.role === 'assistant' && msg.task" class="agent-task">
              <div class="agent-task-head">
                <span class="agent-task-status" :class="msg.task.status">{{ taskStatusText(msg.task) }}</span>
                <span v-if="msg.task.running" class="agent-task-pct">{{ msg.task.progress || 0 }}%</span>
              </div>
              <div v-if="msg.task.running" class="agent-task-bar">
                <div class="agent-task-bar-fill" :style="{ width: (msg.task.progress || 0) + '%' }"></div>
              </div>
              <div v-if="msg.task.step" class="agent-task-step">{{ msg.task.step }}</div>
              <div v-if="msg.task.summary" class="agent-task-summary">{{ msg.task.summary }}</div>
              <button
                v-if="msg.task.status === 'completed' && msg.task.resultPath"
                class="agent-jump"
                @click="goTo({ path: msg.task.resultPath, params: msg.task.resultParams || {} })"
              >查看完整报告 <span aria-hidden="true">→</span></button>
              <button
                v-if="msg.task.status === 'failed'"
                class="agent-jump"
                @click="retryTask(idx, msg)"
              >重试</button>
            </div>

            <button
              v-if="msg.role === 'assistant' && msg.action && msg.action.type === 'navigate' && msg.action.path && !msg.upload && !msg.task"
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
            @keydown.enter.exact.prevent="onEnterKey"
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
import { ref, nextTick, computed, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { agentAPI, documentAPI, reviewAPI, compareAPI, convertAPI, getAPIErrorMessage } from '@/api'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Close, Delete } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'

const router = useRouter()
const userStore = useUserStore()
const open = ref(false)
const input = ref('')
const sending = ref(false)
const messages = ref([])
const bodyRef = ref(null)
const quickPrompts = ['帮我润色一段文本', '生成一篇使用说明书', '审核这份文档', '对比两个版本']
// 用响应式登录态（登录/退出即时生效），不再读非响应式 localStorage
const isAuthenticated = computed(() => userStore.isLoggedIn)

const uploadInputs = ref({})
const pollTimers = ref({})

function setUploadInput(el, idx) {
  if (el) uploadInputs.value[idx] = el
}
function triggerUpload(idx) {
  const el = uploadInputs.value[idx]
  if (el) el.click()
}
function taskStatusText(task) {
  const runningLabel = task.type === 'convert' ? '转换中' : task.type === 'compare' ? '对比中' : '审核中'
  const map = {
    pending: '准备中', uploading: '上传文件中',
    running: runningLabel,
    processing: task.type === 'compare' ? '对比中' : '转换中',
    completed: '已完成', failed: '失败', cancelled: '已停止'
  }
  return map[task.status] || task.status || '处理中'
}
function uploadButtonText(upload) {
  if (upload.intent === 'compare') return '选择两个文件对比'
  if (upload.intent === 'convert') return '选择待转换文件'
  return '选择待审核文件'
}
function stopPolling(idx) {
  if (pollTimers.value[idx]) {
    clearInterval(pollTimers.value[idx])
    delete pollTimers.value[idx]
  }
}
onBeforeUnmount(() => {
  Object.values(pollTimers.value).forEach(t => clearInterval(t))
})

function scrollToBottom() {
  nextTick(() => {
    if (bodyRef.value) bodyRef.value.scrollTop = bodyRef.value.scrollHeight
  })
}

function clearMessages() {
  // 先停掉所有在途轮询，避免清空后定时器仍持续请求并写入已脱离渲染的消息
  Object.keys(pollTimers.value).forEach(stopPolling)
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
    const assistantMsg = {
      role: 'assistant',
      content: data.reply || '抱歉，我暂时无法处理，请稍后重试。',
      action: data.action || null,
      moduleName: data.module_name || null,
      intent: data.intent || null,
      sources: data.sources || [],
      answerSource: data.answer_source || null,
      upload: null,
      task: null
    }
    // 审核/对比/转换：在对话内提供上传入口，不跳转落地页
    const docAccept = '.pdf,.doc,.docx,.txt,.md,.xlsx,.xls'
    if (data.intent === 'review') {
      assistantMsg.upload = { intent: 'review', multiple: false, accept: docAccept, hint: '支持 PDF / Word / Excel / Markdown' }
      assistantMsg.action = null
    } else if (data.intent === 'compare') {
      assistantMsg.upload = { intent: 'compare', multiple: true, accept: docAccept, hint: '请一次选中两个文件（Ctrl/Shift 多选）' }
      assistantMsg.action = null
    } else if (data.intent === 'convert') {
      assistantMsg.upload = { intent: 'convert', multiple: false, accept: '.md,.markdown,.docx,.doc,.csv,.zip,.idml', hint: '支持 Markdown / Word / CSV / IDML', targetFormat: 'markdown' }
      assistantMsg.action = null
    }
    messages.value.push(assistantMsg)
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

function onEnterKey(e) {
  // 中文/日文输入法选词回车（isComposing）不应触发发送
  if (e && (e.isComposing || e.keyCode === 229)) return
  send()
}

function goTo(action) {
  const query = { ...(action.params || {}) }
  router.push({ path: action.path, query })
  open.value = false
}

// 文件选择 → 按意图执行审核或对比
async function onFileSelected(event, idx, msg) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return
  if (msg.intent === 'compare' && files.length < 2) {
    ElMessage.warning('对比需要至少两个文件，请一次选择两个')
    return
  }
  if (msg.intent === 'review') {
    await startReview(files[0], idx, msg)
  } else if (msg.intent === 'compare') {
    await startCompare(files.slice(0, 2), idx, msg)
  } else if (msg.intent === 'convert') {
    await startConvert(files[0], msg.upload.targetFormat || 'markdown', idx, msg)
  }
}

function initTask(msg, type) {
  msg.task = { type, status: 'uploading', progress: 0, step: '上传文件中', running: true, summary: '', resultPath: '' }
  msg.upload = null
  scrollToBottom()
}

// 审核：上传 → 触发 → 轮询进度 → 结果摘要
async function startReview(file, idx, msg) {
  initTask(msg, 'review')
  try {
    const up = await documentAPI.upload(file)
    const documentId = up.data?.id
    if (!documentId) throw new Error('上传未返回文档 id')
    msg.task.step = '已上传，正在启动审核'
    msg.task.progress = 5

    const created = await reviewAPI.create(documentId, 'hybrid')
    const reviewId = created.data?.review_id
    if (!reviewId) throw new Error('启动审核未返回 review id')
    msg.task.reviewId = reviewId
    msg.task.status = 'running'
    msg.task.step = '审核进行中'
    scrollToBottom()

    let failCount = 0
    pollTimers.value[idx] = setInterval(async () => {
      try {
        const p = await reviewAPI.getProgress(reviewId)
        const d = p.data || {}
        msg.task.progress = typeof d.progress === 'number' ? Math.round(d.progress) : (msg.task.progress || 0)
        msg.task.step = d.step || d.message || '审核进行中'
        const st = String(d.status || '').toLowerCase()
        failCount = 0
        if (['completed', 'failed', 'cancelled', 'error', 'timeout'].includes(st)) {
          stopPolling(idx)
          await finishReview(st, reviewId, msg)
        }
      } catch (e) {
        failCount += 1
        if (failCount >= 5) {
          stopPolling(idx)
          msg.task.status = 'failed'
          msg.task.running = false
          msg.task.step = '进度查询失败，请重试'
          scrollToBottom()
        }
      }
    }, 1500)
  } catch (e) {
    msg.task.status = 'failed'
    msg.task.running = false
    msg.task.step = '审核启动失败：' + (getAPIErrorMessage(e) || '未知错误')
    scrollToBottom()
  }
}

async function finishReview(status, reviewId, msg) {
  msg.task.running = false
  if (status !== 'completed') {
    msg.task.status = status === 'failed' || status === 'error' ? 'failed' : 'cancelled'
    msg.task.step = '审核未成功完成'
    scrollToBottom()
    return
  }
  msg.task.status = 'completed'
  msg.task.progress = 100
  msg.task.step = '审核完成'
  try {
    const issuesResp = await reviewAPI.getIssues(reviewId)
    const issues = issuesResp.data || []
    const serious = issues.filter(i => ['serious', 'critical', '严重', '错误'].includes(String(i.severity || '').toLowerCase())).length
    msg.task.summary = issues.length
      ? `共发现 ${issues.length} 个问题，其中严重 ${serious} 个；任务已保存到「审核任务」历史。`
      : '审核完成，未发现问题；任务已保存到「审核任务」历史。'
  } catch (e) {
    msg.task.summary = '审核已完成，任务已保存到「审核任务」历史。'
  }
  msg.task.resultPath = '/review/tasks'
  msg.task.resultParams = { reviewId }
  scrollToBottom()
}

// 对比：上传 → 后台异步对比 → 轮询进度 → 结果摘要（不再同步阻塞聊天）
async function startCompare(files, idx, msg) {
  initTask(msg, 'compare')
  msg.task.step = '正在上传并启动对比'
  try {
    const resp = await compareAPI.create(files, true) // async_mode=true
    const d = resp.data || {}
    const groupId = d.group_id
    if (!groupId) throw new Error('启动对比未返回 group_id')
    msg.task.groupId = groupId
    msg.task.status = 'running'
    msg.task.step = '对比进行中（后台执行）'
    msg.task.progress = 5
    scrollToBottom()

    let failCount = 0
    pollTimers.value[idx] = setInterval(async () => {
      try {
        const p = await compareAPI.getProgress(groupId)
        const pd = p.data || {}
        msg.task.progress = typeof pd.progress === 'number' ? Math.round(pd.progress) : (msg.task.progress || 0)
        msg.task.step = pd.step || pd.message || '对比进行中'
        const st = String(pd.status || '').toLowerCase()
        failCount = 0
        if (['completed', 'failed', 'cancelled', 'error', 'timeout'].includes(st)) {
          stopPolling(idx)
          await finishCompare(st, groupId, files.length, msg, pd)
        }
      } catch (e) {
        failCount += 1
        if (failCount >= 5) {
          stopPolling(idx)
          msg.task.status = 'failed'
          msg.task.running = false
          msg.task.step = '进度查询失败，请到「对比任务」历史查看结果'
          scrollToBottom()
        }
      }
    }, 1500)
  } catch (e) {
    msg.task.running = false
    msg.task.status = 'failed'
    msg.task.step = '对比启动失败：' + (getAPIErrorMessage(e) || '未知错误')
    scrollToBottom()
  }
}

async function finishCompare(status, groupId, fileCount, msg, progressData) {
  msg.task.running = false
  if (status !== 'completed') {
    msg.task.status = status === 'failed' || status === 'error' ? 'failed' : 'cancelled'
    msg.task.step = '对比未成功完成'
    scrollToBottom()
    return
  }
  msg.task.status = 'completed'
  msg.task.progress = 100
  msg.task.step = '对比完成'
  const results = (progressData && progressData.results) || []
  const totalDiffs = results.reduce((s, r) => s + (Number(r.total_diffs) || 0), 0)
  const verdict = results[0]?.verdict || ''
  msg.task.summary = `已对比 ${fileCount} 个文件，共 ${totalDiffs} 处差异${verdict ? `，判定：${verdict}` : ''}；任务已保存到「对比任务」历史。`
  msg.task.resultPath = '/compare/tasks'
  msg.task.resultParams = { groupId }
  scrollToBottom()
}

// 转换：上传 → 触发 → 轮询进度 → 完成提示（任务已落库到转换历史）
async function startConvert(file, targetFormat, idx, msg) {
  initTask(msg, 'convert')
  msg.task.step = '正在上传并启动转换'
  try {
    const resp = await convertAPI.convert(file, targetFormat)
    const d = resp.data || {}
    const taskId = d.task_id
    if (!taskId) throw new Error('转换未返回 task_id')
    msg.task.taskId = taskId
    msg.task.status = 'processing'
    msg.task.step = '转换进行中'
    scrollToBottom()

    let failCount = 0
    pollTimers.value[idx] = setInterval(async () => {
      try {
        const p = await convertAPI.getProgress(taskId)
        const pd = p.data || {}
        msg.task.progress = typeof pd.progress === 'number' ? pd.progress : (msg.task.progress || 0)
        msg.task.step = pd.current_step || '转换进行中'
        msg.task.progressMsg = pd.error_message || ''
        failCount = 0
        const st = String(pd.status || '').toLowerCase()
        if (['completed', 'failed', 'cancelled', 'error'].includes(st)) {
          stopPolling(idx)
          msg.task.running = false
          if (st === 'completed') {
            msg.task.status = 'completed'
            msg.task.progress = 100
            msg.task.step = '转换完成'
            msg.task.summary = `已转换为 ${targetFormat.toUpperCase()}，任务已保存到「转换历史」。`
            msg.task.resultPath = '/convert/history'
            msg.task.resultParams = {}
          } else {
            msg.task.status = 'failed'
            msg.task.step = '转换失败' + (pd.error_message ? '：' + pd.error_message : '')
          }
          scrollToBottom()
        }
      } catch (e) {
        failCount += 1
        if (failCount >= 5) {
          stopPolling(idx)
          msg.task.status = 'failed'
          msg.task.running = false
          msg.task.step = '进度查询失败，可到转换历史查看'
          scrollToBottom()
        }
      }
    }, 1500)
  } catch (e) {
    msg.task.status = 'failed'
    msg.task.running = false
    msg.task.step = '转换启动失败：' + (getAPIErrorMessage(e) || '未知错误')
    scrollToBottom()
  }
}

function retryTask(idx, msg) {
  const type = msg.task?.type
  msg.task = null
  const docAccept = '.pdf,.doc,.docx,.txt,.md,.xlsx,.xls'
  if (type === 'compare') {
    msg.upload = { intent: 'compare', multiple: true, accept: docAccept, hint: '请一次选中两个文件（Ctrl/Shift 多选）' }
  } else if (type === 'convert') {
    msg.upload = { intent: 'convert', multiple: false, accept: '.md,.markdown,.docx,.doc,.csv,.zip,.idml', hint: '支持 Markdown / Word / CSV / IDML', targetFormat: 'markdown' }
  } else {
    msg.upload = { intent: 'review', multiple: false, accept: docAccept, hint: '支持 PDF / Word / Excel / Markdown' }
  }
  nextTick(() => triggerUpload(idx))
}
</script>

<style scoped>
/* z-index 低于 Element Plus 弹层（~2000+），避免盖住对话框；小屏自适应宽度 */
.agent-dock { position: fixed; right: 24px; bottom: 24px; z-index: 1500; max-width: calc(100vw - 32px); }
.agent-fab {
  width: 56px; height: 56px; border-radius: 50%; border: none; cursor: pointer;
  background: #409eff; color: #fff; display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 20px rgba(64, 158, 255, .4); margin-left: auto; transition: transform .2s, background .2s;
}
.agent-fab:hover { transform: translateY(-2px); background: #337ecc; }
.agent-fab.active { background: #5a5a5a; box-shadow: 0 4px 14px rgba(0, 0, 0, .2); }
.agent-panel {
  width: 360px; height: 540px; max-width: 100%; max-height: calc(100vh - 120px); margin-bottom: 12px; margin-left: auto;
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
.agent-sources { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; margin-top: 6px; max-width: 86%; }
.agent-sources-label { font-size: 11px; color: #909399; }
.agent-source-tag {
  display: inline-block; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 11px; color: #409eff; background: #ecf5ff; border: 1px solid #d9ecff;
  border-radius: 10px; padding: 2px 8px; cursor: help;
}
.agent-upload { display: flex; flex-direction: column; gap: 5px; margin-top: 8px; }
.agent-file-input { display: none; }
.agent-upload-btn {
  align-self: flex-start; border: 1px dashed #409eff; background: #f5faff; color: #409eff;
  border-radius: 8px; padding: 8px 14px; font-size: 12px; cursor: pointer; transition: all .2s;
}
.agent-upload-btn:hover:not(:disabled) { background: #ecf5ff; }
.agent-upload-btn:disabled { opacity: .5; cursor: not-allowed; }
.agent-upload-icon { font-size: 14px; margin-right: 3px; }
.agent-upload-hint { font-size: 11px; color: #a8abb2; }
.agent-convert-format { display: flex; align-items: center; gap: 8px; }
.agent-format-select {
  border: 1px solid #dcdfe6; border-radius: 6px; padding: 4px 8px;
  font-size: 12px; color: #606266; background: #fff; cursor: pointer;
}
.agent-task {
  margin-top: 8px; width: 100%; border: 1px solid #e4e7ed; border-radius: 8px;
  padding: 10px 12px; background: #fff; display: flex; flex-direction: column; gap: 6px;
}
.agent-task-head { display: flex; align-items: center; justify-content: space-between; }
.agent-task-status { font-size: 12px; font-weight: 500; color: #606266; }
.agent-task-status.running { color: #409eff; }
.agent-task-status.completed { color: #67c23a; }
.agent-task-status.failed, .agent-task-status.cancelled { color: #f56c6c; }
.agent-task-pct { font-size: 12px; color: #909399; }
.agent-task-bar { height: 6px; border-radius: 3px; background: #e4e7ed; overflow: hidden; }
.agent-task-bar-fill { height: 100%; background: #409eff; transition: width .3s; }
.agent-task-step { font-size: 11px; color: #909399; }
.agent-task-summary { font-size: 12px; color: #303133; line-height: 1.5; }
.agent-thinking { color: #909399; }
.agent-dots { letter-spacing: 2px; }
.agent-footer { flex: 0 0 auto; padding: 10px 12px 12px; border-top: 1px solid #e4e7ed; background: #fff; }
.agent-footer-bar { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; }
.agent-hint { font-size: 11px; color: #a8abb2; }
.agent-panel-enter-active, .agent-panel-leave-active { transition: opacity .18s, transform .18s; }
.agent-panel-enter-from, .agent-panel-leave-to { opacity: 0; transform: translateY(12px); }
</style>
