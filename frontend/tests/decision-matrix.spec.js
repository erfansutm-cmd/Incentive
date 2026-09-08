import { test, expect } from '@playwright/test'
import { makeStep, mockDecisionMatrix } from './fixtures/decisionMatrix'

test.afterEach(async ({ page }) => {
  expect(await page.pageErrors()).toEqual([])
})

const groupButton = (page, name = 'Group A') => page.getByRole('button', { name: `City group ${name}`, exact: true })
const groupPanel = (page, name = 'Group A') => page.getByRole('region', { name: `${name} decision matrix`, exact: true })
const scoreInput = (dialog) => dialog.getByRole('spinbutton', { name: /^Score/ })
const bucketInput = (dialog, index) => dialog.getByRole('spinbutton', { name: `Control bucket value ${index}`, exact: true })
async function openGroup(page, name = 'Group A') {
  const button = groupButton(page, name)
  if (await button.getAttribute('aria-expanded') !== 'true') await button.click()
  const panel = groupPanel(page, name)
  await expect(panel).toBeVisible()
  await expect(panel.getByText('Loading score steps…', { exact: true })).toBeHidden()
  return panel
}
async function openSeries(page, name = 'Delivery', type = 'DAILY', group = 'Group A') {
  const panel = groupPanel(page, group)
  const typeButton = panel.getByRole('button', { name: new RegExp(`${type} #`) })
  if (await typeButton.getAttribute('aria-expanded') !== 'true') await typeButton.click()
  const scoreButton = panel.getByRole('button', { name: new RegExp(`${name} \\d+ active`) })
  if (await scoreButton.getAttribute('aria-expanded') !== 'true') await scoreButton.click()
}
async function fillValues(dialog, target = '0.25', pr = '2.5', bucket = null) {
  await dialog.getByLabel('Target increase', { exact: true }).fill(target)
  await dialog.getByLabel('PR increase', { exact: true }).fill(pr)
  for (let i = 1; i <= 3; i++) await bucketInput(dialog, i).fill(bucket ? String(bucket[i - 1]) : '')
}
async function chooseScoreType(dialog, value) {
  const input = dialog.getByRole('combobox', { name: 'Score type', exact: true })
  await input.click()
  await input.fill(value)
  const preset = ['Performance', 'Weather', 'Order Level Increase'].includes(value)
  await dialog.getByRole('option', { name: preset ? value : `Use “${value.trim()}” New score type`, exact: true }).click()
  await expect(input).toHaveValue(value.trim())
  await expect(dialog.getByRole('listbox')).toBeHidden()
}
async function addTypeForm(page) {
  await groupPanel(page).getByRole('button', { name: '+ Add incentive type', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Add incentive type', exact: true })
  await dialog.getByRole('combobox', { name: 'Incentive type', exact: true }).selectOption('1')
  return dialog
}

test('city groups stay as ordered rows and expand in place without navigation or a new tab', async ({ page, context }) => {
  await mockDecisionMatrix(page, { groups: ['Other', 'tehran', 'Top40', 'Tier10', 'Tier_2', 'Tier 1', 'Tier3', 'Top 4'] })
  await page.goto('/decision-matrix')
  const buttons = page.getByRole('list', { name: 'City groups', exact: true }).getByRole('button')
  await expect(buttons).toHaveCount(8)
  expect(await buttons.evaluateAll((elements) => elements.map((el) => el.getAttribute('aria-label')))).toEqual([
    'City group Top 4', 'City group Tier 1', 'City group Tier_2', 'City group Tier3',
    'City group Tier10', 'City group tehran', 'City group Other', 'City group Top40',
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
  await openGroup(page, 'Top 4')
  await expect(groupButton(page, 'Top 4')).toHaveAttribute('aria-expanded', 'true')
  await expect(groupButton(page, 'Tier 1')).toBeVisible()
  await expect(groupButton(page, 'Other')).toBeVisible()
  await expect(groupButton(page, 'Top 4').locator('..').getByRole('region', { name: 'Top 4 decision matrix', exact: true })).toBeVisible()
  expect(context.pages()).toHaveLength(1)
  await expect(page).toHaveURL(/\/decision-matrix$/)
  await groupButton(page, 'Top 4').click()
  await expect(groupPanel(page, 'Top 4')).toBeHidden()
  await expect(groupButton(page, 'Top 4')).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByText('Manage incentive rules, one score step at a time.')).toHaveCount(0)
  await expect(page.getByRole('list', { name: 'Decision Matrix hierarchy' })).toHaveCount(0)
})

test('Top 4 priority handles capitalization and separators and keeps original lookup values', async ({ page }) => {
  const state = await mockDecisionMatrix(page)
  for (const name of ['top4', 'TOP_4', 'Top-4']) {
    state.groups = ['Other', 'Tehran', 'Tier 1', name]
    await page.goto('/decision-matrix')
    await expect(page.getByRole('list', { name: 'City groups', exact: true }).getByRole('button').first()).toHaveAttribute('aria-label', `City group ${name}`)
    await openGroup(page, name)
    expect(state.reads.at(-1)).toBe(name)
  }
})

test('filtering collapses a hidden group and never leaves a separate group page', async ({ page }) => {
  await mockDecisionMatrix(page)
  await page.goto('/decision-matrix')
  await openGroup(page)
  await page.getByLabel('Search city groups').fill('Group B')
  await expect(groupPanel(page)).toBeHidden()
  await openGroup(page, 'Group B')
  await page.getByLabel('Search city groups').fill('missing group')
  await expect(page.getByText(/No city groups match/)).toBeVisible()
  await page.getByRole('button', { name: 'Clear search', exact: true }).click()
  await expect(groupButton(page)).toHaveAttribute('aria-expanded', 'false')
  await expect(groupButton(page, 'Group B')).toHaveAttribute('aria-expanded', 'false')
})

test('an empty matrix supports its first step with a user-chosen score and required float values', async ({ page }) => {
  const state = await mockDecisionMatrix(page)
  // Even a nullable schema/default must not turn these business fields optional.
  for (const col of state.columns.filter((col) => ['target_increase', 'pr_increase'].includes(col.name))) {
    col.nullable = true
    col.default = 0
  }
  await page.goto('/')
  await page.getByRole('navigation').getByRole('link', { name: 'Decision Matrix', exact: true }).click()
  await openGroup(page)
  const dialog = await addTypeForm(page)
  await chooseScoreType(dialog, 'Performance')
  await expect(scoreInput(dialog)).toHaveValue('1')
  await expect(scoreInput(dialog)).toBeEditable()
  await scoreInput(dialog).fill('4')
  for (const label of ['Target increase', 'PR increase']) {
    const input = dialog.getByLabel(label, { exact: true })
    await expect(input).toHaveAttribute('required')
    await expect(input).toHaveAttribute('step', 'any')
    await expect(input).toHaveValue('')
  }
  await dialog.getByRole('button', { name: 'Save first step', exact: true }).click()
  expect(state.writes).toHaveLength(0)
  await fillValues(dialog, '0', '1.75')
  await dialog.getByRole('button', { name: 'Save first step', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(state.writes[0].payload).toEqual({
    city_group: 'Group A', incentive_type: 1, score_type: 'performance', score: 4,
    target_increase: 0, pr_increase: 1.75, control_bucket: null,
  })
  await groupPanel(page).getByRole('button', { name: '+ Add step', exact: true }).click()
  await expect(scoreInput(page.getByRole('dialog'))).toHaveValue('5')
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel', exact: true }).click()
  await page.reload()
  await openGroup(page)
  await openSeries(page, 'Performance')
  await expect(page.getByRole('rowheader', { name: '4 ID 1', exact: true })).toBeVisible()
})

test('the custom score-type dropdown supports keyboard selection, custom names, and Escape', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [makeStep()] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await groupPanel(page).getByRole('button', { name: '+ Add score type', exact: true }).click()
  const dialog = page.getByRole('dialog')
  const picker = dialog.getByRole('combobox', { name: 'Score type', exact: true })
  await picker.click()
  await expect(dialog.getByRole('listbox', { name: 'Score type choices', exact: true }).getByRole('option')).toHaveText(['Performance', 'Weather', 'Order Level Increase'])
  await expect(dialog.locator('datalist')).toHaveCount(0)
  await picker.press('ArrowDown')
  await picker.press('ArrowDown')
  await picker.press('Enter')
  await expect(picker).toHaveValue('Weather')
  await expect(dialog.getByRole('listbox')).toBeHidden()
  await dialog.getByRole('button', { name: 'Toggle score type choices', exact: true }).click()
  await expect(dialog.getByRole('listbox')).toBeVisible()
  await picker.press('Escape')
  await expect(dialog.getByRole('listbox')).toBeHidden()
  await expect(dialog).toBeVisible()
  await chooseScoreType(dialog, '  Customer Experience  ')
  await fillValues(dialog, '0.125', '0.75')
  await dialog.getByRole('button', { name: 'Save first step', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(state.writes[0].payload.score_type).toBe('Customer Experience')
})

test('preset selections are saved and an existing score type cannot be added twice', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [makeStep({ score_type: 'Performance' })] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page, 'Performance')
  for (const name of ['Weather', 'Order Level Increase']) {
    await groupPanel(page).getByRole('button', { name: '+ Add score type', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await chooseScoreType(dialog, name)
    await fillValues(dialog)
    await dialog.getByRole('button', { name: 'Save first step', exact: true }).click()
    await expect(dialog).toBeHidden()
  }
  await groupPanel(page).getByRole('button', { name: '+ Add score type', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await chooseScoreType(dialog, 'Weather')
  await expect(dialog.getByRole('alert')).toContainText('This score type already exists')
  await expect(dialog.getByRole('button', { name: 'Save first step', exact: true })).toBeDisabled()
  expect(state.writes.map((write) => write.payload.score_type)).toEqual(['weather', 'order_level_increase'])
})

test('nearest active values follow a changed score, prefer the lower tie, and preserve manual overrides', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [
    makeStep({ id: 1, score: 1, target_increase: 0.1, pr_increase: 1.1 }),
    makeStep({ id: 2, score: 5, target_increase: 0.5, pr_increase: 1.5 }),
    makeStep({ id: 3, score: 9, target_increase: 0.9, pr_increase: 1.9 }),
    makeStep({ id: 4, score: 8, target_increase: 99, pr_increase: 99, deactivated_at: '2026-09-08T13:00:00' }),
    makeStep({ id: 5, score: 10, score_type: 'Weather', target_increase: 88, pr_increase: 88 }),
  ] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await groupPanel(page).getByRole('button', { name: '+ Add step', exact: true }).click()
  const dialog = page.getByRole('dialog')
  const target = dialog.getByLabel('Target increase', { exact: true })
  const pr = dialog.getByLabel('PR increase', { exact: true })
  await expect(target).toHaveValue('0.9')
  await expect(pr).toHaveValue('1.9')
  await scoreInput(dialog).fill('7')
  await expect(target).toHaveValue('0.5')
  await expect(pr).toHaveValue('1.5')
  await scoreInput(dialog).fill('8')
  await expect(target).toHaveValue('0.9') // deactivated score 8 is not copied
  await target.fill('7.75')
  await scoreInput(dialog).fill('2')
  await expect(target).toHaveValue('7.75')
  await expect(pr).toHaveValue('1.1')
  await dialog.getByRole('button', { name: 'Use its values', exact: true }).click()
  await expect(target).toHaveValue('0.1')
  await scoreInput(dialog).fill('5')
  await expect(dialog.getByRole('alert')).toContainText('already active')
  await expect(dialog.getByRole('button', { name: 'Save step', exact: true })).toBeDisabled()
  await scoreInput(dialog).fill('4')
  await expect(target).toHaveValue('0.5')
  await expect(pr).toHaveValue('1.5')
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(state.writes[0].payload).toMatchObject({ score: 4, target_increase: 0.5, pr_increase: 1.5 })
})

test('prefill never copies another score type or incentive type', async ({ page }) => {
  await mockDecisionMatrix(page, { rows: [makeStep({ score_type: 'Performance' })] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page, 'Performance')
  await groupPanel(page).getByRole('button', { name: '+ Add score type', exact: true }).click()
  let dialog = page.getByRole('dialog')
  await chooseScoreType(dialog, 'Weather')
  await expect(dialog.getByLabel('Target increase', { exact: true })).toHaveValue('')
  await expect(dialog.getByLabel('PR increase', { exact: true })).toHaveValue('')
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await groupPanel(page).getByRole('button', { name: '+ Add incentive type', exact: true }).click()
  dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('combobox', { name: 'Incentive type', exact: true }).locator('option')).toHaveText(['Select an incentive type…', 'WEEKLY (#2)'])
  await dialog.getByRole('combobox', { name: 'Incentive type', exact: true }).selectOption('2')
  await chooseScoreType(dialog, 'Performance')
  await expect(dialog.getByLabel('Target increase', { exact: true })).toHaveValue('')
})

test('control bucket is null or exactly three float inputs, never a partial list', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [makeStep()] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await groupPanel(page).getByRole('button', { name: '+ Add step', exact: true }).click()
  let dialog = page.getByRole('dialog')
  await bucketInput(dialog, 1).fill('0.125')
  await expect(bucketInput(dialog, 2)).toHaveAttribute('required')
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  expect(state.writes).toHaveLength(0)
  await bucketInput(dialog, 2).fill('0')
  await bucketInput(dialog, 3).fill('-2.5')
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(state.writes[0].payload.control_bucket).toEqual([0.125, 0, -2.5])
  await expect(page.getByRole('region', { name: 'Delivery active steps', exact: true }).getByRole('cell', { name: '[0.125, 0, -2.5]', exact: true })).toBeVisible()
  await groupPanel(page).getByRole('button', { name: '+ Add step', exact: true }).click()
  dialog = page.getByRole('dialog')
  await bucketInput(dialog, 1).fill('1.1')
  await dialog.getByRole('button', { name: 'Clear control bucket', exact: true }).click()
  for (let i = 1; i <= 3; i++) await expect(bucketInput(dialog, i)).toHaveValue('')
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(state.writes[1].payload.control_bucket).toBeNull()
})

test('steps have no Edit or Status, and deactivated history stays separate when reusing a score', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [makeStep(), makeStep({ id: 2, score: 2 })] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await expect(page.getByRole('button', { name: /^Edit/ })).toHaveCount(0)
  await expect(page.getByRole('columnheader', { name: 'Status', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Deactivate score 2', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel', exact: true }).click()
  expect(state.writes).toHaveLength(0)
  await page.getByRole('button', { name: 'Deactivate score 2', exact: true }).click()
  await page.getByRole('button', { name: 'Deactivate step', exact: true }).click()
  await expect(groupPanel(page).getByRole('button', { name: '+ Add step', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Show deactivated (1)', exact: true }).click()
  const history = page.getByRole('region', { name: 'Delivery deactivated steps', exact: true })
  await expect(history.getByRole('rowheader', { name: '2 ID 2', exact: true })).toBeVisible()
  await expect(history.getByRole('button')).toHaveCount(0)
  await page.getByRole('button', { name: '+ Add step', exact: true }).click()
  await expect(scoreInput(page.getByRole('dialog'))).toHaveValue('2')
  await page.getByRole('dialog').getByRole('button', { name: 'Save step', exact: true }).click()
  const active = page.getByRole('region', { name: 'Delivery active steps', exact: true })
  await expect(active.getByRole('rowheader', { name: '2 ID 3', exact: true })).toBeVisible()
  await expect(history.getByRole('rowheader', { name: '2 ID 2', exact: true })).toBeVisible()
  expect(state.rows.map((row) => row.score)).toEqual([1, 2, 2])
})

test('a history-only score type suggests one and requires fresh non-null increases', async ({ page }) => {
  await mockDecisionMatrix(page, { rows: [makeStep({ deactivated_at: '2026-09-08T13:00:00' })] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await page.getByRole('button', { name: '+ Add step', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(scoreInput(dialog)).toHaveValue('1')
  await expect(dialog.getByLabel('Target increase', { exact: true })).toHaveValue('')
  await expect(dialog.getByLabel('PR increase', { exact: true })).toHaveValue('')
  await fillValues(dialog)
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('rowheader', { name: '1 ID 2', exact: true })).toBeVisible()
})

test('save failures retain the chosen score, floats and bucket for retry', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [makeStep()], saveError: 'Could not save this step.' })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await page.getByRole('button', { name: '+ Add step', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await scoreInput(dialog).fill('7')
  await fillValues(dialog, '0.7', '1.25', [0.1, 0.2, 0.3])
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('Could not save this step.')
  await expect(scoreInput(dialog)).toHaveValue('7')
  await expect(dialog.getByLabel('Target increase', { exact: true })).toHaveValue('0.7')
  await expect(bucketInput(dialog, 3)).toHaveValue('0.3')
  expect(state.rows).toHaveLength(1)
  state.saveError = ''
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(state.rows[1].score).toBe(7)
})

test('a concurrent duplicate refreshes occupied scores without overwriting the chosen score or values', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [makeStep()] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await page.getByRole('button', { name: '+ Add step', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await scoreInput(dialog).fill('6')
  await fillValues(dialog, '0.7', '2.75')
  state.rows.push(makeStep({ id: 2, score: 6, target_increase: 99, pr_increase: 99 }))
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(dialog.getByRole('button', { name: 'Save step', exact: true })).toBeDisabled()
  await expect(scoreInput(dialog)).toHaveValue('6')
  await expect(dialog.getByLabel('Target increase', { exact: true })).toHaveValue('0.7')
  await scoreInput(dialog).fill('7')
  await expect(dialog.getByLabel('PR increase', { exact: true })).toHaveValue('2.75')
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(state.writes.map((write) => write.payload.score)).toEqual([6, 7])
})

test('a concurrent deactivation does not force a different requested score', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [makeStep(), makeStep({ id: 2, score: 2 })] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await page.getByRole('button', { name: '+ Add step', exact: true }).click()
  const dialog = page.getByRole('dialog')
  state.rows[1].deactivated_at = '2026-09-08T13:00:00'
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(state.writes[0].payload.score).toBe(3)
})

test('lookup and matrix failures are retryable inside the selected row', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { groupError: 'Cannot read groups.', typeError: 'Cannot read incentive types.' })
  await page.goto('/decision-matrix')
  await expect(page.getByText('Could not load city groups', { exact: true })).toBeVisible()
  state.groupError = ''
  await page.getByRole('button', { name: 'Retry city groups', exact: true }).click()
  await openGroup(page)
  await expect(groupPanel(page).getByRole('button', { name: '+ Add incentive type', exact: true })).toBeDisabled()
  state.typeError = ''
  await page.getByRole('button', { name: 'Retry types', exact: true }).click()
  await expect(groupPanel(page).getByRole('button', { name: '+ Add incentive type', exact: true })).toBeEnabled()
  state.matrixError = 'Matrix table unavailable.'
  await page.getByRole('button', { name: 'Refresh', exact: true }).click()
  await expect(groupPanel(page).getByText('Could not load the matrix', { exact: true })).toBeVisible()
  await expect(groupButton(page, 'Group B')).toBeVisible()
  state.matrixError = ''
  await groupPanel(page).getByRole('button', { name: 'Retry matrix', exact: true }).click()
  await expect(groupPanel(page).getByText('No incentive types configured yet')).toBeVisible()
})

test('empty reference types prevent arbitrary incentive types from being added', async ({ page }) => {
  await mockDecisionMatrix(page, { types: [] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await expect(groupPanel(page).getByText(/No incentive types are available/)).toBeVisible()
  await expect(groupPanel(page).getByRole('button', { name: '+ Add incentive type', exact: true })).toBeDisabled()
})

test('a failed deactivation keeps the active step and can be cancelled', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [makeStep()], deactivateError: 'Could not deactivate.' })
  await page.goto('/decision-matrix')
  await openGroup(page)
  await openSeries(page)
  await page.getByRole('button', { name: 'Deactivate score 1', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByRole('button', { name: 'Deactivate step', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('Could not deactivate.')
  expect(state.rows[0].deactivated_at).toBeNull()
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
})

test('fast accordion changes ignore older responses and leave other groups visible', async ({ page }) => {
  let release
  const pending = new Promise((resolve) => { release = resolve })
  const state = await mockDecisionMatrix(page, {
    rows: [makeStep(), makeStep({ id: 2, city_group: 'Group B', score_type: 'Weather' })],
    groupDelays: { 'Group A': pending },
  })
  await page.goto('/decision-matrix')
  await groupButton(page).click()
  await expect(groupPanel(page).getByText('Loading score steps…')).toBeVisible()
  await openGroup(page, 'Group B')
  release()
  await openSeries(page, 'Weather', 'DAILY', 'Group B')
  await expect(groupPanel(page)).toBeHidden()
  await expect(groupButton(page)).toHaveAttribute('aria-expanded', 'false')
  await expect(groupPanel(page, 'Group B').getByRole('rowheader', { name: '1 ID 2', exact: true })).toBeVisible()
  expect(state.reads).toEqual(['Group A', 'Group B'])
})

test('mobile accordion and dropdown remain within the viewport and work with the keyboard', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockDecisionMatrix(page, { rows: [makeStep()] })
  await page.goto('/decision-matrix')
  await groupButton(page).focus()
  await page.keyboard.press('Enter')
  await openSeries(page)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await groupPanel(page).getByRole('button', { name: '+ Add score type', exact: true }).click()
  const dialog = page.getByRole('dialog')
  const picker = dialog.getByRole('combobox', { name: 'Score type', exact: true })
  await picker.click()
  await expect(dialog.getByRole('listbox')).toBeVisible()
  expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  await picker.press('Escape')
  await expect(dialog).toBeVisible()
  await picker.press('Escape')
  await expect(dialog).toBeHidden()
})


test.describe('touch score-type picker', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })
  test('tapping a dropdown option selects it without submitting or dismissing the form', async ({ page }) => {
    await mockDecisionMatrix(page, { rows: [makeStep()] })
    await page.goto('/decision-matrix')
    await groupButton(page).tap()
    await openSeries(page)
    await groupPanel(page).getByRole('button', { name: '+ Add score type', exact: true }).tap()
    const dialog = page.getByRole('dialog')
    const picker = dialog.getByRole('combobox', { name: 'Score type', exact: true })
    await picker.tap()
    await dialog.getByRole('option', { name: 'Order Level Increase', exact: true }).tap()
    await expect(picker).toHaveValue('Order Level Increase')
    await expect(dialog.getByRole('listbox')).toBeHidden()
    await expect(dialog).toBeVisible()
  })
})


test('stored preset keys keep friendly UI labels and Add step has no number', async ({ page }) => {
  const state = await mockDecisionMatrix(page, { rows: [
    makeStep({ id: 1, score_type: 'performance', score: 6, target_increase: 0.6, pr_increase: 0.06 }),
    makeStep({ id: 2, score_type: 'weather', score: 2 }),
    makeStep({ id: 3, score_type: 'order_level_increase', score: 4, target_increase: 0.4, pr_increase: 0.04 }),
    makeStep({ id: 4, score_type: 'order_level_increase', score: 3, deactivated_at: '2026-09-08T13:00:00' }),
    makeStep({ id: 5, score_type: 'Customer Experience', score: 1 }),
  ] })
  await page.goto('/decision-matrix')
  await openGroup(page)
  for (const label of ['Performance', 'Weather', 'Order Level Increase', 'Customer Experience']) {
    await openSeries(page, label)
    const section = groupPanel(page).getByRole('region', { name: `${label} score type`, exact: true })
    await expect(section.getByRole('button', { name: '+ Add step', exact: true })).toHaveText('+ Add step')
  }
  await expect(page.getByRole('button', { name: /\+ Add step \(/ })).toHaveCount(0)
  await expect(page.getByText('order_level_increase', { exact: true })).toHaveCount(0)

  const performance = groupPanel(page).getByRole('region', { name: 'Performance score type', exact: true })
  await performance.getByRole('button', { name: '+ Add step', exact: true }).click()
  let dialog = page.getByRole('dialog')
  await expect(dialog.locator('.context')).toContainText('Performance')
  await expect(scoreInput(dialog)).toHaveValue('7')
  await expect(dialog.getByLabel('Target increase', { exact: true })).toHaveValue('0.6')
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(state.writes[0].payload.score_type).toBe('performance')

  const order = groupPanel(page).getByRole('region', { name: 'Order Level Increase score type', exact: true })
  await order.getByRole('button', { name: 'Show deactivated (1)', exact: true }).click()
  await expect(order.getByRole('region', { name: 'Order Level Increase deactivated steps', exact: true })).toBeVisible()
  await order.getByRole('button', { name: '+ Add step', exact: true }).click()
  dialog = page.getByRole('dialog')
  await expect(dialog.locator('.context')).toContainText('Order Level Increase')
  await expect(scoreInput(dialog)).toHaveValue('5')
  await expect(dialog.getByLabel('PR increase', { exact: true })).toHaveValue('0.04')
  await dialog.getByRole('button', { name: 'Save step', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(state.writes[1].payload.score_type).toBe('order_level_increase')
  await order.getByRole('button', { name: 'Deactivate score 4', exact: true }).click()
  await expect(page.getByRole('dialog').locator('.confirm-text')).toContainText('Order Level Increase')
})

test('typing a database key selects its friendly label without creating a custom alias', async ({ page }) => {
  const state = await mockDecisionMatrix(page)
  await page.goto('/decision-matrix')
  await openGroup(page)
  const dialog = await addTypeForm(page)
  const picker = dialog.getByRole('combobox', { name: 'Score type', exact: true })
  await picker.fill('order_level_increase')
  await expect(dialog.getByRole('listbox', { name: 'Score type choices', exact: true }).getByRole('option')).toHaveText(['Order Level Increase'])
  await picker.press('Enter')
  await expect(picker).toHaveValue('Order Level Increase')
  await fillValues(dialog)
  await dialog.getByRole('button', { name: 'Save first step', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(state.writes[0].payload.score_type).toBe('order_level_increase')
  await expect(groupPanel(page).getByRole('region', { name: 'Order Level Increase active steps', exact: true })).toBeVisible()
})
