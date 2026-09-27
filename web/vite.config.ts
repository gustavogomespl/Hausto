/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // API local: uv run uvicorn main:app --reload --port 8080
  server: { proxy: { '/v1': 'http://localhost:8080' } },
  build: { outDir: 'dist' },
  test: { environment: 'jsdom', globals: true },
});
