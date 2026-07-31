import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import { createPinia } from 'pinia'

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

window.addEventListener('error', (event) => {
  renderBootstrapError(event.error || event)
})

window.addEventListener('unhandledrejection', (event) => {
  renderBootstrapError(event.reason || event)
})

async function bootstrap() {
  try {
    const [{ default: App }, { default: router }] = await Promise.all([
      import('./App.vue'),
      import('./router'),
    ])
    const app = createApp(App)
    const pinia = createPinia()

    app.use(ElementPlus, { locale: zhCn })
    app.use(pinia)
    app.use(router)
    app.mount('#app')
  } catch (error) {
    console.error('Failed to bootstrap app', error)
    renderBootstrapError(error)
  }
}

bootstrap()
