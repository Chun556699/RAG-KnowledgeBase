import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * Vite 配置。
 *
 * - 开发服务器端口 5173，暴露到 0.0.0.0 便于容器/局域网访问；
 * - 通过 proxy 将 /api 请求转发到后端（默认 http://localhost:8000），
 *   规避开发期跨域并简化前端请求地址。后端地址可通过环境变量 VITE_API_TARGET 覆盖。
 */
export default defineConfig(() => {
  const apiTarget = process.env.VITE_API_TARGET || 'http://localhost:8000'
  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: '0.0.0.0',
      port: 5173,
    },
  }
})
