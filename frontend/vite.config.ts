import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Deployed to GitHub Pages at https://dani-devlop.github.io/shortly-url/
export default defineConfig({
  base: "/shortly-url/",
  plugins: [react(), tailwindcss()],
  server: { port: 5173 },
  preview: { port: 4173 },
  build: { sourcemap: false, chunkSizeWarningLimit: 900 },
});
