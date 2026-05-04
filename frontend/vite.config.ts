import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendPort = process.env.BACKEND_PORT || "8080";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": `http://localhost:${backendPort}`,
      "/generated": `http://localhost:${backendPort}`,
      "/files": `http://localhost:${backendPort}`,
    },
  },
  build: {
    outDir: "../static",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules/")) return;
          if (
            id.includes("node_modules/react-markdown") ||
            id.includes("node_modules/rehype") ||
            id.includes("node_modules/remark") ||
            id.includes("node_modules/lowlight") ||
            id.includes("node_modules/highlight.js") ||
            id.includes("node_modules/unified") ||
            id.includes("node_modules/hast") ||
            id.includes("node_modules/mdast") ||
            id.includes("node_modules/micromark") ||
            id.includes("node_modules/vfile") ||
            id.includes("node_modules/unist")
          ) {
            return "vendor-markdown";
          }
          return "vendor";
        },
      },
    },
  },
});
