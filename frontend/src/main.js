import { createApp } from 'vue'
import { createPinia } from 'pinia'
// Element Plus 按需引入：模板中的 el-* 组件由 unplugin-vue-components 自动导入并附带样式
// ElMessage / ElMessageBox 属于 JS API 调用，无法被模板解析器覆盖，需手动补充样式
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'

function renderBootstrapError(error) {
  const root = document.getElementById('app')
  if (!root) return
  let message = 'Unknown error'
  if (error instanceof Error) {
    message = `${error.name}: ${error.message}${error.stack ? `\n\n${error.stack}` : ''}`
  } else if (typeof error === 'string') {
    message = error
  } else if (error && typeof error === 'object') {
    try {
      message = JSON.stringify(error, Object.getOwnPropertyNames(error), 2)
    } catch {
      const fields = ['type', 'message', 'reason', 'filename', 'lineno', 'colno']
        .map((key) => `${key}: ${error[key] ?? ''}`)
        .join('\n')
      message = fields || String(error)
    }
  }
  root.innerHTML = `
    <div style="padding:24px;font-family:system-ui,sans-serif;color:#111827;background:#f8fafc;min-height:100vh;">
      <h2 style="margin:0 0 12px;font-size:20px;">前端启动失败</h2>
      <pre style="white-space:pre-wrap;word-break:break-word;background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;padding:16px;line-height:1.5;">${message}</pre>
    </div>
  `
}

function isUsefulBootstrapError(error) {
  if (error instanceof Error) return true
  if (typeof error === 'string' && error.trim()) return true
  if (!error || typeof error !== 'object') return false
  return Boolean(error.message || error.reason || error.filename || error.error)
}

function errorMessage(error) {
  if (error instanceof Error) return error.message || ''
  if (typeof error === 'string') return error
  return String(error?.message || error?.reason || '')
}

function isStaleChunkError(error) {
  const message = errorMessage(error)
  return (
    message.includes('Failed to fetch dynamically imported module') ||
    message.includes('error loading dynamically imported module') ||
    message.includes('Importing a module script failed')
  )
}

function reloadStaleChunkOnce() {
  const key = 'vite-stale-chunk-reload'
  const last = Number(sessionStorage.getItem(key) || 0)
  if (Date.now() - last < 8000) return false
  sessionStorage.setItem(key, String(Date.now()))
  window.location.reload()
  return true
}

let appReady = false

window.addEventListener('error', (event) => {
  const payload = event.error || event
  if (appReady && isStaleChunkError(payload) && reloadStaleChunkOnce()) {
    event.preventDefault()
    return
  }
  if (appReady) {
    console.error('Runtime error', payload)
    return
  }
  if (!isUsefulBootstrapError(payload)) {
    console.warn('Ignored non-fatal window error event', event)
    return
  }
  renderBootstrapError(payload)
})

window.addEventListener('unhandledrejection', (event) => {
  const payload = event.reason || event
  if (appReady && isStaleChunkError(payload) && reloadStaleChunkOnce()) {
    event.preventDefault()
    return
  }
  if (appReady) {
    console.error('Unhandled rejection', payload)
    return
  }
  if (!isUsefulBootstrapError(payload)) {
    console.warn('Ignored non-fatal unhandledrejection event', event)
    return
  }
  renderBootstrapError(payload)
})

window.addEventListener('vite:preloadError', (event) => {
  event.preventDefault()
  reloadStaleChunkOnce()
})

async function bootstrap() {
  try {
    const [{ default: App }, { default: router }] = await Promise.all([
      import('./App.vue'),
      import('./router'),
    ])
    const app = createApp(App)
    const pinia = createPinia()

    app.use(pinia)
    app.use(router)
    app.mount('#app')
    appReady = true
  } catch (error) {
    console.error('Failed to bootstrap app', error)
    renderBootstrapError(error)
  }
}

bootstrap()
