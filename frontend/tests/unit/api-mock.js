// Test-only mock of the whole /api surface the plan detail page uses.
// Every request is intercepted, so the unit tests never need a database, the
// incentive services or a browser.
import { vi } from 'vitest'

// incentive.incentive_base_configs, as the API reports it
export const configColumns = [
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

// incentive.incentive_base_configs_logs: the config as it was before a change
export const logColumns = [
  { name: 'log_id', type: 'bigint unsigned', key: 'PRI', extra: 'auto_increment' },
  { name: 'config_id', type: 'bigint unsigned' },
  ...configColumns.slice(1),
  { name: 'changed_at', type: 'datetime' },
]

export const summaryColumns = ['allocator_id', 'rule_name', 'impact_ratio']

// what the three lookup services know about
export const lookupNames = {
  allocators: [
    'foodZooket-kerman-3T-range-base',
    'foodZooket-kerman-3T-range-base-20260905',
    'foodZooket-kish-1T-base',
  ],
  rules: [
    'foodZooket-kerman-3step-base',
    'foodZooket-kerman-3step-base-20260616',
    'foodZooket-kish-1step-base',
  ],
  // one list for every city: /queries/all
  listings: [
    'kerman-daily-foodZooket',
    'kerman-weekly-foodZooket',
    'tehran-daily-foodZooket',
  ],
}

export function makeRow(overrides = {}) {
  return {
    id: 1,
    plan_id: 1,
    listing_id: 'kerman-daily-foodZooket',
    allocator_id: 'foodZooket-kerman-3T-range-base',
    rule_name: 'foodZooket-kerman-3step-base',
    impact_ratio: 0.4,
    duration: 1,
    districts: '["Sadra", null]',
    vendors: null,
    batch_size: 0,
    clustering_method: 'kmeans',
    sensitivity_id: '',
    sensitivity_group: '',
    created_at: '2026-09-05T10:00:00',
    updated_at: '2026-09-14T10:11:16',
    deactivated_at: null,
    ...overrides,
  }
}

// two allocators of plan 1, listing then impact_ratio descending
export function sampleRows() {
  return [
    makeRow({
      id: 2,
      allocator_id: 'foodZooket-kerman-3T-range-base-20260905',
      rule_name: 'foodZooket-kerman-3step-base-20260616',
      impact_ratio: 0.6,
    }),
    makeRow({ id: 1, impact_ratio: 0.4 }),
  ]
}

// the logged previous versions of config 2, newest first
export function sampleLogs() {
  return [
    makeRow({
      id: undefined,
      log_id: 2,
      config_id: 2,
      allocator_id: 'foodZooket-kerman-3T-range-base-20260905',
      rule_name: 'foodZooket-kerman-3step-base-20260616',
      impact_ratio: 0.7,
      batch_size: 5,
      clustering_method: 'dbscan',
      districts: '["Sadra", "District 3", null]',
      updated_at: '2026-09-10T09:00:00',
      changed_at: '2026-09-14T10:11:16',
    }),
  ]
}

export function installMockApi(options = {}) {
  const state = {
    planId: '1',
    plan: { id: 1, city_id: 'kerman', incentive_type_id: 1, business_entity: 'foodZooket', created_at: '2026-09-05T10:00:00', deactivated_at: null },
    types: [{ id: 1, name: 'DAILY' }],
    cities: [{ city_id: 'kerman', city_name: 'kerman' }],
    configs: sampleRows(),
    deactivated: [],
    logs: { 2: sampleLogs() },
    lookups: structuredClone(lookupNames),
    nextId: 3,
    now: '2026-09-14T12:00:00',
    writes: [],
    planError: '',
    configError: '',
    logError: '',
    writeError: '',
    lookupError: '',
    ...options,
  }
  const calls = []
  const active = () => state.configs.filter((row) => !row.deactivated_at)

  global.fetch = vi.fn(async (url, init = {}) => {
    const u = new URL(String(url), 'http://unit.test')
    const method = (init.method || 'GET').toUpperCase()
    const body = init.body ? JSON.parse(init.body) : {}
    calls.push(`${method} ${u.pathname}${u.search}`)
    const json = (data, status = 200) => ({
      ok: status < 400,
      status,
      json: async () => data,
    })
    const fail = (message, status = 503) => json({ status: 'error', message }, status)

    // --- lookups ---------------------------------------------------------
    const lookup = u.pathname.match(/^\/api\/incentive-lookups\/(\w+)$/)
    if (lookup) {
      if (state.lookupError) return fail(state.lookupError, 502)
      const kind = lookup[1]
      const q = (u.searchParams.get('q') || '').toLowerCase()
      const names = (state.lookups[kind] || []).filter((n) => n.toLowerCase().includes(q))
      return json({
        kind,
        source: `mock/${kind}`,
        term: q,
        rows: names.map((name) => ({ name })),
        matched: names.length,
        total: names.length,
        truncated: false,
      })
    }

    // --- writes ----------------------------------------------------------
    const planPut = u.pathname.match(/^\/api\/incentive-base-configs\/plan\/(\d+)$/)
    if (planPut && method === 'PUT') {
      state.writes.push({ kind: 'plan', plan_id: planPut[1], body })
      if (state.writeError) return fail(state.writeError, 500)
      const targets = active().filter(
        (row) =>
          row.listing_id !== body.listing_id ||
          String(row.duration) !== String(body.duration)
      )
      for (const row of targets) {
        state.logs[row.id] = [
          { ...row, log_id: 900 + row.id, config_id: row.id, changed_at: state.now },
          ...(state.logs[row.id] || []),
        ]
        row.listing_id = body.listing_id
        row.duration = Number(body.duration)
        row.updated_at = state.now
      }
      return json({
        status: 'ok',
        logged: targets.length > 0,
        updated: targets.length,
        message: `Updated ${targets.length} allocator(s).`,
      })
    }

    const deactivate = u.pathname.match(/^\/api\/incentive-base-configs\/(\d+)\/deactivate$/)
    if (deactivate && method === 'POST') {
      state.writes.push({ kind: 'deactivate', id: Number(deactivate[1]) })
      if (state.writeError) return fail(state.writeError, 500)
      const row = state.configs.find((r) => r.id === Number(deactivate[1]))
      row.deactivated_at = state.now
      state.configs = state.configs.filter((r) => r.id !== row.id)
      state.deactivated.push(row)
      return json({ status: 'ok', logged: true, active: false })
    }

    if (u.pathname === '/api/incentive-base-configs' && method === 'POST') {
      state.writes.push({ kind: 'add', body })
      if (state.writeError) return fail(state.writeError, 500)
      const template = active()[0] || {}
      const hasActive = active().length > 0
      const created = {
        ...makeRow({}),
        ...body,
        id: state.nextId++,
        plan_id: Number(body.plan_id),
        listing_id: hasActive ? template.listing_id : body.listing_id,
        duration: hasActive ? template.duration : Number(body.duration),
        created_at: state.now,
        updated_at: null,
        deactivated_at: null,
      }
      state.configs.push(created)
      return json({
        status: 'ok',
        id: created.id,
        inherited: { listing_id: created.listing_id, duration: created.duration },
        row: structuredClone(created),
      })
    }

    const activate = u.pathname.match(/^\/api\/incentive-base-configs\/(\d+)\/activate$/)
    if (activate && method === 'POST') {
      state.writes.push({ kind: 'activate', id: Number(activate[1]) })
      if (state.writeError) return fail(state.writeError, 500)
      const row = state.deactivated.find((r) => r.id === Number(activate[1]))
      if (!row) return json({ status: 'ok', logged: false, active: true })
      state.logs[row.id] = [
        { ...row, log_id: 700 + row.id, config_id: row.id, changed_at: state.now },
        ...(state.logs[row.id] || []),
      ]
      row.deactivated_at = null
      row.updated_at = state.now
      state.deactivated = state.deactivated.filter((r) => r.id !== row.id)
      state.configs.push(row)
      return json({ status: 'ok', logged: true, active: true, row: structuredClone(row) })
    }

    const edit = u.pathname.match(/^\/api\/incentive-base-configs\/(\d+)$/)
    if (edit && method === 'PUT') {
      state.writes.push({ kind: 'edit', id: Number(edit[1]), body })
      if (state.writeError) return fail(state.writeError, 500)
      const shared = ['listing_id', 'duration'].filter((name) => name in body)
      if (shared.length) {
        return fail(
          `${shared.join(', ')} is shared by every allocator of the plan. ` +
            'Use PUT /api/incentive-base-configs/plan/{plan_id} to change it.',
          409
        )
      }
      const row = state.configs.find((r) => r.id === Number(edit[1]))
      if (!row) return fail('Base config not found.', 404)
      const changes = {}
      for (const [key, value] of Object.entries(body)) {
        const before = row[key] === null || row[key] === undefined ? '' : row[key]
        const after = value === null || value === undefined ? '' : value
        if (String(before) !== String(after)) changes[key] = { from: row[key], to: value }
      }
      if (!Object.keys(changes).length) {
        return json({
          status: 'ok', message: 'No changes to record.', logged: false,
          changes: {}, row: structuredClone(row),
        })
      }
      state.logs[row.id] = [
        { ...row, log_id: 800 + row.id, config_id: row.id, changed_at: state.now },
        ...(state.logs[row.id] || []),
      ]
      Object.assign(row, body, { updated_at: state.now })
      return json({
        status: 'ok', message: 'Base config updated successfully.', logged: true,
        log_id: state.logs[row.id][0].log_id, changes, row: structuredClone(row),
      })
    }

    const logs = u.pathname.match(/^\/api\/incentive-base-configs\/(\d+)\/logs$/)
    if (logs) {
      if (state.logError) return fail(state.logError, 500)
      const rows = state.logs[logs[1]] || []
      return json({
        config_id: logs[1],
        columns: structuredClone(logColumns),
        rows: structuredClone(rows),
        total: rows.length,
      })
    }

    if (u.pathname === '/api/incentive-base-configs' && method === 'GET') {
      if (state.configError) return fail(state.configError, 404)
      const planId = u.searchParams.get('plan_id')
      const includeDeactivated = u.searchParams.get('include_deactivated') === 'true'
      const own = state.configs.filter((row) => String(row.plan_id) === String(planId))
      const rows = includeDeactivated ? [...own, ...state.deactivated] : own
      const activeRows = rows.filter((row) => !row.deactivated_at)
      return json({
        plan_id: planId,
        include_deactivated: includeDeactivated,
        columns: structuredClone(configColumns),
        summary_columns: [...summaryColumns],
        // a fresh object every time, like a real response
        rows: structuredClone(rows),
        total: activeRows.length + state.deactivated.length,
        active_count: activeRows.length,
        deactivated_count: state.deactivated.length,
        impact_ratio_sum: activeRows.length
          ? activeRows.reduce((sum, row) => sum + row.impact_ratio, 0)
          : null,
      })
    }

    if (u.pathname === `/api/city-plan-mappings/${state.planId}`) {
      return state.planError
        ? fail(state.planError, 404)
        : json({ columns: [], row: structuredClone(state.plan) })
    }
    if (u.pathname === '/api/incentive-types') return json({ rows: state.types })
    if (u.pathname === '/api/cities') {
      return json({
        columns: [{ name: 'city_id' }, { name: 'city_name' }],
        rows: state.cities,
      })
    }
    return json({ status: 'error', message: 'Not found' }, 404)
  })

  return { state, calls }
}

// LookupSelect debounces its search by 200 ms
export const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

export const text = (wrappers) => wrappers.map((w) => w.text())

export function button(scope, label) {
  const found = scope.findAll('button').find((b) => b.text().trim() === label)
  if (!found) throw new Error(`No button labelled "${label}"`)
  return found
}
