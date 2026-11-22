import { createRequire } from 'node:module'

const packageRoot = process.env.PLAYWRIGHT_PACKAGE_ROOT
if (!packageRoot) throw new Error('PLAYWRIGHT_PACKAGE_ROOT must point to the isolated Playwright install')
const require = createRequire(`${packageRoot}/package.json`)
const { chromium } = require('playwright')

const baseURL = process.env.BASE_URL || 'http://127.0.0.1:3000'
const failures = []
const browser = await chromium.launch({ headless: true })

try {
  for (const scenario of [
    { name: 'desktop-en', width: 1440, height: 900, locale: 'en', dir: 'ltr' },
    { name: 'mobile-ar', width: 390, height: 844, locale: 'ar', dir: 'rtl' },
  ]) {
    const context = await browser.newContext({
      viewport: { width: scenario.width, height: scenario.height },
      reducedMotion: 'reduce',
      locale: scenario.locale === 'ar' ? 'ar-EG' : 'en-US',
    })
    await context.addCookies([{
      name: 'NEXT_LOCALE',
      value: scenario.locale,
      domain: '127.0.0.1',
      path: '/',
      sameSite: 'Lax',
    }])
    const page = await context.newPage()
    page.on('pageerror', error => failures.push(`${scenario.name}: pageerror: ${error.message}`))
    page.on('console', message => {
      if (message.type() === 'error' && !message.text().includes('401 (Unauthorized)')) failures.push(`${scenario.name}: console: ${message.text()}`)
    })
    await page.route('**/api/v1/**', route => route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Unauthenticated browser smoke fixture' }),
    }))
    await page.route('**/api/auth/**', route => route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ authenticated: false }),
    }))

    const response = await page.goto(baseURL, { waitUntil: 'networkidle', timeout: 60000 })
    if (!response || response.status() !== 200) failures.push(`${scenario.name}: homepage HTTP status ${response?.status() ?? 'no response'}`)
    const metadata = await page.locator('html').evaluate(el => ({
      title: document.title,
      lang: el.getAttribute('lang'),
      dir: el.getAttribute('dir'),
      bodyText: document.body.innerText.trim(),
      bodyWidth: document.body.scrollWidth,
      viewportWidth: window.innerWidth,
    }))
    if (!metadata.title.includes('CropTwist')) failures.push(`${scenario.name}: unexpected document title: ${metadata.title}`)
    if (metadata.lang !== scenario.locale) failures.push(`${scenario.name}: expected lang ${scenario.locale}, got ${metadata.lang}`)
    if (metadata.dir !== scenario.dir) failures.push(`${scenario.name}: expected dir ${scenario.dir}, got ${metadata.dir}`)
    if (metadata.bodyText.length < 20) failures.push(`${scenario.name}: workspace rendered no meaningful content`)
    const emailInput = page.locator('#login-email')
    if (!(await emailInput.isVisible().catch(() => false))) failures.push(`${scenario.name}: guest sign-in form did not render`)
    const tabs = page.getByRole('tab')
    if (await tabs.count() < 2) failures.push(`${scenario.name}: sign-in/register tabs are missing`)
    else {
      await tabs.nth(1).click()
      if (!(await page.locator('#reg-name').isVisible().catch(() => false))) {
        failures.push(`${scenario.name}: registration form did not render`)
      }
      await tabs.nth(0).click()
      if (!(await emailInput.isVisible().catch(() => false))) failures.push(`${scenario.name}: sign-in tab did not restore the login form`)
    }
    if (scenario.width < 500 && metadata.bodyWidth > metadata.viewportWidth + 2) {
      failures.push(`${scenario.name}: horizontal page overflow ${metadata.bodyWidth}px > ${metadata.viewportWidth}px`)
    }
    // Complete a real demo authentication against the clean-room API, then
    // assert the authenticated workspace shell and page heading render.
    await page.getByRole('button').last().click()
    await page.locator('.ct-topbar').waitFor({ state: 'visible', timeout: 30000 })
    const authenticatedHeading = await page.locator('h1.sr-only').innerText()
    if (!authenticatedHeading.trim()) failures.push(`${scenario.name}: authenticated workspace heading is empty`)
    const authenticatedWidth = await page.evaluate(() => document.body.scrollWidth)
    if (scenario.width < 500 && authenticatedWidth > scenario.width + 2) {
      failures.push(`${scenario.name}: authenticated workspace overflows horizontally (${authenticatedWidth}px)`)
    }
    await page.screenshot({ path: `m2-${scenario.name}.png`, fullPage: true })
    console.log(`[browser-smoke] ${scenario.name}: ${JSON.stringify(metadata)}`)
    await context.close()
  }
} finally {
  await browser.close()
}

if (failures.length) {
  console.error(failures.join('\n'))
  process.exitCode = 1
} else {
  console.log('[browser-smoke] all desktop/RTL viewport checks passed')
}
