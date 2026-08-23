import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/watch": "http://127.0.0.1:8000",
      "/ask": "http://127.0.0.1:8000",
      "/articles": "http://127.0.0.1:8000",
      "/content": "http://127.0.0.1:8000",
      "/input-assets": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
});
