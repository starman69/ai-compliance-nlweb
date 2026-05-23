import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const API = process.env.API_URL || "http://localhost:8000";

// Proxy the NLWeb endpoints to the FastAPI app so the dev origin (:8088) and
// the API (:8000) share an origin in the browser.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 8088,
    host: true,
    proxy: {
      "/ask": API,
      "/mcp": API,
      "/corpus": API,
      "/health": API,
      "/docs": API,
      "/redoc": API,
      "/openapi.json": API,
    },
  },
});
