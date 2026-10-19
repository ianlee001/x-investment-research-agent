import { test, expect, type Page } from '@playwright/test'

async function mockWorkspace(page: Page) {
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    let data: unknown = []
    if (path.endsWith('/health')) data = { worker: 'online' }
    if (path.endsWith('/dashboard')) data = { counts: { watchlist: 1, posts: 12, reports: 3, pending_approvals: 0 }, recent_runs: [] }
    if (path.endsWith('/watchlist')) data = [{ ticker: 'NVDA', company_name: 'NVIDIA' }]
    if (path.endsWith('/watchlist/NVDA')) data = { thesis: '已保存的研究观点', reports: [] }
    if (path.endsWith('/market/NVDA/history')) data = { available: true, data: { bars: Array.from({ length: 8 }, (_, i) => ({ t: Date.UTC(2026, 9, i + 1), c: 100 + i })) } }
    if (path.endsWith('/market/NVDA/profile')) data = { available: true, data: { name: 'NVIDIA', primary_exchange: 'XNAS' } }
    if (path.endsWith('/market/NVDA/quote')) data = { available: true, data: { close: 107, high: 109, low: 105, volume: 123456, intraday_change_percent: 2, as_of: '2026-10-08T20:00:00Z' } }
    if (path.endsWith('/settings')) data = { providers: { massive: true }, provider_health: {}, limits: { model_calls: 10 },
      preferences: { sync_enabled: false, sync_interval_minutes: 60, daily_brief_enabled: false, daily_brief_hour: 8, timezone: 'Asia/Shanghai', auto_research_enabled: false, auto_research_max_per_day: 0 } }
    return route.fulfill({ json: data })
  })
}

test('overview research input carries the question into the real research form', async ({ page }) => {
  await mockWorkspace(page)
  await page.goto('/')
  await page.getByRole('searchbox', { name: '快速研究问题' }).fill('半导体板块近期的风险因素')
  await page.getByRole('button', { name: '开始研究', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '研究问题', exact: true })).toHaveValue('半导体板块近期的风险因素')
  await expect(page.getByRole('button', { name: '开始研究', exact: true })).toBeEnabled()
})

for (const width of [1920, 1440, 390]) {
  test(`${width}px: new research form fills its panel without horizontal overflow`, async ({ page }) => {
    await mockWorkspace(page)
    await page.setViewportSize({ width, height: 1000 })
    await page.goto('/research')
    const question = page.getByRole('textbox', { name: '研究问题', exact: true })
    await expect(question).toBeVisible()
    const panel = (await page.locator('.research-main').boundingBox())!
    const form = (await question.boundingBox())!
    expect(form.x - panel.x).toBeGreaterThanOrEqual(15)
    expect(form.x - panel.x).toBeLessThanOrEqual(40)
    expect(panel.x + panel.width - form.x - form.width).toBeLessThanOrEqual(40)
    expect(form.width).toBeGreaterThan(panel.width - 82)
    const tickerLabel = page.locator('.ticker-input > .label')
    expect((await tickerLabel.boundingBox())!.height).toBeLessThan(30)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    await page.screenshot({ path: `../.runtime/research-form-layout-${width}.png`, fullPage: true, animations: 'disabled' })
  })
}

for (const width of [1440, 390]) {
  test(`${width}px: HeroUI dialog traps focus and restores the trigger after Escape`, async ({ page }) => {
    await mockWorkspace(page)
    await page.setViewportSize({ width, height: 1000 })
    await page.goto('/watchlist')
    const trigger = page.getByRole('button', { name: '添加标的', exact: true })
    await trigger.click()
    const dialog = page.getByRole('dialog', { name: '添加关注标的' })
    await expect(dialog).toBeVisible()
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press('Tab')
      expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBeTruthy()
    }
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(trigger).toBeFocused()
  })

  test(`${width}px: Tremor displays actual chart values in its hover tooltip`, async ({ page }) => {
    await mockWorkspace(page)
    await page.setViewportSize({ width, height: 1000 })
    await page.goto('/watchlist')
    await expect(page.getByRole('heading', { name: 'NVIDIA' })).toBeVisible()
    if (width === 390) expect((await page.getByRole('heading', { name: 'NVIDIA' }).boundingBox())!.height).toBeLessThan(35)
    const chart = page.locator('.market-area-chart')
    await expect(chart.locator('.recharts-area-curve')).toBeVisible()
    await chart.scrollIntoViewIfNeeded()
    const box = (await chart.boundingBox())!
    await page.mouse.move(box.x + box.width * .6, box.y + box.height * .5)
    await expect(chart.locator('.recharts-tooltip-wrapper')).toBeVisible()
    await expect(chart.locator('.recharts-tooltip-wrapper')).toContainText('收盘价')
    await expect(chart.locator('.recharts-tooltip-wrapper')).toContainText('$10')
    await page.screenshot({ path: `../.runtime/redesign-${width}-chart.png`, fullPage: true })
  })
}

test('automatic task switches save immediately and survive reload; form fields still support Save', async ({ page }) => {
  await mockWorkspace(page)
  let saved = { sync_enabled: true, sync_interval_minutes: 60, daily_brief_enabled: true, daily_brief_hour: 8,
    timezone: 'Asia/Shanghai', auto_research_enabled: false, auto_research_max_per_day: 0 }
  const writes: any[] = []
  await page.route('**/api/v1/settings', route => {
    if (route.request().method() === 'PUT') {
      saved = route.request().postDataJSON()
      writes.push(saved)
      return route.fulfill({ json: saved })
    }
    return route.fulfill({ json: { preferences: saved, providers: {}, provider_health: {}, limits: {} } })
  })
  await page.goto('/settings')
  const toggle = page.getByRole('switch', { name: '自动同步 X 账号' })
  await expect(toggle).toBeChecked()
  await page.locator('.switch__content').first().click()
  await expect(toggle).not.toBeChecked()
  await expect(page.getByRole('alertdialog', { name: '设置已保存' })).toBeVisible()
  await expect(toggle).toBeEnabled()
  const brief = page.getByRole('switch', { name: '每日研究简报' })
  await brief.focus()
  await page.keyboard.press('Space')
  await expect(brief).not.toBeChecked()
  await expect(brief).toBeEnabled()
  expect(writes).toHaveLength(2)
  expect(saved.sync_enabled).toBe(false)
  expect(saved.daily_brief_enabled).toBe(false)
  await page.reload()
  await expect(toggle).not.toBeChecked()
  await expect(brief).not.toBeChecked()
  await page.getByRole('button', { name: /同步间隔/ }).click()
  await page.getByRole('option', { name: '120 分钟', exact: true }).click()
  await page.getByRole('button', { name: '保存设置' }).click()
  await expect(page.getByRole('alertdialog', { name: '设置已保存' })).toBeVisible()
  expect(saved.sync_interval_minutes).toBe(120)
  expect(saved.auto_research_enabled).toBe(false)
  await page.reload()
  await expect(page.getByRole('button', { name: /同步间隔/ })).toContainText('120 分钟')
  await expect(toggle).not.toBeChecked()
  await expect(brief).not.toBeChecked()
})

test('failed automatic save restores the previous switch state and displays the error', async ({ page }) => {
  await mockWorkspace(page)
  await page.route('**/api/v1/settings', route => route.request().method() === 'PUT'
    ? route.fulfill({ status: 503, json: { detail: '测试：保存暂不可用' } }) : route.fallback())
  await page.goto('/settings')
  const toggle = page.getByRole('switch', { name: '自动同步 X 账号' })
  await expect(toggle).not.toBeChecked()
  await page.locator('.switch__content').first().click()
  await expect(page.getByRole('alertdialog', { name: /保存失败/ })).toBeVisible()
  await expect(toggle).not.toBeChecked()
  await expect(toggle).toBeEnabled()
  await page.reload()
  await expect(toggle).not.toBeChecked()
})

test('switches wait for their save response before accepting another change', async ({ page }) => {
  await mockWorkspace(page)
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  let writes = 0
  await page.route('**/api/v1/settings', async route => {
    if (route.request().method() !== 'PUT') return route.fallback()
    writes++
    const saved = route.request().postDataJSON()
    await gate
    return route.fulfill({ json: saved })
  })
  await page.goto('/settings')
  await page.locator('.switch__content').first().click()
  await expect(page.getByRole('switch', { name: '自动同步 X 账号' })).toBeDisabled()
  await expect(page.getByRole('switch', { name: '每日研究简报' })).toBeDisabled()
  await expect(page.getByRole('button', { name: /同步间隔/ })).toBeDisabled()
  release()
  await expect(page.getByRole('switch', { name: '自动同步 X 账号' })).toBeEnabled()
  expect(writes).toBe(1)
})

test('start research opens the conversation without creating a task', async ({ page }) => {
  await mockWorkspace(page)
  const writes: string[] = []
  page.on('request', request => { if (request.method() !== 'GET') writes.push(request.url()) })
  await page.goto('/')
  await page.getByRole('button', { name: '发起研究', exact: true }).click()
  await expect(page).toHaveURL(/\/chat$/)
  await expect(page.getByRole('textbox', { name: '对话消息' })).toBeVisible()
  expect(writes).toEqual([])
})

for (const width of [1440, 1024, 768, 390]) {
  test(`${width}px: separate fixed glass pills preserve routes and allow content underneath`, async ({ page }) => {
    await mockWorkspace(page)
    await page.setViewportSize({ width, height: 700 })
    await page.goto('/')
    const nav = page.getByRole('navigation', { name: '主导航' })
    const overview = nav.getByRole('link', { name: '研究总览', exact: true })
    const settings = page.getByRole('link', { name: '偏好设置', exact: true })
    await expect(overview).toHaveAttribute('aria-current', 'page')
    await expect(page.locator('.floating-navigation')).toHaveCSS('position', 'fixed')
    await expect(page.locator('.floating-navigation')).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
    const pills = await nav.getByRole('link').evaluateAll(elements => elements.map(element => {
      const style = getComputedStyle(element), rect = element.getBoundingClientRect()
      return { radius: parseFloat(style.borderRadius), height: rect.height, blur: style.backdropFilter }
    }))
    expect(pills).toHaveLength(6)
    expect(pills.every(pill => pill.radius >= pill.height / 2 && pill.blur.includes('blur'))).toBeTruthy()
    const first = (await overview.boundingBox())!, right = (await settings.boundingBox())!
    expect(right.x).toBeGreaterThan(first.x)
    expect(right.x + right.width).toBeLessThanOrEqual(width)
    await nav.getByRole('link', { name: '关注列表', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'NVIDIA' })).toBeVisible()
    await page.evaluate(() => window.scrollTo(0, 280))
    expect((await settings.boundingBox())!.y).toBeCloseTo(right.y)
    const overlap = await page.locator('.stock-detail').evaluate(element => {
      const rect = element.getBoundingClientRect()
      return rect.top < 60 && rect.bottom > 60
    })
    expect(overlap).toBeTruthy()
    await nav.getByRole('link', { name: '待办审批', exact: true }).click()
    await expect(page).toHaveURL(/\/approvals$/)
    await expect(nav.getByRole('link', { name: '待办审批', exact: true })).toHaveAttribute('aria-current', 'page')
    await settings.click()
    await expect(page.getByRole('heading', { name: '偏好设置', exact: true })).toBeVisible()
    await expect(settings).toHaveAttribute('aria-current', 'page')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
  })
}

test('shared access form accepts the passcode and opens the workspace', async ({ page }) => {
  await mockWorkspace(page)
  await page.route('**/api/v1/health', route => route.fulfill(route.request().headers().authorization === 'Bearer ui-test-passcode'
    ? { json: { worker: 'online' } } : { status: 401, json: { detail: '请登录' } }))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '进入研究工作台' })).toBeVisible()
  await page.getByLabel('访问口令').fill('ui-test-passcode')
  await page.getByRole('button', { name: '进入工作台', exact: true }).click()
  await expect(page.getByRole('heading', { name: '研究总览', exact: true })).toBeVisible()
  expect(await page.evaluate(() => sessionStorage.getItem('app_token'))).toBe('ui-test-passcode')
})

test('HeroUI search clear resets the filter and selecting the all-status item restores results', async ({ page }) => {
  await mockWorkspace(page)
  const requests: string[] = []
  page.on('request', request => { if (request.url().includes('/api/v1/x/posts')) requests.push(request.url()) })
  await page.route('**/api/v1/x/posts?**', route => {
    const params = new URL(route.request().url()).searchParams
    const text = params.get('status') ? '证据支持的测试帖子' : params.get('ticker') ? 'NVDA 测试帖子' : '全部测试帖子'
    return route.fulfill({ json: [{ id: 'post-fixture', username: 'ui-test', text, tickers: [], references: [], metrics: {}, created_at: '2026-10-18T00:00:00Z' }] })
  })
  await page.goto('/intelligence')
  const search = page.getByRole('searchbox', { name: '按股票代码筛选' })
  await search.fill('nvda')
  await expect(search).toHaveValue('NVDA')
  await expect.poll(() => requests.some(url => url.includes('ticker=NVDA'))).toBeTruthy()
  await expect(page.getByText('NVDA 测试帖子', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '清空按股票代码筛选' }).click()
  await expect(search).toHaveValue('')
  await expect(page.getByText('全部测试帖子', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /核查状态/ }).click()
  await page.getByRole('option', { name: '证据支持', exact: true }).click()
  await expect.poll(() => requests.some(url => url.includes('status=supported'))).toBeTruthy()
  await expect(page.getByText('证据支持的测试帖子', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /核查状态/ }).click()
  await page.getByRole('option', { name: '全部核查状态', exact: true }).click()
  // A previously loaded query may be served by React Query's cache without a new request.
  await expect(page.getByRole('button', { name: /核查状态/ })).toContainText('全部核查状态')
  await expect(page.getByText('全部测试帖子', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '上一页', exact: true })).toBeDisabled()
})

test('HeroUI required field validation prevents a write and a valid form preserves its payload', async ({ page }) => {
  await mockWorkspace(page)
  const writes: any[] = []
  await page.route('**/api/v1/watchlist', route => {
    if (route.request().method() !== 'POST') return route.fallback()
    writes.push(route.request().postDataJSON())
    return route.fulfill({ json: { ticker: 'AAPL' } })
  })
  await page.goto('/watchlist')
  await page.getByRole('button', { name: '添加标的', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '添加关注标的' })
  await dialog.getByRole('button', { name: '添加到关注列表' }).click()
  await expect(dialog.getByRole('textbox', { name: '股票代码', exact: true })).toHaveAttribute('aria-invalid', 'true')
  expect(writes).toEqual([])
  await dialog.getByRole('textbox', { name: '股票代码', exact: true }).fill('aapl')
  await dialog.getByRole('textbox', { name: '关注原因（可选）', exact: true }).fill('验证表单')
  await dialog.getByRole('button', { name: '添加到关注列表' }).click()
  await expect(dialog).toHaveCount(0)
  expect(writes).toEqual([{ ticker: 'AAPL', notes: '验证表单' }])
})

test('HeroUI tabs and number stepper support keyboard navigation without saving implicitly', async ({ page }) => {
  await mockWorkspace(page)
  const writes: string[] = []
  page.on('request', request => { if (request.method() !== 'GET') writes.push(request.url()) })
  await page.goto('/approvals')
  await page.getByRole('tab', { name: '等待审批' }).focus()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('tab', { name: '全部记录' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('tabpanel', { name: '全部记录' })).toContainText('暂无审批记录')
  await page.goto('/settings')
  const stepper = page.getByRole('textbox', { name: '每日核查上限' })
  await expect(stepper).toHaveValue('0')
  await expect(page.getByRole('button', { name: '减少每日核查上限' })).toBeDisabled()
  await page.getByRole('button', { name: '增加每日核查上限' }).click()
  await expect(stepper).toHaveValue('1')
  await stepper.focus()
  await page.keyboard.press('ArrowUp')
  await expect(stepper).toHaveValue('2')
  expect(writes).toEqual([])
})
