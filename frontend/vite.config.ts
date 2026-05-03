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
  },
});
