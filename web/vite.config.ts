import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      // In dev (docker without nginx), talk straight to the local services.
      // websockify serves noVNC at the root (:6080/), so strip the /novnc prefix.
      "/novnc": {
        target: "http://127.0.0.1:6080",
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/novnc/, "") || "/",
      },
      "/websockify": { target: "ws://127.0.0.1:6080", changeOrigin: true, ws: true },
      "/api": { target: "http://127.0.0.1:7071", changeOrigin: true },
    },
  },
  preview: { port: 5174 },
});
