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
  { name: 'created_at', type: 'datetime' },
  { name: 'updated_at', type: 'datetime', nullable: true },
  { name: 'deactivated_at', type: 'datetime', nullable: true },
]

// incentive.incentive_base_configs_logs: the config as it was before a change.
export const logColumns = [
  { name: 'log_id', type: 'bigint unsigned', key: 'PRI', extra: 'auto_increment' },
  { name: 'config_id', type: 'bigint unsigned' },
  ...baseConfigColumns.slice(1),
  { name: 'changed_at', type: 'datetime' },
]

export const summaryColumns = ['listing_id', 'allocator_id', 'rule_name', 'impact_ratio']

export function makeConfig(overrides = {}) {
  return {
    id: 1, plan_id: 1, listing_id: 'kerman-daily-foodZooket',
    allocator_id: 'foodZooket-kerman-3T-range-base',
    rule_name: 'foodZooket-kerman-3step-base', impact_ratio: 0.4,
    duration: 1, districts: '', vendors: '', batch_size: 0,
    clustering_method: 'kmeans', sensitivity_id: '', sensitivity_group: '',
    created_at: '2026-09-05T10:00:00', updated_at: '2026-09-14T10:11:16',
    deactivated_at: null,
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

// The logged previous versions of config 2, newest first.
export const sampleLogs = [
  makeConfig({
    id: undefined, log_id: 2, config_id: 2, impact_ratio: 0.7, batch_size: 5,
    clustering_method: 'dbscan', updated_at: '2026-09-10T09:00:00',
    changed_at: '2026-09-14T10:11:16',
    allocator_id: 'foodZooket-kerman-3T-range-base-20260905',
    rule_name: 'foodZooket-kerman-3step-base-20260616',
  }),
  makeConfig({
    id: undefined, log_id: 1, config_id: 2, impact_ratio: 0.6,
    updated_at: null, changed_at: '2026-09-10T09:00:00',
    allocator_id: 'foodZooket-kerman-3T-range-base-20260905',
    rule_name: 'foodZooket-kerman-3step-base-20260616',
  }),
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
    deactivated: [],
    logs: { 2: structuredClone(sampleLogs) },
    planError: '', configError: '', logError: '',
    ...options,
  }

  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const reply = (data, status = 200) => route.fulfill({ status, json: data })
    const fail = (message, status = 503) => reply({ status: 'error', message }, status)

    const logs = url.pathname.match(/^\/api\/incentive-base-configs\/(\d+)\/logs$/)
    if (logs) {
      if (state.logError) return fail(state.logError, 500)
      const rows = state.logs[logs[1]] || []
      return reply({
        config_id: logs[1], columns: structuredClone(logColumns), rows, total: rows.length,
      })
    }

    if (url.pathname === '/api/incentive-base-configs') {
      if (state.configError) return fail(state.configError, 404)
      const planId = url.searchParams.get('plan_id')
      const includeDeactivated = url.searchParams.get('include_deactivated') === 'true'
      const own = state.configs.filter((row) => String(row.plan_id) === String(planId))
      const rows = includeDeactivated ? [...own, ...state.deactivated] : own
      const activeRows = rows.filter((row) => !row.deactivated_at)
      return reply({
        plan_id: planId,
        include_deactivated: includeDeactivated,
        columns: structuredClone(baseConfigColumns),
        summary_columns: [...summaryColumns],
        rows,
        // the counts cover the deactivated rows even in the default fetch
        total: activeRows.length + state.deactivated.length,
        active_count: activeRows.length,
        deactivated_count: state.deactivated.length,
        impact_ratio_sum: activeRows.length
          ? activeRows.reduce((sum, row) => sum + row.impact_ratio, 0)
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
