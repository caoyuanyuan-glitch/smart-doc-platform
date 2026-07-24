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
              :active-action="activeTreeAction"
              @toggle="handleToggle"
              @select="handleFolderSelect"
              @create-sub="handleCreateSubFolderAction"
              @move="handleMoveFolderAction"
              @rename="handleRenameFolderAction"
              @delete="handleDeleteFolderAction"
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
            <div class="files-breadcrumb" aria-label="当前文件夹路径">
              <router-link class="path-segment" to="/knowledge">全部文件夹</router-link>
              <template v-for="item in folderPathItems" :key="`files-${item.id}`">
                <span class="path-separator">/</span>
                <router-link
                  class="path-segment"
                  :to="`/knowledge/${item.id}`"
                  :class="{ 'is-current': item.id === currentFolderId }"
                >
                  {{ item.name }}
                </router-link>
              </template>
            </div>

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
                <el-table-column label="操作" width="480" fixed="right" align="center">
                  <template #default="{ row }">
                    <el-button class="table-action-btn" size="small" @click="handlePreviewFile(row)">
                      <el-icon><View /></el-icon>
                      预览
                    </el-button>
                    <el-button class="table-action-btn" size="small" :disabled="row.permission === 'read'" @click="handleDownloadFile(row)">
                      <el-icon><Download /></el-icon>
                      下载
                    </el-button>
                    <el-button class="table-action-btn" size="small" @click="showMoveFile(row)">
                      <svg class="inline-move-icon" viewBox="0 0 1024 1024" aria-hidden="true">
                        <path fill="currentColor" d="M896 301.653333L618.24 64a77.226667 77.226667 0 0 0-14.933333-11.52L597.333333 50.346667h-2.986666A72.533333 72.533333 0 0 0 567.466667 42.666667H178.773333A72.106667 72.106667 0 0 0 106.666667 114.773333v794.453334A72.106667 72.106667 0 0 0 178.773333 981.333333h298.666667a35.84 35.84 0 0 0 0-71.68h-298.666667V114.773333h354.56v197.12A72.106667 72.106667 0 0 0 605.44 384h240.213333v164.693333a35.84 35.84 0 0 0 71.68 0v-196.266666a72.106667 72.106667 0 0 0-21.333333-50.773334z m-290.986667 10.24V153.173333l199.68 158.72z" />
                        <path fill="currentColor" d="M906.666667 760.32l-98.986667-98.986667a35.84 35.84 0 0 0-50.773333 50.773334l37.973333 37.973333h-384v-85.333333a35.84 35.84 0 0 0-71.68 0v122.026666a35.84 35.84 0 0 0 35.84 35.84h420.266667l-37.973334 37.973334a35.84 35.84 0 0 0 50.773334 50.773333L906.666667 810.666667a35.84 35.84 0 0 0 0-50.346667z" />
                      </svg>
                      移动
                    </el-button>
                    <el-button v-if="isEditableType(row)" class="table-action-btn" size="small" :disabled="row.permission !== 'edit'" type="warning" @click="openEditDialog(row)">
                      <el-icon><Edit /></el-icon>
                      编辑
                    </el-button>
                    <el-button v-if="userStore.isAdmin" class="table-action-btn" size="small" type="info" @click="openPermissionDialog(row)">
                      <el-icon><Lock /></el-icon>
                      权限
                    </el-button>
                    <el-button class="table-action-btn" size="small" type="danger" @click="handleDeleteFile(row)">
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
    <el-dialog v-model="createFolderVisible" :title="createFolderParentId ? '新建子文件夹' : '新建根文件夹'" width="400px" @closed="closeCreateFolderDialog">
      <el-input v-model="createFolderName" placeholder="请输入文件夹名称" @keyup.enter="confirmCreateFolder" />
      <template #footer>
        <el-button @click="closeCreateFolderDialog">取消</el-button>
        <el-button type="primary" @click="confirmCreateFolder">确定</el-button>
      </template>
    </el-dialog>

    <!-- 重命名对话框 -->
    <el-dialog v-model="renameFolderVisible" title="重命名文件夹" width="400px" @closed="closeRenameFolderDialog">
      <el-input v-model="renameFolderName" placeholder="请输入新名称" @keyup.enter="confirmRenameFolder" />
      <template #footer>
        <el-button @click="closeRenameFolderDialog">取消</el-button>
        <el-button type="primary" @click="confirmRenameFolder">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="moveDialogVisible" :title="moveDialogTitle" width="520px">
      <div class="move-dialog-body">
        <div class="move-path-line">
          <span class="move-path-label">当前路径</span>
          <span class="move-path-value">{{ moveSourcePathLabel }}</span>
        </div>
        <div class="move-path-line">
          <span class="move-path-label">目标路径</span>
          <span class="move-path-value">{{ selectedMoveTargetLabel || '请选择目标路径' }}</span>
        </div>
        <div v-if="moveTargetType === 'folder'" class="move-root-option">
          <el-button
            size="small"
            :type="moveDestinationId === null ? 'primary' : 'default'"
            @click="moveDestinationId = null"
          >
            移动到根目录
          </el-button>
        </div>
        <el-tree
          class="move-tree"
          :data="moveTreeData"
          node-key="id"
          default-expand-all
          highlight-current
          :expand-on-click-node="false"
          :current-node-key="moveDestinationId"
          :props="{ label: 'name', children: 'children' }"
          @node-click="handleMoveTargetSelect"
        />
      </div>
      <template #footer>
        <el-button @click="closeMoveDialog">取消</el-button>
        <el-button type="primary" :disabled="isMoveConfirmDisabled" @click="confirmMoveTarget">确定</el-button>
      </template>
    </el-dialog>

    <!-- 文件编辑对话框 -->
    <el-dialog v-model="editDialogVisible" :title="`编辑：${editFileName}`" width="85%" top="3vh" @closed="closeEditDialog" destroy-on-close>
      <div v-if="editLoading" class="edit-loading">加载中...</div>
      <div v-else-if="editError" class="edit-error">{{ editError }}</div>
      <div v-else class="edit-container">
        <div v-if="isXlsxEdit" class="edit-hint">提示：以 Tab 分隔展示表格内容，直接编辑后保存即可。</div>
        <el-input
          v-model="editContent"
          type="textarea"
          :rows="25"
          class="edit-textarea"
          placeholder="文件内容加载中..."
        />
      </div>
      <template #footer>
        <el-button @click="closeEditDialog">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="saveEditContent">保存</el-button>
      </template>
    </el-dialog>

    <!-- 权限管理对话框 -->
    <el-dialog v-model="permDialogVisible" title="权限管理" width="450px" @closed="closePermDialog">
      <div v-if="permFile" class="perm-dialog-body">
        <div class="perm-item">
          <span class="perm-label">文件名</span>
          <span class="perm-value">{{ permFile.name }}</span>
        </div>
        <div class="perm-item">
          <span class="perm-label">操作权限</span>
          <el-select v-model="permPermission" size="small" style="width: 160px">
            <el-option label="只读" value="read" />
            <el-option label="编辑" value="edit" />
            <el-option label="下载" value="download" />
          </el-select>
        </div>
        <div class="perm-item" v-if="permPermission === 'edit'">
          <span class="perm-label">编辑范围</span>
          <el-select v-model="permEditScope" size="small" style="width: 160px">
            <el-option label="所有人" value="all" />
            <el-option label="上传者" value="owner" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </div>
        <div class="perm-item" v-if="permPermission !== 'edit'">
          <span class="perm-label">编辑范围</span>
          <span class="perm-value perm-disabled">—</span>
        </div>
      </div>
      <template #footer>
        <el-button @click="closePermDialog">取消</el-button>
        <el-button type="primary" :loading="permSaving" @click="savePermission">保存</el-button>
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
  Plus, ArrowDown, ArrowRight, Edit, Lock
} from '@element-plus/icons-vue'
import { knowledgeAPI } from '@/api'
import { useUserStore } from '@/store/user'
import RecursiveTree from '@/components/RecursiveTree.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

// -------- 文件夹树 --------
const folderTree = ref([])
const currentFolderId = ref(null)
const expandedNodeIds = ref(new Set())
const activeTreeAction = ref({ folderId: null, type: '' })

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
const folderPathItems = computed(() => {
  if (!currentFolderId.value) return []
  return findPath(folderTree.value, currentFolderId.value) || []
})

function findPath(nodes, targetId, path = []) {
  for (const node of nodes) {
    const nextPath = [...path, { id: node.id, name: node.name }]
    if (node.id === targetId) return nextPath
    if (node.children && node.children.length > 0) {
      const found = findPath(node.children, targetId, nextPath)
      if (found) return found
    }
  }
  return null
}

function getFolderPathLabel(folderId) {
  const path = findPath(folderTree.value, folderId) || []
  return path.map(item => item.name).join(' / ')
}

function locateFolderNode(nodes, folderId) {
  for (const node of nodes) {
    if (node.id === folderId) return node
    if (node.children?.length) {
      const found = locateFolderNode(node.children, folderId)
      if (found) return found
    }
  }
  return null
}

function collectDescendantIds(folderId) {
  const descendants = new Set()
  const sourceNode = locateFolderNode(folderTree.value, folderId)

  const walk = (nodes) => {
    nodes.forEach(node => {
      descendants.add(node.id)
      if (node.children?.length) {
        walk(node.children)
      }
    })
  }

  if (sourceNode?.children?.length) {
    walk(sourceNode.children)
  }
  return descendants
}

function buildMoveTree(nodes, excludedIds) {
  return nodes.reduce((result, node) => {
    if (excludedIds.has(node.id)) {
      return result
    }
    result.push({
      ...node,
      children: buildMoveTree(node.children || [], excludedIds)
    })
    return result
  }, [])
}

const createFolderVisible = ref(false)
const createFolderName = ref('')
const createFolderParentId = ref(null)

const renameFolderVisible = ref(false)
const renameFolderName = ref('')
const renameFolderId = ref(null)

const moveDialogVisible = ref(false)
const moveTargetType = ref('file')
const moveFolderItem = ref(null)
const moveFileItem = ref(null)
const moveDestinationId = ref(null)

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

// -------- 文件编辑 --------
const editDialogVisible = ref(false)
const editContent = ref('')
const editFileName = ref('')
const editFileId = ref(null)
const editLoading = ref(false)
const editSaving = ref(false)
const editError = ref('')
const isXlsxEdit = ref(false)

// -------- 权限管理 --------
const permDialogVisible = ref(false)
const permFile = ref(null)
const permPermission = ref('edit')
const permEditScope = ref('all')
const permSaving = ref(false)

const folderId = computed(() => {
  const id = route.params.id
  return id ? parseInt(id) : null
})

const moveDialogTitle = computed(() => moveTargetType.value === 'folder' ? '移动文件夹' : '移动文件')

const moveSourcePathLabel = computed(() => {
  if (moveTargetType.value === 'folder' && moveFolderItem.value) {
    return getFolderPathLabel(moveFolderItem.value.id)
  }
  if (moveTargetType.value === 'file' && moveFileItem.value?.folder_id) {
    return `${getFolderPathLabel(moveFileItem.value.folder_id)} / ${moveFileItem.value.name}`
  }
  return moveFileItem.value?.name || ''
})

const selectedMoveTargetLabel = computed(() => {
  if (moveDestinationId.value === null) {
    return moveTargetType.value === 'folder' ? '全部文件夹' : ''
  }
  return getFolderPathLabel(moveDestinationId.value)
})

const moveTreeData = computed(() => {
  if (moveTargetType.value !== 'folder' || !moveFolderItem.value) {
    return folderTree.value
  }
  const excludedIds = collectDescendantIds(moveFolderItem.value.id)
  excludedIds.add(moveFolderItem.value.id)
  return buildMoveTree(folderTree.value, excludedIds)
})

const isMoveConfirmDisabled = computed(() => {
  if (moveTargetType.value === 'folder' && moveFolderItem.value) {
    return moveDestinationId.value === (moveFolderItem.value.parent_id ?? null)
  }
  if (moveTargetType.value === 'file' && moveFileItem.value) {
    return moveDestinationId.value === moveFileItem.value.folder_id || moveDestinationId.value === null
  }
  return true
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
  activeTreeAction.value = { folderId: null, type: '' }
  router.push({ path: `/knowledge/${folder.id}` })
}

function setActiveTreeAction(folderId, type) {
  activeTreeAction.value = { folderId, type }
}

function clearActiveTreeAction() {
  activeTreeAction.value = { folderId: null, type: '' }
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
  clearActiveTreeAction()
  createFolderParentId.value = null
  createFolderName.value = ''
  createFolderVisible.value = true
}

function showCreateSubFolder(parentId) {
  createFolderParentId.value = parentId
  createFolderName.value = ''
  createFolderVisible.value = true
}

function handleCreateSubFolderAction(parentId) {
  setActiveTreeAction(parentId, 'create-sub')
  showCreateSubFolder(parentId)
}

function closeCreateFolderDialog() {
  createFolderVisible.value = false
  clearActiveTreeAction()
}

async function confirmCreateFolder() {
  if (!createFolderName.value.trim()) {
    ElMessage.warning('请输入文件夹名称')
    return
  }
  try {
    await knowledgeAPI.createFolder({ name: createFolderName.value.trim(), parent_id: createFolderParentId.value })
    ElMessage.success('文件夹创建成功')
    closeCreateFolderDialog()
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

function handleRenameFolderAction(folder) {
  setActiveTreeAction(folder.id, 'rename')
  showRenameFolder(folder)
}

function closeRenameFolderDialog() {
  renameFolderVisible.value = false
  clearActiveTreeAction()
}

function showMoveFolder(folder) {
  moveTargetType.value = 'folder'
  moveFolderItem.value = folder
  moveFileItem.value = null
  moveDestinationId.value = folder.parent_id ?? null
  moveDialogVisible.value = true
}

function handleMoveFolderAction(folder) {
  setActiveTreeAction(folder.id, 'move')
  showMoveFolder(folder)
}

function showMoveFile(file) {
  moveTargetType.value = 'file'
  moveFileItem.value = file
  moveFolderItem.value = null
  moveDestinationId.value = file.folder_id
  moveDialogVisible.value = true
}

function handleMoveTargetSelect(node) {
  moveDestinationId.value = node.id
}

function closeMoveDialog() {
  moveDialogVisible.value = false
  moveTargetType.value = 'file'
  moveFolderItem.value = null
  moveFileItem.value = null
  moveDestinationId.value = null
  clearActiveTreeAction()
}

async function confirmMoveTarget() {
  if (isMoveConfirmDisabled.value) {
    return
  }

  try {
    if (moveTargetType.value === 'folder' && moveFolderItem.value) {
      await knowledgeAPI.moveFolder(moveFolderItem.value.id, { parent_id: moveDestinationId.value })
      ElMessage.success('文件夹移动完成')
    } else if (moveTargetType.value === 'file' && moveFileItem.value) {
      await knowledgeAPI.moveFile(moveFileItem.value.id, { folder_id: moveDestinationId.value })
      ElMessage.success('文件移动完成')
    }

    closeMoveDialog()
    await loadFolderTree()
    if (folderId.value) {
      await loadFolderContent(folderId.value)
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '移动失败')
  }
}

async function confirmRenameFolder() {
  if (!renameFolderName.value.trim()) {
    ElMessage.warning('请输入文件夹名称')
    return
  }
  try {
    await knowledgeAPI.renameFolder(renameFolderId.value, { name: renameFolderName.value.trim() })
    ElMessage.success('重命名成功')
    closeRenameFolderDialog()
    await loadFolderTree()
  } catch (e) {
    ElMessage.error('重命名失败')
  }
}

async function handleDeleteFolderAction(folder) {
  setActiveTreeAction(folder.id, 'delete')
  await showDeleteFolder(folder)
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
  } finally {
    clearActiveTreeAction()
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

// -------- 权限管理 --------
function openPermissionDialog(file) {
  permFile.value = file
  permPermission.value = file.permission || 'edit'
  permEditScope.value = file.edit_scope || 'all'
  permDialogVisible.value = true
}

function closePermDialog() {
  permDialogVisible.value = false
  permFile.value = null
  permSaving.value = false
}

async function savePermission() {
  if (!permFile.value) return
  permSaving.value = true
  try {
    const data = { permission: permPermission.value }
    if (permPermission.value === 'edit') {
      data.edit_scope = permEditScope.value
    }
    await knowledgeAPI.updateFilePermission(permFile.value.id, data)
    permFile.value.permission = permPermission.value
    permFile.value.edit_scope = permPermission.value === 'edit' ? permEditScope.value : 'all'
    ElMessage.success('权限更新成功')
    closePermDialog()
  } catch (e) {
    const msg = e.response?.data?.detail || '未知错误'
    ElMessage.error('权限更新失败：' + msg)
  } finally {
    permSaving.value = false
  }
}

// -------- 文件编辑 --------
const EDITABLE_EXTENSIONS = ['.md', '.docx', '.xlsx']

function isEditableType(file) {
  const name = (file.name || '').toLowerCase()
  return EDITABLE_EXTENSIONS.some(ext => name.endsWith(ext))
}

async function openEditDialog(file) {
  editFileId.value = file.id
  editFileName.value = file.name
  editContent.value = ''
  editError.value = ''
  editLoading.value = true
  isXlsxEdit.value = file.name.toLowerCase().endsWith('.xlsx')
  editDialogVisible.value = true

  try {
    const res = await knowledgeAPI.getFileContent(file.id)
    editContent.value = res.data.content || ''
  } catch (e) {
    const msg = e.response?.data?.detail || e.message || '未知错误'
    editError.value = '加载文件内容失败：' + msg
  } finally {
    editLoading.value = false
  }
}

function closeEditDialog() {
  editDialogVisible.value = false
  editFileId.value = null
  editFileName.value = ''
  editContent.value = ''
  editError.value = ''
  isXlsxEdit.value = false
  editLoading.value = false
  editSaving.value = false
}

async function saveEditContent() {
  if (!editFileId.value) return
  editSaving.value = true
  try {
    await knowledgeAPI.updateFileContent(editFileId.value, editContent.value)
    ElMessage.success('保存成功')
    closeEditDialog()
  } catch (e) {
    const msg = e.response?.data?.detail || e.message || '未知错误'
    ElMessage.error('保存失败：' + msg)
  } finally {
    editSaving.value = false
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

.files-breadcrumb {
  display: flex;
  align-items: center;
  padding: 14px 20px 0;
  min-height: 24px;
  overflow: hidden;
  white-space: nowrap;
  font-size: 13px;
  color: #6b7280;
  flex-shrink: 0;
}

.path-separator {
  flex-shrink: 0;
  margin: 0 4px;
}

.path-segment {
  border: 0;
  background: transparent;
  padding: 0;
  color: #2563eb;
  cursor: pointer;
  font-size: 13px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  pointer-events: auto;
}

.path-segment:hover {
  color: #1d4ed8;
  text-decoration: underline;
}

.path-segment.is-current {
  color: #1f2937;
  font-weight: 600;
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

.files-table :deep(.table-action-btn > span) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.files-table :deep(.table-action-btn .el-icon) {
  margin-right: 0;
}

.inline-move-icon {
  width: 14px;
  height: 14px;
  display: block;
  flex-shrink: 0;
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
  flex: 1;
}

.move-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.move-path-line {
  display: flex;
  gap: 10px;
  font-size: 14px;
  line-height: 1.5;
}

.move-path-label {
  color: #6b7280;
  flex-shrink: 0;
}

.move-path-value {
  color: #1f2937;
  word-break: break-all;
}

.move-root-option {
  padding-top: 4px;
}

.move-tree {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 8px;
  max-height: 320px;
  overflow: auto;
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

/* 文件编辑 */
.edit-loading,
.edit-error {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  font-size: 15px;
  color: #6b7280;
}

.edit-error {
  color: #ef4444;
}

.edit-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.edit-hint {
  font-size: 13px;
  color: #6b7280;
  padding: 6px 10px;
  background: #fef3c7;
  border-radius: 4px;
}

.edit-textarea :deep(.el-textarea__inner) {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 14px;
  line-height: 1.6;
}

/* 权限管理弹窗 */
.perm-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.perm-item {
  display: flex;
  align-items: center;
  gap: 16px;
}

.perm-label {
  width: 80px;
  font-size: 14px;
  color: #374151;
  flex-shrink: 0;
}

.perm-value {
  font-size: 14px;
  color: #6b7280;
}

.perm-value.perm-disabled {
  color: #d1d5db;
}
</style>
