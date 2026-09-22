import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5190,
    proxy: {
      // Preserve the browser Host so the API's same-origin write check remains valid.
      '/v1': { target: 'http://localhost:8097', changeOrigin: false },
      '/v2': { target: 'http://localhost:8097', changeOrigin: false },
      '/catalog-assets': { target: 'http://localhost:8097', changeOrigin: false },
      '/api/docs': 'http://localhost:8097',
      '/api/openapi.json': 'http://localhost:8097',
      '/api/schema': 'http://localhost:8097',
    },
  },
  test: { environment: 'jsdom', setupFiles: './src/test/setup.ts' },
});
