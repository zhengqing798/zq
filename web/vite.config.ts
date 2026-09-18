import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 前端开发服务器：5173；构建产物 dist/（任务12 用 nginx 托管）
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    host: '127.0.0.1',
    watch: {
      // 有些编辑器/工具用「临时目录 + 原子改名」的方式写文件，watch 到临时文件时会抛
      // EBUSY 把 dev server 直接打挂。这里忽略临时目录/临时文件，只监听真正的源文件。
      ignored: (p: string) => /\.tmpdir([\\/]|$)|\.tmp$/.test(p),
    },
    proxy: {
      // 开发期代理，前端只需请求 /api/*，避免跨域与硬编码后端地址
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 2000,
  },
})
