import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5190,
    proxy: {
      '/v1': 'http://localhost:8097',
      '/api/docs': 'http://localhost:8097',
      '/api/openapi.json': 'http://localhost:8097',
      '/api/schema': 'http://localhost:8097',
    },
  },
  test: { environment: 'jsdom', setupFiles: './src/test/setup.ts' },
});
