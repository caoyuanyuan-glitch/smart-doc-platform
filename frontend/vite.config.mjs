import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

export default defineConfig({
  plugins: [
    vue(),
    // Element Plus 按需引入：模板中出现的 el-* 组件自动导入组件与样式，
    // 替代原先 main.js 中的全量 app.use(ElementPlus)
    Components({
      resolvers: [ElementPlusResolver()],
      dts: false
    }),
    {
      // element-plus 的 es/index.mjs 入口顶层仅有 import/export（无副作用调用），
      // 但 Rollup 将其视为有副作用，导致 `import { ElMessage } from 'element-plus'`
      // 无法被 tree-shake，整个库被全量打包。此处显式声明入口无副作用以恢复摇树。
      name: 'force-tree-shake-element-plus',
      transform(code, id) {
        if (id.includes('/element-plus/es/index.mjs')) {
          return { code, moduleSideEffects: false }
        }
      }
    }
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  optimizeDeps: {
    holdUntilCrawlEnd: true,
    include: [
      'vue',
      'vue-router',
      'pinia',
      'axios',
      'element-plus',
      'element-plus/es'
    ]
  },
  build: {
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        // 只对明确的公共依赖做稳定分包（利于长缓存），其余交给 Rollup 默认机制：
        // 动态 import 的库（pdfjs-dist / jszip）保持独立 chunk 按需加载，
        // element-plus 按需组件随使用页面自然聚合。
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('/echarts/') || id.includes('/zrender/')) return 'echarts'
          if (id.includes('/vue/') || id.includes('/vue-router/') || id.includes('/pinia/')) return 'vue-vendor'
          if (id.includes('/axios/')) return 'axios'
        }
      }
    }
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    // 预览网关下关闭 HMR，避免 WebSocket 断连和按需依赖发现导致整页刷新
    hmr: false,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        ws: true,
        proxyTimeout: 600000,
        timeout: 600000,
        rewrite: (path) => path.replace(/^\/api/, '/api'),
        configure: (proxy, options) => {
          proxy.on('proxyReq', (proxyReq, req, res) => {
            proxyReq.setTimeout(600000)
          })
          proxy.on('error', (err, req, res) => {
            console.error('Proxy error:', err.message)
          })
        }
      }
    }
  },
  preview: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        ws: true,
        proxyTimeout: 600000,
        timeout: 600000
      }
    }
  }
})
