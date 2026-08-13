import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development the frontend runs on :5173 and proxies /api to the
// FastAPI backend on :8000, so there are no CORS issues locally.
// In production, set VITE_API_BASE_URL to your backend URL at build time.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
