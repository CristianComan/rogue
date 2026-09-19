import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    // maplibre-gl loads its worker script by resolving a relative URL
    // against its own import.meta.url at runtime (see
    // node_modules/maplibre-gl/dist/maplibre-gl-dev.mjs's defaultWorkerUrl),
    // not via a static import Vite's dependency scanner can see — so the
    // pre-bundled copy under node_modules/.vite/deps/ never gets a sibling
    // maplibre-gl-worker.mjs written next to it, and that relative request
    // 404s (observed directly: "WebGL context was lost" + "Loading Worker
    // ... was blocked because of a disallowed MIME type" from the 404's
    // empty Content-Type). Excluding it here serves maplibre-gl straight
    // from its own package directory instead, where the real worker file
    // sits right next to it and resolves correctly.
    exclude: ["maplibre-gl"],
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    exclude: ["**/node_modules/**", "**/e2e/**"],
  },
});
