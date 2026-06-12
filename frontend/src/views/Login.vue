<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <h1>智能技术文档平台</h1>
        <p>AI赋能的技术文档生产平台</p>
      </div>
      <el-form ref="formRef" :model="form" label-width="80px" class="login-form">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="login" class="login-button">登录</el-button>
          <el-button @click="register" class="register-button">注册</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { authAPI } from '@/api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const userStore = useUserStore()

const form = ref({
  username: '',
  password: ''
})

async function login() {
  try {
    const response = await authAPI.login(form.value.username, form.value.password)
    userStore.setToken(response.data.access_token)
    userStore.setUser(response.data.user)
    ElMessage.success('登录成功')
    router.push('/')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '登录失败')
  }
}

async function register() {
  try {
    await authAPI.register(form.value.username, form.value.password)
    ElMessage.success('注册成功，请登录')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '注册失败')
  }
}
</script>

<style>
.login-container {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  background: #fff;
  border-radius: 12px;
  padding: 40px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  width: 400px;
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
}

.login-header h1 {
  font-size: 24px;
  color: #333;
  margin-bottom: 8px;
}

.login-header p {
  color: #999;
  font-size: 14px;
}

.login-form {
  padding: 0 20px;
}

.login-button {
  width: 45%;
  margin-right: 10%;
}

.register-button {
  width: 45%;
}
</style>
