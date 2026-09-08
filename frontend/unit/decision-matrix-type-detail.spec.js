import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import DecisionMatrixTypeDetail from '../src/views/DecisionMatrixTypeDetail.vue'
import DecisionMatrix from '../src/views/DecisionMatrix.vue'

// ---- fixtures (mirror tests/fixtures/decisionMatrix.js) ------------------
const makeStep = (o = {}) => ({
  id: 1, incentive_type: 1, city_group: 'Group A', score_type: 'Delivery', score: 1,
  target_increase: 0.125, pr_increase: 1.75, control_bucket: [0.2, 0.2, 0.1],
  created_at: '2026-09-08T12:00:00', deactivated_at: null, ...o,
})

function matrixPayload(cityGroup, rows) {
  const all = rows.map((r) => ({ ...r, score_type: scoreTypeValueFor(r.score_type) }))
  const grouped = new Map()
  for (const row of all) {
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
  return { city_group: cityGroup, columns: [], series: [...grouped.values()], rows: all }
}
// Mirrors the real score-type mapping: only known presets change, custom names
// keep their spelling (so 'Delivery' stays 'Delivery').
const SCORE_TYPES = new Map([
  ['performance', 'performance'], ['weather', 'weather'],
  ['order_level_increase', 'order_level_increase'], ['order level increase', 'order_level_increase'],
])
function scoreTypeValueFor(v) {
  return SCORE_TYPES.get(String(v).trim().toLowerCase()) ?? v
}

const types = [{ id: 1, name: 'DAILY' }, { id: 2, name: 'WEEKLY' }]

// ---- fetch mock ----------------------------------------------------------
let state
function installFetch(rows) {
  state = { rows: structuredClone(rows), writes: [] }
  global.fetch = vi.fn(async (url, options = {}) => {
    const u = new URL(url, 'http://localhost')
    const json = (data, ok = true, status = 200) => ({ ok, status, json: async () => data })
    if (u.pathname === '/api/incentive-types') return json({ rows: types })
    if (u.pathname === '/api/decision-matrix' && (!options.method || options.method === 'GET')) {
      const g = u.searchParams.get('city_group')
      const all = state.rows.filter((r) => r.city_group === g)
      const withNames = all.map((r) => ({ ...r, incentive_type_name: types.find((t) => t.id === r.incentive_type)?.name }))
      return json({ ...matrixPayload(g, all), rows: withNames })
    }
    if (u.pathname === '/api/decision-matrix' && options.method === 'POST') {
      const p = JSON.parse(options.body)
      state.writes.push(p)
      const row = makeStep({ ...p, id: 99, incentive_type: Number(p.incentive_type), score: Number(p.score) })
      state.rows.push(row)
      return json({ status: 'ok', message: 'Score 3 added successfully.', row })
    }
    const deact = /^\/api\/decision-matrix\/(\d+)\/deactivate$/.exec(u.pathname)
    if (deact && options.method === 'POST') {
      const row = state.rows.find((r) => r.id === Number(deact[1]))
      if (row) row.deactivated_at = '2026-09-08T13:00:00'
      return json({ status: 'ok', message: 'Score step deactivated successfully.', active: false })
    }
    if (u.pathname === '/api/decision-matrix/city-groups') return json({ rows: [{ city_group: 'Group A' }, { city_group: 'Group B' }] })
    return json({ status: 'error', message: `unmocked ${u.pathname}` }, false, 404)
  })
}

// ---- happy-dom dialog shims ----------------------------------------------
beforeAll(() => {
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
    HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
  }
})

function makeRouter(path) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/decision-matrix', name: 'decision-matrix', component: DecisionMatrix },
      { path: '/decision-matrix/type', name: 'decision-matrix-type', component: DecisionMatrixTypeDetail },
    ],
  })
  return router
}

afterEach(() => vi.restoreAllMocks())

describe('decision-matrix/type dedicated page', () => {
  it('renders the incentive type + city group header and only that type\'s steps', async () => {
    installFetch([
      makeStep(),
      makeStep({ id: 2, score: 2 }),
      makeStep({ id: 3, score: 3, deactivated_at: '2026-09-08T13:00:00' }),
      makeStep({ id: 4, score_type: 'Weather' }),
      makeStep({ id: 5, incentive_type: 2, score_type: 'Weather' }), // other type: must NOT appear
    ])
    const router = makeRouter('/decision-matrix/type')
    await router.push('/decision-matrix/type?city_group=Group%20A&type=1')
    await router.isReady()
    const wrapper = mount(DecisionMatrixTypeDetail, { global: { plugins: [router] } })
    await flushPromises()
    await flushPromises()

    const text = wrapper.text()
    // header: type name + id + city group
    expect(text).toContain('DAILY')
    expect(text).toContain('#1')
    expect(text).toContain('Group A')
    // only this type's score types/steps appear
    expect(text).toContain('Delivery')
    expect(text).toContain('Weather')
    // other incentive type (WEEKLY / type 2) is not rendered
    expect(text).not.toContain('WEEKLY')
    // steps of this type are shown
    expect(text).toContain('ID 1')
    expect(text).toContain('ID 2')
    // action buttons from the first page exist
    expect(text).toContain('+ Add score type')
    expect(text).toContain('+ Add step')
    expect(text).toContain('Show deactivated')
  })

  it('adds a step from the dedicated page (full flow)', async () => {
    installFetch([makeStep()])
    const router = makeRouter('/decision-matrix/type')
    await router.push('/decision-matrix/type?city_group=Group%20A&type=1')
    await router.isReady()
    const wrapper = mount(DecisionMatrixTypeDetail, { global: { plugins: [router] } })
    await flushPromises()
    await flushPromises()

    // Open the add-step form
    await wrapper.findAll('button').find((b) => b.text().includes('+ Add step')).trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Add step')

    // Fill the required floats and submit
    const form = wrapper.find('form')
    const inputs = form.findAll('input[type="number"]')
    const scoreInput = inputs.find((i) => i.attributes('aria-describedby') === 'matrix-score-hint')
    await scoreInput.setValue('3')
    const target = form.findAll('input').find((i) => i.attributes('placeholder') === 'Enter a float')
    await target.setValue('0.5')
    const prInputs = form.findAll('input[placeholder="Enter a float"]')
    await prInputs[1].setValue('1.25')
    await form.trigger('submit')
    await flushPromises()
    await flushPromises()

    expect(state.writes.length).toBe(1)
    expect(state.writes[0]).toMatchObject({ city_group: 'Group A', incentive_type: 1, score: 3 })
    // New step now appears
    expect(wrapper.text()).toContain('ID 99')
  })

  it('main page shows an Open link per type pointing at the dedicated page', async () => {
    installFetch([makeStep()])
    const router = makeRouter('/decision-matrix')
    await router.push('/decision-matrix')
    await router.isReady()
    const wrapper = mount(DecisionMatrix, { global: { plugins: [router] } })
    await flushPromises()
    await flushPromises()

    const groupButton = wrapper.findAll('button')
      .find((b) => b.attributes('aria-label') === 'City group Group A')
    expect(groupButton).toBeTruthy()
    await groupButton.trigger('click')
    await flushPromises()
    await flushPromises()

    const openLink = wrapper.find('a.open-type')
    expect(openLink.exists()).toBe(true)
    expect(openLink.attributes('href')).toBe('/decision-matrix/type?city_group=Group%20A&type=1')
    expect(openLink.attributes('target')).toBe('_blank')
  })

  it('deactivates a step from the dedicated page', async () => {
    installFetch([makeStep()])
    const router = makeRouter('/decision-matrix/type')
    await router.push('/decision-matrix/type?city_group=Group%20A&type=1')
    await router.isReady()
    const wrapper = mount(DecisionMatrixTypeDetail, { global: { plugins: [router] } })
    await flushPromises()
    await flushPromises()

    await wrapper.findAll('button').find((b) => b.text().includes('Deactivate')).trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Deactivate score 1?')
    await wrapper.findAll('button').find((b) => b.text().includes('Deactivate step')).trigger('click')
    await flushPromises()
    await flushPromises()
    expect(state.rows[0].deactivated_at).not.toBeNull()
  })
})
