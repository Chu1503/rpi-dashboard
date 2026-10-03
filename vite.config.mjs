import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  root: resolve(projectRoot, "frontend"),
  plugins: [react()],
  build: {
    outDir: resolve(projectRoot, "static", "app"),
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      input: resolve(projectRoot, "frontend", "src", "main.jsx"),
      output: {
        entryFileNames: "dashboard.js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: (asset) =>
          asset.name?.endsWith(".css") ? "style.css" : "assets/[name]-[hash][extname]"
      }
    }
  }
});
