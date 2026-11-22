import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the Vite server proxies /api to FastAPI, so the session cookie stays same-origin.
export default defineConfig({
  plugins: [react()],
  // Built files go to /static so they never clash with app routes such as /assets/12.
  build: { assetsDir: "static" },
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } },
  },
});
