import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: "chart-vendor",
              test: /node_modules[\\/]recharts/,
            },
            {
              name: "solana-vendor",
              test: /node_modules[\\/]@solana[\\/]web3\.js/,
            },
            {
              name: "motion-vendor",
              test: /node_modules[\\/]framer-motion/,
            },
            {
              name: "icon-vendor",
              test: /node_modules[\\/]lucide-react/,
            },
          ],
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173
  }
});
