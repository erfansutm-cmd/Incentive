// Final Decisions tab — the plans of every city.
//
// The whole /api surface is mocked, so the tests need no backend, no database
// and no browser: they drive the real FinalDecisions.vue (and the shared
// OrderEditor popup) against the sample payload below.
//
// Plans are shown the way scores are: one column per plan type in the header,
// in the order the API sends (and the user can reorder), with the plan of each
// city in line in its column.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import FinalDecisions from '../../src/views/FinalDecisions.vue'

// incentive_type: 1 = DAILY, 2 = default, 3 = ON-TOP-FOOD, 4 = WEEKLY.
// "default" is not a plan type of the database: it is only in the sample rows,
// so it must show up as an unlisted type at the end of the order.
function plan(overrides = {}) {
  return {
    id: 1,
    incentive_date: '2026-09-16',
    plan_mapping_id: 8,
    city_id: 20,
    incentive_type_id: 2,
    incentive_type: 'default',
    incentive_type_label: 'default',
    business_entity: 'food',
    target_change: 1.0,
    pr_change: 1.3,
    control_bucket: [0.2, 0.2, 0.1],
    updated_at: '2026-09-15T13:17:22',
    updated_by: 'System',
    mapping_active: true,
    mapping_deactivated_at: null,
    type_rank: 0,
    ...overrides,
  }
}

function entity(name, scores = {}) {
  return {
    business_entity: name,
    business_entity_id: name,
    business_entity_name: name,
    scores: { performance: 0.4, order_level_increase: 0.3, weather: 0.2, ...scores },
    priority: name === 'foodZooket' ? 0 : 1,
  }
}

// Cities arrive already grouped by the API: Top 4 (tehran) before Tier 2 (kerman).
const response = {
  incentive_date: '2026-09-16',
  score_types: ['performance', 'order_level_increase', 'weather'],
  group_order: ['Tehran Group', 'Top 4', 'Tier 1', 'Tier 2', 'Tier 3'],
  plan_type_order: ['DAILY', 'ON-TOP-FOOD'],
  plans_error: null,
  total_plans: 5,
  generated_at: '2026-09-15T13:17:22Z',
  cities: [
    {
      id: 10,
      active_id: 10,
      city_id: 10,
      city_id_raw: '10',
      city: 'tehran',
      box_city_name: 'Tehran',
      city_group: 'Top 4',
      business_entities: [entity('foodZooket', { performance: 0.42 })],
      primary_entity: entity('foodZooket'),
      entity_count: 1,
      plan_count: 2,
      plans: [
        plan({
          id: 3,
          plan_mapping_id: 118,
          city_id: 10,
          incentive_type_id: 3,
          incentive_type: 'ON-TOP-FOOD',
          incentive_type_label: 'ON-TOP-FOOD',
          business_entity: 'foodZooket',
          pr_change: 1.35,
          control_bucket: null,
          mapping_active: false,
          mapping_deactivated_at: '2026-09-14T09:00:00',
        }),
        plan({
          id: 5,
          plan_mapping_id: 23,
          city_id: 10,
          incentive_type_id: 1,
          incentive_type: 'DAILY',
          incentive_type_label: 'DAILY',
          business_entity: 'foodZooket',
          pr_change: 1.2,
          control_bucket: null,
        }),
      ],
      top_plan: plan({ id: 5, city_id: 10 }),
    },
    {
      id: 8,
      active_id: 8,
      city_id: 8,
      city_id_raw: '8',
      city: 'kerman',
      box_city_name: 'Kerman',
      city_group: 'Tier 2',
      business_entities: [entity('foodZooket'), entity('food', { performance: 0.9 })],
      primary_entity: entity('foodZooket'),
      entity_count: 2,
      plan_count: 3,
      plans: [
        plan({ id: 1, plan_mapping_id: 122, incentive_type_id: 4, incentive_type: 'WEEKLY', incentive_type_label: 'WEEKLY', business_entity: 'foodZooket', pr_change: 1.1, control_bucket: null }),
        plan({ id: 2, plan_mapping_id: 8, incentive_type_id: 2, incentive_type: 'default', business_entity: 'food' }),
        plan({ id: 4, plan_mapping_id: 132, incentive_type_id: 1, incentive_type: 'DAILY', incentive_type_label: 'DAILY', business_entity: 'food', pr_change: 1.2, control_bucket: null }),
        // a second DAILY plan, for another entity: both share the DAILY column
        plan({ id: 6, plan_mapping_id: 133, incentive_type_id: 1, incentive_type: 'DAILY', incentive_type_label: 'DAILY', business_entity: 'foodZooket', target_change: 1.4, pr_change: 1.9, control_bucket: [0.4, 0.4, 0.2] }),
      ],
      top_plan: plan({ id: 6 }),
    },
  ],
}

function installMockApi(payload = response) {
  const calls = []
  global.fetch = vi.fn(async (url) => {
    const u = new URL(String(url), 'http://unit.test')
    calls.push(u.pathname + u.search)
    const json = (data, status = 200) => ({ ok: status < 400, status, json: async () => data })
    if (u.pathname === '/api/incentive-types') {
      return json({
        rows: [
          { id: 1, name: 'DAILY' },
          { id: 2, name: 'default' },
          { id: 3, name: 'ON-TOP-FOOD' },
          { id: 4, name: 'WEEKLY' },
        ],
      })
    }
    if (u.pathname === '/api/final-decisions') return json(payload)
    return json({ status: 'error', message: `unexpected ${u.pathname}` }, 404)
  })
  return { calls }
}

async function setup(payload) {
  const api = installMockApi(payload)
  const wrapper = mount(FinalDecisions, { attachTo: document.body })
  await flushPromises()
  return { wrapper, ...api }
}

const cityRow = (wrapper, city) =>
  wrapper.findAll('tr.city-row').find((row) => row.find('.city-name').text() === city)
const cityOrder = (wrapper) => wrapper.findAll('tr.city-row .city-name').map((c) => c.text())
const buttonWith = (scope, label) =>
  scope.findAll('button').find((b) => b.text().trim() === label)
// The score columns sort with a button that carries the arrow (Performance ↕).
const sortButton = (wrapper, label) =>
  wrapper.findAll('thead button').find((b) => b.text().trim().startsWith(label))

// The plan fields are columns, like the scores: type, target, PR, bucket, updated.
const planHeaders = (wrapper) => wrapper.findAll('thead .plan-th').map((th) => th.text())
const planCells = (wrapper, city) => cityRow(wrapper, city).findAll('td.plan-cell')
// the score cells come first, so target/PR are addressed by their position
const planCell = (wrapper, city, key) => {
  const cells = planCells(wrapper, city)
  if (key === 'target') return cells.length > 1 ? cells[1] : null
  if (key === 'pr') return cells.length > 2 ? cells[2] : null
  return cells.find((cell) => cell.classes().some((name) => name.endsWith(`plan-cell-${key}`))) || null
}
const cellText = (wrapper, city, key) => planCell(wrapper, city, key)?.text() ?? ''
// the plans listed in the expanded panel, one row each
const expandedPlans = (wrapper) => wrapper.findAll('.plans-mini tbody tr')
const expandedPlan = (wrapper, label) =>
  expandedPlans(wrapper).find((row) => row.find('.plan-type-name').text() === label)
const planNumbers = (wrapper) => wrapper.findAll('.plans-mini .plan-number').map((n) => n.text())

async function openOrderEditor(wrapper, label) {
  await buttonWith(wrapper, label).trigger('click')
  await flushPromises()
}
const orderNames = (wrapper) => wrapper.findAll('.order-row .order-name').map((n) => n.text())
async function moveInOrderEditor(wrapper, name, direction) {
  const row = wrapper.findAll('.order-row').find((r) => r.find('.order-name').text() === name)
  const buttons = row.findAll('.order-actions button')
  await buttons[direction === 'up' ? 0 : 1].trigger('click')
  await flushPromises()
}

beforeEach(() => {
  global.fetch = vi.fn()
  document.body.innerHTML = ''
  window.localStorage.clear()
  // the component touches localStorage on mount; nothing must leak between tests
})

describe('Final Decisions plans', () => {
  it('shows the plan fields in columns, like the scores', async () => {
    const { wrapper } = await setup()
    expect(wrapper.find('.head-sub').text()).toContain('6 plans')
    expect(planHeaders(wrapper)).toEqual([
      'Incentive Type', 'Target change', 'PR change', 'Control bucket', 'Updated', '',
    ])
    const groups = wrapper.findAll('thead .group-head-row th').map((th) => th.text()).filter(Boolean)
    expect(groups).toEqual(['Scores', 'Plans'])
    expect(planCells(wrapper, 'kerman').length).toBe(6)
  })

  it('shows only the first plan of a city in the collapsed row, one value per column', async () => {
    const { wrapper } = await setup()
    const row = cityRow(wrapper, 'tehran')
    // teheran has DAILY + ON-TOP-FOOD: DAILY is the top one, not the first row of the API
    expect(planCell(wrapper, 'tehran', 'type').find('.plan-type-name').text()).toBe('DAILY')
    expect(planCell(wrapper, 'tehran', 'type').find('.plan-entity').text()).toBe('foodZooket')
    expect(planCell(wrapper, 'tehran', 'target').find('.plan-number').text()).toBe('1.000')
    expect(planCell(wrapper, 'tehran', 'pr').find('.plan-number').text()).toBe('1.200')
    expect(cellText(wrapper, 'tehran', 'bucket')).toBe('—')
    expect(planCell(wrapper, 'tehran', 'updated').text()).toContain('System')
    expect(planCell(wrapper, 'tehran', 'details').find('a.plan-link').attributes('href')).toBe('/plans/23')
    // only the first plan is written in the row: the others sit behind the +N flag
    expect(row.findAll('.plan-number').map((n) => n.text())).toEqual(['1.000', '1.200'])
    expect(row.find('.plan-flag.more-flag').text()).toBe('+1')
    expect(row.find('.plan-flag.more-flag').attributes('title')).toContain('1 more plan')

    // kerman keeps its own top plan (the DAILY one of the first entity)
    const kerman = cityRow(wrapper, 'kerman')
    expect(planCell(wrapper, 'kerman', 'type').find('.plan-type-name').text()).toBe('DAILY')
    expect(planCell(wrapper, 'kerman', 'type').find('.plan-entity').text()).toBe('foodZooket')
    expect(planCell(wrapper, 'kerman', 'pr').find('.plan-number').text()).toBe('1.900')
    expect(kerman.find('.plan-flag.more-flag').text()).toBe('+3')
    expect(kerman.find('.plan-flag.top-flag').exists()).toBe(false)
  })

  it('colors the target and PR columns like the scores: more number, more red', async () => {
    const { wrapper } = await setup()
    const color = (cell) => {
      const match = /rgb\((\d+), (\d+), (\d+)\)/.exec(cell.find('.plan-number').attributes('style'))
      return { red: Number(match[1]), green: Number(match[2]) }
    }
    // the top plan of kerman (target 1.400 / PR 1.900) is the highest of the date
    for (const key of ['target', 'pr']) {
      const { red, green } = color(planCell(wrapper, 'kerman', key))
      expect(red).toBeGreaterThan(green)
    }
    // tehran's 1.000 / 1.200 are the lowest: the tint turns green
    for (const key of ['target', 'pr']) {
      const { red, green } = color(planCell(wrapper, 'tehran', key))
      expect(green).toBeGreaterThan(red)
    }
    expect(planCell(wrapper, 'kerman', 'target').find('.plan-number').text()).toBe('1.400')
    expect(planCell(wrapper, 'kerman', 'pr').find('.plan-number').text()).toBe('1.900')
    expect(planCell(wrapper, 'kerman', 'target').find('.plan-number').attributes('title')).toBe('Target change')
  })

  it('lists every plan of a city when it is expanded, in order', async () => {
    const { wrapper } = await setup()
    await cityRow(wrapper, 'kerman').trigger('click')
    await flushPromises()

    // DAILY (both entities, entity order first) → default → WEEKLY
    expect(expandedPlans(wrapper).length).toBe(4)
    expect(expandedPlans(wrapper).map((row) => row.find('.plan-type-name').text())).toEqual([
      'DAILY', 'DAILY', 'default', 'WEEKLY',
    ])
    expect(expandedPlans(wrapper).map((row) => row.find('.plan-entity-cell').text())).toEqual([
      'foodZooket', 'food', 'food', 'foodZooket',
    ])
    // only the first one is the top plan
    expect(expandedPlans(wrapper)[0].find('.plan-flag.top-flag').text()).toBe('top')
    expect(expandedPlans(wrapper)[0].find('.plan-rank').text()).toBe('1')
    expect(expandedPlans(wrapper).filter((row) => row.find('.plan-flag.top-flag').exists()).length).toBe(1)
    // the collapsed row and the panel agree on the same first plan
    expect(planCell(wrapper, 'kerman', 'type').find('.plan-type-name').text()).toBe('DAILY')
    expect(planCell(wrapper, 'kerman', 'type').find('.plan-entity').text()).toBe('foodZooket')
  })

  it('shows every plan field in the expanded table, including the plan page link', async () => {
    const { wrapper } = await setup()
    await cityRow(wrapper, 'kerman').trigger('click')
    await flushPromises()

    const headers = wrapper.findAll('.plans-mini thead th').map((th) => th.text()).filter(Boolean)
    expect(headers).toEqual(['#', 'Incentive Type', 'Business Entity', 'Target', 'PR', 'Bucket', 'Updated'])
    // the "default" plan is the one with a bucket
    const row = expandedPlan(wrapper, 'default')
    expect(row.find('.plan-entity-cell').text()).toBe('food')
    expect(row.findAll('.plan-number').map((n) => n.text())).toEqual(['1.000', '1.300'])
    expect(row.findAll('.bucket-chip .bucket-value').map((c) => c.text())).toEqual(['0.2', '0.2', '0.1'])
    expect(row.find('.plan-stamp').text()).toContain('2026')
    expect(row.find('.plan-stamp-by').text()).toBe('System')
    expect(row.find('a.plan-link').attributes('href')).toBe('/plans/8')
    // the numbers are colored here too, exactly like in the columns
    expect(row.find('.plan-number').attributes('style')).toContain('rgb(')
    // the rows carry the same colored numbers as the columns, in the same order
    expect(planNumbers(wrapper)).toEqual(['1.400', '1.900', '1.000', '1.200', '1.000', '1.300', '1.000', '1.100'])
  })

  it('flags a plan whose mapping is deactivated', async () => {
    const { wrapper } = await setup()
    await cityRow(wrapper, 'tehran').trigger('click')
    await flushPromises()
    const row = expandedPlan(wrapper, 'ON-TOP-FOOD')
    expect(row.find('.plan-flag.off-flag').text()).toBe('off')
    expect(row.find('.plan-flag.top-flag').exists()).toBe(false)
    // it is not the top plan, so the collapsed row shows the DAILY plan instead
    expect(planCell(wrapper, 'tehran', 'type').find('.plan-type-name').text()).toBe('DAILY')
  })

  it('the plan type order decides which plan the collapsed row shows', async () => {
    const { wrapper } = await setup()
    // before: the DAILY plan of the first entity
    expect(planCell(wrapper, 'kerman', 'type').find('.plan-type-name').text()).toBe('DAILY')
    expect(planCell(wrapper, 'kerman', 'type').find('.plan-entity').text()).toBe('foodZooket')

    await openOrderEditor(wrapper, 'Plan type order')
    expect(orderNames(wrapper)).toEqual(['DAILY', 'ON-TOP-FOOD', 'default', 'WEEKLY'])
    await moveInOrderEditor(wrapper, 'WEEKLY', 'up')
    await moveInOrderEditor(wrapper, 'WEEKLY', 'up')
    expect(orderNames(wrapper)).toEqual(['DAILY', 'WEEKLY', 'ON-TOP-FOOD', 'default'])
    // DAILY is still first, so the collapsed row still shows the DAILY plan
    expect(planCell(wrapper, 'kerman', 'type').find('.plan-type-name').text()).toBe('DAILY')
    await moveInOrderEditor(wrapper, 'WEEKLY', 'up')
    expect(orderNames(wrapper)).toEqual(['WEEKLY', 'DAILY', 'ON-TOP-FOOD', 'default'])
    await buttonWith(wrapper.find('.order-modal'), 'Done').trigger('click')
    await flushPromises()

    // the columns are unchanged (they are the fields), but the first plan is the
    // WEEKLY one now — and the expanded list follows the same order
    expect(planHeaders(wrapper)).toEqual([
      'Incentive Type', 'Target change', 'PR change', 'Control bucket', 'Updated', '',
    ])
    expect(planCell(wrapper, 'kerman', 'type').find('.plan-type-name').text()).toBe('WEEKLY')
    expect(planCell(wrapper, 'kerman', 'type').find('.plan-entity').text()).toBe('foodZooket')
    expect(planCell(wrapper, 'kerman', 'pr').find('.plan-number').text()).toBe('1.100')

    await cityRow(wrapper, 'kerman').trigger('click')
    await flushPromises()
    // kerman has no ON-TOP-FOOD plan, so the unlisted "default" comes next
    expect(expandedPlans(wrapper).map((row) => row.find('.plan-type-name').text())).toEqual([
      'WEEKLY', 'DAILY', 'DAILY', 'default',
    ])
    expect(expandedPlans(wrapper)[0].find('.plan-flag.top-flag').text()).toBe('top')
  })

  it('keeps the city order of the API (city groups) for equal scores', async () => {
    const tied = structuredClone(response)
    // kerman has the same performance score as tehran: the group order wins
    tied.cities[1].business_entities[0].scores.performance = 0.42
    const { wrapper } = await setup(tied)

    expect(cityOrder(wrapper)).toEqual(['tehran', 'kerman'])
    await sortButton(wrapper, 'Performance').trigger('click')
    await flushPromises()
    expect(cityOrder(wrapper)).toEqual(['tehran', 'kerman'])
    await sortButton(wrapper, 'Performance').trigger('click')
    await flushPromises()
    expect(cityOrder(wrapper)).toEqual(['tehran', 'kerman'])
    // the group filter follows the same order
    expect(wrapper.findAll('#group-filter option').map((o) => o.text())).toEqual([
      'All groups',
      'Top 4',
      'Tier 2',
    ])
    expect(wrapper.find('.sort-clear').attributes('title')).toContain('Tehran Group → Top 4')
  })

  it('says when plans fall on cities without scores for the date', async () => {
    const partial = structuredClone(response)
    partial.plans_without_scores = 2
    partial.plans_without_scores_cities = ['Tehran', 'Qom']
    const { wrapper } = await setup(partial)

    const notice = wrapper.find('.banner.notice')
    expect(notice.exists()).toBe(true)
    expect(notice.text()).toContain('2 plans are not listed')
    expect(notice.text()).toContain('Tehran, Qom')
  })

  it('closes the order popup on Escape', async () => {
    const { wrapper } = await setup()
    await openOrderEditor(wrapper, 'Entity order')
    expect(wrapper.find('.order-modal').exists()).toBe(true)
    await wrapper.find('.order-modal').trigger('cancel')
    await flushPromises()
    expect(wrapper.find('.order-modal').exists()).toBe(false)
  })

  it('resets the order to default and re-syncs the cities', async () => {
    const { wrapper } = await setup()
    await openOrderEditor(wrapper, 'Plan type order')
    await moveInOrderEditor(wrapper, 'DAILY', 'down')
    expect(orderNames(wrapper)).toEqual(['ON-TOP-FOOD', 'DAILY', 'default', 'WEEKLY'])
    // tehran has an ON-TOP-FOOD plan, so its collapsed row starts with it now;
    // kerman has none, so its own top plan is still the DAILY one
    expect(planCell(wrapper, 'tehran', 'type').find('.plan-type-name').text()).toBe('ON-TOP-FOOD')
    expect(planCell(wrapper, 'kerman', 'type').find('.plan-type-name').text()).toBe('DAILY')
    await buttonWith(wrapper.find('.order-modal'), '↺ Reset to default').trigger('click')
    await flushPromises()
    expect(orderNames(wrapper)).toEqual(['DAILY', 'ON-TOP-FOOD', 'default', 'WEEKLY'])
    expect(planCell(wrapper, 'tehran', 'type').find('.plan-type-name').text()).toBe('DAILY')
  })

  it('keeps the entity order popup working (top entity in the collapsed row)', async () => {
    const { wrapper } = await setup()
    expect(cityRow(wrapper, 'kerman').find('.entity-cell').text()).toBe('foodZooket')

    await openOrderEditor(wrapper, 'Entity order')
    expect(orderNames(wrapper)).toEqual(['foodZooket', 'food', 'Zooket'])
    await moveInOrderEditor(wrapper, 'food', 'up')
    expect(orderNames(wrapper)).toEqual(['food', 'foodZooket', 'Zooket'])
    await buttonWith(wrapper.find('.order-modal'), 'Done').trigger('click')
    await flushPromises()

    // the popup is closed again and the new order drives the table
    expect(wrapper.find('.order-modal').exists()).toBe(false)
    expect(cityRow(wrapper, 'kerman').find('.entity-cell').text()).toBe('food')
  })

  it('explains an empty plans list instead of leaving a placeholder', async () => {
    const { wrapper } = await setup()
    await cityRow(wrapper, 'kerman').trigger('click')
    await flushPromises()
    expect(wrapper.find('.plan-warning').exists()).toBe(false)

    const empty = structuredClone(response)
    empty.cities = [empty.cities[1]]
    empty.cities[0].plans = []
    empty.cities[0].plan_count = 0
    empty.cities[0].top_plan = null
    empty.total_plans = 0
    const { wrapper: second } = await setup(empty)
    // no plans: the columns stay, the row shows the status pill across them
    expect(cityRow(second, 'kerman').find('.decisions-pill').text()).toBe('No plans')
    expect(planCells(second, 'kerman').length).toBe(1)
    expect(planCells(second, 'kerman')[0].attributes('colspan')).toBe('6')
    await cityRow(second, 'kerman').trigger('click')
    await flushPromises()
    expect(second.find('.decisions-hint').text()).toContain('No plans for kerman')
  })

  it('shows a retryable message when the plans table cannot be read', async () => {
    const broken = structuredClone(response)
    broken.plans_error = "Table 'incentive/final_incentive_plans' does not exist in the database."
    broken.cities.forEach((city) => {
      city.plans = []
      city.plan_count = 0
      city.top_plan = null
    })
    const { wrapper } = await setup(broken)
    expect(cityRow(wrapper, 'kerman').find('.decisions-pill').text()).toBe('Plans unavailable')
    await cityRow(wrapper, 'kerman').trigger('click')
    await flushPromises()
    expect(wrapper.find('.plan-warning').text()).toContain('final_incentive_plans')
    // the scores are untouched by the plan failure
    expect(cityRow(wrapper, 'kerman').find('.score-badge').exists()).toBe(true)
  })

  it('remembers the orders in the browser and can clear them again', async () => {
    const { wrapper } = await setup()
    await openOrderEditor(wrapper, 'Plan type order')
    await moveInOrderEditor(wrapper, 'WEEKLY', 'up')
    await buttonWith(wrapper.find('.order-modal'), 'Done').trigger('click')
    await flushPromises()
    expect(JSON.parse(window.localStorage.getItem('finalDecisions.planTypeOrder'))).toEqual([
      'DAILY',
      'ON-TOP-FOOD',
      'WEEKLY',
      'default',
    ])
    wrapper.unmount()

    // a reload (fresh mount) keeps the user's order for both popups
    const { wrapper: reloaded } = await setup()
    await openOrderEditor(reloaded, 'Plan type order')
    expect(orderNames(reloaded)).toEqual(['DAILY', 'ON-TOP-FOOD', 'WEEKLY', 'default'])
    await buttonWith(reloaded.find('.order-modal'), '↺ Reset to default').trigger('click')
    await flushPromises()
    expect(orderNames(reloaded)).toEqual(['DAILY', 'ON-TOP-FOOD', 'default', 'WEEKLY'])
    expect(window.localStorage.getItem('finalDecisions.planTypeOrder')).toBeNull()
  })
})
