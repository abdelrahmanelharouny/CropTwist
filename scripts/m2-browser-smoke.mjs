import { chromium } from 'playwright'

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
      if (message.type() === 'error') failures.push(`${scenario.name}: console: ${message.text()}`)
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
    if (scenario.width < 500 && metadata.bodyWidth > metadata.viewportWidth + 2) {
      failures.push(`${scenario.name}: horizontal page overflow ${metadata.bodyWidth}px > ${metadata.viewportWidth}px`)
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
