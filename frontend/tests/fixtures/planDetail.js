// Test-only API fixtures for the plan detail page (/plans/:id).
// All /api requests are intercepted; no real database is touched.

// incentive.incentive_base_configs, as the API reports it.
export const baseConfigColumns = [
  { name: 'id', type: 'bigint unsigned', key: 'PRI', extra: 'auto_increment' },
  { name: 'plan_id', type: 'bigint unsigned' },
  { name: 'listing_id', type: 'varchar(100)' },
  { name: 'allocator_id', type: 'varchar(100)' },
  { name: 'rule_name', type: 'varchar(100)' },
  { name: 'impact_ratio', type: 'decimal(10,4)' },
  { name: 'duration', type: 'int' },
  { name: 'districts', type: 'varchar(255)', nullable: true },
  { name: 'vendors', type: 'varchar(255)', nullable: true },
  { name: 'batch_size', type: 'int' },
  { name: 'clustering_method', type: 'varchar(50)' },
  { name: 'sensitivity_id', type: 'varchar(100)', nullable: true },
  { name: 'sensitivity_group', type: 'varchar(100)', nullable: true },
]

export const summaryColumns = ['listing_id', 'allocator_id', 'rule_name', 'impact_ratio']

export function makeConfig(overrides = {}) {
  return {
    id: 1, plan_id: 1, listing_id: 'kerman-daily-foodZooket',
    allocator_id: 'foodZooket-kerman-3T-range-base',
    rule_name: 'foodZooket-kerman-3step-base', impact_ratio: 0.4,
    duration: 1, districts: '', vendors: '', batch_size: 0,
    clustering_method: 'kmeans', sensitivity_id: '', sensitivity_group: '',
    ...overrides,
  }
}

// Two allocators of plan 1, as the API returns them (listing, then ratio desc).
export const sampleConfigs = [
  makeConfig({
    id: 2, allocator_id: 'foodZooket-kerman-3T-range-base-20260905',
    rule_name: 'foodZooket-kerman-3step-base-20260616', impact_ratio: 0.6,
  }),
  makeConfig({ id: 1, impact_ratio: 0.4 }),
]

export async function mockPlanDetail(page, options = {}) {
  const state = {
    planId: '1',
    plan: {
      id: 1, city_id: 'kerman', incentive_type_id: 1, business_entity: 'foodZooket',
      created_at: '2026-09-05T10:00:00', deactivated_at: null,
    },
    types: [{ id: 1, name: 'DAILY' }],
    cities: [{ city_id: 'kerman', city_name: 'Kerman' }],
    configs: structuredClone(sampleConfigs),
    planError: '', configError: '',
    ...options,
  }

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const reply = (data, status = 200) => route.fulfill({ status, json: data })
    const fail = (message, status = 503) => reply({ status: 'error', message }, status)

    if (url.pathname === '/api/incentive-base-configs') {
      if (state.configError) return fail(state.configError, 404)
      const planId = url.searchParams.get('plan_id')
      const rows = state.configs.filter((row) => String(row.plan_id) === String(planId))
      return reply({
        plan_id: planId,
        columns: structuredClone(baseConfigColumns),
        summary_columns: [...summaryColumns],
        rows,
        total: rows.length,
        impact_ratio_sum: rows.length
          ? rows.reduce((sum, row) => sum + row.impact_ratio, 0)
          : null,
      })
    }
    if (url.pathname === `/api/city-plan-mappings/${state.planId}`) {
      return state.planError
        ? fail(state.planError, 404)
        : reply({ columns: [], row: structuredClone(state.plan) })
    }
    if (url.pathname === '/api/incentive-types') return reply({ rows: state.types })
    if (url.pathname === '/api/cities') {
      return reply({
        columns: [{ name: 'city_id' }, { name: 'city_name' }],
        rows: state.cities,
      })
    }
    return reply({ status: 'error', message: 'Not found' }, 404)
  })

  return state
}
