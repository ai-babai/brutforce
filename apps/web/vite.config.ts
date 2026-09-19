import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { port: 5190, proxy: { '/api': 'http://localhost:8097' } },
  test: { environment: 'jsdom', setupFiles: './src/test/setup.ts' },
});
