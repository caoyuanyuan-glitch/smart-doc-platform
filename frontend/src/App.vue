<template>
  <div class="app-container">
    <router-view v-if="$route.path === '/login'" />
    <template v-else>
      <header class="header">
        <div class="header-left">
          <span class="logo">智能技术文档平台</span>
        </div>
        <div class="header-right">
          <span class="system-info">智能技术文档审核系统</span>
        </div>
      </header>

      <aside class="sidebar">
        <el-menu
          :default-active="activeMenu"
          class="sidebar-menu"
          mode="vertical"
          :collapse="isCollapsed"
          :collapse-transition="false"
          @select="handleMenuSelect"
        >
          <div class="collapse-btn" @click="toggleCollapse" v-if="!isCollapsed">
            <el-icon><Fold /></el-icon>
          </div>
          <div class="collapse-btn" @click="toggleCollapse" v-else>
            <el-icon><Expand /></el-icon>
          </div>

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
          </el-sub-menu>

          <el-sub-menu index="review-sub">
            <template #title>
              <el-icon><DocumentChecked /></el-icon>
              <span>文档审核</span>
            </template>
            <el-menu-item index="/review">文档管理</el-menu-item>
            <el-menu-item index="/review/tasks">审核任务</el-menu-item>
            <el-menu-item index="/review/rules">规则管理</el-menu-item>
            <el-menu-item index="/review/reports">审核报告</el-menu-item>
            <el-menu-item index="/review/basis">审核依据</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="qa-sub">
            <template #title>
              <el-icon><ChatDotRound /></el-icon>
              <span>智能问答</span>
            </template>
            <el-menu-item index="/qa">知识库问答</el-menu-item>
            <el-menu-item index="/qa/library">知识库管理</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="translate-sub">
            <template #title>
              <el-icon><Switch /></el-icon>
              <span>AI翻译</span>
            </template>
            <el-menu-item index="/translate">文本翻译</el-menu-item>
            <el-menu-item index="/translate/docs">文档翻译</el-menu-item>
          </el-sub-menu>

          <el-sub-menu index="library-sub">
            <template #title>
              <el-icon><Box /></el-icon>
              <span>内容库</span>
            </template>
            <el-menu-item index="/translate/memory">记忆库</el-menu-item>
          </el-sub-menu>

                    <el-menu-item index="/users">




            <el-icon><User /></el-icon>
            <template #title>用户管理</template>
          </el-menu-item>
        </el-menu>
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
import {
  House, DocumentChecked, MagicStick, ChatDotRound, DocumentAdd,
  Files, Refresh, CollectionTag, Fold, Expand, Switch, Box
} from '@element-plus/icons-vue'

const router = useRouter()
const isCollapsed = ref(false)

const activeMenu = computed(() => router.currentRoute.value.path)

function handleMenuSelect(index) {
  router.push(index)
}

function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
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

/* 顶部导航栏 - 浅蓝色主题 */
.header {
  position: fixed;
  top: 0;
  left: 240px;
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
}

/* 左侧菜单栏 - 浅蓝色主题 */
.sidebar {
  width: 240px;
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
}

.sidebar.collapsed {
  width: 64px;
}

/* 折叠按钮 */
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

/* el-menu 浅蓝色主题覆盖 */
.sidebar-menu {
  border-right: none !important;
  height: 100vh;
  padding-top: 60px;
  background: transparent !important;
}

/* 一级菜单项 */
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

/* 子菜单标题 */
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

/* 二级子菜单项 */
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

/* 折叠状态下 */
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

/* 主内容区 */
.main-content {
  margin-left: 240px;
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

/* Element Plus 弹窗深色背景下拉菜单修正 */
.el-dropdown-menu {
  border: 1px solid #e4e7ed !important;
}

/* 加载状态样式 */
.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: #f5f7fa;
}

.loading-content {
  text-align: center;
  color: #64748b;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 4px solid #dbeafe;
  border-top: 4px solid #2563eb;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

/* 隐藏不需要的默认分隔线 */
.sidebar-menu .el-menu-item-group__title {
  padding: 8px 20px;
  font-size: 12px;
  color: #94a3b8;
  font-weight: 600;
}
</style>
