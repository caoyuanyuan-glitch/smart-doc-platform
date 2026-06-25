<template>
  <div class="login-page">
    <div class="page-badge">Smart Doc Platform</div>
    <div class="page-corner page-corner-top"></div>
    <div class="page-corner page-corner-bottom"></div>

    <div class="login-shell">
      <section class="brand-panel">
        <div class="brand-visual" aria-hidden="true">
          <div class="tech-fragment fragment-doc"></div>
          <div class="tech-fragment fragment-code"></div>
          <div class="tech-fragment fragment-data"></div>
          <div class="circuit-line circuit-line-left circuit-line-top"></div>
          <div class="circuit-line circuit-line-left circuit-line-mid"></div>
          <div class="circuit-line circuit-line-left circuit-line-bottom"></div>
          <div class="circuit-line circuit-line-right circuit-line-top"></div>
          <div class="circuit-line circuit-line-right circuit-line-mid"></div>
          <div class="circuit-line circuit-line-right circuit-line-bottom"></div>
          <div class="ring ring-outer"></div>
          <div class="ring ring-middle"></div>
          <div class="ring ring-inner"></div>
          <div class="chip-core">
            <div class="chip-pins chip-pins-top"></div>
            <div class="chip-pins chip-pins-right"></div>
            <div class="chip-pins chip-pins-bottom"></div>
            <div class="chip-pins chip-pins-left"></div>
            <div class="brain-mark">
              <span></span><span></span><span></span>
            </div>
          </div>
        </div>

        <div class="brand-copy">
          <p class="brand-kicker">智能技术文档协同工作台</p>
          <h1>一站式AI技术文档协作平台</h1>
        </div>

        <div class="capability-grid">
          <article class="capability-card">
            <el-icon class="capability-icon"><DocumentChecked /></el-icon>
            <span>审核/润色/格式转换</span>
          </article>
          <article class="capability-card">
            <el-icon class="capability-icon"><EditPen /></el-icon>
            <span>智能生成+专业翻译</span>
          </article>
          <article class="capability-card">
            <el-icon class="capability-icon"><ChatDotRound /></el-icon>
            <span>研发智能问答</span>
          </article>
          <article class="capability-card">
            <el-icon class="capability-icon"><Collection /></el-icon>
            <span>企业知识库管理</span>
          </article>
        </div>
      </section>

      <section class="login-card-wrap">
        <div class="login-card">
          <div class="login-header">
            <span class="sign-tag">Sign In</span>
            <h2>欢迎回来</h2>
            <p>研发/文档工程师账号登录，进入工作台高效处理文档工作。</p>
          </div>

          <div class="account-tip">
            <el-icon class="account-tip-icon"><InfoFilled /></el-icon>
            <span class="account-tip-label">测试账号</span>
            <strong>admin / admin123</strong>
          </div>

          <el-form
            ref="formRef"
            :model="form"
            :rules="rules"
            class="login-form"
            label-position="top"
            :hide-required-asterisk="true"
            @submit.prevent
          >
            <el-form-item prop="username">
              <template #label>
                <span class="field-label">用户名 <em>*</em></span>
              </template>
              <el-input v-model.trim="form.username" placeholder="请输入用户名" size="large" @keyup.enter="handleSubmit">
                <template #prefix>
                  <el-icon class="input-icon"><User /></el-icon>
                </template>
              </el-input>
            </el-form-item>

            <el-form-item prop="password">
              <template #label>
                <span class="field-label">密码 <em>*</em></span>
              </template>
              <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" size="large" @keyup.enter="handleSubmit">
                <template #prefix>
                  <el-icon class="input-icon"><Lock /></el-icon>
                </template>
              </el-input>
            </el-form-item>

            <el-form-item class="submit-item">
              <el-button type="primary" :loading="submitting" @click="handleSubmit" class="login-button">
                进入平台
              </el-button>
            </el-form-item>
          </el-form>

          <div class="login-footer">
            <span>暂无账号</span>
            <button type="button" class="contact-link" @click="contactAdmin">联系管理员开通</button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { authAPI } from '@/api'
import { ElMessage } from 'element-plus'
import {
  ChatDotRound,
  Collection,
  DocumentChecked,
  EditPen,
  InfoFilled,
  Lock,
  User,
} from '@element-plus/icons-vue'

const router = useRouter()
const userStore = useUserStore()
const formRef = ref(null)
const submitting = ref(false)

const form = reactive({
  username: '',
  password: ''
})

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]{3,20}$/, message: '用户名为 3-20 位字母、数字或下划线', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { pattern: /^\S{8,32}$/, message: '密码为 8-32 位，且不能包含空格', trigger: 'blur' }
  ]
}

onMounted(async () => {
  if (!userStore.token) {
    return
  }
  try {
    const resp = await authAPI.getMe()
    if (resp.data) {
      userStore.setUser(resp.data)
      router.replace('/')
    }
  } catch {
    userStore.logout()
  }
})

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
    const response = await authAPI.login(form.username.trim(), form.password)
    userStore.setToken(response.data.access_token)
    userStore.setUser(response.data.user)
    ElMessage.success('登录成功')
    router.push('/')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '登录失败')
  } finally {
    submitting.value = false
  }
}

function contactAdmin() {
  ElMessage.info('请联系管理员开通账号')
}
</script>

<style>
.login-page {
  --color-bg-top: #081426;
  --color-bg-bottom: #0f223d;
  --color-primary: #0077e6;
  --color-accent: #42c4ff;
  --text-main: #ffffff;
  --text-accent: #42c4ff;
  --text-secondary: #b0c6e3;
  --text-weak: #849bc0;
  position: relative;
  width: 100vw;
  min-height: 100vh;
  align-self: stretch;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 56px 48px;
  font-family: 'Source Han Sans SC', 'Source Han Sans CN', 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background:
    linear-gradient(180deg, var(--color-bg-top) 0%, var(--color-bg-bottom) 100%);
}

.login-page::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(176, 198, 227, 0.05) 0.4px, transparent 0.4px),
    linear-gradient(90deg, rgba(176, 198, 227, 0.05) 0.4px, transparent 0.4px);
  background-size: 36px 36px;
  pointer-events: none;
}

.page-badge {
  position: absolute;
  top: 34px;
  left: 42px;
  z-index: 2;
  padding: 8px 16px;
  border-radius: 999px;
  border: 1px solid rgba(66, 196, 255, 0.38);
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(12px);
  color: var(--text-accent);
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.04em;
}

.page-corner {
  position: absolute;
  width: 280px;
  height: 280px;
  border-radius: 50%;
  background: rgba(0, 119, 230, 0.12);
  filter: blur(90px);
  pointer-events: none;
}

.page-corner-top {
  top: -100px;
  right: -60px;
}

.page-corner-bottom {
  left: -80px;
  bottom: -120px;
}

.login-shell {
  position: relative;
  z-index: 1;
  width: min(100%, 1220px);
  display: grid;
  grid-template-columns: minmax(0, 620px) 430px;
  justify-content: center;
  align-items: center;
  gap: 120px;
}

.brand-panel {
  position: relative;
  padding: 40px 32px 40px 40px;
  color: var(--text-main);
}

.brand-visual {
  position: absolute;
  z-index: 0;
  top: 92px;
  left: 50%;
  width: 620px;
  height: 360px;
  opacity: 1;
  transform: translateX(-56%);
  pointer-events: none;
}

.ring,
.chip-core {
  position: absolute;
  inset: 50%;
  border-radius: 50%;
  transform: translate(-50%, -50%);
}

.ring {
  border: 1px solid rgba(66, 196, 255, 0.2);
  box-shadow: 0 0 34px rgba(66, 196, 255, 0.12);
}

.ring-outer {
  width: 292px;
  height: 292px;
}

.ring-middle {
  width: 210px;
  height: 210px;
}

.ring-inner {
  width: 136px;
  height: 136px;
}

.chip-core {
  width: 118px;
  height: 118px;
  border-radius: 16px;
  border: 1px solid rgba(66, 196, 255, 0.64);
  background:
    linear-gradient(135deg, rgba(66, 196, 255, 0.28), rgba(0, 119, 230, 0.16)),
    rgba(8, 20, 38, 0.9);
  box-shadow:
    0 0 54px rgba(66, 196, 255, 0.36),
    0 0 120px rgba(0, 119, 230, 0.16),
    inset 0 0 26px rgba(66, 196, 255, 0.18);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-accent);
}

.chip-core::before,
.chip-core::after {
  content: '';
  position: absolute;
  inset: -13px;
  border-radius: 24px;
  border: 1px solid rgba(66, 196, 255, 0.24);
}

.chip-pins {
  position: absolute;
  background: repeating-linear-gradient(90deg, rgba(66, 196, 255, 0.5) 0 3px, transparent 3px 10px);
  opacity: 0.9;
}

.chip-pins-top,
.chip-pins-bottom {
  left: 14px;
  right: 14px;
  height: 5px;
}

.chip-pins-top {
  top: -10px;
}

.chip-pins-bottom {
  bottom: -10px;
}

.chip-pins-left,
.chip-pins-right {
  top: 14px;
  bottom: 14px;
  width: 5px;
  background: repeating-linear-gradient(180deg, rgba(66, 196, 255, 0.5) 0 3px, transparent 3px 10px);
}

.chip-pins-left {
  left: -10px;
}

.chip-pins-right {
  right: -10px;
}

.brain-mark {
  position: absolute;
  inset: 16px;
  opacity: 0.55;
}

.brain-mark span {
  position: absolute;
  width: 28px;
  height: 18px;
  border: 1px solid rgba(66, 196, 255, 0.62);
  border-radius: 50%;
}

.brain-mark span:nth-child(1) {
  top: 6px;
  left: 10px;
}

.brain-mark span:nth-child(2) {
  top: 18px;
  right: 8px;
}

.brain-mark span:nth-child(3) {
  bottom: 8px;
  left: 20px;
}

.circuit-line {
  position: absolute;
  top: 50%;
  width: 202px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(66, 196, 255, 0.62), rgba(66, 196, 255, 0.24));
  box-shadow: 0 0 16px rgba(66, 196, 255, 0.28);
  filter: blur(0.2px);
}

.circuit-line::before,
.circuit-line::after {
  content: '';
  position: absolute;
  right: 0;
  width: 42px;
  height: 1px;
  background: rgba(66, 196, 255, 0.4);
  box-shadow: 0 0 10px rgba(66, 196, 255, 0.22);
  transform-origin: right center;
}

.circuit-line::before {
  transform: rotate(35deg);
}

.circuit-line::after {
  transform: rotate(-35deg);
}

.circuit-line-left {
  left: 0;
}

.circuit-line-right {
  right: 0;
  transform: scaleX(-1);
}

.circuit-line-top {
  top: 34%;
}

.circuit-line-mid {
  top: 50%;
  width: 236px;
}

.tech-fragment {
  position: absolute;
  border: 1px solid rgba(66, 196, 255, 0.12);
  border-radius: 8px;
  opacity: 1;
}

.tech-fragment::before,
.tech-fragment::after {
  content: '';
  position: absolute;
  left: 12px;
  right: 12px;
  height: 1px;
  background: rgba(66, 196, 255, 0.12);
}

.fragment-doc {
  top: 24px;
  left: 74px;
  width: 78px;
  height: 94px;
}

.fragment-doc::before {
  top: 26px;
}

.fragment-doc::after {
  top: 48px;
}

.fragment-code {
  right: 48px;
  top: 62px;
  width: 106px;
  height: 58px;
}

.fragment-code::before {
  top: 20px;
}

.fragment-code::after {
  top: 36px;
}

.fragment-data {
  left: 104px;
  bottom: 42px;
  width: 118px;
  height: 54px;
}

.fragment-data::before {
  top: 18px;
}

.fragment-data::after {
  top: 34px;
}

.circuit-line-bottom {
  top: 66%;
}

.brand-copy,
.capability-grid {
  position: relative;
  z-index: 1;
}

.brand-kicker {
  margin: 20px 0 12px;
  color: var(--text-accent);
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.02em;
}

.brand-copy h1 {
  margin: 0 0 22px;
  color: var(--text-main);
  font-size: 36px;
  font-weight: 600;
  line-height: 1.2;
  white-space: nowrap;
  letter-spacing: -0.01em;
}

.capability-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 28px;
  width: 100%;
  margin-top: 282px;
}

.capability-card {
  display: flex;
  align-items: center;
  gap: 18px;
  min-height: 104px;
  padding: 20px 22px;
  border-radius: 10px;
  border: 1px solid rgba(66, 196, 255, 0.28);
  background: rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(10px);
  color: var(--text-main);
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.capability-card:hover {
  transform: translateY(-3px);
  border-color: rgba(66, 196, 255, 0.42);
  box-shadow: 0 14px 32px rgba(0, 119, 230, 0.18);
}

.capability-icon {
  width: 34%;
  min-width: 54px;
  max-width: 68px;
  height: 44px;
  color: var(--text-accent);
  flex-shrink: 0;
  filter: drop-shadow(0 0 10px rgba(66, 196, 255, 0.28));
}

.capability-icon svg {
  width: 100%;
  height: 100%;
}

.capability-card span {
  color: var(--text-main);
  font-size: 15px;
  font-weight: 600;
  line-height: 1.4;
  white-space: nowrap;
}

.login-card-wrap {
  display: flex;
  justify-content: center;
}

.login-card {
  width: 430px;
  padding: 42px 38px;
  border-radius: 14px;
  border: 1px solid rgba(66, 196, 255, 0.34);
  background: rgba(255, 255, 255, 0.09);
  backdrop-filter: blur(16px);
  box-shadow:
    0 26px 70px rgba(0, 119, 230, 0.16),
    0 10px 28px rgba(3, 12, 28, 0.34),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.login-header {
  margin-bottom: 26px;
}

.sign-tag {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(66, 196, 255, 0.12);
  color: var(--text-accent);
  font-size: 12px;
  font-weight: 500;
}

.login-header h2 {
  margin: 14px 0 8px;
  color: var(--text-main);
  font-size: 28px;
  font-weight: 600;
}

.login-header p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.8;
}

.account-tip {
  display: grid;
  grid-template-columns: auto auto 1fr;
  align-items: center;
  gap: 10px;
  margin-bottom: 30px;
  padding: 10px 14px;
  border-radius: 8px;
  background: rgba(66, 196, 255, 0.16);
  border: 1px solid rgba(66, 196, 255, 0.38);
  box-shadow: inset 0 0 18px rgba(66, 196, 255, 0.04);
}

.account-tip-icon {
  color: var(--text-accent);
  font-size: 16px;
}

.account-tip-label {
  color: var(--text-secondary);
  font-size: 13px;
}

.account-tip strong {
  justify-self: end;
  color: var(--text-main);
  font-size: 14px;
  font-weight: 600;
}

.login-form .el-form-item {
  margin-bottom: 20px;
}

.field-label {
  color: var(--text-main);
  font-size: 14px;
  font-weight: 500;
}

.field-label em {
  color: var(--text-weak);
  font-style: normal;
}

.login-page .login-form .el-form-item__label {
  padding-bottom: 8px;
}

.login-page .login-form .el-input__wrapper {
  min-height: 46px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05) !important;
  box-shadow: inset 0 0 0 1px #335a8c !important;
  transition: box-shadow 0.18s ease, background 0.18s ease, transform 0.18s ease;
}

.login-page .login-form .el-input__inner {
  color: var(--text-main) !important;
  caret-color: var(--color-accent);
}

.login-page .login-form .el-input__inner::placeholder {
  color: var(--text-weak) !important;
}

.login-page .login-form .el-input__wrapper.is-focus {
  box-shadow: inset 0 0 0 1px var(--color-primary), 0 0 0 4px rgba(0, 119, 230, 0.12) !important;
}

.login-page .login-form .el-input__prefix,
.login-page .login-form .el-input__suffix,
.login-page .login-form .el-input__password {
  color: var(--text-weak) !important;
}

.login-page .login-form .el-form-item__error {
  color: #ff9f9f;
}

.input-icon {
  color: var(--color-accent);
  filter: drop-shadow(0 0 6px rgba(66, 196, 255, 0.24));
}

.submit-item {
  margin-top: 30px;
  margin-bottom: 0;
}

.login-button {
  width: 100%;
  height: 48px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(180deg, #0077e8 0%, #229cff 100%);
  color: #fff;
  font-size: 16px;
  font-weight: 500;
  box-shadow: 0 14px 26px rgba(0, 119, 230, 0.22);
  transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
}

.login-button:hover {
  transform: translateY(-2px);
  filter: brightness(1.04);
  box-shadow: 0 18px 30px rgba(34, 156, 255, 0.24);
}

.login-footer {
  margin-top: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 15px;
  font-weight: 500;
}

.contact-link {
  padding: 0;
  border: none;
  background: transparent;
  color: #73d6ff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: color 0.18s ease, text-decoration-color 0.18s ease;
}

.contact-link:hover {
  color: #78d6ff;
  text-decoration: underline;
}

@media (max-width: 1200px) {
  .login-shell {
    gap: 64px;
  }
}

@media (max-width: 980px) {
  .login-page {
    padding: 88px 24px 32px;
  }

  .page-badge {
    top: 24px;
    left: 24px;
  }

  .login-shell {
    width: min(100%, 640px);
    grid-template-columns: 1fr;
    gap: 36px;
  }

  .brand-panel,
  .login-card-wrap {
    justify-self: center;
    width: 100%;
  }

  .brand-visual {
    width: 260px;
    height: 260px;
  }

  .ring-outer {
    width: 260px;
    height: 260px;
  }

  .ring-middle {
    width: 188px;
    height: 188px;
  }

  .ring-inner {
    width: 122px;
    height: 122px;
  }
}

@media (max-width: 640px) {
  .login-page {
    padding: 84px 18px 24px;
  }

  .brand-copy h1 {
    font-size: 30px;
  }

  .capability-grid {
    grid-template-columns: 1fr;
  }

  .login-card {
    width: 100%;
    padding: 30px 22px;
  }

  .account-tip {
    grid-template-columns: auto 1fr;
  }

  .account-tip strong {
    grid-column: 1 / -1;
    justify-self: start;
    padding-left: 26px;
  }
}
</style>
