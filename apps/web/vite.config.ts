import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Fail loudly on a port collision instead of silently drifting to 5174/5175,
    // which lands the app on an origin the API may not allow.
    strictPort: true,
    watch: {
      ignored: ['**/workspace/**', '**/.next/**', '**/runner_ide.db**', '**/*.log']
    }
  }
})
