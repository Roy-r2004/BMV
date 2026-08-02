import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// `@` resolves to the template's src, exactly as preview-template/vite.config.ts
// defines it, so template-internal imports resolve without editing the template.
const templateSrc = fileURLToPath(new URL('../preview-template/src', import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': templateSrc,
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
  },
});
