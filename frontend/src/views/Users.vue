<template>
  <div class="users-page">
    <div class="page-header">
      <h2>用户管理</h2>
    </div>

    <div class="panel">
      <div class="toolbar">
        <el-input
          v-model="search"
          placeholder="按用户名或真实姓名搜索"
          clearable
          style="width:240px"
          @clear="handleFilterChange"
          @keyup.enter="handleFilterChange"
        />
          <el-select v-model="roleFilter" placeholder="角色筛选" clearable style="width:140px" @change="handleFilterChange">
            <el-option label="管理员" value="admin" />
            <el-option label="普通用户" value="user" />
          </el-select>
        <el-select v-model="statusFilter" placeholder="状态筛选" clearable style="width:120px" @change="handleFilterChange">
          <el-option label="正常" value="active" />
          <el-option label="禁用" value="disabled" />
        </el-select>
        <el-button @click="handleFilterChange">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
        <el-button type="primary" @click="openAddDialog">添加用户</el-button>
      </div>

      <el-table :data="users" border v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" sortable />
        <el-table-column prop="username" label="用户名" sortable />
        <el-table-column prop="display_name" label="真实姓名" />
        <el-table-column prop="role" label="角色" width="120" sortable>
          <template #default="scope">
            <el-tag v-if="scope.row.role === 'admin'" type="danger" size="small">管理员</el-tag>
            <el-tag v-else size="small">普通用户</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100" sortable>
          <template #default="scope">
            <el-tag :type="scope.row.status === 'active' ? 'success' : 'danger'" size="small">
              {{ scope.row.status === 'active' ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170" sortable>
          <template #default="scope">
            {{ scope.row.created_at ? scope.row.created_at.slice(0, 19).replace('T', ' ') : '' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" align="center" fixed="right">
          <template #default="scope">
            <el-button size="small" @click="openEditDialog(scope.row)">编辑</el-button>
            <el-button
              size="small"
              :type="scope.row.status === 'active' ? 'warning' : 'success'"
              :disabled="isCurrentUser(scope.row)"
              @click="toggleStatus(scope.row)"
            >
              {{ isCurrentUser(scope.row) ? '当前账号' : scope.row.status === 'active' ? '禁用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadUsers"
        />
      </div>
    </div>

    <el-dialog v-model="showAddDialog" title="添加用户" width="860px" @close="resetAddForm">
      <el-form :model="addForm" :rules="addRules" ref="addFormRef" label-width="100px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="addForm.username" placeholder="3-20位，字母/数字/下划线" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="addForm.password" type="password" show-password placeholder="8-32位，不能含空格" />
        </el-form-item>
        <el-form-item label="真实姓名" prop="display_name">
          <el-input v-model="addForm.display_name" placeholder="2-20字符" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="addForm.role" style="width:100%">
            <el-option label="管理员" value="admin" />
            <el-option label="普通用户" value="user" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-radio-group v-model="addForm.status">
            <el-radio label="active">正常</el-radio>
            <el-radio label="disabled">禁用</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="addForm.role !== 'admin'" label="知识库权限" class="grant-form-item">
          <p class="grant-hint">给该账号勾选可访问的文件夹。未勾选时，「写作规范」「资源库」默认可浏览和预览；下载、编辑、删除需单独勾选。</p>
          <el-table
            :data="grantFolders"
            row-key="id"
            border
            default-expand-all
            :tree-props="{ children: 'children' }"
            v-loading="grantLoading"
            class="grant-table"
            max-height="360"
          >
            <el-table-column prop="name" label="文件夹" min-width="220" show-overflow-tooltip />
            <el-table-column label="只读" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox :model-value="hasGrantAction(row, 'read')" @change="(checked) => toggleGrantAction(row, 'read', checked)" />
              </template>
            </el-table-column>
            <el-table-column label="预览" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox :model-value="hasGrantAction(row, 'preview')" @change="(checked) => toggleGrantAction(row, 'preview', checked)" />
              </template>
            </el-table-column>
            <el-table-column label="下载" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox :model-value="hasGrantAction(row, 'download')" @change="(checked) => toggleGrantAction(row, 'download', checked)" />
              </template>
            </el-table-column>
            <el-table-column label="编辑" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox :model-value="hasGrantAction(row, 'edit')" @change="(checked) => toggleGrantAction(row, 'edit', checked)" />
              </template>
            </el-table-column>
            <el-table-column label="删除" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox :model-value="hasGrantAction(row, 'delete')" @change="(checked) => toggleGrantAction(row, 'delete', checked)" />
              </template>
            </el-table-column>
          </el-table>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="adding" @click="handleAddUser">确认</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showEditDialog" title="编辑用户" width="860px" @close="resetEditForm">
      <el-form :model="editForm" :rules="editRules" ref="editFormRef" label-width="100px">
        <el-form-item label="用户名">
          <el-input :model-value="editForm.username" disabled />
        </el-form-item>
        <el-form-item label="真实姓名" prop="display_name">
          <el-input v-model="editForm.display_name" placeholder="2-20字符" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="editForm.role" style="width:100%" :disabled="isEditingCurrentUser">
            <el-option label="管理员" value="admin" />
            <el-option label="普通用户" value="user" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-radio-group v-model="editForm.status" :disabled="isEditingCurrentUser">
            <el-radio label="active">正常</el-radio>
            <el-radio label="disabled">禁用</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-alert
          v-if="isEditingCurrentUser"
          title="当前登录管理员可修改真实姓名，角色和状态保持受保护状态。"
          type="info"
          :closable="false"
          show-icon
          class="self-protection-alert"
        />
        <el-form-item label="密码重置">
          <el-popconfirm
            title="确定重置该用户密码？"
            @confirm="handleResetPassword"
          >
            <template #reference>
              <el-button type="warning" size="small">重置密码</el-button>
            </template>
          </el-popconfirm>
          <span v-if="resetPwdResult" class="reset-result">{{ resetPwdResult }}</span>
        </el-form-item>
        <el-form-item v-if="editForm.role !== 'admin'" label="知识库权限" class="grant-form-item">
          <p class="grant-hint">给该账号勾选可访问的文件夹。未勾选时，「写作规范」「资源库」默认可浏览和预览；下载、编辑、删除需单独勾选。</p>
          <el-table
            :data="grantFolders"
            row-key="id"
            border
            default-expand-all
            :tree-props="{ children: 'children' }"
            v-loading="grantLoading"
            class="grant-table"
            max-height="360"
          >
            <el-table-column prop="name" label="文件夹" min-width="220" show-overflow-tooltip />
            <el-table-column label="只读" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox :model-value="hasGrantAction(row, 'read')" @change="(checked) => toggleGrantAction(row, 'read', checked)" />
              </template>
            </el-table-column>
            <el-table-column label="预览" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox :model-value="hasGrantAction(row, 'preview')" @change="(checked) => toggleGrantAction(row, 'preview', checked)" />
              </template>
            </el-table-column>
            <el-table-column label="下载" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox :model-value="hasGrantAction(row, 'download')" @change="(checked) => toggleGrantAction(row, 'download', checked)" />
              </template>
            </el-table-column>
            <el-table-column label="编辑" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox :model-value="hasGrantAction(row, 'edit')" @change="(checked) => toggleGrantAction(row, 'edit', checked)" />
              </template>
            </el-table-column>
            <el-table-column label="删除" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox :model-value="hasGrantAction(row, 'delete')" @change="(checked) => toggleGrantAction(row, 'delete', checked)" />
              </template>
            </el-table-column>
          </el-table>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="editing" @click="handleEditUser">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { userAPI, knowledgeAPI } from '@/api'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()

const users = ref([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const search = ref('')
const roleFilter = ref('')
const statusFilter = ref('')

const showAddDialog = ref(false)
const showEditDialog = ref(false)
const adding = ref(false)
const editing = ref(false)
const addFormRef = ref(null)
const editFormRef = ref(null)
const resetPwdResult = ref('')
const editingUserId = ref(null)
const isEditingCurrentUser = computed(() => editingUserId.value === userStore.user?.id)
const grantFolders = ref([])
const grantLoading = ref(false)
const GRANT_ACTION_ORDER = ['read', 'preview', 'download', 'edit', 'delete']
const GRANT_ACTION_IMPLIES = {
  read: ['read'],
  preview: ['read', 'preview'],
  download: ['read', 'preview', 'download'],
  edit: ['read', 'preview', 'download', 'edit'],
  delete: ['read', 'preview', 'download', 'edit', 'delete'],
}

const addForm = reactive({
  username: '',
  password: '',
  display_name: '',
  role: 'user',
  status: 'active',
})

const editForm = reactive({
  username: '',
  display_name: '',
  role: '',
  status: '',
})

const addRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]{3,20}$/, message: '3-20位，字母/数字/下划线', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { pattern: /^\S{8,32}$/, message: '8-32位，不能含空格', trigger: 'blur' },
  ],
  display_name: [
    { required: true, message: '请输入真实姓名', trigger: 'blur' },
    { min: 2, max: 20, message: '2-20字符', trigger: 'blur' },
  ],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
  status: [{ required: true, message: '请选择状态', trigger: 'change' }],
}

const editRules = {
  display_name: [
    { required: true, message: '请输入真实姓名', trigger: 'blur' },
    { min: 2, max: 20, message: '2-20字符', trigger: 'blur' },
  ],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
  status: [{ required: true, message: '请选择状态', trigger: 'change' }],
}

async function loadUsers() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (search.value) params.search = search.value
    if (roleFilter.value) params.role = roleFilter.value
    if (statusFilter.value) params.status = statusFilter.value
    const resp = await userAPI.list(params)
    users.value = resp.data.items
    total.value = resp.data.total
  } catch (e) {
    ElMessage.error('加载用户失败')
  } finally {
    loading.value = false
  }
}

function isCurrentUser(row) {
  return row.id === userStore.user?.id
}

function handleFilterChange() {
  page.value = 1
  loadUsers()
}

function resetFilters() {
  search.value = ''
  roleFilter.value = ''
  statusFilter.value = ''
  handleFilterChange()
}

function resetAddForm() {
  Object.assign(addForm, { username: '', password: '', display_name: '', role: 'user', status: 'active' })
  addFormRef.value?.resetFields()
  grantFolders.value = []
}

function resetEditForm() {
  resetPwdResult.value = ''
  editingUserId.value = null
  grantFolders.value = []
}

function cloneGrantTree(nodes) {
  return (nodes || []).map((node) => ({
    id: node.id,
    name: node.name,
    parent_id: node.parent_id,
    actions: [...(node.actions || [])],
    children: cloneGrantTree(node.children),
  }))
}

function collectGrants(nodes, acc = []) {
  for (const node of nodes || []) {
    if ((node.actions || []).length) {
      acc.push({ folder_id: node.id, actions: [...node.actions] })
    }
    if (node.children?.length) {
      collectGrants(node.children, acc)
    }
  }
  return acc
}

function hasGrantAction(row, action) {
  return (row.actions || []).includes(action)
}

function toggleGrantAction(row, action, checked) {
  if (checked) {
    row.actions = [...(GRANT_ACTION_IMPLIES[action] || [action])]
    return
  }
  const idx = GRANT_ACTION_ORDER.indexOf(action)
  row.actions = idx > 0 ? GRANT_ACTION_ORDER.slice(0, idx) : []
}

async function loadGrantTree(userId = null) {
  grantLoading.value = true
  try {
    const resp = userId
      ? await knowledgeAPI.getUserGrants(userId)
      : await knowledgeAPI.getGrantTree()
    grantFolders.value = cloneGrantTree(resp.data.folders || [])
  } catch (e) {
    grantFolders.value = []
    ElMessage.error(e.response?.data?.detail || '加载文件夹权限失败')
  } finally {
    grantLoading.value = false
  }
}

async function saveUserGrants(userId, role) {
  if (!userId) return
  const grants = role === 'admin' ? [] : collectGrants(grantFolders.value)
  await knowledgeAPI.updateUserGrants(userId, { grants })
}

async function openAddDialog() {
  resetAddForm()
  showAddDialog.value = true
  await loadGrantTree()
}

async function handleAddUser() {
  const valid = await addFormRef.value.validate().catch(() => false)
  if (!valid) return
  adding.value = true
  try {
    const created = await userAPI.create({ ...addForm })
    await saveUserGrants(created.data.id, addForm.role)
    ElMessage.success('用户已创建')
    showAddDialog.value = false
    await loadUsers()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '创建失败')
  } finally {
    adding.value = false
  }
}

function openEditDialog(row) {
  editingUserId.value = row.id
  Object.assign(editForm, {
    username: row.username,
    display_name: row.display_name || '',
    role: row.role,
    status: row.status,
  })
  resetPwdResult.value = ''
  showEditDialog.value = true
  loadGrantTree(row.id)
}

async function handleEditUser() {
  const valid = await editFormRef.value.validate().catch(() => false)
  if (!valid) return
  editing.value = true
  try {
    await userAPI.update(editingUserId.value, {
      display_name: editForm.display_name,
      role: editForm.role,
      status: editForm.status,
    })
    if (isEditingCurrentUser.value) {
      userStore.setUser({
        ...userStore.user,
        display_name: editForm.display_name,
      })
    }
    await saveUserGrants(editingUserId.value, editForm.role)
    ElMessage.success('用户已更新')
    showEditDialog.value = false
    await loadUsers()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '更新失败')
  } finally {
    editing.value = false
  }
}

async function toggleStatus(row) {
  if (isCurrentUser(row)) {
    ElMessage.warning('当前登录账号保持受保护状态')
    return
  }
  const newStatus = row.status === 'active' ? 'disabled' : 'active'
  try {
    await userAPI.updateStatus(row.id, newStatus)
    ElMessage.success(newStatus === 'active' ? '已启用' : '已禁用')
    await loadUsers()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

async function handleResetPassword() {
  try {
    const newPwd = 'admin123'
    await userAPI.resetPassword(editingUserId.value, newPwd)
    resetPwdResult.value = '新密码: ' + newPwd
    ElMessage.success('密码已重置')
  } catch (e) {
    ElMessage.error('重置失败')
  }
}

onMounted(() => loadUsers())
</script>

<style scoped>
.users-page { padding: 0; }

.page-header { margin-bottom: 20px; }
.page-header h2 { font-size: 20px; font-weight: 600; color: #1f2937; margin: 0; }

.panel {
  background: #fff;
  border-radius: 10px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.reset-result {
  color: #16a34a;
  font-size: 13px;
  margin-left: 12px;
  font-family: monospace;
}

.self-protection-alert {
  margin-bottom: 18px;
}
.grant-form-item {
  align-items: flex-start;
}
.grant-hint {
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.6;
  color: #6b7280;
}
.grant-table {
  width: 100%;
}
</style>
