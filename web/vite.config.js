import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Em desenvolvimento, /api vai para o backend local (porta 8000). Só escuta em 127.0.0.1.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    // O backend só aceita Host/Origin locais; o proxy repassa como 127.0.0.1:8000.
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, headers: { origin: 'http://127.0.0.1:8000' } } },
  },
  build: { outDir: 'dist', chunkSizeWarningLimit: 1200 },
})
