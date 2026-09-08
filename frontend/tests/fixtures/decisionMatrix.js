// Test-only API fixtures. All /api requests are intercepted; no real DB writes.
export const columns = [
  { name: 'id', type: 'bigint unsigned', key: 'PRI', extra: 'auto_increment' },
  { name: 'incentive_type', type: 'int' },
  { name: 'city_group', type: 'varchar(100)' },
  { name: 'score_type', type: 'varchar(100)' },
  { name: 'score', type: 'int unsigned' },
  { name: 'target_increase', type: 'decimal(10,4)', nullable: false, default: null },
  { name: 'pr_increase', type: 'decimal(10,4)', nullable: false, default: null },
  { name: 'control_bucket', type: 'json', nullable: true, default: null },
  { name: 'created_at', type: 'datetime' },
  { name: 'deactivated_at', type: 'datetime', nullable: true },
]
export const incentiveTypes = [{ id: 1, name: 'DAILY' }, { id: 2, name: 'WEEKLY' }]

export function makeStep(overrides = {}) {
  return {
    id: 1, incentive_type: 1, city_group: 'Group A', score_type: 'Delivery', score: 1,
    target_increase: 0.125, pr_increase: 1.75, control_bucket: null,
    created_at: '2026-09-08T12:00:00', deactivated_at: null,
    ...overrides,
  }
}

export async function mockDecisionMatrix(page, options = {}) {
  const state = {
    rows: structuredClone(options.rows || []),
    groups: ['Group A', 'Group B', "O'Hare / A&B"],
    types: [...incentiveTypes], columns: structuredClone(columns),
    writes: [], reads: [], groupError: '', typeError: '', matrixError: '', saveError: '', deactivateError: '',
    groupDelays: {},
    ...options,
  }
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const reply = (data, status = 200) => route.fulfill({ status, json: data })
    const fail = (message, status = 503) => reply({ status: 'error', message }, status)
    if (url.pathname === '/api/incentive-types') {
      return state.typeError ? fail(state.typeError) : reply({ rows: state.types })
    }
    if (url.pathname === '/api/decision-matrix/city-groups') {
      return state.groupError ? fail(state.groupError) : reply({ rows: state.groups.map((city_group) => ({ city_group })) })
    }
    if (url.pathname === '/api/decision-matrix' && request.method() === 'GET') {
      const cityGroup = url.searchParams.get('city_group')
      state.reads.push(cityGroup)
      if (state.groupDelays[cityGroup]) await state.groupDelays[cityGroup]
      if (state.matrixError) return fail(state.matrixError)
      const allRows = state.rows.filter((row) => row.city_group === cityGroup)
      const grouped = new Map()
      for (const row of allRows) {
        const key = JSON.stringify([row.incentive_type, row.score_type])
        if (!grouped.has(key)) grouped.set(key, {
          incentive_type: row.incentive_type, score_type: row.score_type,
          next_score: 1, active_count: 0, deactivated_count: 0,
        })
        const item = grouped.get(key)
        if (row.deactivated_at === null) {
          item.next_score = Math.max(item.next_score, row.score + 1)
          item.active_count++
        } else item.deactivated_count++
      }
      return reply({
        city_group: cityGroup, columns: state.columns, series: [...grouped.values()],
        rows: allRows
          .filter((row) => url.searchParams.get('include_deactivated') === 'true' || row.deactivated_at === null)
          .map((row) => ({ ...row, incentive_type_name: state.types.find((type) => type.id === row.incentive_type)?.name })),
      })
    }
    if (url.pathname === '/api/decision-matrix' && request.method() === 'POST') {
      const payload = request.postDataJSON()
      state.writes.push({ action: 'add', payload })
      if (state.saveError) return fail(state.saveError)
      const existing = state.rows.filter((row) => row.city_group === payload.city_group &&
        String(row.incentive_type) === String(payload.incentive_type) && row.score_type === payload.score_type && row.deactivated_at === null)
      const chosen = payload.score ?? Math.max(0, ...existing.map((row) => row.score)) + 1
      if (existing.some((row) => row.score === chosen)) return fail(`Score ${chosen} is already active for this score type. Choose another score.`, 409)
      const float = (value) => typeof value === 'number' && Number.isFinite(value)
      if (!float(payload.target_increase) || !float(payload.pr_increase)) return fail('Target and PR must be non-null floats.', 400)
      if (payload.control_bucket !== null && (!Array.isArray(payload.control_bucket) || payload.control_bucket.length !== 3 || !payload.control_bucket.every(float))) {
        return fail('Control bucket must be null or three floats.', 400)
      }
      const row = makeStep({
        ...payload, id: Math.max(0, ...state.rows.map((row) => row.id)) + 1,
        incentive_type: Number(payload.incentive_type), score: chosen,
        target_increase: Number(payload.target_increase), pr_increase: Number(payload.pr_increase),
        control_bucket: payload.control_bucket === null ? null : payload.control_bucket,
      })
      state.rows.push(row)
      return reply({ status: 'ok', message: `Score ${chosen} added successfully.`, row })
    }
    const deactivate = /^\/api\/decision-matrix\/(\d+)\/deactivate$/.exec(url.pathname)
    if (deactivate && request.method() === 'POST') {
      state.writes.push({ action: 'deactivate', id: Number(deactivate[1]) })
      if (state.deactivateError) return fail(state.deactivateError)
      const row = state.rows.find((row) => row.id === Number(deactivate[1]))
      if (!row) return fail('Score step not found.', 404)
      row.deactivated_at ||= '2026-09-08T13:00:00'
      return reply({ status: 'ok', message: 'Score step deactivated successfully.', active: false })
    }
    if (url.pathname.startsWith('/api/health')) return reply({ status: 'ok' })
    return fail(`Unmocked API route: ${request.method()} ${url.pathname}`, 404)
  })
  return state
}
