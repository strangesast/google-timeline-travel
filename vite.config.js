import { defineConfig } from 'vite';
import { resolve } from 'node:path';

// Two build tiers selected by --mode:
//   --mode dev   -> full-fidelity data (exact dates); LOCAL ONLY, gitignored
//   (any other)  -> public data (redacted; season only). This is the default,
//                   so `vite build` and `vite preview` are safe by default.
export default defineConfig(({ mode }) => {
  const tier = mode === 'dev' ? 'dev' : 'public';
  const dir = import.meta.dirname;
  return {
    root: dir,
    base: './',        // relative asset paths → deployable under any subpath
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      rollupOptions: {
        input: {
          viewer: resolve(dir, 'viewer.html'),
          density: resolve(dir, 'density.html'),
        },
      },
    },
    resolve: {
      alias: {
        '@trips': resolve(dir, `src/data/trips.${tier}.json`),
        '@alltrips': resolve(dir, `src/data/alltrips.${tier}.json`),
      },
    },
  };
});
