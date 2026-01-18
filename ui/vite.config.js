import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: path.resolve(__dirname, "dist"), // will create ui/dist
    assetsDir: "assets",                      // will create ui/dist/assets
    sourcemap: true,                          // creates .map files like before
    rollupOptions: {
      // point at the HTML entry that mounts your widget
      input: path.resolve(__dirname, "src/my-widgets/index.html"),
    },
  },
  esbuild: {
    jsx: "automatic",
    target: "es2022",
  },
});
