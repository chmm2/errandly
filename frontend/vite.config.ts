import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // Same-origin in dev: the browser talks to Vite, Vite forwards to FastAPI.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        ws: true, // proxy WebSocket upgrades too (/api/ws/…)
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
