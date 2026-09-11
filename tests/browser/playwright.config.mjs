import { defineConfig } from '@playwright/test';
import { results, metadata } from './site.mjs';

export default defineConfig({
  testDir: '.', testMatch: '*.spec.mjs',
  timeout: 180_000, expect: {timeout: 15_000},
  workers: 1, retries: 0, forbidOnly: Boolean(process.env.CI),
  metadata, outputDir: `${results}/artifacts`,
  reporter: [['list'], ['json', {outputFile: `${results}/browser-results.json`}]],
  use: {
    baseURL: 'http://127.0.0.1:8766', browserName: 'chromium',
    viewport: {width:1280, height:900}, serviceWorkers: 'block',
    trace: 'retain-on-failure', screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'node server.mjs', url: 'http://127.0.0.1:8766',
    reuseExistingServer: false, timeout: 15_000,
  },
});
