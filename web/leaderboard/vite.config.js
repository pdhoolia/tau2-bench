import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { commentsHandler, usernameHandler } from './server/commentsApi.js'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    {
      name: 'comments-api',
      configureServer(server) {
        // Mount API handlers for comments feature
        server.middlewares.use('/api/comments', commentsHandler)
        server.middlewares.use('/api/username', usernameHandler)
      }
    }
  ],
  // Note: base path configuration may need adjustment based on deployment strategy
  // Previously configured for standalone GitHub Pages deployment
  base: process.env.NODE_ENV === 'production' ? (process.env.GITHUB_PAGES_BASE || '/') : '/',
  build: {
    outDir: 'dist'
  }
})
