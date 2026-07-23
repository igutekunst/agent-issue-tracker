import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The production build is emitted straight into the Python package so that
// `issue serve` can host the SPA with no separate web server.
export default defineConfig({
  plugins: [vue()],
  base: './',
  build: {
    outDir: '../src/issue_tracker/static',
    emptyOutDir: true,
  },
  server: {
    // During `npm run dev`, proxy API + SSE to the FastAPI backend.
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/events': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
