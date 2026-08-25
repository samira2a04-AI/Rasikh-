import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      // Forward all /auth, /requests, /counts, /drafts, /audit, /obligations,
      // /reviews, /approvals, /history, /health requests to the FastAPI backend.
      "/auth": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/requests": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/counts": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/drafts": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/audit": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/obligations": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/reviews": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/approvals": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/history": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
