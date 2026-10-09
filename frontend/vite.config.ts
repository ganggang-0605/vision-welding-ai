import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 로컬 백엔드(FastAPI, uvicorn) 주소
const BACKEND_URL = 'http://localhost:8000'
const API_PREFIX = '/api'

/**
 * 백엔드 리다이렉트의 Location 을 프록시 경로로 되돌린다.
 * 예: FastAPI 슬래시 리다이렉트 `http://localhost:8000/workspaces` → `/api/workspaces`
 * (그대로 두면 브라우저·휴대폰이 프록시를 우회해 :8000 으로 직접 가서 실패한다)
 */
function toProxyLocation(location: string): string {
  if (location.startsWith(BACKEND_URL)) return API_PREFIX + location.slice(BACKEND_URL.length)
  if (location.startsWith('/') && !location.startsWith('//')) return API_PREFIX + location
  return location
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 0.0.0.0 으로 열어 같은 Wi-Fi의 휴대폰에서 http://<PC IP>:5173 으로 접속 가능
    host: true,
    port: 5173,
    proxy: {
      // /api/health → http://localhost:8000/health
      [API_PREFIX]: {
        target: BACKEND_URL,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            const location = proxyRes.headers.location
            if (location) proxyRes.headers.location = toProxyLocation(location)
          })
        },
      },
    },
  },
})
