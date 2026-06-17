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
              <el-menu-item index="/review/rules">规则管理</el-menu-item>
              <el-menu-item index="/review/basis">审核依据</el-menu-item>
            </el-sub-menu>

            <el-sub-menu index="qa-sub">
              <template #title>
                <el-icon><ChatDotRound /></el-icon>
                <span>智能问答</span>
              </template>
              <el-menu-item index="/qa">知识库问答</el-menu-item>
              <el-menu-item index="/knowledge">知识库管理</el-menu-item>
            </el-sub-menu>

            <el-menu-item v-if="userStore.isAdmin" index="/users">
              <el-icon><User /></el-icon>
              <template #title>用户管理</template>
            </el-menu-item>
          </el-menu>

          <div class="sidebar-divider"></div>

          <div class="knowledge-sidebar-section" v-if="!isCollapsed">
            <div class="knowledge-section">
              <div class="knowledge-header">
                <span class="knowledge-title">知识库管理</span>
                <div class="knowledge-header-actions">
                  <el-icon class="action-icon small" @click="toggleAllTree" :title="isAllExpanded ? '收起全部' : '展开全部'">
                    <ArrowDown v-if="!isAllExpanded" />
                    <ArrowRight v-else />
                  </el-icon>
                  <el-icon class="action-icon" @click="showCreateRootFolder" title="新建文件夹"><Plus /></el-icon>
                </div>
              </div>
              <div class="knowledge-tree-container">
                <recursive-tree
                  :nodes="folderTree"
                  :current-folder-id="currentFolderId"
                  :expanded-ids="expandedNodeIds"
                  @toggle="handleToggle"
                  @select="handleFolderSelect"
                  @create-sub="showCreateSubFolder"
                  @rename="showRenameFolder"
                  @delete="showDeleteFolder"
                />
              </div>
            </div>
          </div>
        </div>
      </aside>

      <main class="main-content">
        <router-view />
      </main>

      <el-dialog v-model="createFolderVisible" :title="createFolderParentId ? '新建子文件夹' : '新建根文件夹'" width="400px">
        <el-input v-model="createFolderName" placeholder="请输入文件夹名称" @keyup.enter="confirmCreateFolder" />
        <template #footer>
          <el-button @click="createFolderVisible = false">取消</el-button>
          <el-button type="primary" @click="confirmCreateFolder">确定</el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="renameFolderVisible" title="重命名文件夹" width="400px">
        <el-input v-model="renameFolderName" placeholder="请输入新名称" @keyup.enter="confirmRenameFolder" />
        <template #footer>
          <el-button @click="renameFolderVisible = false">取消</el-button>
          <el-button type="primary" @click="confirmRenameFolder">确定</el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '@/store/user'
import {
  House, DocumentChecked, MagicStick, ChatDotRound, DocumentAdd,
  Files, Refresh, Fold, Expand, User, Plus, Edit, Delete, FolderAdd,
  ArrowDown, ArrowRight
} from '@element-plus/icons-vue'
import { knowledgeAPI } from '@/api'
import RecursiveTree from '@/components/RecursiveTree.vue'

const router = useRouter()
const userStore = useUserStore()
const isCollapsed = ref(false)
const folderTree = ref([])
const currentFolderId = ref(null)
const expandedNodeIds = ref(new Set())

const isAllExpanded = computed(() => {
  const collectAllIds = (nodes) => {
    let ids = []
    nodes.forEach(node => {
      if (node.children && node.children.length > 0) {
        ids.push(node.id)
        ids = ids.concat(collectAllIds(node.children))
      }
    })
    return ids
  }
  const allIds = collectAllIds(folderTree.value)
  return allIds.length > 0 && allIds.every(id => expandedNodeIds.value.has(id))
})

const activeMenu = computed(() => {
  if (router.currentRoute.value.path.startsWith('/knowledge')) {
    return 'knowledge'
  }
  return router.currentRoute.value.path
})

const createFolderVisible = ref(false)
const createFolderName = ref('')
const createFolderParentId = ref(null)

const renameFolderVisible = ref(false)
const renameFolderName = ref('')
const renameFolderId = ref(null)

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

async function loadFolderTree() {
  try {
    const resp = await knowledgeAPI.getTree()
    folderTree.value = resp.data
  } catch (e) {
    console.error('加载文件夹树失败')
  }
}

function handleToggle(id) {
  if (expandedNodeIds.value.has(id)) {
    expandedNodeIds.value.delete(id)
  } else {
    expandedNodeIds.value.add(id)
  }
}

function handleFolderSelect(folder) {
  currentFolderId.value = folder.id
  router.push(`/knowledge/${folder.id}`)
}

function toggleAllTree() {
  if (isAllExpanded.value) {
    // 收起全部
    expandedNodeIds.value.clear()
  } else {
    // 展开全部
    const collectIds = (nodes) => {
      nodes.forEach(node => {
        if (node.children && node.children.length > 0) {
          expandedNodeIds.value.add(node.id)
          collectIds(node.children)
        }
      })
    }
    collectIds(folderTree.value)
  }
}

function showCreateRootFolder() {
  createFolderParentId.value = null
  createFolderName.value = ''
  createFolderVisible.value = true
}

function showCreateSubFolder(parentId) {
  createFolderParentId.value = parentId
  createFolderName.value = ''
  createFolderVisible.value = true
}

async function confirmCreateFolder() {
  if (!createFolderName.value.trim()) {
    ElMessage.warning('请输入文件夹名称')
    return
  }
  const folderData = {
    name: createFolderName.value.trim(),
    parent_id: createFolderParentId.value
  }
  try {
    await knowledgeAPI.createFolder(folderData)
    ElMessage.success('文件夹创建成功')
    createFolderVisible.value = false
    loadFolderTree()
    if (createFolderParentId.value) {
      expandedNodeIds.value.add(createFolderParentId.value)
    }
  } catch (e) {
    ElMessage.error('创建文件夹失败')
  }
}

function showRenameFolder(folder) {
  renameFolderId.value = folder.id
  renameFolderName.value = folder.name
  renameFolderVisible.value = true
}

async function confirmRenameFolder() {
  if (!renameFolderName.value.trim()) {
    ElMessage.warning('请输入文件夹名称')
    return
  }
  try {
    await knowledgeAPI.renameFolder(renameFolderId.value, { name: renameFolderName.value.trim() })
    ElMessage.success('重命名成功')
    renameFolderVisible.value = false
    loadFolderTree()
  } catch (e) {
    ElMessage.error('重命名失败')
  }
}

async function showDeleteFolder(folder) {
  try {
    await ElMessageBox.confirm(
      `确定要删除文件夹 "${folder.name}" 及其所有内容吗？`,
      '确认删除',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await knowledgeAPI.deleteFolder(folder.id)
    ElMessage.success('删除成功')
    if (currentFolderId.value === folder.id) {
      router.push('/knowledge')
      currentFolderId.value = null
    }
    await loadFolderTree()
    expandedNodeIds.value.delete(folder.id)
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

onMounted(() => {
  loadFolderTree()
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

.sidebar-divider {
  height: 1px;
  background: #dbeafe;
  margin: 12px 16px;
}

.knowledge-sidebar-section {
  padding: 8px 12px;
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.knowledge-section {
  display: flex;
  flex-direction: column;
  height: 100%;
  flex: 1;
  min-height: 0;
}

.knowledge-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 8px 12px;
  flex-shrink: 0;
}

.knowledge-title {
  font-weight: 600;
  color: #1e40af;
  font-size: 14px;
}

.knowledge-header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.knowledge-tree-container {
  flex: 1;
  overflow-y: auto;
  padding-bottom: 12px;
  min-height: 0;
}

.tree-list {
  list-style: none;
  padding-left: 8px;
  margin: 0;
}

.tree-node {
  list-style: none;
}

.tree-row {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 6px;
  border-radius: 4px;
  cursor: pointer;
  margin: 1px 0;
  font-size: 13px;
}

.tree-row:hover {
  background: #dbeafe !important;
}

.tree-row.active {
  background: #2563eb !important;
  color: #fff !important;
}

.expand-arrow {
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #64748b;
  cursor: pointer;
  flex-shrink: 0;
  transition: transform 0.2s;
}

.expand-arrow.expanded {
  transform: rotate(90deg);
}

.expand-arrow:hover {
  color: #3b82f6;
}

.expand-placeholder {
  width: 16px;
  flex-shrink: 0;
}

.tree-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.tree-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-actions {
  display: none;
  gap: 2px;
  flex-shrink: 0;
}

.tree-row:hover .tree-actions {
  display: flex;
}

.tree-action {
  font-size: 13px;
  cursor: pointer;
  color: #6b7280;
}

.tree-action:hover {
  color: #3b82f6;
}

.tree-action.delete {
  color: #ef4444;
}

.tree-action.delete:hover {
  color: #dc2626;
}

.tree-children {
  list-style: none;
  padding-left: 12px;
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
