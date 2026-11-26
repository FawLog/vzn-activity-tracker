import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

const buildSha = /^[0-9a-f]{40}$/.test(process.env.GITHUB_SHA ?? "") ? process.env.GITHUB_SHA! : null;

export default defineConfig({
  define: { __VZN_BUILD_SHA__: JSON.stringify(buildSha) },
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8088",
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8088",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    exclude: [...configDefaults.exclude, "e2e/**"],
    setupFiles: "./src/test-setup.ts",
  },
});
