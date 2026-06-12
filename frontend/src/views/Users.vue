<template>
  <div class="users-container">
    <div class="header-section">
      <h3>用户管理</h3>
    </div>

    <div class="table-section">
      <el-table :data="users" border>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="role" label="角色" width="120">
          <template #default="scope">
            <el-select v-model="scope.row.role" @change="updateUserRole(scope.row)">
              <el-option label="管理员" value="admin" />
              <el-option label="审核员" value="reviewer" />
              <el-option label="普通用户" value="user" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.status === 'active' ? 'success' : 'danger'">
              {{ scope.row.status === 'active' ? '活跃' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" />
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { authAPI } from '@/api'
import { ElMessage } from 'element-plus'

const users = ref([])

onMounted(async () => {
  await loadUsers()
})

async function loadUsers() {
  try {
    const response = await authAPI.getUsers()
    users.value = response.data
  } catch (error) {
    ElMessage.error('加载用户失败')
  }
}

async function updateUserRole(user) {
  try {
    await authAPI.updateRole(user.id, user.role)
    ElMessage.success('角色更新成功')
  } catch (error) {
    ElMessage.error('更新失败')
    loadUsers()
  }
}
</script>

<style>
.users-container {
  padding: 20px;
}

.header-section {
  margin-bottom: 20px;
}

.header-section h3 {
  margin: 0;
  color: #333;
}

.table-section {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
}
</style>
