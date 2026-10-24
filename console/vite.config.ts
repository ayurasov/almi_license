/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// The API is served by the Django server; in deploy/dev nginx proxies /api, here Vite does.
const apiTarget = process.env.VITE_API_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: { proxy: { '/api': { target: apiTarget, changeOrigin: false } } },
  // Screens are loaded lazily: scan them up front, otherwise the dev server finds new
  // dependencies on the first visit and reloads the page (it broke the first e2e sign-in).
  optimizeDeps: { entries: ['index.html', 'src/views/**/*.vue', 'src/components/**/*.vue'] },
  preview: { proxy: { '/api': { target: apiTarget, changeOrigin: false } } },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.spec.ts'],
  },
})
