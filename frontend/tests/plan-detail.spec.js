import { test, expect } from '@playwright/test'
import { mockPlanDetail, makeConfig } from './fixtures/planDetail'

test.afterEach(async ({ page }) => {
  expect(await page.pageErrors()).toEqual([])
})

const section = (page) => page.getByRole('region', { name: 'Base configs', exact: true })
const allocatorRows = (page) => section(page).locator('tr.config-row')
const detailRows = (page) => section(page).locator('tr.detail-row')
// one field of a detail grid, by its label
const field = (scope, label) =>
  scope.locator('.detail-facts > div').filter({ hasText: label }).locator('dd')

test('allocators are listed with only the four summary columns up front', async ({ page }) => {
  await mockPlanDetail(page)
  await page.goto('/plans/1')
  await expect(allocatorRows(page)).toHaveCount(2)
  await expect(section(page).getByRole('columnheader')).toHaveText([
    'Details', 'Listing ID', 'Allocator ID', 'Rule Name', 'Impact Ratio',
  ])
  // no explanatory hint line under the heading
  await expect(section(page).locator('.hint')).toHaveCount(0)
  await expect(section(page).getByText(/open a row to see/)).toHaveCount(0)
  // the API orders a listing's allocators by impact_ratio, biggest first
  const first = allocatorRows(page).first()
  await expect(first).toContainText('kerman-daily-foodZooket')
  await expect(first).toContainText('foodZooket-kerman-3T-range-base-20260905')
  await expect(first).toContainText('foodZooket-kerman-3step-base-20260616')
  await expect(first.locator('.ratio')).toHaveText('60%')
  await expect(first.locator('.ratio-raw')).toHaveText('0.6')
  await expect(allocatorRows(page).nth(1).locator('.ratio')).toHaveText('40%')
  // everything else of the row stays behind its dropdown
  await expect(section(page).getByText('Clustering Method')).toHaveCount(0)
  await expect(section(page).getByText('kmeans', { exact: true })).toHaveCount(0)
  await expect(section(page).getByText('Batch Size')).toHaveCount(0)
  await expect(section(page).getByText('Updated At')).toHaveCount(0)
  await expect(section(page).getByText('2 allocators')).toBeVisible()
  await expect(section(page).getByText('impact 100%')).toBeVisible()
})

test('a row dropdown reveals the rest of the config with readable dates', async ({ page }) => {
  await mockPlanDetail(page)
  await page.goto('/plans/1')
  const toggle = section(page).getByRole('button', {
    name: 'Toggle details of allocator foodZooket-kerman-3T-range-base-20260905',
    exact: true,
  })
  await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  await toggle.click()
  await expect(detailRows(page)).toHaveCount(1)
  await expect(toggle).toHaveAttribute('aria-expanded', 'true')
  const detail = detailRows(page).first()
  for (const label of [
    'ID', 'Plan ID', 'Duration', 'Districts', 'Vendors', 'Batch Size',
    'Clustering Method', 'Sensitivity ID', 'Sensitivity Group',
    'Created At', 'Updated At', 'Deactivated At',
  ]) {
    await expect(detail.getByText(label, { exact: true })).toBeVisible()
  }
  await expect(detail.getByText('kmeans', { exact: true })).toBeVisible()
  await expect(field(detail, 'Batch Size')).toHaveText('0')
  await expect(field(detail, 'Deactivated At')).toHaveText('—')
  // the timestamps are formatted, never shown as raw ISO strings
  await expect(detail).not.toContainText('2026-09-14T10:11:16')
  await expect(detail).not.toContainText('2026-09-05T10:00:00')
  await expect(field(detail, 'Updated At')).toContainText(/2026/)
  await expect(field(detail, 'Updated At')).toContainText(/10:11/)
  await expect(field(detail, 'Created At')).toContainText(/10:00/)
  await toggle.click()
  await expect(detailRows(page)).toHaveCount(0)
})

test('clicking the row itself opens the same dropdown', async ({ page }) => {
  await mockPlanDetail(page)
  await page.goto('/plans/1')
  await allocatorRows(page).nth(1).click()
  await expect(detailRows(page)).toHaveCount(1)
  await expect(allocatorRows(page).nth(1)).toHaveClass(/expanded/)
  await expect(allocatorRows(page).first()).not.toHaveClass(/expanded/)
})

test('a row dropdown loads its logged previous versions on demand', async ({ page }) => {
  await mockPlanDetail(page)
  await page.goto('/plans/1')
  await section(page).getByRole('button', {
    name: 'Toggle details of allocator foodZooket-kerman-3T-range-base-20260905',
    exact: true,
  }).click()
  const detail = detailRows(page).first()
  await expect(detail.getByRole('button', { name: 'Change history', exact: true })).toBeVisible()
  await expect(detail.locator('.history-item')).toHaveCount(0)

  await detail.getByRole('button', { name: 'Change history', exact: true }).click()
  await expect(detail.locator('.history-item')).toHaveCount(2)
  await expect(detail.getByRole('button', { name: 'Hide change history', exact: true })).toBeVisible()

  // newest first: the values the config had before its last change
  const latest = detail.locator('.history-item').first()
  await expect(latest).toContainText('previous values')
  await expect(latest.locator('.history-when')).toContainText(/2026/)
  await expect(latest).not.toContainText('2026-09-14T10:11:16')
  await expect(field(latest, 'Impact Ratio')).toHaveText('0.7')
  await expect(field(latest, 'Clustering Method')).toHaveText('dbscan')
  await expect(field(latest, 'Batch Size')).toHaveText('5')
  // the log's own bookkeeping columns are not repeated as fields
  await expect(latest.getByText('Log ID', { exact: true })).toHaveCount(0)
  await expect(latest.getByText('Config ID', { exact: true })).toHaveCount(0)
  await expect(latest.getByText('Changed At', { exact: true })).toHaveCount(0)
  await expect(field(latest, 'Updated At')).toContainText(/2026/)

  await detail.getByRole('button', { name: 'Hide change history', exact: true }).click()
  await expect(detail.locator('.history-item')).toHaveCount(0)
  await detail.getByRole('button', { name: 'Change history (2)', exact: true }).click()
  await expect(detail.locator('.history-item')).toHaveCount(2)
})

test('a config without logged changes says so', async ({ page }) => {
  await mockPlanDetail(page, { logs: {} })
  await page.goto('/plans/1')
  await allocatorRows(page).first().click()
  const detail = detailRows(page).first()
  await detail.getByRole('button', { name: 'Change history', exact: true }).click()
  await expect(detail.getByText('No previous versions recorded yet.')).toBeVisible()
  await expect(detail.locator('.history-item')).toHaveCount(0)
})

test('expand all opens every allocator and collapse all closes them', async ({ page }) => {
  await mockPlanDetail(page)
  await page.goto('/plans/1')
  await expect(allocatorRows(page)).toHaveCount(2)
  await section(page).getByRole('button', { name: 'Expand all', exact: true }).click()
  await expect(detailRows(page)).toHaveCount(2)
  await section(page).getByRole('button', { name: 'Collapse all', exact: true }).click()
  await expect(detailRows(page)).toHaveCount(0)
})

test('a single-allocator plan shows no expand-all control', async ({ page }) => {
  await mockPlanDetail(page, { configs: [makeConfig({ impact_ratio: 1 })] })
  await page.goto('/plans/1')
  await expect(allocatorRows(page)).toHaveCount(1)
  await expect(section(page).getByText('1 allocator', { exact: true })).toBeVisible()
  await expect(section(page).getByText('impact 100%')).toBeVisible()
  await expect(section(page).getByRole('button', { name: 'Expand all', exact: true })).toHaveCount(0)
})

test('deactivated configs stay hidden until asked for', async ({ page }) => {
  await mockPlanDetail(page, {
    deactivated: [makeConfig({ id: 3, impact_ratio: 0.2, deactivated_at: '2026-09-12T08:00:00' })],
  })
  await page.goto('/plans/1')
  await expect(allocatorRows(page)).toHaveCount(2)
  await section(page).getByRole('button', { name: 'Show deactivated (1)', exact: true }).click()
  await expect(allocatorRows(page)).toHaveCount(3)
  const off = allocatorRows(page).last()
  await expect(off).toHaveClass(/is-deactivated/)
  await expect(off).toContainText('Deactivated')
  // the counts and the plan's share keep describing the active allocators
  await expect(section(page).getByText('2 allocators')).toBeVisible()
  await expect(section(page).getByText('1 deactivated')).toBeVisible()
  await expect(section(page).getByText('impact 100%')).toBeVisible()
  await section(page).getByRole('button', { name: 'Hide deactivated', exact: true }).click()
  await expect(allocatorRows(page)).toHaveCount(2)
})

test('a plan without base configs shows an empty state', async ({ page }) => {
  await mockPlanDetail(page, { configs: [] })
  await page.goto('/plans/1')
  await expect(section(page).getByText('No base configs for this plan yet.')).toBeVisible()
  await expect(section(page).getByText('0 allocators')).toBeVisible()
  await expect(allocatorRows(page)).toHaveCount(0)
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
