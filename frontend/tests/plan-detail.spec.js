import { test, expect } from '@playwright/test'
import { mockPlanDetail, makeConfig } from './fixtures/planDetail'

test.afterEach(async ({ page }) => {
  expect(await page.pageErrors()).toEqual([])
})

const section = (page) => page.getByRole('region', { name: 'Base configs', exact: true })
const allocatorRows = (page) => section(page).locator('tr.config-row')
const detailRows = (page) => section(page).locator('tr.detail-row')
const dialog = (page) => page.locator('.modal')
const dialogButton = (page, name) =>
  dialog(page).getByRole('button', { name, exact: true })
// one field of a detail grid, by its label
const field = (scope, label) =>
  scope.locator('.detail-facts > div').filter({ hasText: label }).locator('dd')

test('allocators are listed with only the summary columns up front', async ({ page }) => {
  await mockPlanDetail(page)
  await page.goto('/plans/1')
  await expect(allocatorRows(page)).toHaveCount(2)
  await expect(section(page).getByRole('columnheader')).toHaveText([
    'Details', 'Allocator ID', 'Rule Name', 'Impact Ratio', 'Actions',
  ])
  // no explanatory hint line under the heading
  await expect(section(page).locator('.hint')).toHaveCount(0)
  await expect(section(page).getByText(/open a row to see/)).toHaveCount(0)
  const first = allocatorRows(page).first()
  await expect(first.locator('.ratio')).toHaveText('60%')
  await expect(first.locator('.ratio-raw')).toHaveText('0.6')
  await expect(allocatorRows(page).nth(1).locator('.ratio')).toHaveText('40%')
  // everything else of the row stays behind its dropdown
  await expect(section(page).getByText('Clustering Method')).toHaveCount(0)
  await expect(section(page).getByText('Updated At')).toHaveCount(0)
  await expect(section(page).getByText('2 allocators')).toBeVisible()
  await expect(section(page).getByText('impact 100%')).toBeVisible()
  await expect(section(page).getByRole('button', { name: '+ Add allocator', exact: true })).toBeVisible()
})

test('the dropdown hides the plan-level columns and formats the timestamps', async ({ page }) => {
  await mockPlanDetail(page)
  await page.goto('/plans/1')
  await allocatorRows(page).first().click()
  const detail = detailRows(page).first()
  await expect(detail).toContainText('Clustering Method')
  // plan_id, listing_id and duration are shown once at plan level
  for (const label of ['Plan ID', 'Listing ID', 'Duration']) {
    await expect(detail.getByText(label, { exact: true })).toHaveCount(0)
  }
  for (const label of ['ID', 'Batch Size', 'Districts', 'Vendors', 'Created At', 'Updated At', 'Deactivated At']) {
    await expect(detail.getByText(label, { exact: true })).toBeVisible()
  }
  await expect(detail).not.toContainText('2026-09-14T10:11:16')
  await expect(field(detail, 'Updated At')).toContainText(/2026/)
  await expect(field(detail, 'Updated At')).toContainText(/10:11/)
  await expect(field(detail, 'Deactivated At')).toHaveText('—')
})

test('a list column is shown as chips, without the nulls its JSON holds', async ({ page }) => {
  await mockPlanDetail(page)
  await page.goto('/plans/1')
  await allocatorRows(page).first().click()
  const detail = detailRows(page).first()
  // districts is stored as ["Sadra", null]: one chip, and no "null" in sight
  await expect(field(detail, 'Districts').locator('.chip')).toHaveText(['Sadra'])
  await expect(detail).not.toContainText('null')
  // vendors is null, so it reads as an empty value rather than an empty list
  await expect(field(detail, 'Vendors')).toHaveText('—')
})

test('listing and duration are shown once and edited for every allocator', async ({ page }) => {
  const state = await mockPlanDetail(page)
  await page.goto('/plans/1')
  const bar = section(page).locator('.shared-bar')
  await expect(bar).toContainText('Listing')
  await expect(bar).toContainText('kerman-daily-foodZooket')
  await expect(bar).toContainText('Duration')
  await expect(bar).toContainText('Same for every allocator of this plan')

  await section(page).getByRole('button', { name: 'Edit for all', exact: true }).click()
  await expect(dialog(page)).toContainText('updates all 2 of them')
  await dialog(page).locator('#plan-listing').click()
  await page.getByRole('option', { name: 'kerman-weekly-foodZooket', exact: true }).click()
  await dialog(page).locator('#plan-duration').fill('30')
  await dialogButton(page, 'Save for all allocators').click()

  await expect(dialog(page)).toHaveCount(0)
  await expect(section(page).getByText('Updated 2 allocators of this plan.')).toBeVisible()
  await expect(bar).toContainText('kerman-weekly-foodZooket')
  await expect(bar).toContainText('30')
  expect(state.writes).toEqual([
    { kind: 'plan', plan_id: '1', body: { listing_id: 'kerman-weekly-foodZooket', duration: 30 } },
  ])
})

test('the listing field only takes a name from the list', async ({ page }) => {
  const state = await mockPlanDetail(page)
  await page.goto('/plans/1')
  await section(page).getByRole('button', { name: 'Edit for all', exact: true }).click()
  const listing = dialog(page).locator('#plan-listing')
  await listing.click()
  // one list for all cities, no per-city lookup
  await expect(page.getByRole('option', { name: 'tehran-daily-foodZooket', exact: true })).toBeVisible()
  await expect(page.getByRole('option', { name: 'kerman-daily-foodZooket', exact: true })).toBeVisible()
  // typing narrows the list, but is not itself a value
  await listing.fill('kerman')
  await expect(page.getByRole('option', { name: 'tehran-daily-foodZooket', exact: true })).toHaveCount(0)
  await page.getByRole('option', { name: 'kerman-weekly-foodZooket', exact: true }).click()
  await expect(listing).toHaveValue('kerman-weekly-foodZooket')
  await dialogButton(page, 'Save for all allocators').click()
  await expect(dialog(page)).toHaveCount(0)
  expect(state.writes[0].body.listing_id).toBe('kerman-weekly-foodZooket')
})

test('editing an allocator updates its row and logs the previous values', async ({ page }) => {
  const state = await mockPlanDetail(page)
  await page.goto('/plans/1')
  await allocatorRows(page).first().getByRole('button', { name: 'Edit', exact: true }).click()
  await expect(dialog(page)).toContainText('Edit allocator')
  await expect(dialog(page)).toContainText('written to the change log')
  // the identifying fields are required, the rest optional
  await expect(dialog(page).getByText('Allocator ID').locator('..')).toContainText('required')
  await expect(dialog(page).getByText('Districts').locator('..')).toContainText('(optional)')

  const ratio = dialog(page).locator('#config-impact_ratio')
  await expect(ratio).toHaveAttribute('type', 'number')
  await ratio.fill('0.75')
  await dialogButton(page, 'Save changes').click()

  await expect(dialog(page)).toHaveCount(0)
  await expect(section(page).getByText('Allocator updated.')).toBeVisible()
  expect(state.writes).toHaveLength(1)
  expect(state.writes[0]).toMatchObject({ kind: 'edit', id: 2 })
  expect(state.writes[0].body.impact_ratio).toBe(0.75)
  // the plan link and the shared columns are never sent per allocator
  expect(state.writes[0].body).not.toHaveProperty('plan_id')
  expect(state.writes[0].body).not.toHaveProperty('listing_id')
  expect(state.writes[0].body).not.toHaveProperty('duration')
  // the row kept its identity: same two allocators, nothing deactivated
  await expect(allocatorRows(page)).toHaveCount(2)
  await expect(allocatorRows(page).first().locator('.ratio')).toHaveText('75%')
  expect(state.deactivated).toEqual([])
})

test('a list column is edited by adding and removing values', async ({ page }) => {
  const state = await mockPlanDetail(page)
  await page.goto('/plans/1')
  await allocatorRows(page).first().getByRole('button', { name: 'Edit', exact: true }).click()
  // the stored ["Sadra", null] arrives as one editable chip
  await expect(dialog(page).locator('.tag-field .chip .chip-name')).toHaveText(['Sadra'])

  const districts = dialog(page).locator('#config-districts')
  await districts.fill('District 9')
  await districts.press('Enter')
  await expect(dialog(page).locator('.tag-field .chip .chip-name')).toHaveText(['Sadra', 'District 9'])

  await dialog(page).getByRole('button', { name: 'Remove Districts Sadra' }).click()
  await expect(dialog(page).locator('.tag-field .chip .chip-name')).toHaveText(['District 9'])

  await dialogButton(page, 'Save changes').click()
  await expect(dialog(page)).toHaveCount(0)
  // stored back as the JSON list the column holds, without the null
  expect(state.writes[0].body.districts).toBe('["District 9"]')
})

test('a row can be deactivated behind a confirmation', async ({ page }) => {
  const state = await mockPlanDetail(page)
  await page.goto('/plans/1')
  await allocatorRows(page).first().getByRole('button', { name: 'Deactivate', exact: true }).click()
  await expect(dialog(page)).toContainText('Deactivate allocator')
  await expect(dialog(page)).toContainText('foodZooket-kerman-3T-range-base-20260905')
  await expect(dialog(page)).toContainText('Nothing is deleted')
  await dialogButton(page, 'Deactivate').click()

  await expect(dialog(page)).toHaveCount(0)
  await expect(section(page).getByText('Allocator deactivated.')).toBeVisible()
  expect(state.writes).toEqual([{ kind: 'deactivate', id: 2 }])
  await expect(allocatorRows(page)).toHaveCount(1)
  await expect(section(page).getByText('1 allocator', { exact: true })).toBeVisible()
  await section(page).getByRole('button', { name: 'Show deactivated (1)', exact: true }).click()
  const off = allocatorRows(page).last()
  await expect(off).toHaveClass(/is-deactivated/)
  // a deactivated row offers no actions
  await expect(off.getByRole('button', { name: 'Edit', exact: true })).toHaveCount(0)
  await expect(off.getByRole('button', { name: 'Deactivate', exact: true })).toHaveCount(0)
})

test('adding an allocator searches the available allocators and rules', async ({ page }) => {
  const state = await mockPlanDetail(page)
  await page.goto('/plans/1')
  await section(page).getByRole('button', { name: '+ Add allocator', exact: true }).click()
  await expect(dialog(page)).toContainText('Add allocator')
  // the plan already has allocators, so listing and duration are inherited
  await expect(dialog(page)).toContainText('kerman-daily-foodZooket')
  await expect(dialog(page).locator('#add-listing')).toHaveCount(0)

  const allocator = dialog(page).locator('#config-allocator_id')
  await expect(allocator).toHaveAttribute('role', 'combobox')
  await allocator.click()
  await allocator.fill('kish')
  await expect(page.getByRole('option', { name: 'foodZooket-kish-1T-base', exact: true })).toBeVisible()
  await page.getByRole('option', { name: 'foodZooket-kish-1T-base', exact: true }).click()
  await expect(allocator).toHaveValue('foodZooket-kish-1T-base')

  const rule = dialog(page).locator('#config-rule_name')
  await rule.click()
  await expect(page.getByRole('option', { name: 'foodZooket-kish-1step-base', exact: true })).toBeVisible()
  await page.getByRole('option', { name: 'foodZooket-kish-1step-base', exact: true }).click()

  await dialog(page).locator('#config-impact_ratio').fill('0.25')
  await dialogButton(page, 'Add allocator').click()

  await expect(dialog(page)).toHaveCount(0)
  await expect(section(page).getByText('Allocator added.')).toBeVisible()
  await expect(allocatorRows(page)).toHaveCount(3)
  expect(state.writes).toHaveLength(1)
  expect(state.writes[0]).toMatchObject({
    kind: 'add',
    body: {
      plan_id: '1', allocator_id: 'foodZooket-kish-1T-base',
      rule_name: 'foodZooket-kish-1step-base', impact_ratio: 0.25,
    },
  })
  expect(state.writes[0].body).not.toHaveProperty('listing_id')
  expect(state.writes[0].body).not.toHaveProperty('duration')
})

test('the first allocator of a plan also sets its listing and duration', async ({ page }) => {
  const state = await mockPlanDetail(page, { configs: [] })
  await page.goto('/plans/1')
  await expect(section(page).getByText('No base configs for this plan yet.')).toBeVisible()
  await section(page).getByRole('button', { name: '+ Add allocator', exact: true }).click()
  await expect(dialog(page)).toContainText('first allocator of plan 1')
  await expect(dialog(page).locator('#add-listing')).toBeVisible()
  await expect(dialog(page).locator('#add-duration')).toBeVisible()

  // required fields are checked before anything is sent
  await dialogButton(page, 'Add allocator').click()
  await expect(dialog(page).locator('.form-error')).toContainText("'Allocator ID' is required")
  expect(state.writes).toHaveLength(0)

  await dialog(page).locator('#add-listing').click()
  await page.getByRole('option', { name: 'kerman-daily-foodZooket', exact: true }).click()
  await dialog(page).locator('#add-duration').fill('1')
  await dialog(page).locator('#config-allocator_id').click()
  await page.getByRole('option', { name: 'foodZooket-kish-1T-base', exact: true }).click()
  await dialog(page).locator('#config-rule_name').click()
  await page.getByRole('option', { name: 'foodZooket-kish-1step-base', exact: true }).click()
  await dialog(page).locator('#config-impact_ratio').fill('1')
  await dialogButton(page, 'Add allocator').click()
  await expect(dialog(page)).toHaveCount(0)
  expect(state.writes[0].body).toMatchObject({
    plan_id: '1', listing_id: 'kerman-daily-foodZooket', duration: 1, impact_ratio: 1,
  })
})

test('a lookup outage says so instead of accepting a typed name', async ({ page }) => {
  const state = await mockPlanDetail(page, { lookupError: 'Could not reach the allocators service' })
  await page.goto('/plans/1')
  await section(page).getByRole('button', { name: '+ Add allocator', exact: true }).click()
  await dialog(page).locator('#config-allocator_id').click()
  await expect(dialog(page)).toContainText('allocator lookup unavailable')

  // the value can only come from the list, so a typed name is not accepted
  await dialog(page).locator('#config-allocator_id').fill('typed-by-hand')
  await dialog(page).locator('#config-rule_name').fill('typed-rule')
  await dialog(page).locator('#config-impact_ratio').fill('0.5')
  await dialogButton(page, 'Add allocator').click()
  await expect(dialog(page).locator('.form-error')).toContainText("'Allocator ID' is required")
  await expect(dialog(page)).toBeVisible()
  expect(state.writes).toHaveLength(0)
})

test('a failed write keeps the popup open and shows the reason', async ({ page }) => {
  const state = await mockPlanDetail(page, { writeError: 'Cannot connect to the database' })
  await page.goto('/plans/1')
  await section(page).getByRole('button', { name: 'Edit for all', exact: true }).click()
  await dialogButton(page, 'Save for all allocators').click()
  await expect(dialog(page).locator('.form-error')).toContainText('Cannot connect to the database')
  await expect(dialog(page)).toBeVisible()
  await expect(page.locator('.toast')).toHaveCount(0)
  expect(state.writes).toHaveLength(1)
})

test('a row dropdown loads its logged previous versions on demand', async ({ page }) => {
  await mockPlanDetail(page)
  await page.goto('/plans/1')
  await allocatorRows(page).first().click()
  const detail = detailRows(page).first()
  await detail.getByRole('button', { name: 'Change history', exact: true }).click()
  await expect(detail.locator('.history-item')).toHaveCount(1)
  const latest = detail.locator('.history-item').first()
  await expect(latest).toContainText('previous values')
  await expect(latest.locator('.history-when')).toContainText(/2026/)
  await expect(latest).not.toContainText('2026-09-14T10:11:16')
  await expect(field(latest, 'Impact Ratio')).toHaveText('0.7')
  await expect(field(latest, 'Clustering Method')).toHaveText('dbscan')
  await expect(latest.getByText('Log ID', { exact: true })).toHaveCount(0)
  await expect(latest.getByText('Plan ID', { exact: true })).toHaveCount(0)
  await detail.getByRole('button', { name: 'Hide change history', exact: true }).click()
  await expect(detail.locator('.history-item')).toHaveCount(0)
  await detail.getByRole('button', { name: 'Change history (1)', exact: true }).click()
  await expect(detail.locator('.history-item')).toHaveCount(1)
})

test('expand all opens every allocator and collapse all closes them', async ({ page }) => {
  await mockPlanDetail(page)
  await page.goto('/plans/1')
  await section(page).getByRole('button', { name: 'Expand all', exact: true }).click()
  await expect(detailRows(page)).toHaveCount(2)
  await section(page).getByRole('button', { name: 'Collapse all', exact: true }).click()
  await expect(detailRows(page)).toHaveCount(0)
})

test('deactivated configs stay hidden until asked for', async ({ page }) => {
  await mockPlanDetail(page, {
    deactivated: [makeConfig({ id: 3, impact_ratio: 0.2, deactivated_at: '2026-09-12T08:00:00' })],
  })
  await page.goto('/plans/1')
  await expect(allocatorRows(page)).toHaveCount(2)
  await section(page).getByRole('button', { name: 'Show deactivated (1)', exact: true }).click()
  await expect(allocatorRows(page)).toHaveCount(3)
  await expect(allocatorRows(page).last()).toContainText('Deactivated')
  await expect(section(page).getByText('2 allocators')).toBeVisible()
  await expect(section(page).getByText('1 deactivated')).toBeVisible()
  await section(page).getByRole('button', { name: 'Hide deactivated', exact: true }).click()
  await expect(allocatorRows(page)).toHaveCount(2)
})

test('a failing base-config lookup keeps the plan on screen with a retry', async ({ page }) => {
  await mockPlanDetail(page, {
    configError: "Table 'incentive/incentive_base_configs' does not exist in the database.",
  })
  await page.goto('/plans/1')
  await expect(page.getByRole('heading', { name: 'Plan #1' })).toBeVisible()
  await expect(page.getByText('DAILY (#1)')).toBeVisible()
  await expect(allocatorRows(page)).toHaveCount(0)
  await expect(section(page).getByText(/does not exist in the database/)).toBeVisible()
  await expect(section(page).getByRole('button', { name: 'Retry', exact: true })).toBeVisible()
})
