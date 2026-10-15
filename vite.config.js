import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Forward /api/... calls to the Flask backend so the frontend can use
    // relative URLs (works the same locally and in GitHub Codespaces).
    proxy: {
      '/api': 'http://localhost:5000',
    },
  },
})
