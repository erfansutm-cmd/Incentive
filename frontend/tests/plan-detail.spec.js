import { test, expect } from '@playwright/test'
import { mockPlanDetail, makeConfig } from './fixtures/planDetail'

test.afterEach(async ({ page }) => {
  expect(await page.pageErrors()).toEqual([])
})

const section = (page) => page.getByRole('region', { name: 'Base configs', exact: true })
const allocatorRows = (page) => section(page).locator('tr.config-row')
const detailRows = (page) => section(page).locator('tr.detail-row')

test('allocators are listed with only the four summary columns up front', async ({ page }) => {
  await mockPlanDetail(page)
  await page.goto('/plans/1')
  await expect(allocatorRows(page)).toHaveCount(2)
  await expect(section(page).getByRole('columnheader')).toHaveText([
    'Details', 'Listing ID', 'Allocator ID', 'Rule Name', 'Impact Ratio',
  ])
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
  await expect(section(page).getByText('2 allocators')).toBeVisible()
  await expect(section(page).getByText('impact 100%')).toBeVisible()
})

test('a row dropdown reveals the rest of the config and closes again', async ({ page }) => {
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
  ]) {
    await expect(detail.getByText(label, { exact: true })).toBeVisible()
  }
  await expect(detail.getByText('kmeans', { exact: true })).toBeVisible()
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
