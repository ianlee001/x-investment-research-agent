import { test, expect, type Page } from '@playwright/test'

const webId = 'src_96a94792384576d814f61b19'
const marketId = 'src_f5fbb3af7f6e29ff89b32267'
const missingId = 'src_000000000000000000000000'
const web = { id: webId, title: '公开文章（界面测试）', url: 'https://example.com/research/article', source_type: 'web', excerpt: '这是已保存的文章摘录。' }
const data = { ticker: 'TSLA', close: 354.72, open: 369.145, high: 370.5, low: 349.33,
  volume: 62067344, currency: 'USD', as_of: '2026-10-16T20:00:00+00:00', session_date: '2026-10-16',
  price_type: 'previous_session_close', adjusted: true, intraday_change_percent: -3.908,
  change_basis: 'close_vs_same_session_open', is_realtime: false }
const market = { id: marketId, title: 'Massive · TSLA', url: 'https://api.massive.com/v2/aggs/ticker/TSLA/prev',
  provider: 'massive', source_type: 'market', published_at: '2026-10-16', excerpt: JSON.stringify(data) }
const run = { id: 'citation-run', thread_id: 'citation-thread', kind: 'chat', question: '引用回归测试', status: 'completed',
  stage: '研究完成', created_at: '2026-10-18T12:00:00Z', usage: {}, sources: [web, market], approvals: [], events: [] }
const content = `文章支持这一点 [${webId}]。行情数据 [${marketId}]。缺失记录 [${missingId}]。\n\n[历史 API 引用](${market.url})\n\n[旧式来源](${web.url})\n\n[${webId}](${web.url})\n\n\`[${webId}]\``

async function fixtures(page: Page) {
  // All requests are isolated UI fixtures; no model/provider calls or personal data writes.
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    let result: unknown = []
    if (path.endsWith('/health')) result = { worker: 'online' }
    if (path.endsWith('/chat/threads')) result = [{ id: run.thread_id, title: run.question }]
    if (path.endsWith(`/chat/threads/${run.thread_id}`)) result = { id: run.thread_id, runs: [run], sources: [web, market],
      messages: [{ id: 'answer', role: 'assistant', content, created_at: run.created_at }] }
    if (path.endsWith(`/research/runs/${run.id}`)) result = run
    await route.fulfill({ json: result })
  })
}

for (const width of [1440, 390]) {
  test(`${width}px: chat citations resolve, snapshots stay local, missing references are explicit`, async ({ page }) => {
    await fixtures(page)
    await page.setViewportSize({ width, height: 1000 })
    await page.goto(`/chat?thread=${run.thread_id}`)
    const answer = page.locator('.message.assistant')
    await expect(answer.getByRole('link', { name: '[1]', exact: true }).first()).toHaveAttribute('href', web.url)
    await expect(answer.getByRole('link', { name: '[1]', exact: true }).first()).toHaveAttribute('target', '_blank')
    const local = answer.getByRole('link', { name: '[2]', exact: true })
    await expect(local).toHaveAttribute('href', `#message-answer-source-${marketId}`)
    await expect(local).not.toHaveAttribute('target')
    await expect(answer.getByText('来源未找到', { exact: true })).toBeVisible()
    await expect(answer.locator('a[href*="api.massive.com"]')).toHaveCount(0)
    await expect(answer.getByRole('link', { name: '历史 API 引用', exact: true })).toHaveAttribute('href', `#message-answer-source-${marketId}`)
    await expect(answer.getByRole('link', { name: '旧式来源', exact: true })).toHaveAttribute('href', web.url)
    await expect(answer.locator('.markdown code')).toHaveText(`[${webId}]`)
    // Source tokens in ordinary prose disappear, but literal code examples are intentionally untouched.
    expect(await answer.locator('.markdown').evaluate(el => [...el.childNodes].map(n => n.textContent).join(''))).not.toContain(missingId)
    await local.click()
    const snapshot = page.locator(`[id="message-answer-source-${marketId}"]`)
    await expect(snapshot.getByText('354.72', { exact: true })).toBeVisible()
    await expect(snapshot.getByText('当日开盘至收盘变化', { exact: true })).toBeVisible()
    await expect(snapshot.getByText('-3.908%', { exact: true })).toBeVisible()
    await expect(snapshot.getByText('USD', { exact: true })).toBeVisible()
    await expect(snapshot.locator('pre')).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    await page.screenshot({ path: `../.runtime/citations-chat-${width}.png`, animations: 'disabled' })
    await page.reload()
    await expect(page.locator('.message.assistant').getByRole('link', { name: '[1]', exact: true }).first()).toHaveAttribute('href', web.url)
  })

  test(`${width}px: report evidence distinguishes data snapshots from article excerpts`, async ({ page }) => {
    await fixtures(page)
    const report = { title: 'TSLA 行情引用界面回归', summary: `已保存行情 [${marketId}]，文章 [${webId}]。`,
      generated_at: run.created_at, sources: [web, market], claims: [{ claim_id: 'claim', text: '收盘价数据（界面夹具）', kind: 'fact', status: 'supported',
        explanation: '核对保存的数据。', evidence: [{ source_id: marketId, stance: 'support', quote: market.excerpt, rationale: '数值与日期一致。' }] }],
      positive_factors: [{ text: '测试来源跳转', source_ids: [marketId] }], negative_factors: [] }
    await page.route(`**/api/v1/research/runs/${run.id}`, route => route.fulfill({ json: { ...run, kind: 'research', result: report } }))
    await page.setViewportSize({ width, height: 1000 })
    await page.goto(`/research?run=${run.id}`)
    await expect(page.getByRole('heading', { name: report.title, exact: true })).toBeVisible()
    await expect(page.locator('.evidence-quote').getByText('354.72', { exact: true })).toBeVisible()
    await expect(page.locator('.evidence-quote blockquote')).toHaveCount(0)
    await expect(page.locator('a[href*="api.massive.com"]')).toHaveCount(0)
    await expect(page.locator('.report pre')).toHaveCount(0)
    await expect(page.locator('.report')).not.toContainText('"intraday_change_percent"')
    const source = page.locator(`[id="report-source-${marketId}"]`)
    await source.getByText('查看数据', { exact: true }).click()
    await expect(source.getByText('2026-10-16', { exact: true })).toBeVisible()
    await expect(source.getByText('上一交易日收盘', { exact: true })).toBeVisible()
    const article = page.locator(`[id="report-source-${webId}"]`)
    await expect(article.locator('.source-link')).toHaveAttribute('href', web.url)
    await article.getByText('查看摘录', { exact: true }).click()
    await expect(article.getByText(web.excerpt, { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
    await page.screenshot({ path: `../.runtime/citations-report-${width}.png`, fullPage: true, animations: 'disabled' })
  })
}

test('incomplete data remains a snapshot and never exposes the API as an article', async ({ page }) => {
  await fixtures(page)
  const truncated = { ...market, excerpt: '{"bars": [' }
  await page.route(`**/api/v1/chat/threads/${run.thread_id}`, route => route.fulfill({ json: { id: run.thread_id, runs: [], sources: [truncated],
    messages: [{ id: 'truncated', role: 'assistant', content: `数据 [${marketId}]。` }] } }))
  await page.goto(`/chat?thread=${run.thread_id}`)
  await expect(page.getByText('已保存该来源，但数据快照不完整，暂时无法展开字段。', { exact: true })).toBeVisible()
  await expect(page.locator('a[href*="api.massive.com"]')).toHaveCount(0)
})

test('streamed answer resolves registered source IDs with the same renderer', async ({ page }) => {
  await fixtures(page)
  const active = { ...run, status: 'running' }
  await page.route(`**/api/v1/chat/threads/${run.thread_id}`, route => route.fulfill({ json: { id: run.thread_id, runs: [active], sources: [],
    messages: [{ id: 'question', role: 'user', content: '流式引用测试' }] } }))
  await page.route(`**/api/v1/research/runs/${run.id}`, route => route.fulfill({ json: { ...active, sources: [web, market] } }))
  await page.route(`**/api/v1/research/runs/${run.id}/events?*`, route => route.fulfill({ contentType: 'text/event-stream',
    body: `id: 1\nevent: assistant_delta\ndata: ${JSON.stringify({ data: { text: `查询结果 [${webId}] 与 [${marketId}]。` } })}\n\nid: 2\nevent: evidence_added\ndata: {"data":{}}\n\nevent: stream_end\ndata: {}\n\n` }))
  await page.goto(`/chat?thread=${run.thread_id}`)
  const answer = page.locator('.message.assistant')
  await expect(answer.getByRole('link', { name: '[1]', exact: true })).toHaveAttribute('href', web.url)
  await expect(answer.getByRole('link', { name: '[2]', exact: true })).toHaveAttribute('href', `#live-${run.id}-source-${marketId}`)
  await expect(answer.locator('.markdown')).not.toContainText('src_')
  await expect(answer.locator('a[href*="api.massive.com"]')).toHaveCount(0)
})
