<template>
  <div class="users-page">
    <div class="page-header">
      <h2>用户管理</h2>
    </div>

    <div class="panel">
      <div class="toolbar">
        <el-input v-model="search" placeholder="按用户名搜索" clearable style="width:200px" @keyup.enter="loadUsers" />
        <el-select v-model="roleFilter" placeholder="角色筛选" clearable style="width:140px" @change="loadUsers">
          <el-option label="管理员" value="admin" />
          <el-option label="技术作者" value="writer" />
          <el-option label="审核员" value="reviewer" />
        </el-select>
        <el-select v-model="statusFilter" placeholder="状态筛选" clearable style="width:120px" @change="loadUsers">
          <el-option label="正常" value="active" />
          <el-option label="禁用" value="disabled" />
        </el-select>
        <el-button type="primary" @click="showAddDialog = true">添加用户</el-button>
      </div>

      <el-table :data="users" border v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" sortable />
        <el-table-column prop="username" label="用户名" sortable />
        <el-table-column prop="display_name" label="真实姓名" />
        <el-table-column prop="role" label="角色" width="120" sortable>
          <template #default="scope">
            <el-tag v-if="scope.row.role === 'admin'" type="danger" size="small">管理员</el-tag>
            <el-tag v-else-if="scope.row.role === 'writer'" size="small">技术作者</el-tag>
            <el-tag v-else-if="scope.row.role === 'reviewer'" type="warning" size="small">审核员</el-tag>
            <el-tag v-else size="small" type="info">{{ scope.row.role }}</el-tag>
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
              @click="toggleStatus(scope.row)"
            >
              {{ scope.row.status === 'active' ? '禁用' : '启用' }}
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

    <el-dialog v-model="showAddDialog" title="添加用户" width="480px" @close="resetAddForm">
      <el-form :model="addForm" :rules="addRules" ref="addFormRef" label-width="100px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="addForm.username" placeholder="3-20位，字母/数字/下划线" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="addForm.password" type="password" show-password placeholder="8-32位，含大小写+数字" />
        </el-form-item>
        <el-form-item label="真实姓名" prop="display_name">
          <el-input v-model="addForm.display_name" placeholder="2-20字符" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="addForm.role" style="width:100%">
            <el-option label="管理员" value="admin" />
            <el-option label="技术作者" value="writer" />
            <el-option label="审核员" value="reviewer" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-radio-group v-model="addForm.status">
            <el-radio label="active">正常</el-radio>
            <el-radio label="disabled">禁用</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="adding" @click="handleAddUser">确认</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showEditDialog" title="编辑用户" width="480px" @close="resetEditForm">
      <el-form :model="editForm" :rules="editRules" ref="editFormRef" label-width="100px">
        <el-form-item label="用户名">
          <el-input :model-value="editForm.username" disabled />
        </el-form-item>
        <el-form-item label="真实姓名" prop="display_name">
          <el-input v-model="editForm.display_name" placeholder="2-20字符" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="editForm.role" style="width:100%">
            <el-option label="管理员" value="admin" />
            <el-option label="技术作者" value="writer" />
            <el-option label="审核员" value="reviewer" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-radio-group v-model="editForm.status">
            <el-radio label="active">正常</el-radio>
            <el-radio label="disabled">禁用</el-radio>
          </el-radio-group>
        </el-form-item>
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
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="editing" @click="handleEditUser">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { userAPI } from '@/api'

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

const addForm = reactive({
  username: '',
  password: '',
  display_name: '',
  role: 'writer',
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
    { pattern: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,32}$/, message: '8-32位，含大小写+数字', trigger: 'blur' },
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

function resetAddForm() {
  Object.assign(addForm, { username: '', password: '', display_name: '', role: 'writer', status: 'active' })
  addFormRef.value?.resetFields()
}

function resetEditForm() {
  resetPwdResult.value = ''
  editingUserId.value = null
}

async function handleAddUser() {
  const valid = await addFormRef.value.validate().catch(() => false)
  if (!valid) return
  adding.value = true
  try {
    await userAPI.create({ ...addForm })
    ElMessage.success('用户已创建')
    showAddDialog.value = false
    loadUsers()
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
    ElMessage.success('用户已更新')
    showEditDialog.value = false
    loadUsers()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '更新失败')
  } finally {
    editing.value = false
  }
}

async function toggleStatus(row) {
  const newStatus = row.status === 'active' ? 'disabled' : 'active'
  try {
    await userAPI.updateStatus(row.id, newStatus)
    ElMessage.success(newStatus === 'active' ? '已启用' : '已禁用')
    loadUsers()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

async function handleResetPassword() {
  try {
    const newPwd = generateRandomPassword()
    await userAPI.resetPassword(editingUserId.value, newPwd)
    resetPwdResult.value = '新密码: ' + newPwd
    ElMessage.success('密码已重置')
  } catch (e) {
    ElMessage.error('重置失败')
  }
}

function generateRandomPassword() {
  const upper = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
  const lower = 'abcdefghijkmnpqrstuvwxyz'
  const digits = '23456789'
  const all = upper + lower + digits
  let pwd = ''
  pwd += upper[Math.floor(Math.random() * upper.length)]
  pwd += lower[Math.floor(Math.random() * lower.length)]
  pwd += digits[Math.floor(Math.random() * digits.length)]
  for (let i = 0; i < 7; i++) {
    pwd += all[Math.floor(Math.random() * all.length)]
  }
  return pwd.split('').sort(() => Math.random() - 0.5).join('')
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
</style>
