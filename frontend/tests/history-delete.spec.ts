import { test, expect, type Page } from '@playwright/test'

async function historyFixtures(page: Page) {
  const created_at = '2026-10-18T12:00:00Z'
  const makeRun = (id: string, kind: string, question: string, thread_id: string) => ({ id, kind, question, title: question, thread_id,
    status: 'completed', stage: '研究完成', created_at, usage: {}, approvals: [], events: [], sources: [],
    result: kind === 'research' ? { title: question, summary: '测试报告摘要', sources: [] } : undefined })
  const state = {
    runs: [makeRun('research-one', 'research', '第一份研究', 'research-thread'), makeRun('research-two', 'research', '第二份研究', 'research-thread-two'),
      makeRun('chat-run', 'chat', '第一段对话', 'chat-one')],
    threads: [{ id: 'chat-one', title: '第一段对话', has_active_run: false, updated_at: created_at },
      { id: 'chat-two', title: '空白对话', has_active_run: false, updated_at: created_at }],
    deletes: [] as string[], failure: 0,
  }
  // Every API request is isolated. DELETE never reaches any personal database.
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname.replace('/api/v1', '')
    if (request.method() === 'DELETE') {
      state.deletes.push(path)
      if (state.failure) return route.fulfill({ status: state.failure, json: { detail: '删除失败，请刷新后重试' } })
      if (path.startsWith('/research/runs/')) state.runs = state.runs.filter(run => run.id !== path.split('/').pop())
      else if (path.startsWith('/chat/threads/')) {
        const id = path.split('/').pop()
        state.threads = state.threads.filter(thread => thread.id !== id)
        state.runs = state.runs.filter(run => run.thread_id !== id)
      } else throw new Error('Unexpected DELETE')
      return route.fulfill({ json: { deleted: true } })
    }
    let result: unknown = []
    if (path === '/health') result = { worker: 'online' }
    if (path === '/research/runs') result = state.runs.filter(run => run.kind === 'research')
    if (path.startsWith('/research/runs/')) result = state.runs.find(run => run.id === path.split('/').pop()) || {}
    if (path === '/chat/threads') result = state.threads
    if (path.startsWith('/chat/threads/')) {
      const thread = state.threads.find(thread => thread.id === path.split('/').pop())
      result = { ...thread, runs: state.runs.filter(run => run.thread_id === thread?.id), sources: [],
        messages: thread?.id === 'chat-one' ? [{ id: 'answer', role: 'assistant', content: '保存的对话回答', created_at }] : [] }
    }
    if (path.endsWith('/events')) return route.fulfill({ contentType: 'text/event-stream', body: 'event: stream_end\ndata: {}\n\n' })
    await route.fulfill({ json: result })
  })
  return state
}

for (const width of [1440, 1920]) {
  test(`${width}px: selected research and chat records highlight the entire row`, async ({ page }) => {
    await historyFixtures(page)
    await page.setViewportSize({ width, height: 1000 })
    for (const [path, row, selected, next] of [
      ['/research?run=research-one', '.history-entry', '.history-item.selected', '第二份研究'],
      ['/chat?thread=chat-one', '.thread-entry', '.chat-thread.selected', '空白对话'],
    ]) {
      await page.goto(path)
      const selection = page.locator(selected)
      await expect(selection).toBeVisible()
      for (let index = 0; index < 2; index++) {
        const bounds = (await selection.boundingBox())!
        const entry = (await selection.locator('..').boundingBox())!
        expect(bounds.x).toBeCloseTo(entry.x, 0)
        expect(bounds.width).toBeCloseTo(entry.width, 0)
        expect(bounds.height).toBeGreaterThanOrEqual(entry.height - 2)
        await expect(selection).toHaveCSS('border-radius', '0px')
        expect(await selection.evaluate(element => getComputedStyle(element).backgroundColor)).not.toBe('rgba(0, 0, 0, 0)')
        if (!index) await page.locator(row).getByRole('button').filter({ hasText: next }).click()
      }
      await page.screenshot({ path: `../.runtime/record-selection-${width}-${path.startsWith('/chat') ? 'chat' : 'research'}.png`, animations: 'disabled' })
    }
  })
}

for (const width of [1440, 390]) {
  test(`${width}px: delete selected research after confirmation and remain deleted after refresh`, async ({ page }) => {
    const state = await historyFixtures(page)
    await page.setViewportSize({ width, height: 1000 })
    await page.goto('/research?run=research-one')
    await page.getByRole('button', { name: '删除研究', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '删除研究记录', exact: true })
    await expect(dialog.getByText('第一份研究', { exact: true })).toBeVisible()
    expect(state.deletes).toEqual([])
    await page.screenshot({ path: `../.runtime/delete-research-${width}.png`, animations: 'disabled' })
    await dialog.getByRole('button', { name: '确认删除', exact: true }).click()
    await expect(dialog).toHaveCount(0)
    await expect(page).toHaveURL('/research')
    await expect(page.getByRole('button', { name: '删除研究：第一份研究', exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: '删除研究：第二份研究', exact: true })).toHaveCount(1)
    expect(state.deletes).toEqual(['/research/runs/research-one'])
    await page.reload()
    await expect(page.getByRole('button', { name: '删除研究：第一份研究', exact: true })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
  })

  test(`${width}px: delete selected chat using the visible toolbar and clear selection`, async ({ page }) => {
    const state = await historyFixtures(page)
    await page.setViewportSize({ width, height: 1000 })
    await page.goto('/chat?thread=chat-one')
    await page.getByRole('button', { name: '删除对话', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '删除研究对话', exact: true })
    await expect(dialog.getByText('第一段对话', { exact: true })).toBeVisible()
    await page.screenshot({ path: `../.runtime/delete-chat-${width}.png`, animations: 'disabled' })
    await dialog.getByRole('button', { name: '确认删除', exact: true }).click()
    await expect(dialog).toHaveCount(0)
    await expect(page).toHaveURL('/chat')
    await expect(page.getByRole('heading', { name: '开始对话', exact: true })).toBeVisible()
    expect(state.deletes).toEqual(['/chat/threads/chat-one'])
    await page.reload()
    await expect(page.locator('.chat-thread').filter({ hasText: '第一段对话' })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy()
  })
}

test('research list delete supports cancel and leaves another selected report open', async ({ page }) => {
  const state = await historyFixtures(page)
  await page.goto('/research?run=research-one')
  await page.getByRole('button', { name: '删除研究：第二份研究', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '删除研究记录', exact: true })
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  expect(state.deletes).toEqual([])
  await page.getByRole('button', { name: '删除研究：第二份研究', exact: true }).click()
  await dialog.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(page).toHaveURL('/research?run=research-one')
  await expect(page.getByRole('heading', { name: '第一份研究', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '删除研究：第二份研究', exact: true })).toHaveCount(0)
  await expect(page.locator('button button')).toHaveCount(0)
})

test('chat list can delete another empty conversation without switching current selection', async ({ page }) => {
  const state = await historyFixtures(page)
  await page.goto('/chat?thread=chat-one')
  await page.getByRole('button', { name: '删除对话：空白对话', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '删除研究对话', exact: true })
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  expect(state.deletes).toEqual([])
  await page.getByRole('button', { name: '删除对话：空白对话', exact: true }).click()
  await dialog.getByRole('button', { name: '确认删除', exact: true }).click()
  await expect(page).toHaveURL('/chat?thread=chat-one')
  await expect(page.getByText('保存的对话回答', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '删除对话：空白对话', exact: true })).toHaveCount(0)
  await expect(page.locator('button button')).toHaveCount(0)
})

for (const kind of ['research', 'chat']) {
  test(`${kind}: failure keeps the history and running tasks disable deletion`, async ({ page }) => {
    const state = await historyFixtures(page)
    state.failure = 409
    const url = kind === 'research' ? '/research?run=research-one' : '/chat?thread=chat-one'
    const button = kind === 'research' ? '删除研究' : '删除对话'
    await page.goto(url)
    await page.getByRole('button', { name: button, exact: true }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByRole('button', { name: '确认删除', exact: true }).click()
    await expect(dialog.getByText('删除失败，请刷新后重试', { exact: true })).toBeVisible()
    await expect(page).toHaveURL(url)
    await dialog.getByRole('button', { name: '取消', exact: true }).click()
    const run = state.runs.find(run => run.kind === kind)!
    run.status = 'running'
    if (kind === 'chat') state.threads[0].has_active_run = true
    await page.reload()
    await expect(page.getByRole('button', { name: button, exact: true })).toBeDisabled()
    await expect(page.getByRole('button', { name: kind === 'research' ? '删除研究：第一份研究' : '删除对话：第一段对话', exact: true })).toBeDisabled()
  })
}
