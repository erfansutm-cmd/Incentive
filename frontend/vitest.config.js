import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

// Component tests run in jsdom against a mocked /api, so they need no browser,
// no backend and no database. The browser suite stays in tests/*.spec.js and is
// run by Playwright (`npm run test:e2e`).
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    include: ['tests/unit/**/*.spec.js'],
    restoreMocks: true,
    clearMocks: true,
  },
})
