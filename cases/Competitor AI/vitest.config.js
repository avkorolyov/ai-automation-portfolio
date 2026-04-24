import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["frontend/**/*.test.js"],
    clearMocks: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary"],
      reportsDirectory: "tests/artifacts/coverage/frontend",
      include: ["frontend/app.js"],
      thresholds: {
        lines: 80,
        statements: 80,
        functions: 90,
        branches: 60
      }
    }
  }
});
