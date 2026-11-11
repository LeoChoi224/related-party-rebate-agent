import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 개발 중 /api 요청을 FastAPI(8000번)로 넘긴다. 브라우저에는 같은 주소로 보여서 CORS 설정이 필요 없다.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
