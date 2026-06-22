<template>
  <div class="app-container">
    <router-view v-if="$route.path === '/login'" />
    <template v-else>
      <header class="header">
        <div class="header-left">
          <span class="logo">智能技术文档平台</span>
        </div>
        <div class="header-right">
          <span class="user-badge" v-if="userStore.isLoggedIn">{{ userStore.user?.username }} ({{ userStore.user?.role }})</span>
          <el-button text @click="handleLogout" class="logout-btn">退出</el-button>
        </div>
      </header>

      <aside class="sidebar">
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
              <el-menu-item index="/polish/history">已润色文档</el-menu-item>
            </el-sub-menu>

            <el-sub-menu index="generate-sub">
              <template #title>
                <el-icon><DocumentAdd /></el-icon>
                <span>内容生成</span>
              </template>
              <el-menu-item index="/generate">文档生成</el-menu-item>
              <el-menu-item index="/generate/templates">模板管理</el-menu-item>
              <el-menu-item index="/terms">术语库</el-menu-item>
            </el-sub-menu>

            <el-sub-menu index="compare-sub">
              <template #title>
                <el-icon><Files /></el-icon>
                <span>文档对比</span>
              </template>
              <el-menu-item index="/compare">对比上传</el-menu-item>
              <el-menu-item index="/compare/tasks">历史任务</el-menu-item>
              <el-menu-item index="/compare/config">对比配置</el-menu-item>
            </el-sub-menu>

            <el-sub-menu index="convert-sub">
              <template #title>
                <el-icon><Refresh /></el-icon>
                <span>格式转换</span>
              </template>
              <el-menu-item index="/convert">格式转换</el-menu-item>
              <el-menu-item index="/convert/history">转换历史</el-menu-item>
              <el-menu-item index="/convert/rules">转换规则库</el-menu-item>
            </el-sub-menu>

            <el-sub-menu index="review-sub">
              <template #title>
                <el-icon><DocumentChecked /></el-icon>
                <span>文档审核</span>
              </template>
              <el-menu-item index="/review">文档管理</el-menu-item>
              <el-menu-item index="/review/tasks">审核任务</el-menu-item>
              <el-sub-menu index="spell-check-sub">
                <template #title>拼写检查</template>
                <el-menu-item index="/review/spell-check">开始检查</el-menu-item>
                <el-menu-item index="/review/spell-check/history">检查历史</el-menu-item>
                <el-menu-item index="/review/spell-check/whitelist">白名单管理</el-menu-item>
              </el-sub-menu>
            </el-sub-menu>

            <el-menu-item index="/review/rules">
              <el-icon><Setting /></el-icon>
              <template #title>规则管理</template>
            </el-menu-item>

            <el-sub-menu index="qa-sub">
              <template #title>
                <el-icon><ChatDotRound /></el-icon>
                <span>智能问答</span>
              </template>
              <el-menu-item index="/qa">知识库问答</el-menu-item>
            </el-sub-menu>

            <el-sub-menu index="translate-sub">
              <template #title>
                <el-icon><Switch /></el-icon>
                <span>AI翻译</span>
              </template>
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

      <main class="main-content">
        <router-view />
      </main>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import {
  House, DocumentChecked, MagicStick, ChatDotRound, DocumentAdd,
  Files, Refresh, CollectionTag, Fold, Expand, Switch, User, FolderOpened,
  Edit, Setting
} from '@element-plus/icons-vue'

const router = useRouter()
const userStore = useUserStore()
const isCollapsed = ref(false)

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

.sidebar.collapsed ~ .main-content,
.sidebar.collapsed + .main-content,
.sidebar.collapsed + * + .main-content {
  margin-left: 64px;
}

.sidebar.collapsed + .header {
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
</style>
