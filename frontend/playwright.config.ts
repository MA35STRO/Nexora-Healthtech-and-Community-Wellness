import { defineConfig } from '@playwright/test'

// E2E against the real backend serving the built dashboard. Chromium gets a FAKE webcam
// (a synthetic test pattern), so camera auto-start and the on-device model can be tested headless.
const py = process.platform === 'win32' ? String.raw`.venv\Scripts\python.exe` : '.venv/bin/python'

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:8000',
    permissions: ['camera', 'microphone'],
    launchOptions: {
      args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
    },
  },
  webServer: {
    command: `${py} -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
    cwd: '../backend',
    url: 'http://127.0.0.1:8000/api/health',
    reuseExistingServer: true,
    env: { BAYMAX_DB: ':memory:', CHECKIN_TIMEOUT_S: '20' },
  },
})
