/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the browser talks to Vite, which proxies /api to the Django dev server.
// In Docker, nginx does the same proxying. Either way the browser only sees same-origin URLs.
const backend = process.env.VITE_DEV_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": { target: backend, changeOrigin: true, timeout: 600000 } } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
