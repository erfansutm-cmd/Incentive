import { test, expect } from '@playwright/test'
import { makeStep, mockDecisionMatrix } from './fixtures/decisionMatrix'

test.afterEach(async ({ page }) => {
  expect(await page.pageErrors()).toEqual([])
})

async function openGroup(page, name = 'Group A') {
  await page.getByRole('button', { name: `Open city group ${name}`, exact: true }).click()
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()
  await expect(page.getByText('Loading score steps…')).toBeHidden()
}
async function openSeries(page, name = 'Delivery', type = 'DAILY') {
  const typeButton = page.getByRole('button', { name: new RegExp(`^.*${type} #`) })
  if (await typeButton.getAttribute('aria-expanded') !== 'true') await typeButton.click()
  const scoreButton = page.getByRole('button', { name: new RegExp(`^.*${name} \\d+ active`) })
  if (await scoreButton.getAttribute('aria-expanded') !== 'true') await scoreButton.click()
}
async function fillValues(dialog, target = '0.25', pr = '2.5', bucket = '0') {
  await dialog.getByLabel('Target increase', { exact: true }).fill(target)
  await dialog.getByLabel('PR increase', { exact: true }).fill(pr)
  await dialog.getByLabel(/^Control bucket/).fill(bucket)
}
function scoreInput(dialog) {
  return dialog.getByRole('spinbutton', { name: /^Score/ })
}

test('navigation, city search, and first step work with a completely empty matrix', async ({ page }) => {
  const state = await mockDecisionMatrix(page)
  await page.goto('/')
  await page.getByRole('navigation').getByRole('link', { name: 'Decision Matrix' }).click()
  await expect(page).toHaveURL(/\/decision-matrix$/)
  await expect(page.getByRole('heading', { name: 'Select a city group' })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Open city group/ })).toHaveCount(3)
  await page.getByLabel('Search city groups').fill('Group B')
  await expect(page.getByRole('button', { name: /^Open city group/ })).toHaveCount(1)
  await page.getByLabel('Search city groups').fill('no match')
  await expect(page.getByText(/No city groups match/)).toBeVisible()
  await page.getByRole('button', { name: 'Clear search' }).click()
  await openGroup(page)
  await expect(page.getByText('No incentive types configured yet')).toBeVisible()
  await page.getByRole('button', { name: '+ Add incentive type', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Add incentive type', exact: true })
  await expect(dialog.getByRole('button', { name: 'Save first step' })).toBeDisabled()
  await dialog.getByRole('combobox').selectOption('1')
  await dialog.getByLabel('Score type', { exact: true }).fill(' Delivery ')
  await expect(scoreInput(dialog)).toHaveValue('1')
  await expect(scoreInput(dialog)).toHaveAttribute('readonly')
  await fillValues(dialog, '0.125', '1.75')
  await dialog.getByRole('button', { name: 'Save first step' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('button', { name: '+ Add step (2)', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: '0.125', exact: true })).toBeVisible()
  expect(state.writes[0].payload).toEqual({
    city_group: 'Group A', incentive_type: 1, score_type: 'Delivery', score: 1,
    target_increase: '0.125', pr_increase: '1.75', control_bucket: '0',
  })
  // Reload from the API, rather than relying on transient client-side parents.
  await page.reload()
  await openGroup(page)
  await openSeries(page)
  await expect(page.getByRole('rowheader', { name: '1 ID 1', exact: true })).toBeVisible()
})

test('adds sequential steps, confirms deactivation, and preserves history after further additions', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [makeStep(), makeStep({ id: 2, score: 2 })] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await page.getByRole('button', { name: '+ Add step (3)', exact: true }).click()
  let dialog = page.getByRole('dialog')
  await expect(scoreInput(dialog)).toHaveValue('3')
  await fillValues(dialog)
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(page.getByRole('rowheader', { name: '3 ID 3', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Deactivate score 2', exact: true }).click()
  dialog = page.getByRole('dialog', { name: 'Deactivate score 2?', exact: true })
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  expect(state.writes.filter((write) => write.action === 'deactivate')).toHaveLength(0)
  await page.getByRole('button', { name: 'Deactivate score 2', exact: true }).click()
  await page.getByRole('button', { name: 'Deactivate step', exact: true }).click()
  await expect(page.getByRole('rowheader', { name: '2 ID 2', exact: true })).toBeHidden()
  await expect(page.getByRole('button', { name: '+ Add step (4)', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Show deactivated (1)', exact: true }).click()
  const active = page.getByRole('region', { name: 'Delivery active steps', exact: true })
  const history = page.getByRole('region', { name: 'Delivery deactivated steps', exact: true })
  await expect(active.getByRole('rowheader', { name: '2 ID 2', exact: true })).toHaveCount(0)
  await expect(history.getByRole('rowheader', { name: '2 ID 2', exact: true })).toBeVisible()
  await expect(history.getByRole('button')).toHaveCount(0)
  await expect(history.getByRole('columnheader', { name: 'Deactivated at' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Status', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '+ Add step (4)', exact: true }).click()
  dialog = page.getByRole('dialog')
  await fillValues(dialog)
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(page.getByRole('rowheader')).toHaveCount(4)
  await expect(page.getByRole('button', { name: 'Hide deactivated' })).toHaveAttribute('aria-expanded', 'true')
  await expect(active.getByRole('rowheader')).toHaveCount(3)
  await expect(history.getByRole('rowheader')).toHaveCount(1)
  expect(state.rows.map((row) => row.score)).toEqual([1, 2, 3, 4])
})

test('new score types and incentive types start at one and configured types cannot be added twice', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [makeStep()] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await page.getByRole('button', { name: '+ Add score type', exact: true }).click()
  let dialog = page.getByRole('dialog', { name: 'Add score type', exact: true })
  await dialog.getByLabel('Score type', { exact: true }).fill('delivery')
  await fillValues(dialog)
  await dialog.getByRole('button', { name: 'Save first step' }).click()
  await expect(dialog.getByRole('alert')).toContainText('This score type already exists')
  expect(state.writes).toHaveLength(0)
  await dialog.getByLabel('Score type', { exact: true }).fill('Quality')
  await expect(scoreInput(dialog)).toHaveValue('1')
  await dialog.getByRole('button', { name: 'Save first step' }).click()
  await expect(dialog).toBeHidden()
  await page.getByRole('button', { name: '+ Add incentive type', exact: true }).click()
  dialog = page.getByRole('dialog')
  await expect(dialog.locator('option')).toHaveText(['Select an incentive type…', 'WEEKLY (#2)'])
  await dialog.getByRole('combobox').selectOption('2')
  await dialog.getByLabel('Score type', { exact: true }).fill('Delivery')
  await fillValues(dialog)
  await dialog.getByRole('button', { name: 'Save first step' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('button', { name: '+ Add incentive type', exact: true })).toBeDisabled()
  expect(state.rows.map(({ incentive_type, score_type, score }) => [incentive_type, score_type, score])).toEqual([
    [1, 'Delivery', 1], [1, 'Quality', 1], [2, 'Delivery', 1],
  ])
  await page.getByRole('button', { name: '← All city groups', exact: true }).click()
  await openGroup(page, 'Group B')
  await expect(page.getByText('No incentive types configured yet')).toBeVisible()
  await expect(page.getByRole('button', { name: '+ Add incentive type', exact: true })).toBeEnabled()
})

test('a history-only score type restarts at one while keeping its old row separate', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [makeStep({ deactivated_at: '2026-09-08T13:00:00' })] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await expect(page.getByText('No active steps. Add step 1 to start again.')).toBeVisible()
  await expect(page.getByRole('button', { name: '+ Add step (1)', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Show deactivated (1)', exact: true }).click()
  const history = page.getByRole('region', { name: 'Delivery deactivated steps', exact: true })
  await expect(history.getByRole('rowheader', { name: '1 ID 1', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '+ Add step (1)', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(scoreInput(dialog)).toHaveValue('1')
  await fillValues(dialog)
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(dialog).toBeHidden()
  const active = page.getByRole('region', { name: 'Delivery active steps', exact: true })
  await expect(active.getByRole('rowheader', { name: '1 ID 2', exact: true })).toBeVisible()
  await expect(history.getByRole('rowheader', { name: '1 ID 1', exact: true })).toBeVisible()
  await expect(history.getByRole('button')).toHaveCount(0)
  expect(state.rows.map((row) => row.score)).toEqual([1, 1])
  await expect(page.getByRole('columnheader', { name: 'Status', exact: true })).toHaveCount(0)
})

test('save failures keep entered values and are retryable', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { saveError: 'Database temporarily unavailable.' })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await page.getByRole('button', { name: '+ Add incentive type', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('combobox').selectOption('1')
  await dialog.getByLabel('Score type', { exact: true }).fill('Delivery')
  // Required database fields are also required in the browser.
  await dialog.getByRole('button', { name: 'Save first step' }).click()
  expect(state.writes).toHaveLength(0)
  await fillValues(dialog)
  await dialog.getByRole('button', { name: 'Save first step' }).click()
  await expect(dialog.getByRole('alert')).toContainText('Database temporarily unavailable.')
  await expect(dialog.getByLabel('Target increase', { exact: true })).toHaveValue('0.25')
  await expect(dialog.getByLabel('Score type', { exact: true })).toHaveValue('Delivery')
  expect(state.rows).toHaveLength(0)
  state.saveError = ''
  await dialog.getByRole('button', { name: 'Save first step' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('rowheader', { name: '1 ID 1', exact: true })).toBeVisible()
})

test('a concurrent addition refreshes the displayed next score without losing entered values', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [makeStep()] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await page.getByRole('button', { name: '+ Add step (2)', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await fillValues(dialog, '0.75', '3.5')
  // Another client saves score 2 after this form was opened.
  state.rows.push(makeStep({ id: 2, score: 2 }))
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('The next score is now 3')
  await expect(scoreInput(dialog)).toHaveValue('3')
  await expect(dialog.getByLabel('Target increase', { exact: true })).toHaveValue('0.75')
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('rowheader', { name: '3 ID 3', exact: true })).toBeVisible()
  expect(state.writes.map((write) => write.payload.score)).toEqual([2, 3])
})

test('lookup and matrix errors have retry controls and never offer arbitrary incentive types', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { groupError: 'Cannot read active cities.', typeError: 'Cannot read incentive types.' })
  await page.goto('/decision-matrix')
  await expect(page.getByText('Could not load city groups', { exact: true })).toBeVisible()
  state.groupError = ''
  await page.getByRole('button', { name: 'Retry city groups' }).click()
  await openGroup(page)
  await expect(page.getByRole('button', { name: '+ Add incentive type', exact: true })).toBeDisabled()
  state.typeError = ''
  await page.getByRole('button', { name: 'Retry types' }).click()
  await expect(page.getByRole('button', { name: '+ Add incentive type', exact: true })).toBeEnabled()
  state.matrixError = 'Matrix table unavailable.'
  await page.getByRole('button', { name: 'Refresh', exact: true }).click()
  await expect(page.getByText('Could not load the matrix', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '+ Add incentive type', exact: true })).toBeDisabled()
  state.matrixError = ''
  await page.getByRole('button', { name: 'Retry matrix' }).click()
  await expect(page.getByText('No incentive types configured yet')).toBeVisible()
})

test('deactivation failures stay in the confirmation dialog and do not hide the active step', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [makeStep()], deactivateError: 'Could not deactivate this step.' })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await page.getByRole('button', { name: 'Deactivate score 1', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('button', { name: 'Deactivate step', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('Could not deactivate this step.')
  expect(state.rows[0].deactivated_at).toBeNull()
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('button', { name: 'Deactivate score 1', exact: true })).toBeVisible()
})

test('fast city changes ignore an older pending response', async ({ page }) => {
  let release
  const pending = new Promise((resolve) => { release = resolve })
  const state = await mockDecisionMatrix(page, {
    rows: [makeStep(), makeStep({ id: 2, city_group: 'Group B', score_type: 'Quality' })],
    groupDelays: { 'Group A': pending },
  })
  await page.goto('/decision-matrix')
  await page.getByRole('button', { name: 'Open city group Group A', exact: true }).click()
  await expect(page.getByText('Loading score steps…')).toBeVisible()
  await page.getByRole('button', { name: '← All city groups', exact: true }).click()
  await openGroup(page, 'Group B')
  release()
  await openSeries(page, 'Quality')
  await expect(page.getByRole('heading', { name: 'Group B', exact: true })).toBeVisible()
  await expect(page.getByRole('rowheader', { name: '1 ID 2', exact: true })).toBeVisible()
  expect(state.reads).toEqual(['Group A', 'Group B'])
})

test('mobile layout stays within the viewport and native dialogs support keyboard dismissal', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockDecisionMatrix(page, { rows: [makeStep()] })
  await page.goto('/decision-matrix')
  const group = page.getByRole('button', { name: 'Open city group Group A', exact: true })
  await group.focus()
  await page.keyboard.press('Enter')
  await openSeries(page)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  const addButton = page.getByRole('button', { name: '+ Add step (2)', exact: true })
  await addButton.click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByLabel('Target increase', { exact: true })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(addButton).toBeFocused()
})

test('empty incentive lookup disables creation and explains why', async ({ page }) => {
  await mockDecisionMatrix(page, { types: [] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await expect(page.getByText(/No incentive types are available in the reference table/)).toBeVisible()
  await expect(page.getByRole('button', { name: '+ Add incentive type', exact: true })).toBeDisabled()
})


test('city groups are separate lines ordered by tiers, Tehran, then other groups', async ({ page }) => {
  await mockDecisionMatrix(page, {
    groups: ['Other', 'tehran', 'Tier10', 'Tier_2', 'Tier 1', 'Another group', 'Tier3'],
  })
  await page.goto('/decision-matrix')
  const list = page.getByRole('list', { name: 'City groups', exact: true })
  const buttons = list.getByRole('button')
  await expect(buttons).toHaveCount(7)
  expect(await buttons.evaluateAll((elements) => elements.map((el) => el.getAttribute('aria-label')))).toEqual([
    'Open city group Tier 1', 'Open city group Tier_2', 'Open city group Tier3', 'Open city group Tier10',
    'Open city group tehran', 'Open city group Another group', 'Open city group Other',
  ])
  const boxes = await buttons.evaluateAll((elements) => elements.map((el) => {
    const { x, y, width, height } = el.getBoundingClientRect()
    return { x, y, width, height }
  }))
  for (let i = 1; i < boxes.length; i++) {
    expect(boxes[i].x).toBe(boxes[0].x)
    expect(boxes[i].width).toBe(boxes[0].width)
    expect(boxes[i].y).toBeGreaterThanOrEqual(boxes[i - 1].y + boxes[i - 1].height)
  }
  await expect(page.getByText('Manage incentive rules, one score step at a time.')).toHaveCount(0)
  await expect(page.getByRole('list', { name: 'Decision Matrix hierarchy', exact: true })).toHaveCount(0)
  await page.getByLabel('Search city groups').fill('tier')
  await expect(buttons).toHaveCount(4)
})

test('deactivating the highest active score allows reuse without mixing history into active steps', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [
    makeStep(), makeStep({ id: 2, score: 2 }),
    makeStep({ id: 3, score: 9, deactivated_at: '2026-09-08T13:00:00' }),
  ] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await expect(page.getByRole('button', { name: '+ Add step (3)', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Deactivate score 2', exact: true }).click()
  await page.getByRole('button', { name: 'Deactivate step', exact: true }).click()
  await expect(page.getByRole('button', { name: '+ Add step (2)', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Show deactivated (2)', exact: true }).click()
  const history = page.getByRole('region', { name: 'Delivery deactivated steps', exact: true })
  await expect(history.getByRole('rowheader')).toHaveCount(2)
  await page.getByRole('button', { name: '+ Add step (2)', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await fillValues(dialog)
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(dialog).toBeHidden()
  const active = page.getByRole('region', { name: 'Delivery active steps', exact: true })
  await expect(active.getByRole('rowheader', { name: '2 ID 4', exact: true })).toBeVisible()
  await expect(active.getByRole('rowheader')).toHaveCount(2)
  await expect(history.getByRole('rowheader', { name: '2 ID 2', exact: true })).toBeVisible()
  expect(state.rows[1].deactivated_at).not.toBeNull()
  expect(state.rows[3].deactivated_at).toBeNull()
})

test('a deactivation while adding refreshes the next score downward and preserves input', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [makeStep(), makeStep({ id: 2, score: 2 })] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await page.getByRole('button', { name: '+ Add step (3)', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await fillValues(dialog, '0.75', '3.5')
  state.rows[1].deactivated_at = '2026-09-08T13:00:00'
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('The next score is now 2')
  await expect(scoreInput(dialog)).toHaveValue('2')
  await expect(dialog.getByLabel('Target increase', { exact: true })).toHaveValue('0.75')
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(state.writes.map((write) => write.payload.score)).toEqual([3, 2])
})

test('editing an active step prefills values, supports cancel, and updates only those values', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [makeStep()] })
  const original = structuredClone(state.rows[0])
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await page.getByRole('button', { name: 'Edit score 1', exact: true }).click()
  let dialog = page.getByRole('dialog', { name: 'Edit score 1', exact: true })
  await expect(dialog.getByLabel('Target increase', { exact: true })).toHaveValue('0.125')
  await expect(dialog.getByLabel('PR increase', { exact: true })).toHaveValue('1.75')
  await expect(dialog.getByLabel(/^Control bucket/)).toHaveValue('0')
  await expect(scoreInput(dialog)).toHaveValue('1')
  await expect(scoreInput(dialog)).toHaveAttribute('readonly')
  await expect(dialog.getByLabel('Score type', { exact: true })).toHaveCount(0)
  await fillValues(dialog, '0.5', '4.25', '')
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  expect(state.writes).toHaveLength(0)
  expect(state.rows[0]).toEqual(original)
  await page.getByRole('button', { name: 'Edit score 1', exact: true }).click()
  dialog = page.getByRole('dialog')
  await expect(dialog.getByLabel('Target increase', { exact: true })).toHaveValue('0.125')
  await fillValues(dialog, '0.5', '4.25', '')
  await dialog.getByRole('button', { name: 'Save changes', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(state.writes).toEqual([{
    action: 'edit', id: 1,
    payload: { target_increase: '0.5', pr_increase: '4.25', control_bucket: null },
  }])
  expect(state.rows).toEqual([{ ...original, target_increase: 0.5, pr_increase: 4.25, control_bucket: null }])
  await expect(page.getByRole('button', { name: '+ Add step (2)', exact: true })).toBeVisible()
  await page.reload()
  await openGroup(page)
  await openSeries(page)
  const active = page.getByRole('region', { name: 'Delivery active steps', exact: true })
  await expect(active.getByRole('cell', { name: '0.5', exact: true })).toBeVisible()
  await expect(active.getByRole('cell', { name: '4.25', exact: true })).toBeVisible()
})

test('an edit failure preserves the entered changes for retry', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [makeStep()], editError: 'Could not save changes.' })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await page.getByRole('button', { name: 'Edit score 1', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await fillValues(dialog, '0.6', '4.5', '1')
  await dialog.getByRole('button', { name: 'Save changes', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('Could not save changes.')
  await expect(dialog.getByLabel('Target increase', { exact: true })).toHaveValue('0.6')
  expect(state.rows[0].target_increase).toBe(0.125)
  state.editError = ''
  await dialog.getByRole('button', { name: 'Save changes', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(state.rows[0].target_increase).toBe(0.6)
})

for (const change of ['deactivated', 'deleted']) {
  test(`a step ${change} while its edit form is open cannot be saved`, async ({ page }) => {
    const state = await mockDecisionMatrix(page, { rows: [makeStep()] })
    await page.goto('/decision-matrix')
    await openGroup(page)
    await openSeries(page)
    await page.getByRole('button', { name: 'Edit score 1', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await fillValues(dialog, '0.8', '5.5')
    if (change === 'deactivated') state.rows[0].deactivated_at = '2026-09-08T13:00:00'
    else state.rows = []
    await dialog.getByRole('button', { name: 'Save changes', exact: true }).click()
    await expect(dialog.getByRole('alert')).toContainText(change === 'deactivated' ? 'can no longer be edited' : 'not found')
    await expect(dialog.getByRole('button', { name: 'Save changes', exact: true })).toBeDisabled()
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Edit score 1', exact: true })).toHaveCount(0)
    if (change === 'deactivated') {
      await page.getByRole('button', { name: 'Show deactivated (1)', exact: true }).click()
      const history = page.getByRole('region', { name: 'Delivery deactivated steps', exact: true })
      await expect(history.getByRole('button')).toHaveCount(0)
      expect(state.rows[0].target_increase).toBe(0.125)
    }
  })
}
