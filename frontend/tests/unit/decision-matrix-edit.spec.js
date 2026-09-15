// Decision Matrix — editing a score step.
//
// Editing is one action that keeps the history complete: the row is
// deactivated and a new row with the new details is added. These tests drive
// the real views and the real edit form against a mocked /api (no backend, no
// database, no browser) and assert the request that reaches the server.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import DecisionMatrix from '../../src/views/DecisionMatrix.vue'
import DecisionMatrixStepEditForm from '../../src/components/DecisionMatrixStepEditForm.vue'

function makeStep(overrides = {}) {
  return {
    id: 1,
    incentive_type: 1,
    city_group: 'Group A',
    score_type: 'Delivery',
    score: 1,
    target_increase: 0.125,
    pr_increase: 1.75,
    control_bucket: null,
    created_at: '2026-09-08T12:00:00',
    deactivated_at: null,
    ...overrides,
  }
}

const columns = [
  { name: 'id', type: 'bigint unsigned', key: 'PRI', extra: 'auto_increment' },
  { name: 'incentive_type', type: 'int' },
  { name: 'city_group', type: 'varchar(100)' },
  { name: 'score_type', type: 'varchar(100)' },
  { name: 'score', type: 'int unsigned' },
  { name: 'target_increase', type: 'decimal(10,4)', nullable: false },
  { name: 'pr_increase', type: 'decimal(10,4)', nullable: false },
  { name: 'control_bucket', type: 'json', nullable: true },
  { name: 'created_at', type: 'datetime' },
  { name: 'deactivated_at', type: 'datetime', nullable: true },
]

// A mock of the three endpoints the page uses, with the same "edit = archive
// the row and add the new one" behavior as the API.
function installMockApi(rows = [makeStep()]) {
  const state = { rows: structuredClone(rows), writes: [], editError: '' }
  global.fetch = vi.fn(async (url, init = {}) => {
    const u = new URL(String(url), 'http://unit.test')
    const method = (init.method || 'GET').toUpperCase()
    const json = (data, status = 200) => ({ ok: status < 400, status, json: async () => data })
    const fail = (message, status) => json({ status: 'error', message }, status)

    if (u.pathname === '/api/decision-matrix/city-groups') {
      return json({ rows: [{ city_group: 'Group A' }, { city_group: 'Group B' }] })
    }
    if (u.pathname === '/api/incentive-types') {
      return json({ rows: [{ id: 1, name: 'DAILY' }] })
    }
    if (u.pathname === '/api/decision-matrix' && method === 'GET') {
      const group = u.searchParams.get('city_group')
      const all = state.rows
        .filter((row) => row.city_group === group)
        .map((row) => ({ ...row, incentive_type_name: 'DAILY' }))
      const grouped = new Map()
      for (const row of all) {
        const key = JSON.stringify([row.incentive_type, row.score_type])
        if (!grouped.has(key)) {
          grouped.set(key, {
            incentive_type: row.incentive_type, score_type: row.score_type,
            next_score: 1, active_count: 0, deactivated_count: 0,
          })
        }
        const item = grouped.get(key)
        if (row.deactivated_at === null) {
          item.next_score = Math.max(item.next_score, row.score + 1)
          item.active_count += 1
        } else item.deactivated_count += 1
      }
      return json({ city_group: group, columns, series: [...grouped.values()], rows: all })
    }
    const edit = /^\/api\/decision-matrix\/(\d+)\/edit$/.exec(u.pathname)
    if (edit && method === 'POST') {
      const id = Number(edit[1])
      const payload = JSON.parse(init.body)
      state.writes.push({ id, payload })
      if (state.editError) return fail(state.editError, 409)
      const original = state.rows.find((row) => row.id === id)
      if (!original) return fail('Score step not found.', 404)
      const others = state.rows.filter(
        (row) => row.id !== id && row.city_group === original.city_group &&
          row.incentive_type === original.incentive_type &&
          row.score_type === original.score_type && row.deactivated_at === null
      )
      if (others.some((row) => row.score === payload.score)) {
        return fail(`Score ${payload.score} is already active for this score type. Choose another score.`, 409)
      }
      original.deactivated_at = '2026-09-08T13:30:00'
      const created = makeStep({
        ...original, id: Math.max(...state.rows.map((row) => row.id)) + 1,
        score: payload.score, target_increase: payload.target_increase,
        pr_increase: payload.pr_increase, control_bucket: payload.control_bucket,
        created_at: '2026-09-08T13:30:00', deactivated_at: null,
      })
      state.rows.push(created)
      return json({
        status: 'ok', replaced_id: id, row: created,
        message: `Score ${original.score} deactivated and score ${created.score} added with the new details.`,
      })
    }
    return fail(`Unexpected request: ${method} ${u.pathname}`, 404)
  })
  return state
}

const buttonByLabel = (wrapper, label) =>
  wrapper.findAll('button').find((button) => button.attributes('aria-label') === label)
const buttonWithText = (scope, text) =>
  scope.findAll('button').find((button) => button.text().trim() === text)
const dialog = (wrapper) => wrapper.find('dialog.modal')
const fieldByLabel = (wrapper, label) =>
  wrapper.findAll('label').find((label_) => label_.text().startsWith(label))?.find('input')

async function openSeries(wrapper) {
  await buttonByLabel(wrapper, 'City group Group A').trigger('click')
  await flushPromises()
  const typeTrigger = wrapper.findAll('.type-trigger')[0]
  await typeTrigger.trigger('click')
  await flushPromises()
  await wrapper.find('.score-trigger').trigger('click')
  await flushPromises()
}
async function openEdit(wrapper, label = 'Edit score 1') {
  await buttonByLabel(wrapper, label).trigger('click')
  await flushPromises()
  return dialog(wrapper)
}

beforeEach(() => {
  global.fetch = vi.fn()
  document.body.innerHTML = ''
})

describe('Decision Matrix step editing', () => {
  it('prefills the form from the row and cannot save identical details', async () => {
    const wrapper = mount(DecisionMatrixStepEditForm, {
      props: {
        row: makeStep(), cityGroup: 'Group A', typeName: 'DAILY',
        nextScore: 3, activeScores: [2],
      },
      attachTo: document.body,
    })
    await flushPromises()

    expect(wrapper.find('h2').text()).toBe('Edit score 1')
    expect(fieldByLabel(wrapper, 'Score').element.value).toBe('1')
    expect(fieldByLabel(wrapper, 'Target increase').element.value).toBe('0.125')
    expect(fieldByLabel(wrapper, 'PR increase').element.value).toBe('1.75')
    expect(wrapper.text()).toContain('deactivates this step')
    expect(wrapper.text()).toContain('Suggested: 3')
    expect(buttonWithText(wrapper, 'Deactivate & add new step').attributes('disabled')).toBeDefined()
  })

  it('emits the new details and refuses a score that is already active', async () => {
    const wrapper = mount(DecisionMatrixStepEditForm, {
      props: { row: makeStep(), cityGroup: 'Group A', nextScore: 3, activeScores: [2, 5] },
      attachTo: document.body,
    })
    await flushPromises()

    await fieldByLabel(wrapper, 'Score').setValue('5')
    expect(wrapper.text()).toContain('Score 5 is already active for this score type')
    expect(buttonWithText(wrapper, 'Deactivate & add new step').attributes('disabled')).toBeDefined()

    // Keeping the row's own score is allowed: that row is archived by the same save.
    await fieldByLabel(wrapper, 'Score').setValue('1')
    expect(wrapper.text()).not.toContain('is already active for this score type')

    await fieldByLabel(wrapper, 'Target increase').setValue('0.5')
    await fieldByLabel(wrapper, 'PR increase').setValue('2.25')
    await wrapper.findAll('input[type="number"]')[3].setValue('0.1')
    await wrapper.findAll('input[type="number"]')[4].setValue('0.2')
    await wrapper.findAll('input[type="number"]')[5].setValue('0.3')
    await buttonWithText(wrapper, 'Deactivate & add new step').trigger('click')

    expect(wrapper.emitted('save')[0][0]).toEqual({
      score: 1, target_increase: 0.5, pr_increase: 2.25, control_bucket: [0.1, 0.2, 0.3],
    })
  })

  it('offers the suggested score of the series', async () => {
    const wrapper = mount(DecisionMatrixStepEditForm, {
      props: { row: makeStep({ score: 7 }), cityGroup: 'Group A', nextScore: 8, activeScores: [] },
      attachTo: document.body,
    })
    await flushPromises()
    await buttonWithText(wrapper, 'Use suggested score 8').trigger('click')
    expect(fieldByLabel(wrapper, 'Score').element.value).toBe('8')
    expect(wrapper.text()).toContain('score 8 active')
  })

  it('edits a step as one action: the row is deactivated and a new one is added', async () => {
    const state = installMockApi([makeStep(), makeStep({ id: 2, score: 2 })])
    const wrapper = mount(DecisionMatrix, { attachTo: document.body })
    await flushPromises()
    await openSeries(wrapper)

    const form = await openEdit(wrapper)
    expect(form.exists()).toBe(true)
    expect(form.find('h2').text()).toBe('Edit score 1')
    expect(form.text()).toContain('Score 1 → deactivated')
    expect(form.text()).toContain('Suggested: 3 (the next free score of this series)')

    await fieldByLabel(form, 'Score').setValue('3')
    await fieldByLabel(form, 'Target increase').setValue('0.5')
    await fieldByLabel(form, 'PR increase').setValue('2.25')
    await buttonWithText(form, 'Deactivate & add new step').trigger('click')
    await flushPromises()

    // one request, to the edit endpoint, carrying only the editable fields
    expect(state.writes).toEqual([
      { id: 1, payload: { score: 3, target_increase: 0.5, pr_increase: 2.25, control_bucket: null } },
    ])
    expect(state.rows[0].deactivated_at).toBe('2026-09-08T13:30:00')
    expect(state.rows[0].score).toBe(1)
    expect(state.rows.at(-1).score).toBe(3)
    expect(wrapper.find('dialog.modal').exists()).toBe(false)
    expect(wrapper.find('.toast').text()).toContain('Score 1 deactivated and score 3 added')

    // the new row is active, the edited one is history — and the history of the
    // edited series is revealed so the archive is visible right away
    const activeTable = wrapper.findAll('.table-scroll').find((el) => !el.classes().includes('history'))
    expect(activeTable.findAll('tbody th strong').map((th) => th.text())).toEqual(['2', '3'])
    expect(buttonWithText(wrapper, 'Hide deactivated')).toBeTruthy()
    const historyTable = wrapper.find('.table-scroll.history')
    expect(historyTable.findAll('tbody th strong').map((th) => th.text())).toEqual(['1'])
    expect(historyTable.text()).toContain('2026')
    // only the two active steps offer Edit
    expect(wrapper.findAll('button[aria-label^="Edit score"]').length).toBe(2)
  })

  it('keeps the form open with its values when the API refuses the new score', async () => {
    const state = installMockApi([makeStep(), makeStep({ id: 2, score: 2 })])
    const wrapper = mount(DecisionMatrix, { attachTo: document.body })
    await flushPromises()
    await openSeries(wrapper)

    const form = await openEdit(wrapper)
    await fieldByLabel(form, 'Score').setValue('4')
    await fieldByLabel(form, 'PR increase').setValue('9')
    state.editError = 'Score 4 is already active for this score type. Choose another score.'
    await buttonWithText(form, 'Deactivate & add new step').trigger('click')
    await flushPromises()

    const reopened = dialog(wrapper)
    expect(reopened.exists()).toBe(true)
    expect(reopened.text()).toContain('Score 4 is already active for this score type')
    expect(fieldByLabel(reopened, 'PR increase').element.value).toBe('9')
    // nothing was archived
    expect(state.rows.every((row) => row.deactivated_at === null)).toBe(true)
    await buttonWithText(reopened, 'Cancel').trigger('click')
    await flushPromises()
    expect(wrapper.find('dialog.modal').exists()).toBe(false)
  })

  it('offers Edit only for active steps, never in the history table', async () => {
    installMockApi([makeStep(), makeStep({ id: 2, score: 2, deactivated_at: '2026-09-08T13:00:00' })])
    const wrapper = mount(DecisionMatrix, { attachTo: document.body })
    await flushPromises()
    await openSeries(wrapper)

    expect(wrapper.findAll('button[aria-label^="Edit score"]').length).toBe(1)
    await buttonWithText(wrapper, 'Show deactivated (1)').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('button[aria-label^="Edit score"]').length).toBe(1)
    const history = wrapper.find('.history')
    expect(history.findAll('button').some((b) => b.text().trim() === 'Edit')).toBe(false)
  })
})
