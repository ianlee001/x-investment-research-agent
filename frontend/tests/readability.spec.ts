import { test, expect, type Page } from '@playwright/test'

async function auditText(page: Page) {
  return page.evaluate(() => {
    // Computed HeroUI tokens can be oklch()/color-mix(), not only rgb(). Let the browser
    // resolve those colors to sRGB before calculating WCAG relative luminance.
    const canvas = document.createElement('canvas')
    canvas.width = canvas.height = 1
    const context = canvas.getContext('2d', { willReadFrequently: true })!
    function rgba(value: string): number[] {
      context.clearRect(0, 0, 1, 1)
      context.fillStyle = value
      context.fillRect(0, 0, 1, 1)
      const [r, g, b, a] = context.getImageData(0, 0, 1, 1).data
      return [r, g, b, a / 255]
    }
    function over(top: number[], base: number[]) {
      return top.slice(0, 3).map((channel, i) => channel * top[3] + base[i] * (1 - top[3])).concat(1)
    }
    function background(element: Element | null): number[] {
      if (!element) return [255, 255, 255, 1]
      const color = rgba(getComputedStyle(element).backgroundColor)
      return color[3] === 1 ? color : over(color, background(element.parentElement))
    }
    function luminance(color: number[]) {
      const values = color.slice(0, 3).map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
      return values[0] * .2126 + values[1] * .7152 + values[2] * .0722
    }
    const problems: object[] = []
    let count = 0
    for (const element of document.querySelectorAll('body *')) {
      if (!(element instanceof HTMLElement)) continue
      const text = Array.from(element.childNodes).filter(node => node.nodeType === Node.TEXT_NODE)
        .map(node => node.textContent?.trim()).filter(Boolean).join(' ')
      const field = element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement
      if (!text && !field) continue
      const rect = element.getBoundingClientRect(), style = getComputedStyle(element)
      if (!rect.width || !rect.height || rect.right <= 0 || rect.left >= window.innerWidth || style.visibility !== 'visible') continue
      if (element.closest('script, style, option')) continue
      // React Aria's screen reader only labels have a 1px clipped box.
      if (style.clipPath === 'inset(50%)' || style.clip === 'rect(0px, 0px, 0px, 0px)') continue
      count++
      const size = parseFloat(style.fontSize), bg = background(element)
      const fg = over(rgba(style.color), bg)
      const l1 = luminance(fg), l2 = luminance(bg)
      const contrast = (Math.max(l1, l2) + .05) / (Math.min(l1, l2) + .05)
      if (size < 14 || contrast < 4.5) problems.push({ text: text.slice(0, 60), tag: element.tagName,
        class: element.className, size, contrast: Number(contrast.toFixed(3)), color: style.color })
      if (field && !(element instanceof HTMLSelectElement) && element.placeholder) {
        const placeholder = getComputedStyle(element, '::placeholder')
        const p1 = luminance(over(rgba(placeholder.color), bg))
        const ratio = (Math.max(p1, l2) + .05) / (Math.min(p1, l2) + .05)
        if (ratio < 4.5) problems.push({ placeholder: element.placeholder, contrast: ratio })
      }
    }
    return { count, problems, overflow: document.documentElement.scrollWidth > window.innerWidth + 1 }
  })
}

async function expectReadable(page: Page) {
  const audit = await auditText(page)
  expect(audit.count).toBeGreaterThanOrEqual(8)
  expect(audit.problems, JSON.stringify(audit.problems, null, 2)).toEqual([])
  expect(audit.overflow, 'Page must not overflow horizontally').toBeFalsy()
}

for (const width of [1440, 390]) {
  test(`${width}px: all seven pages use readable text and contrast`, async ({ page }) => {
    test.setTimeout(60000)
    await page.route('**/api/v1/market/**', route => route.fulfill({ json: { available: false, reason: 'UI test: external requests disabled' } }))
    await page.setViewportSize({ width, height: 1000 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    for (const route of ['/', '/watchlist', '/intelligence', '/research', '/chat', '/approvals', '/settings']) {
      await page.goto(route)
      await page.waitForLoadState('networkidle')
      await expectReadable(page)
      if (route === '/intelligence') {
        if (await page.locator('.post-text').count()) await expect(page.locator('.post-text').first()).toHaveCSS('font-size', '16px')
      }
      await page.screenshot({ path: `../.runtime/readability-${width}-${route.slice(1) || 'dashboard'}.png`, fullPage: true, animations: 'disabled' })
    }
    await page.goto('/research')
    await page.getByRole('textbox', { name: '研究问题' }).fill('检查输入框可读性')
    await expectReadable(page)
  })
}

test('saved report and existing chat remain readable at desktop and phone widths', async ({ page, request }) => {
  const runs = await (await request.get('/api/v1/research/runs')).json()
  const report = runs.find((run: any) => run.status === 'completed' && run.coverage?.sources > 0)
  const threads = await (await request.get('/api/v1/chat/threads')).json()
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    if (report) {
      await page.goto(`/research?run=${report.id}`)
      await expect(page.getByRole('heading', { name: '信息来源', exact: true })).toBeVisible()
      await expectReadable(page)
      await page.screenshot({ path: `../.runtime/readability-${width}-report.png`, fullPage: true, animations: 'disabled' })
    }
    if (threads.length) {
      await page.goto(`/chat?thread=${threads[0].id}`)
      await page.waitForLoadState('networkidle')
      await expectReadable(page)
    }
  }
})

test('populated stock and pending approval dialogs: isolated UI fixtures', async ({ page }) => {
  // Fixtures cover otherwise-empty UI states without changing personal data or consuming API quotas.
  await page.route('**/api/v1/watchlist', route => route.fulfill({ json: [{ ticker: 'NVDA', company_name: 'NVIDIA', notes: '测试备注' }] }))
  await page.route('**/api/v1/watchlist/NVDA', route => route.fulfill({ json: { ticker: 'NVDA', thesis: '测试研究观点', reports: [] } }))
  await page.route('**/api/v1/market/NVDA/*', route => route.fulfill({ json: { available: true, data:
    route.request().url().endsWith('/history') ? { bars: [{ t: 1791158400000, c: 100 }, { t: 1791244800000, c: 103 }] }
    : route.request().url().endsWith('/profile') ? { name: 'NVIDIA', primary_exchange: 'XNAS', market_cap: 1000000000 }
    : { close: 103, volume: 1000000, high: 104, low: 100, as_of: '2026-10-07T20:00:00Z', intraday_change_percent: 3 },
  } }))
  await page.route('**/api/v1/approvals?status=pending', route => route.fulfill({ json: [{ id: 'ui-fixture', tool_name: 'add_to_watchlist',
    args: { ticker: 'NVDA', company_name: 'NVIDIA', notes: '测试审批备注' }, status: 'pending', execution_status: 'not_started',
    created_at: '2026-10-08T00:00:00Z', expires_at: '2026-10-11T00:00:00Z' }] }))
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto('/watchlist')
    await expect(page.getByRole('heading', { name: 'NVIDIA' })).toBeVisible()
    await expectReadable(page)
    await page.screenshot({ path: `../.runtime/readability-${width}-stock.png`, fullPage: true, animations: 'disabled' })
    await page.getByRole('button', { name: '添加标的', exact: true }).click()
    await expectReadable(page)
    await page.getByRole('button', { name: '关闭', exact: true }).click()
    await page.goto('/approvals')
    await page.getByRole('button', { name: '编辑后批准', exact: true }).click()
    await expectReadable(page)
    await page.screenshot({ path: `../.runtime/readability-${width}-approval.png`, fullPage: true, animations: 'disabled' })
  }
})
