<template>
  <div class="knowledge-page">
    <div class="page-header">
      <h2 class="page-title">知识库管理</h2>
    </div>

    <div class="content-area">
      <div class="knowledge-layout">
        <!-- 左侧：文件夹树 -->
        <div class="tree-panel">
          <div class="tree-panel-header">
            <span class="tree-panel-label">文件夹结构</span>
            <span v-if="folderPath" class="tree-panel-path">/ {{ folderPath }}</span>
          </div>
          <div class="tree-toolbar">
            <el-button size="small" @click="toggleAllTree" text>
              <el-icon><ArrowDown v-if="!isAllExpanded" /><ArrowRight v-else /></el-icon>
              {{ isAllExpanded ? '收起全部' : '展开全部' }}
            </el-button>
            <el-button size="small" type="primary" @click="showCreateRootFolder">
              <el-icon><Plus /></el-icon>
              新建文件夹
            </el-button>
          </div>
          <div class="tree-container">
            <div v-if="folderTree.length === 0" class="tree-empty">
              <el-icon :size="36" color="#cbd5e1"><FolderOpened /></el-icon>
              <p>暂无文件夹</p>
            </div>
            <recursive-tree
              v-else
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

        <!-- 右侧：文件列表 -->
        <div class="files-panel">
          <div v-if="!currentFolder" class="files-empty">
            <el-icon :size="50" color="#cbd5e1"><FolderOpened /></el-icon>
            <p>请在左侧选择文件夹查看文件</p>
          </div>

          <template v-else>
            <!-- 有文件时显示文件列表 -->
            <template v-if="currentFiles.length > 0">
              <div class="files-header">
                <div class="files-header-left">
                  <span class="files-title">文件列表</span>
                  <span class="file-count">共 {{ currentFiles.length }} 个文件</span>
                </div>
                <el-upload
                  ref="uploadRef"
                  action=""
                  :auto-upload="false"
                  :show-file-list="false"
                  :on-change="handleFileChange"
                  accept="*"
                  multiple
                >
                  <el-button type="primary" size="small">
                    <el-icon><Upload /></el-icon>
                    上传文件
                  </el-button>
                </el-upload>
              </div>

              <el-table
                :data="currentFiles"
                border
                class="files-table"
                style="width: 100%"
                v-loading="fileLoading"
              >
                <el-table-column prop="name" label="文件名" min-width="180" show-overflow-tooltip />
                <el-table-column prop="file_type" label="文件类型" width="90" align="center" />
                <el-table-column label="提交人" width="110" align="center">
                  <template #default="{ row }">
                    <span class="uploader-name">{{ row.created_by_name || '未知用户' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="文件大小" width="100" align="center">
                  <template #default="{ row }">
                    {{ formatFileSize(row.file_size) }}
                  </template>
                </el-table-column>
                <el-table-column label="修改时间" width="180">
                  <template #default="{ row }">
                    {{ formatDateTime(row.updated_at || row.created_at) }}
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="280" fixed="right" align="center">
                  <template #default="{ row }">
                    <el-button size="small" @click="handlePreviewFile(row)">
                      <el-icon><View /></el-icon>
                      预览
                    </el-button>
                    <el-button size="small" @click="handleDownloadFile(row)">
                      <el-icon><Download /></el-icon>
                      下载
                    </el-button>
                    <el-button size="small" type="danger" @click="handleDeleteFile(row)">
                      <el-icon><Delete /></el-icon>
                      删除
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>

              <!-- 子文件夹 -->
              <div v-if="currentSubfolders.length > 0" class="subfolders-section">
                <div class="subfolders-label">子文件夹</div>
                <div
                  v-for="sf in currentSubfolders"
                  :key="sf.id"
                  class="subfolder-row"
                  @click="handleFolderSelect(sf)"
                >
                  <span class="subfolder-icon">📁</span>
                  <span class="subfolder-name">{{ sf.name }}</span>
                </div>
              </div>
            </template>

            <!-- 只有子文件夹、没有文件 -->
            <template v-else-if="currentSubfolders.length > 0">
              <div class="files-header">
                <div class="files-header-left">
                  <span class="files-title">子文件夹</span>
                  <span class="file-count">共 {{ currentSubfolders.length }} 个</span>
                </div>
                <el-upload
                  ref="uploadRef"
                  action=""
                  :auto-upload="false"
                  :show-file-list="false"
                  :on-change="handleFileChange"
                  accept="*"
                  multiple
                >
                  <el-button type="primary" size="small">
                    <el-icon><Upload /></el-icon>
                    上传文件
                  </el-button>
                </el-upload>
              </div>

              <div class="subfolders-only">
                <div
                  v-for="sf in currentSubfolders"
                  :key="sf.id"
                  class="subfolder-row"
                  @click="handleFolderSelect(sf)"
                >
                  <span class="subfolder-icon">📁</span>
                  <span class="subfolder-name">{{ sf.name }}</span>
                </div>
              </div>
            </template>

            <!-- 既无文件也无子文件夹 -->
            <template v-else>
              <div class="files-header">
                <div class="files-header-left">
                  <span class="files-title">文件列表</span>
                </div>
                <el-upload
                  ref="uploadRef"
                  action=""
                  :auto-upload="false"
                  :show-file-list="false"
                  :on-change="handleFileChange"
                  accept="*"
                  multiple
                >
                  <el-button type="primary" size="small">
                    <el-icon><Upload /></el-icon>
                    上传文件
                  </el-button>
                </el-upload>
              </div>
              <div class="files-empty-inline">
                <el-icon :size="36" color="#cbd5e1"><FolderOpened /></el-icon>
                <p>暂无文件，请上传</p>
              </div>
            </template>
          </template>
        </div>
      </div>
    </div>

    <!-- 文件预览对话框 -->
    <el-dialog v-model="previewDialogVisible" :title="`预览：${previewFileName}`" width="85%" top="3vh" @closed="closePreview">
      <div class="preview-container">
        <div v-if="previewType === 'text'" class="text-preview"><pre>{{ previewContent }}</pre></div>
        <div v-if="previewType === 'image'" class="image-preview"><img :src="previewFileUrl" alt="预览图片" /></div>
        <div v-if="previewType === 'unsupported' || previewType === 'error'" class="unsupported-preview">
          <el-icon :size="50" color="#9ca3af"><Document /></el-icon>
          <p>{{ previewContent }}</p>
        </div>
      </div>
    </el-dialog>

    <!-- 新建文件夹对话框 -->
    <el-dialog v-model="createFolderVisible" :title="createFolderParentId ? '新建子文件夹' : '新建根文件夹'" width="400px">
      <el-input v-model="createFolderName" placeholder="请输入文件夹名称" @keyup.enter="confirmCreateFolder" />
      <template #footer>
        <el-button @click="createFolderVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmCreateFolder">确定</el-button>
      </template>
    </el-dialog>

    <!-- 重命名对话框 -->
    <el-dialog v-model="renameFolderVisible" title="重命名文件夹" width="400px">
      <el-input v-model="renameFolderName" placeholder="请输入新名称" @keyup.enter="confirmRenameFolder" />
      <template #footer>
        <el-button @click="renameFolderVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmRenameFolder">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Upload, Download, View, Delete, FolderOpened, Document,
  Plus, ArrowDown, ArrowRight
} from '@element-plus/icons-vue'
import { knowledgeAPI } from '@/api'
import RecursiveTree from '@/components/RecursiveTree.vue'

const route = useRoute()
const router = useRouter()

// -------- 文件夹树 --------
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

// 当前文件夹路径
const folderPath = computed(() => {
  if (!currentFolderId.value) return ''
  const path = findPath(folderTree.value, currentFolderId.value)
  return path ? path.join(' / ') : ''
})

function findPath(nodes, targetId, path = []) {
  for (const node of nodes) {
    if (node.id === targetId) return [...path, node.name]
    if (node.children && node.children.length > 0) {
      const found = findPath(node.children, targetId, [...path, node.name])
      if (found) return found
    }
  }
  return null
}

const createFolderVisible = ref(false)
const createFolderName = ref('')
const createFolderParentId = ref(null)

const renameFolderVisible = ref(false)
const renameFolderName = ref('')
const renameFolderId = ref(null)

// -------- 文件列表 --------
const currentFiles = ref([])
const currentSubfolders = ref([])
const fileLoading = ref(false)
const currentFolder = ref(null)

const previewDialogVisible = ref(false)
const previewContent = ref('')
const previewType = ref('text')
const previewFileName = ref('')
const previewFileUrl = ref('')

const folderId = computed(() => {
  const id = route.params.id
  return id ? parseInt(id) : null
})

// -------- 树操作 --------
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
  router.push({ path: `/knowledge/${folder.id}` })
}

function toggleAllTree() {
  if (isAllExpanded.value) {
    expandedNodeIds.value.clear()
  } else {
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
  try {
    await knowledgeAPI.createFolder({ name: createFolderName.value.trim(), parent_id: createFolderParentId.value })
    ElMessage.success('文件夹创建成功')
    createFolderVisible.value = false
    await loadFolderTree()
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
    await loadFolderTree()
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
      currentFolder.value = null
      currentFiles.value = []
      currentSubfolders.value = []
    }
    await loadFolderTree()
    expandedNodeIds.value.delete(folder.id)
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

// -------- 文件操作 --------
function formatFileSize(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}

function formatDateTime(dateStr) {
  if (!dateStr) return ''
  try {
    const d = new Date(dateStr)
    if (isNaN(d.getTime())) return dateStr
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    }).format(d).replace(/\//g, '/')
  } catch (e) {
    return dateStr
  }
}

async function loadFolderContent(id) {
  if (!id) {
    currentFolder.value = null
    currentFiles.value = []
    currentSubfolders.value = []
    return
  }
  fileLoading.value = true
  try {
    const resp = await knowledgeAPI.getFolderContent(id)
    currentFolder.value = resp.data.folder
    currentSubfolders.value = resp.data.subfolders || []
    currentFiles.value = resp.data.files || []
  } catch (e) {
    ElMessage.error('加载文件列表失败')
    currentFiles.value = []
    currentSubfolders.value = []
  } finally {
    fileLoading.value = false
  }
}

async function handleFileChange(file) {
  if (!folderId.value) {
    ElMessage.warning('请先选择文件夹')
    return
  }
  try {
    await knowledgeAPI.uploadFile(folderId.value, file.raw)
    ElMessage.success('上传成功')
    loadFolderContent(folderId.value)
  } catch (e) {
    ElMessage.error('上传失败：' + (e.response?.data?.detail || e.message))
  }
}

async function handlePreviewFile(file) {
  try {
    const resp = await knowledgeAPI.previewFile(file.id)
    const data = resp.data
    previewFileName.value = data.file_name
    previewType.value = data.type
    previewContent.value = data.content || ''
    previewFileUrl.value = data.file_path || ''
    previewDialogVisible.value = true
  } catch (e) {
    ElMessage.error('预览失败')
  }
}

async function handleDownloadFile(file) {
  try {
    await knowledgeAPI.downloadFile(file.id, file.name)
    ElMessage.success('下载已开始')
  } catch (e) {
    ElMessage.error('下载失败')
  }
}

async function handleDeleteFile(file) {
  try {
    await ElMessageBox.confirm(
      `确定要删除文件 "${file.name}" 吗？`,
      '确认删除',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await knowledgeAPI.deleteFile(file.id)
    ElMessage.success('删除成功')
    loadFolderContent(folderId.value)
  } catch (e) {
    if (e !== 'cancel') {
      const msg = e.response?.data?.detail || '未知错误'
      if (msg.includes('仅管理员') || msg.includes('创建者')) {
        ElMessage.error('您没有权限删除此文件')
      } else {
        ElMessage.error('删除文件失败：' + msg)
      }
    }
  }
}

function closePreview() {
  // 清理预览状态
}

// -------- 路由联动 --------
watch(() => route.params.id, (newId) => {
  if (newId) {
    const id = parseInt(newId)
    currentFolderId.value = id
    loadFolderContent(id)
  } else {
    currentFolderId.value = null
    currentFolder.value = null
    currentFiles.value = []
    currentSubfolders.value = []
  }
})

onMounted(() => {
  loadFolderTree()
  if (folderId.value) {
    currentFolderId.value = folderId.value
    loadFolderContent(folderId.value)
  }
})
</script>

<style scoped>
.knowledge-page {
  height: calc(100vh - 108px);
  display: flex;
  flex-direction: column;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: #1f2937;
}

.content-area {
  flex: 1;
  overflow: hidden;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

/* 双栏布局 */
.knowledge-layout {
  display: flex;
  height: 100%;
}

.tree-panel {
  width: 360px;
  flex-shrink: 0;
  border-right: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.tree-panel-header {
  padding: 16px 16px 8px;
  flex-shrink: 0;
  display: flex;
  align-items: baseline;
  gap: 4px;
  min-height: 44px;
}

.tree-panel-label {
  font-weight: 600;
  color: #1f2937;
  font-size: 15px;
  white-space: nowrap;
}

.tree-panel-path {
  font-size: 13px;
  color: #6b7280;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.tree-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 16px 8px;
  flex-shrink: 0;
}

.tree-container {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 12px;
  min-height: 0;
}

.tree-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 150px;
  color: #94a3b8;
  font-size: 14px;
  gap: 8px;
}

/* 右侧文件面板 */
.files-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.files-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 15px;
  gap: 12px;
}

.files-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px 12px;
  flex-shrink: 0;
  border-bottom: 1px solid #f0f0f0;
}

.files-header-left {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.files-title {
  font-weight: 600;
  color: #1f2937;
  font-size: 15px;
}

.file-count {
  font-size: 12px;
  color: #9ca3af;
}

.files-table {
  flex: 0 0 auto;
}

.files-table :deep(.el-table__header-wrapper th) {
  background: #f8fafc;
  color: #111827;
  font-weight: 700;
}

/* 子文件夹列表 */
.subfolders-section {
  padding: 8px 20px 12px;
  border-top: 1px solid #f0f0f0;
}

.subfolders-label {
  font-size: 12px;
  color: #9ca3af;
  font-weight: 500;
  margin-bottom: 6px;
  display: block;
}

.subfolder-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 15px;
  transition: background 0.15s;
}

.subfolder-row:hover {
  background: #dbeafe;
}

.subfolder-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.subfolder-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #1f2937;
}

/* 仅子文件夹列表 */
.subfolders-only {
  padding: 8px 20px;
  flex: 1;
  overflow-y: auto;
}

/* 空文件内联提示 */
.files-empty-inline {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #9ca3af;
  font-size: 14px;
  gap: 8px;
  padding: 40px 0;
}

/* 预览 */
.preview-container {
  max-height: 70vh;
  overflow: auto;
}

.text-preview pre {
  white-space: pre-wrap;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 14px;
  line-height: 1.6;
  margin: 0;
}

.image-preview img {
  max-width: 100%;
  max-height: 70vh;
  display: block;
  margin: 0 auto;
}

.unsupported-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: #6b7280;
  font-size: 16px;
  padding: 40px;
}
</style>
