<template>
  <div class="login-container">
    <div class="login-hero">
      <div class="hero-badge">AI Document Workspace</div>
      <div class="hero-content">
        <span class="hero-kicker">智能文档协作平台</span>
        <h1>让知识沉淀、内容生成与问题处理在同一工作台高效完成</h1>
        <p>面向技术文档场景打造的统一入口，覆盖知识问答、文档处理、内容优化与反馈闭环，帮助团队更快完成专业内容协作。</p>
      </div>
      <div class="hero-grid">
        <div class="hero-panel">
          <span class="panel-label">Knowledge</span>
          <strong>知识检索与多轮问答</strong>
          <p>围绕知识库和上传文档进行追问、定位与归纳。</p>
        </div>
        <div class="hero-panel">
          <span class="panel-label">Workflow</span>
          <strong>润色、审核与格式转换</strong>
          <p>将文档生产、校验与输出环节集中在同一工作流中完成。</p>
        </div>
        <div class="hero-panel hero-panel-wide">
          <span class="panel-label">Management</span>
          <strong>反馈回流与处理闭环</strong>
          <p>统一管理用户反馈、状态处理与结果追踪，提升内容质量迭代效率。</p>
        </div>
      </div>
    </div>

    <div class="login-card-shell">
      <div class="login-card-glow"></div>
      <div class="login-card">
        <div class="login-header">
          <span class="login-section-tag">{{ isRegisterMode ? 'Create Account' : 'Sign In' }}</span>
          <h2>{{ isRegisterMode ? '创建使用账号' : '欢迎回来' }}</h2>
          <p>{{ isRegisterMode ? '创建普通用户账号后即可进入平台开展文档协作。' : '请输入用户名和密码，进入您的智能文档工作台。' }}</p>
        </div>

        <el-form ref="formRef" :model="form" :rules="rules" class="login-form" label-position="top" @submit.prevent>
          <el-form-item label="用户名" prop="username">
            <el-input v-model.trim="form.username" placeholder="请输入用户名" size="large" @keyup.enter="handleSubmit" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" size="large" @keyup.enter="handleSubmit" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="submitting" @click="handleSubmit" class="login-button">
              {{ isRegisterMode ? '注册并返回登录' : '进入平台' }}
            </el-button>
          </el-form-item>
        </el-form>

        <div class="login-footer">
          <span>{{ isRegisterMode ? '已有账号' : '还没有账号' }}</span>
          <el-button text type="primary" @click="toggleMode">
            {{ isRegisterMode ? '去登录' : '立即注册' }}
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { authAPI } from '@/api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const formRef = ref(null)
const submitting = ref(false)
const isRegisterMode = ref(false)

const form = reactive({
  username: '',
  password: ''
})

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 2, max: 50, message: '用户名长度为 2-50 个字符', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 100, message: '密码长度为 6-100 个字符', trigger: 'blur' }
  ]
}

onMounted(async () => {
  const mode = String(route.query.mode || '')
  isRegisterMode.value = mode === 'register'
  if (!userStore.token) {
    return
  }
  try {
    const resp = await authAPI.getMe()
    if (resp.data) {
      userStore.setUser(resp.data)
      router.replace('/')
      return
    }
  } catch {
    userStore.logout()
  }
})

function toggleMode() {
  isRegisterMode.value = !isRegisterMode.value
  form.password = ''
  router.replace({ path: '/login', query: isRegisterMode.value ? { mode: 'register' } : {} })
}

async function validateForm() {
  if (!formRef.value) return false
  try {
    await formRef.value.validate()
    return true
  } catch {
    return false
  }
}

async function handleSubmit() {
  const valid = await validateForm()
  if (!valid || submitting.value) return
  submitting.value = true
  try {
    if (isRegisterMode.value) {
      await authAPI.register(form.username.trim(), form.password)
      ElMessage.success('注册成功，请登录')
      isRegisterMode.value = false
      form.password = ''
      router.replace('/login')
    } else {
      const response = await authAPI.login(form.username.trim(), form.password)
      userStore.setToken(response.data.access_token)
      userStore.setUser(response.data.user)
      ElMessage.success('登录成功')
      router.push('/')
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || (isRegisterMode.value ? '注册失败' : '登录失败'))
  } finally {
    submitting.value = false
  }
}
</script>

<style>
.login-container {
  position: relative;
  overflow: hidden;
  width: 100%;
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(420px, 1.15fr) minmax(420px, 500px);
  justify-content: center;
  align-items: center;
  gap: 40px;
  padding: 56px 64px;
  background:
    radial-gradient(circle at 12% 18%, rgba(125, 211, 252, 0.2), transparent 24%),
    radial-gradient(circle at 85% 20%, rgba(129, 140, 248, 0.22), transparent 28%),
    radial-gradient(circle at 70% 78%, rgba(96, 165, 250, 0.18), transparent 24%),
    linear-gradient(135deg, #081226 0%, #102347 38%, #132f63 68%, #0f1f43 100%);
}

.login-container::before,
.login-container::after {
  content: '';
  position: absolute;
  border-radius: 999px;
  filter: blur(12px);
  opacity: 0.4;
  pointer-events: none;
}

.login-container::before {
  width: 220px;
  height: 220px;
  top: 72px;
  right: 18%;
  background: rgba(96, 165, 250, 0.24);
}

.login-container::after {
  width: 280px;
  height: 280px;
  left: -60px;
  bottom: -70px;
  background: rgba(167, 139, 250, 0.18);
}

.login-hero {
  position: relative;
  z-index: 1;
  color: #fff;
  max-width: 640px;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  padding: 7px 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.14);
  backdrop-filter: blur(10px);
  font-size: 12px;
  color: rgba(255, 255, 255, 0.86);
  letter-spacing: 0.12em;
  margin-bottom: 24px;
}

.hero-content {
  margin-bottom: 28px;
}

.hero-kicker {
  display: inline-block;
  margin-bottom: 12px;
  color: #93c5fd;
  font-size: 14px;
  letter-spacing: 0.08em;
}

.login-hero h1 {
  font-size: 46px;
  line-height: 1.18;
  font-weight: 700;
  margin-bottom: 18px;
  letter-spacing: -0.02em;
}

.login-hero p {
  max-width: 560px;
  font-size: 16px;
  line-height: 1.9;
  color: rgba(255, 255, 255, 0.76);
}

.hero-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.hero-panel {
  padding: 18px 18px 20px;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.12) 0%, rgba(255, 255, 255, 0.06) 100%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(14px);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.hero-panel-wide {
  grid-column: 1 / -1;
}

.panel-label {
  display: inline-block;
  margin-bottom: 10px;
  font-size: 11px;
  color: rgba(191, 219, 254, 0.92);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.hero-panel strong {
  display: block;
  margin-bottom: 8px;
  font-size: 17px;
  font-weight: 600;
  color: #ffffff;
}

.hero-panel p {
  margin: 0;
  font-size: 13px;
  line-height: 1.8;
  color: rgba(226, 232, 240, 0.84);
}

.login-card-shell {
  position: relative;
  z-index: 1;
}

.login-card-glow {
  position: absolute;
  inset: 18px -8px -18px 12px;
  background: linear-gradient(135deg, rgba(96, 165, 250, 0.26), rgba(129, 140, 248, 0.18));
  filter: blur(28px);
  border-radius: 30px;
}

.login-card {
  position: relative;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(255, 255, 255, 0.78);
  border-radius: 28px;
  padding: 38px 34px 30px;
  box-shadow: 0 24px 80px rgba(8, 18, 38, 0.28);
  backdrop-filter: blur(18px);
}

.login-header {
  margin-bottom: 26px;
}

.login-section-tag {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  margin-bottom: 14px;
  border-radius: 999px;
  background: #eff6ff;
  color: #2563eb;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
}

.login-header h2 {
  font-size: 30px;
  color: #0f172a;
  margin-bottom: 10px;
  letter-spacing: -0.02em;
}

.login-header p {
  color: #64748b;
  font-size: 14px;
  line-height: 1.75;
}

.login-form .el-form-item {
  margin-bottom: 18px;
}

.login-form :deep(.el-input__wrapper) {
  min-height: 46px;
  border-radius: 14px;
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.18) inset;
}

.login-button {
  width: 100%;
  height: 46px;
  border-radius: 14px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.02em;
  box-shadow: 0 14px 30px rgba(37, 99, 235, 0.24);
}

.login-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 10px;
  color: #64748b;
  font-size: 14px;
}

@media (max-width: 1100px) {
  .login-container {
    grid-template-columns: 1fr;
    gap: 28px;
    padding: 28px 24px 32px;
  }

  .login-hero,
  .login-hero p {
    max-width: none;
  }

  .login-hero h1 {
    font-size: 36px;
  }
}

@media (max-width: 640px) {
  .hero-grid {
    grid-template-columns: 1fr;
  }

  .login-card {
    padding: 28px 22px 24px;
  }

  .login-hero h1 {
    font-size: 30px;
  }
}
</style>
