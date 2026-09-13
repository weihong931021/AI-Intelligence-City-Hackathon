import path from "node:path";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
    dedupe: ["react", "react-dom", "@assistant-ui/react"],
  },
  optimizeDeps: {
    include: ["remark-gfm"],
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
