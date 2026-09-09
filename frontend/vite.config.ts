import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
// Every data route lives under /v1 now (bugs.md #13, app/main.py) -- a
// single proxy entry instead of one per top-level path, and (unlike the old
// list) nothing to remember to add when a new route module ships (this is
// exactly how /admin got missed after it was added in an earlier pass).
const BACKEND_URL = 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/v1': BACKEND_URL,
    },
  },
})
