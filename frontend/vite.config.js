import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': {
        // "backend" is the docker-compose service name; override with VITE_API_TARGET
        target: process.env.VITE_API_TARGET || 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
})
