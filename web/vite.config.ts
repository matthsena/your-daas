import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      // No dev (docker sem o nginx), fala direto com os serviços locais.
      // websockify serve o noVNC na raiz (:6080/), então tira o prefixo /novnc.
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
