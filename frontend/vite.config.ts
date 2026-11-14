import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The browser only ever talks to this server, so the backend needs no CORS
// settings. Like the backend, the app stays on 127.0.0.1: there is no login yet.
const apiProxy = {
  "/api": {
    target: process.env.VITALA_API_TARGET ?? "http://127.0.0.1:8000",
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/api/, ""),
  },
};

export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", port: 5173, strictPort: true, proxy: apiProxy },
  preview: { host: "127.0.0.1", port: 5173, strictPort: true, proxy: apiProxy },
});
