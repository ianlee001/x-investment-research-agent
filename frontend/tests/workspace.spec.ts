import { test, expect } from '@playwright/test'

test('workspace navigation, real report and mobile layout', async ({ page }) => {
  await page.route('**/api/v1/market/**', route => route.fulfill({ json: { available: false, reason: 'UI test: external requests disabled' } }))
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '研究总览', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '发起研究', exact: true })).toBeVisible()
  await page.screenshot({ path: '../.runtime/dashboard-desktop.png', fullPage: true, animations: 'disabled' })
  for (const [url, heading] of [['/watchlist', '关注列表'], ['/intelligence', 'X 情报'], ['/research', '深度研究'], ['/approvals', '待办审批'], ['/settings', '偏好设置']]) {
    await page.goto(url)
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
  }
  await page.goto('/chat')
  await expect(page.getByRole('textbox', { name: '对话消息' })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await expect(page.getByRole('navigation', { name: '主导航' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'X 情报', exact: true })).toBeVisible()
  await page.getByRole('link', { name: 'X 情报', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'X 情报', exact: true })).toBeVisible()
  await page.screenshot({ path: '../.runtime/intelligence-mobile.png', fullPage: true, animations: 'disabled' })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy()
  await page.goto('/chat')
  await expect(page.getByRole('button', { name: /选择研究对话/ })).toBeVisible()
  await expect(page.getByRole('button', { name: '新对话', exact: true })).toBeVisible()
  expect(errors).toEqual([])
})

test('completed report displays saved citations and claims', async ({ page, request }) => {
  const response = await request.get('/api/v1/research/runs')
  const runs = await response.json()
  const run = runs.find((r: any) => r.status === 'completed' && r.coverage?.sources > 0)
  test.skip(!run, 'Generate a real report first with scripts/live_smoke.py start')
  await page.goto(`/research?run=${run.id}`)
  await expect(page.getByRole('heading', { name: '关键断言', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: '信息来源', exact: true })).toBeVisible()
  expect(await page.locator('.source-link').count()).toBeGreaterThan(0)
  await page.screenshot({ path: '../.runtime/research-desktop.png', fullPage: true, animations: 'disabled' })
})
