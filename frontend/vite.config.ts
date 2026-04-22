import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "chart-vendor": ["recharts"],
          "solana-vendor": ["@solana/web3.js"],
          "motion-vendor": ["framer-motion"],
          "icon-vendor": ["lucide-react"],
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173
  }
});
