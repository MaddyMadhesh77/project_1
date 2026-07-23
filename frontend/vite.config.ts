import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
// Backend routes are unprefixed (see DESIGN.md 7), so the dev proxy lists
// each top-level path rather than a single "/api" prefix.
const BACKEND_URL = 'http://localhost:8000'
const BACKEND_PATHS = [
  'chat',
  'memories',
  'trust',
  'integrity',
  'rollback',
  'attack',
  'search',
  'analytics',
  'logs',
]

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: Object.fromEntries(BACKEND_PATHS.map((path) => [`/${path}`, BACKEND_URL])),
  },
})
