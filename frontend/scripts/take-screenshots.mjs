// Captures the README screenshots: npm run screenshots (the app must be running on http://127.0.0.1:8000)
import { chromium } from '@playwright/test'
const out = new URL('../../docs/screenshots/', import.meta.url).pathname.replace(/^\/([A-Z]:)/, '$1')
const base = 'http://127.0.0.1:8000'
const browser = await chromium.launch({
  args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
})
const ctx = await browser.newContext({
  viewport: { width: 1360, height: 900 },
  permissions: ['camera'],
  colorScheme: process.argv[2] === 'dark' ? 'dark' : 'light',
})
const post = (p) => fetch(base + p, { method: 'POST' })
await post('/api/demo/stop')
await post('/api/reset')
await fetch(base + '/api/profile', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ user_name: 'Demo user', caregiver_name: 'Demo caregiver' }),
})
const page = await ctx.newPage()
await page.goto(base + '/')
await page.waitForSelector('text=LIVE', { timeout: 45000 })
await page.waitForTimeout(1500)
await page.screenshot({ path: out + 'companion.png' })
await post('/api/demo/fall_no_response')
await page.waitForSelector('.countdown', { timeout: 15000 })
await page.waitForTimeout(1200)
await page.screenshot({ path: out + 'companion-checkin.png' })
const cg = await ctx.newPage()
await cg.goto(base + '/caregiver')
await cg.waitForSelector('.banner.escalated', { timeout: 40000 })
await cg.waitForTimeout(2500)
await cg.screenshot({ path: out + 'caregiver-alert.png', fullPage: true })
await page.bringToFront()
await page.waitForTimeout(500)
await page.screenshot({ path: out + 'companion-alert.png' })
const rp = await ctx.newPage()
await rp.goto(base + '/report')
await rp.waitForSelector('[data-testid=report]')
await rp.waitForTimeout(800)
await rp.screenshot({ path: out + 'report.png', fullPage: true })
const mob = await browser.newContext({
  viewport: { width: 390, height: 844 },
  permissions: ['camera'],
  isMobile: true,
})
const mp = await mob.newPage()
await mp.goto(base + '/')
await mp.waitForTimeout(4000)
await mp.screenshot({ path: out + 'mobile.png', fullPage: true })
await post('/api/demo/stop')
await browser.close()
console.log('saved to', out)
