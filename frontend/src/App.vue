<template>
  <div class="app-container">
    <router-view v-if="$route.path === '/login'" />
    <template v-else>
      <header class="header" :class="{ collapsed: isCollapsed }">
        <div class="header-left">
          <span class="logo">智能技术文档平台</span>
        </div>
        <div class="header-right">
          <el-popover
            placement="bottom-end"
            trigger="click"
            width="360"
            popper-class="ai-status-popover"
          >
            <template #reference>
              <button class="ai-status-chip" :class="aiStatusClass" type="button" @click="fetchAIStatus">
                <span class="ai-status-dot"></span>
                <span>{{ aiStatusLabel }}</span>
              </button>
            </template>
            <div class="ai-status-panel">
              <div class="ai-status-title-row">
                <div>
                  <div class="ai-status-title">AI 调用状态</div>
                  <div class="ai-status-subtitle">{{ aiStatusSubtitle }}</div>
                </div>
                <el-button size="small" :loading="aiStatusLoading" @click="fetchAIStatus">刷新</el-button>
              </div>
              <div v-if="aiStatusError" class="ai-status-error">{{ aiStatusError }}</div>
              <div v-else class="ai-provider-list">
                <div v-for="provider in providerRows" :key="provider.name" class="ai-provider-row">
                  <span class="provider-name">{{ provider.label }}</span>
                  <span class="provider-state" :class="provider.stateClass">{{ provider.text }}</span>
                  <span class="provider-meta">{{ provider.meta }}</span>
                </div>
              </div>
            </div>
          </el-popover>
          <el-badge v-if="userStore.isAdmin" :value="unreadFeedbackCount" :hidden="unreadFeedbackCount === 0" class="feedback-badge">
            <el-icon class="feedback-icon" @click="goToFeedback"><Message /></el-icon>
          </el-badge>
          <span class="user-badge" v-if="userStore.isLoggedIn">{{ userStore.user?.username }} ({{ userStore.user?.role }})</span>
          <el-button text @click="handleLogout" class="logout-btn">退出</el-button>
        </div>
      </header>

      <aside class="sidebar" :class="{ collapsed: isCollapsed }">
        <div class="collapse-btn" @click="toggleCollapse" v-if="!isCollapsed">
          <el-icon><Fold /></el-icon>
        </div>
        <div class="collapse-btn" @click="toggleCollapse" v-else>
          <el-icon><Expand /></el-icon>
        </div>

        <div class="sidebar-content" :class="{ collapsed: isCollapsed }">
          <el-menu
            :default-active="activeMenu"
            class="sidebar-menu"
            mode="vertical"
            :collapse="isCollapsed"
            :collapse-transition="false"
            @select="handleMenuSelect"
          >
            <el-menu-item index="/">
              <el-icon><House /></el-icon>
              <template #title>首页</template>
            </el-menu-item>

            <el-sub-menu index="polish-sub">
              <template #title>
                <el-icon><MagicStick /></el-icon>
                <span>智能润色</span>
              </template>
              <el-menu-item index="/polish">文本润色</el-menu-item>
              <el-menu-item index="/polish/document">文档润色</el-menu-item>
              <el-menu-item index="/tools/polish-rules">润色规则</el-menu-item>
              <el-menu-item index="/polish/history">已润色文档</el-menu-item>
            </el-sub-menu>

            <el-sub-menu index="generate-sub">
              <template #title>
                <el-icon><DocumentAdd /></el-icon>
                <span>内容生成</span>
              </template>
              <el-menu-item index="/generate/image-descriptions">图片描述生成</el-menu-item>
              <el-menu-item index="/tools/doc-generator">说明书初稿</el-menu-item>
              <el-menu-item index="/generate/paragraph">智能续写</el-menu-item>
              <el-menu-item index="/generate/templates">模板管理</el-menu-item>
              <el-menu-item index="/terms">术语库</el-menu-item>
            </el-sub-menu>

            <el-sub-menu index="compare-sub">
              <template #title>
                <el-icon><Files /></el-icon>
                <span>文档对比</span>
              </template>
              <el-menu-item index="/compare">对比上传</el-menu-item>
              <el-menu-item index="/compare/params">参数对比</el-menu-item>
              <el-menu-item index="/compare/tasks">历史任务</el-menu-item>
            </el-sub-menu>

            <el-sub-menu index="convert-sub">
              <template #title>
                <el-icon><Refresh /></el-icon>
                <span>格式转换</span>
              </template>
              <el-menu-item index="/convert">格式转换</el-menu-item>
              <el-menu-item index="/convert/history">转换历史</el-menu-item>
            </el-sub-menu>

            <el-sub-menu index="review-sub">
              <template #title>
                <el-icon><DocumentChecked /></el-icon>
                <span>文档审核</span>
              </template>
              <el-menu-item index="/review/dashboard">统计看板</el-menu-item>
              <el-menu-item index="/review">开始审核</el-menu-item>
              <el-menu-item index="/review/tasks">历史审核任务</el-menu-item>
              <el-menu-item index="/review/rules">规则管理</el-menu-item>
              <el-sub-menu index="spell-check-sub">
                <template #title>拼写检查</template>
                <el-menu-item index="/review/spell-check">开始检查</el-menu-item>
                <el-menu-item index="/review/spell-check/history">检查历史</el-menu-item>
                <el-menu-item index="/review/spell-check/whitelist">白名单管理</el-menu-item>
              </el-sub-menu>
            </el-sub-menu>

            <el-sub-menu index="qa-sub">
              <template #title>
                <el-icon><ChatDotRound /></el-icon>
                <span>智能问答</span>
              </template>
              <el-menu-item index="/qa">知识库问答</el-menu-item>
              <el-menu-item index="/qa/manual">说明书问答</el-menu-item>
              <el-sub-menu index="qa-history-sub" class="qa-history-sub">
                <template #title><span>历史记录</span></template>
                <el-menu-item index="/qa/history/general">知识库问答历史</el-menu-item>
                <el-menu-item index="/qa/history/doc">说明书问答历史</el-menu-item>
              </el-sub-menu>
              <el-menu-item v-if="userStore.isAdmin" index="/qa/dashboard">问答看板</el-menu-item>
            </el-sub-menu>

            <el-sub-menu index="translate-sub">
              <template #title>
                <el-icon><Switch /></el-icon>
                <span>AI翻译</span>
              </template>
              <el-menu-item index="/translate/stats">统计面板</el-menu-item>
              <el-menu-item index="/translate">文本翻译</el-menu-item>
              <el-menu-item index="/translate/docs">文档翻译</el-menu-item>
            </el-sub-menu>

            <el-menu-item index="/knowledge">
              <el-icon><FolderOpened /></el-icon>
              <template #title>知识库管理</template>
            </el-menu-item>

            <el-menu-item v-if="userStore.isAdmin" index="/users">
              <el-icon><User /></el-icon>
              <template #title>用户管理</template>
            </el-menu-item>
          </el-menu>
        </div>
      </aside>

      <main class="main-content" :class="{ collapsed: isCollapsed }">
        <router-view v-slot="{ Component }">
          <keep-alive :include="['Compare', 'CompareParams', 'QA', 'QAHistory', 'QADoc', 'PolishHistory', 'SpellCheckHistory']">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </main>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, provide } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { qaAPI, systemAPI } from '@/api'
import {
  House, DocumentChecked, MagicStick, ChatDotRound, DocumentAdd,
  Files, Refresh, CollectionTag, Fold, Expand, Switch, User, FolderOpened,
  Edit, Setting, Message
} from '@element-plus/icons-vue'

const router = useRouter()
const userStore = useUserStore()
const isCollapsed = ref(false)
const unreadFeedbackCount = ref(0)
const aiStatus = ref(null)
const aiStatusLoading = ref(false)
const aiStatusError = ref('')
let feedbackTimer = null
let aiStatusTimer = null

const providerLabels = {
  kimi: 'Kimi',
  deepseek: 'DeepSeek',
  arkclaw: 'ArkClaw',
  proxy: 'Proxy',
  mcai: 'MCAI Proxy'
}

const activeMenu = computed(() => {
  const path = router.currentRoute.value.path
  if (path.startsWith('/knowledge')) return '/knowledge'
  return path
})

function handleMenuSelect(index) {
  router.push(index)
}

function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
}

function handleLogout() {
  userStore.logout()
  router.push('/login')
}

function goToFeedback() {
  router.push('/feedback')
}

const aiStatusClass = computed(() => {
  if (aiStatusLoading.value && !aiStatus.value) return 'checking'
  if (aiStatusError.value) return 'offline'
  if (!aiStatus.value) return 'unknown'
  if (aiStatus.value.healthy && aiStatus.value.ok_providers > 0) return 'online'
  if (aiStatus.value.ok_providers > 0) return 'degraded'
  return 'offline'
})

const aiStatusLabel = computed(() => {
  if (aiStatusLoading.value && !aiStatus.value) return 'AI 检测中'
  if (aiStatusError.value) return 'AI 异常'
  if (!aiStatus.value) return 'AI 未检测'
  if (aiStatus.value.healthy && aiStatus.value.ok_providers > 0) return `AI 可用 ${aiStatus.value.ok_providers}/${aiStatus.value.total_providers}`
  if (aiStatus.value.ok_providers > 0) return `AI 部分可用 ${aiStatus.value.ok_providers}/${aiStatus.value.total_providers}`
  return 'AI 不可用'
})

const aiStatusSubtitle = computed(() => {
  if (aiStatusError.value) return '后端状态接口访问失败'
  if (!aiStatus.value) return '点击刷新检测 provider'
  const primary = aiStatus.value.primary || 'kimi'
  const primaryStatus = aiStatus.value.primary_status || 'unknown'
  return `主 provider: ${providerLabels[primary] || primary} · ${primaryStatus}`
})

const providerRows = computed(() => {
  const providers = aiStatus.value?.providers || {}
  return Object.entries(providers).map(([name, item]) => {
    const status = item?.status || 'unknown'
    const model = item?.model || ''
    const latency = item?.latency_ms ? `${item.latency_ms}ms` : ''
    const reason = item?.reason || item?.error || ''
    return {
      name,
      label: providerLabels[name] || name,
      text: status === 'ok' ? '可用' : status === 'error' ? '异常' : '未配置',
      stateClass: status === 'ok' ? 'ok' : status === 'error' ? 'error' : 'unavailable',
      meta: status === 'ok' ? [model, latency].filter(Boolean).join(' · ') : reason
    }
  })
})

async function fetchAIStatus() {
  aiStatusLoading.value = true
  aiStatusError.value = ''
  try {
    const resp = await systemAPI.getAIStatus()
    aiStatus.value = resp.data
  } catch (e) {
    aiStatusError.value = e?.response?.data?.detail || e?.message || 'AI 状态检测失败'
  } finally {
    aiStatusLoading.value = false
  }
}

async function fetchUnreadCount() {
  try {
    const resp = await qaAPI.getUnreadFeedbackCount()
    unreadFeedbackCount.value = resp.data?.count || 0
  } catch (e) {
    unreadFeedbackCount.value = 0
  }
}

provide('refreshFeedbackCount', fetchUnreadCount)

onMounted(() => {
  if (userStore.isLoggedIn) {
    fetchUnreadCount()
    fetchAIStatus()
    feedbackTimer = setInterval(fetchUnreadCount, 30000)
    aiStatusTimer = setInterval(fetchAIStatus, 120000)
  }
})

onUnmounted(() => {
  if (feedbackTimer) clearInterval(feedbackTimer)
  if (aiStatusTimer) clearInterval(aiStatusTimer)
})
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: #f5f7fa;
}

.app-container {
  display: flex;
  width: 100%;
  min-height: 100vh;
}

.header {
  position: fixed;
  top: 0;
  left: 260px;
  right: 0;
  height: 60px;
  background: linear-gradient(90deg, #3b82f6 0%, #60a5fa 50%, #3b82f6 100%);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.15);
  z-index: 100;
  transition: left 0.3s ease;
}

.header-left .logo {
  font-size: 18px;
  font-weight: 600;
  color: #fff;
  letter-spacing: 1px;
}

.header-right .system-info {
  color: rgba(255, 255, 255, 0.9);
  font-size: 14px;
  margin-right: 16px;
}

.header-right {
  display: flex;
  align-items: center;
  min-width: 0;
}

.ai-status-chip {
  height: 30px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 1px solid rgba(255, 255, 255, 0.28);
  border-radius: 999px;
  padding: 0 12px;
  margin-right: 14px;
  color: #fff;
  background: rgba(255, 255, 255, 0.14);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

.ai-status-chip:hover {
  background: rgba(255, 255, 255, 0.22);
}

.ai-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #cbd5e1;
  box-shadow: 0 0 0 3px rgba(203, 213, 225, 0.2);
}

.ai-status-chip.online .ai-status-dot {
  background: #22c55e;
  box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.22);
}

.ai-status-chip.degraded .ai-status-dot,
.ai-status-chip.checking .ai-status-dot {
  background: #f59e0b;
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.24);
}

.ai-status-chip.offline .ai-status-dot {
  background: #ef4444;
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.24);
}

.ai-status-panel {
  color: #0f172a;
}

.ai-status-title-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.ai-status-title {
  font-size: 15px;
  font-weight: 800;
  color: #0f172a;
}

.ai-status-subtitle {
  margin-top: 3px;
  font-size: 12px;
  color: #64748b;
}

.ai-status-error {
  padding: 10px 12px;
  border-radius: 8px;
  color: #991b1b;
  background: #fee2e2;
  font-size: 13px;
}

.ai-provider-list {
  display: grid;
  gap: 8px;
}

.ai-provider-row {
  display: grid;
  grid-template-columns: 96px 58px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  font-size: 12px;
}

.provider-name {
  font-weight: 700;
  color: #1e293b;
}

.provider-state {
  justify-self: start;
  border-radius: 999px;
  padding: 2px 8px;
  font-weight: 700;
}

.provider-state.ok {
  color: #166534;
  background: #dcfce7;
}

.provider-state.error {
  color: #991b1b;
  background: #fee2e2;
}

.provider-state.unavailable {
  color: #475569;
  background: #e2e8f0;
}

.provider-meta {
  min-width: 0;
  overflow: hidden;
  color: #64748b;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.logout-btn {
  color: rgba(255, 255, 255, 0.9) !important;
  font-size: 13px;
}
.logout-btn:hover { color: #fff !important; }

.user-badge {
  color: rgba(255, 255, 255, 0.85);
  font-size: 12px;
  margin-right: 12px;
  padding: 2px 10px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 10px;
}

.feedback-badge {
  margin-right: 16px;
}
.feedback-icon {
  font-size: 22px;
  color: rgba(255, 255, 255, 0.9);
  cursor: pointer;
}
.feedback-icon:hover {
  color: #fff;
}

.sidebar {
  width: 260px;
  background: #eff6ff;
  min-height: 100vh;
  position: fixed;
  top: 0;
  left: 0;
  box-shadow: 2px 0 8px rgba(59, 130, 246, 0.08);
  transition: width 0.3s ease;
  z-index: 101;
  overflow: hidden;
  border-right: 1px solid #dbeafe;
  display: flex;
  flex-direction: column;
}

.sidebar.collapsed {
  width: 64px;
}

.sidebar-content {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow-y: auto;
}

.collapse-btn {
  position: absolute;
  right: 8px;
  top: 18px;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #3b82f6;
  background: rgba(255, 255, 255, 0.8);
  z-index: 10;
  transition: all 0.2s;
  border: 1px solid #bfdbfe;
}

.collapse-btn:hover {
  color: #1d4ed8;
  background: #dbeafe;
}

.sidebar.collapsed .collapse-btn {
  right: auto;
  left: 50%;
  transform: translateX(-50%);
}

.sidebar-menu {
  border-right: none !important;
  padding-top: 60px;
  background: transparent !important;
  flex-shrink: 0;
}

.sidebar-menu .el-menu-item {
  height: 44px;
  line-height: 44px;
  margin: 4px 12px;
  border-radius: 8px;
  background: transparent !important;
  color: #475569 !important;
  font-size: 14px;
  border-bottom: none !important;
  padding: 0 16px !important;
  font-weight: 500;
}

.sidebar-menu .el-menu-item:hover {
  background: #dbeafe !important;
  color: #1e40af !important;
}

.sidebar-menu .el-menu-item.is-active {
  background: #2563eb !important;
  color: #fff !important;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
  font-weight: 600;
}

.sidebar-menu .el-menu-item .el-icon {
  margin-right: 10px;
  font-size: 16px;
  color: inherit;
}

.sidebar-menu .el-sub-menu__title {
  height: 44px;
  line-height: 44px;
  margin: 4px 12px;
  border-radius: 8px;
  color: #475569 !important;
  font-size: 14px;
  padding: 0 16px !important;
  font-weight: 500;
}

.sidebar-menu .el-sub-menu__title:hover {
  background: #dbeafe !important;
  color: #1e40af !important;
}

.sidebar-menu .el-sub-menu.is-active > .el-sub-menu__title {
  color: #1e40af !important;
}

.sidebar-menu .el-sub-menu__title .el-sub-menu__icon-arrow {
  color: #94a3b8;
}

.sidebar-menu .el-sub-menu__title .el-icon {
  margin-right: 10px;
  font-size: 16px;
  color: inherit;
}

.sidebar-menu .el-sub-menu .el-menu {
  background: #f0f9ff !important;
  padding: 4px 0 !important;
  margin: 0 !important;
  border: none !important;
}

.sidebar-menu .el-sub-menu .el-menu-item {
  height: 40px;
  line-height: 40px;
  margin: 2px 16px 2px 28px !important;
  padding-left: 24px !important;
  padding-right: 12px !important;
  border-radius: 6px;
  background: transparent !important;
  color: #64748b !important;
  font-size: 13px;
  border: none !important;
  min-width: auto !important;
}

.sidebar-menu .el-sub-menu .el-menu-item:hover {
  background: #dbeafe !important;
  color: #1e40af !important;
}

.sidebar-menu .el-sub-menu .el-menu-item.is-active {
  background: #2563eb !important;
  color: #fff !important;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
  font-weight: 600;
}

.sidebar-menu .el-sub-menu .el-menu-item .el-icon {
  color: inherit;
}

.sidebar.collapsed .sidebar-menu .el-menu-item,
.sidebar.collapsed .sidebar-menu .el-sub-menu__title {
  justify-content: center;
  padding: 0 !important;
  margin: 4px 8px;
}

.sidebar.collapsed .sidebar-menu .el-menu-item .el-icon,
.sidebar.collapsed .sidebar-menu .el-sub-menu__title .el-icon {
  margin: 0;
}

.main-content {
  margin-left: 260px;
  margin-top: 60px;
  flex: 1;
  padding: 24px;
  background: #f5f7fa;
  min-height: calc(100vh - 60px);
  transition: margin-left 0.3s ease;
}

.main-content.collapsed {
  margin-left: 64px;
}

.header.collapsed {
  left: 64px;
}

.el-dropdown-menu {
  border: 1px solid #e4e7ed !important;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.sidebar-menu .el-menu-item-group__title {
  padding: 8px 20px;
  font-size: 12px;
  color: #94a3b8;
  font-weight: 600;
}

.sidebar-menu .qa-history-sub .el-sub-menu__title {
  height: 40px;
  line-height: 40px;
  margin: 2px 16px 2px 28px !important;
  padding: 0 12px 0 24px !important;
  border-radius: 6px;
  color: #475569 !important;
  font-size: 13px;
  font-weight: 500;
}

.sidebar-menu .qa-history-sub .el-sub-menu__title:hover {
  background: #dbeafe !important;
  color: #1e40af !important;
}

.sidebar-menu .qa-history-sub .el-menu {
  background: #e8f4ff !important;
  padding: 2px 0 !important;
  margin: 0 !important;
  border: none !important;
}

.sidebar-menu .qa-history-sub .el-menu-item {
  height: 36px;
  line-height: 36px;
  margin: 1px 16px 1px 48px !important;
  padding-left: 20px !important;
  padding-right: 12px !important;
  border-radius: 6px;
  background: transparent !important;
  color: #64748b !important;
  font-size: 13px;
  border: none !important;
  min-width: auto !important;
}

.sidebar-menu .qa-history-sub .el-menu-item:hover {
  background: #dbeafe !important;
  color: #1e40af !important;
}

.sidebar-menu .qa-history-sub .el-menu-item.is-active {
  background: #2563eb !important;
  color: #fff !important;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
  font-weight: 600;
}
</style>
