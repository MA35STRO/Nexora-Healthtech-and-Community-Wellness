import { expect, test } from '@playwright/test'

test.beforeEach(async ({ request }) => {
  await request.post('/api/demo/stop')
  await request.post('/api/reset')
})

test('camera starts automatically and streams pose landmarks to the hub', async ({ page, request }) => {
  await page.goto('/')
  await expect(page.getByTestId('cam-status')).toHaveText(/LIVE/, { timeout: 45_000 })
  // the hub sees browser frames (the fake camera shows no person, so "not in view" is expected)
  await expect
    .poll(async () => (await (await request.get('/api/state')).json()).camera.browser_fps, {
      timeout: 10_000,
    })
    .toBeGreaterThan(0)
  await expect(page.locator('.cam-overlay')).toContainText(/no person in view|standing|sitting|lying|upright/)
})

test('fall demo → check-in on companion → escalation card on caregiver → resolve', async ({
  page,
  context,
}) => {
  await page.goto('/')
  const caregiver = await context.newPage()
  await caregiver.goto('/caregiver')
  await expect(caregiver.getByTestId('status-banner')).toContainText('All clear')

  await caregiver.getByTestId('demo-fall').click()
  await expect(page.locator('.bubble')).toContainText(/fall/i, { timeout: 15_000 })
  await expect(page.locator('.countdown')).toBeVisible()
  await expect(caregiver.getByTestId('status-banner')).toContainText('Checking in')

  await page.getByRole('button', { name: 'Help', exact: true }).click()
  await expect(caregiver.getByTestId('status-banner')).toContainText('ALERT', { timeout: 5_000 })
  const card = caregiver.getByTestId('active-incident')
  await expect(card).toContainText('Possible fall')
  await expect(card).toContainText('Hip position dropped')

  await card.getByRole('button', { name: /Acknowledge/ }).click()
  await expect(card).toContainText('acknowledged')
  await card.getByPlaceholder('Resolution note').fill('Called her, she is fine')
  await card.getByRole('button', { name: 'Resolve' }).click()
  await expect(caregiver.getByTestId('status-banner')).toContainText('All clear')
})

test('user says they are okay → attention, not an emergency', async ({ page, request }) => {
  await page.goto('/')
  await request.post('/api/demo/fall')
  await expect(page.locator('.bubble')).toContainText(/fall/i, { timeout: 15_000 })
  await page.getByRole('button', { name: "I'm okay" }).click()
  await expect.poll(async () => (await (await request.get('/api/state')).json()).state).toBe('attention')
})

test('medicine reminder can be confirmed', async ({ page, request }) => {
  await page.goto('/')
  await request.post('/api/demo/med_missed') // creates a dose due now
  await expect(page.locator('.dose').filter({ hasText: 'Due now' }).first()).toBeVisible({ timeout: 10_000 })
  await page.getByRole('button', { name: 'I took my medicine' }).click()
  await expect(page.locator('.msg.assistant').last()).toContainText(/recorded/i)
})

test('offline health question gets an answer', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Message Kawan').fill('What is metformin?')
  await page.getByLabel('Message Kawan').press('Enter')
  await expect(page.locator('.msg.assistant').last()).toContainText(/blood sugar/i, { timeout: 15_000 })
})

test('red-flag symptom in Malay escalates immediately', async ({ page, request }) => {
  await page.goto('/')
  await page.getByLabel('Message Kawan').fill('Saya sakit dada')
  await page.getByLabel('Message Kawan').press('Enter')
  await expect(page.locator('.msg.assistant').last()).toContainText('999')
  await expect.poll(async () => (await (await request.get('/api/state')).json()).state).toBe('escalated')
})

test('daily check-in gives triage guidance', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Daily check-in' }).first().click()
  await page.getByRole('button', { name: 'mood 4 of 5' }).click()
  await page.getByRole('button', { name: 'Cough' }).click()
  await page.getByRole('button', { name: 'Submit check-in' }).click()
  await expect(page.locator('.triage')).toContainText('Keep an eye on it')
})

test('report renders and caregiver charts load', async ({ page, request }) => {
  await request.post('/api/meds', { data: { name: 'Metformin', dose: '500 mg', times: ['08:00'] } })
  await page.goto('/report')
  await expect(page.getByTestId('report')).toContainText('Medication adherence')
  await expect(page.getByTestId('report')).toContainText('Metformin')
  await page.goto('/caregiver')
  await expect(page.locator('.heat .cell').first()).toBeVisible()
})

test('fresh install shows no invented data and a welcome card', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByTestId('welcome')).toBeVisible()
  await expect(page.getByText('No readings yet')).toBeVisible()
  await expect(page.getByText(/No medicines scheduled/)).toBeVisible()
  await page.goto('/caregiver')
  await expect(page.getByText('No doses recorded yet')).toBeVisible()
  await expect(page.getByText('No daily check-ins yet')).toBeVisible()
})

test('caregiver saves profile; a real reading appears on the companion', async ({ page }) => {
  await page.goto('/caregiver#setup')
  await page.getByLabel('Name of person at home').fill('Aminah')
  await page.getByLabel('Caregiver name').fill('Farid')
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.getByTestId('status-banner')).toContainText('Aminah')
  await page.goto('/')
  await expect(page.locator('.bubble')).toContainText('Aminah') // live data has loaded
  await expect(page.getByTestId('welcome')).toHaveCount(0)
  await page.getByLabel('BP top (systolic)').fill('128')
  await page.getByLabel('BP bottom (diastolic)').fill('82')
  await page.getByRole('button', { name: 'Save reading' }).click()
  await expect(page.getByText('Reading saved.')).toBeVisible()
  await expect(page.locator('.vital').filter({ hasText: 'BLOOD PRESSURE' })).toContainText('128/82', {
    timeout: 15_000,
  })
  await expect(page.getByText(/entered by you/)).toBeVisible()
})

test('health answers show their source', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Message Kawan').fill('What is gliclazide?')
  await page.getByLabel('Message Kawan').press('Enter')
  await expect(page.locator('.msg.assistant').last().locator('.refs')).toContainText('NHS', {
    timeout: 15_000,
  })
})

test('how-to-use guide is reachable and bilingual', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: 'How to use' }).first().click()
  await expect(page.getByTestId('guide')).toContainText('Set up in 3 minutes')
  await page.getByRole('button', { name: 'BM' }).click()
  await expect(page.getByTestId('guide')).toContainText('Cara menggunakan Kawan')
})
