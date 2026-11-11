// High-resolution card screenshots for the A1 poster (poster/assets/screens).
//   node scripts/take-poster-screenshots.mjs http://127.0.0.1:8765
// Run the backend with KAWAN_DB=:memory: SEED_DEMO_HISTORY=1 VITALS_SIM=1 so charts have
// (clearly labelled SIMULATED) data. The camera panel is skipped: it would show the fake webcam.
import { mkdirSync } from 'node:fs'
import { chromium } from '@playwright/test'

const base = process.argv[2] ?? 'http://127.0.0.1:8000'
const out = new URL('../../poster/assets/screens/', import.meta.url).pathname.replace(/^\/([A-Z]:)/, '$1')
mkdirSync(out, { recursive: true })
const SCALE = 2.5 // 1360 css px × 2.5 = 3400 px: ~300 dpi at 29 cm wide on the poster

const post = (p, body) =>
  fetch(base + p, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
const wait = (ms) => new Promise((r) => setTimeout(r, ms))

/** Screenshot the union of several elements (plus padding), so a tile can hold e.g. card + buttons. */
async function shotUnion(page, locators, file, pad = 14) {
  const boxes = []
  for (const l of locators) boxes.push(await l.boundingBox())
  const x = Math.min(...boxes.map((b) => b.x)) - pad
  const y = Math.min(...boxes.map((b) => b.y)) - pad
  const r = Math.max(...boxes.map((b) => b.x + b.width)) + pad
  const btm = Math.max(...boxes.map((b) => b.y + b.height)) + pad
  await page.screenshot({ path: out + file, clip: { x, y, width: r - x, height: btm - y } })
  console.log('saved', file)
}
const card = (page, heading) =>
  page.locator('section.card', { has: page.locator(`h2:text-is("${heading}")`) })

const browser = await chromium.launch({
  args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
})
const ctx = await browser.newContext({
  viewport: { width: 1360, height: 1000 },
  deviceScaleFactor: SCALE,
  permissions: ['camera'],
  colorScheme: 'light',
})

await post('/api/demo/stop')
await post('/api/profile', { user_name: 'Demo user', caregiver_name: 'Demo caregiver' })

// 1. Companion: a health question answered from the cited library
const page = await ctx.newPage()
await page.goto(base + '/')
await page.waitForSelector('text=LIVE', { timeout: 45000 })
const chatCard = card(page, 'Kawan')
await chatCard.locator('.composer input, .composer textarea').fill('What is ibuprofen?')
await chatCard.locator('.composer button').click()
await page.waitForSelector('.msg .refs', { timeout: 20000 })
await wait(800)
await shotUnion(page, [chatCard], 'answer-with-source.png')

// 2. Companion: check-in after a (simulated) fall — mascot, question, countdown, big buttons
await post('/api/demo/fall_no_response')
await page.waitForSelector('.countdown', { timeout: 20000 })
await wait(1500)
const hero = page.locator('section.card', { has: page.locator('.hero') })
await shotUnion(page, [hero, page.locator('section.big-actions')], 'companion-checkin.png')

// 3. Caregiver: escalated alert with reasons, and the timeline
const cg = await ctx.newPage()
await cg.goto(base + '/caregiver')
await cg.waitForSelector('.banner.escalated', { timeout: 40000 })
await wait(2500)
await shotUnion(
  cg,
  [cg.locator('[data-testid=status-banner]'), card(cg, 'Active alert')],
  'caregiver-alert.png',
)
await shotUnion(cg, [card(cg, 'Live timeline')], 'timeline.png')
await shotUnion(cg, [card(cg, 'Vital signs (live)')], 'vitals.png')
await shotUnion(cg, [card(cg, 'Medication adherence')], 'adherence.png')
await shotUnion(cg, [card(cg, 'Daily check-ins')], 'checkins.png')
await shotUnion(cg, [card(cg, 'Activity pattern (active minutes / hour)')], 'activity.png')
await cg.screenshot({ path: out + 'caregiver-full.png', fullPage: true })
console.log('saved caregiver-full.png')

// 4. Companion: red-flag symptom in Bahasa Melayu → call 999 + caregiver alerted
await post('/api/demo/stop')
await post('/api/reset')
await post('/api/profile', { user_name: 'Demo user', caregiver_name: 'Demo caregiver' })
await page.bringToFront()
await page.reload()
await page.waitForSelector('text=LIVE', { timeout: 45000 })
await chatCard.locator('.composer input, .composer textarea').fill('Saya sakit dada dan sesak nafas')
await chatCard.locator('.composer button').click()
await wait(2500)
await shotUnion(page, [chatCard], 'red-flag-bm.png')

// 5. Doctor report (top part)
const rp = await ctx.newPage()
await rp.goto(base + '/report')
await rp.waitForSelector('[data-testid=report]')
await wait(1000)
await rp.screenshot({ path: out + 'report.png', clip: { x: 0, y: 0, width: 1360, height: 1000 } })
console.log('saved report.png')

// 6. Phone view
const mob = await browser.newContext({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 3,
  permissions: ['camera'],
  isMobile: true,
})
const mp = await mob.newPage()
await mp.goto(base + '/')
await mp.waitForTimeout(4000)
await mp.screenshot({ path: out + 'mobile.png' })
console.log('saved mobile.png')

await post('/api/demo/stop')
await browser.close()
