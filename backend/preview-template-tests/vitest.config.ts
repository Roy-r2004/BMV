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
    // The template's source lives outside this package, so its bare imports
    // resolve from ITS directory, not ours — `preview-template/node_modules`.
    // Two consequences, and both have bitten:
    //
    //  * On a clean checkout that directory does not exist and every template
    //    import fails ("Failed to resolve import 'react'"). CI installs the
    //    template's deps for exactly this reason — see the workflow.
    //  * Once it does exist, React resolves TWICE — once for the test file from
    //    here, once for the template source from there — and two React copies
    //    break hooks at runtime with an unrelated-looking error.
    //
    // `dedupe` collapses both to this package's copy, which is pinned to the
    // template's major.
    dedupe: ['react', 'react-dom'],
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
  },
});
