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
      ],
      top_plan: plan({ id: 4 }),
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
const planCards = (wrapper) => wrapper.findAll('.plan-card')
const cardTexts = (wrapper) => planCards(wrapper).map((card) => card.text())
const buttonWith = (scope, label) =>
  scope.findAll('button').find((b) => b.text().trim() === label)
// The score columns sort with a button that carries the arrow (Performance ↕).
const sortButton = (wrapper, label) =>
  wrapper.findAll('thead button').find((b) => b.text().trim().startsWith(label))

// One column per plan type; the cell of a city in the column of a plan type.
const planHeaders = (wrapper) => wrapper.findAll('thead .plan-th').map((th) => th.text())
const planCell = (wrapper, city, label) => {
  const index = planHeaders(wrapper).indexOf(label)
  if (index === -1) return null
  const row = cityRow(wrapper, city)
  const cells = row.findAll('td.plan-cell')
  return cells.length > index ? cells[index] : null
}
const cellText = (wrapper, city, label) => planCell(wrapper, city, label)?.text() ?? ''

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
  it('lists one column per plan type, like the scores, and counts the plans', async () => {
    const { wrapper } = await setup()
    expect(wrapper.find('.head-sub').text()).toContain('5 plans')
    // the configured order first, then the unlisted types of the sample data
    expect(planHeaders(wrapper)).toEqual(['DAILY', 'ON-TOP-FOOD', 'default', 'WEEKLY'])
    const groups = wrapper.findAll('thead .group-head-row th').map((th) => th.text()).filter(Boolean)
    expect(groups).toEqual(['Scores', 'Plans'])
    // the city row is one table row with a cell per plan type (no stacked block)
    expect(cityRow(wrapper, 'kerman').findAll('td.plan-cell').length).toBe(4)
    expect(cellText(wrapper, 'kerman', 'ON-TOP-FOOD')).toBe('—')
  })

  it('shows each plan in line in its own type column, top plan marked', async () => {
    const { wrapper } = await setup()
    const row = cityRow(wrapper, 'tehran')
    // teheran has DAILY + ON-TOP-FOOD: DAILY is the top one, not the first row of the API
    const daily = row.findAll('td.plan-cell')[planHeaders(wrapper).indexOf('DAILY')]
    expect(daily.find('.plan-inline-entity').text()).toBe('foodZooket')
    expect(daily.find('.plan-inline').classes()).toContain('is-top')
    expect(daily.find('.pill.tiny').text()).toBe('top')
    const values = daily.findAll('.plan-value').map((v) => v.text())
    expect(values[0]).toContain('1.000')
    expect(values[1]).toContain('1.200')
    expect(values[2]).toContain('—')
    expect(daily.find('.plan-updated').text()).toContain('System')
    expect(daily.find('a.plan-link').attributes('href')).toBe('/plans/23')

    // the other type of the same city sits in its own column, without the badge
    const onTop = planCell(wrapper, 'tehran', 'ON-TOP-FOOD')
    expect(onTop.find('.plan-inline').classes()).toContain('is-mapping-off')
    expect(onTop.find('.pill.tiny').text()).toBe('mapping off')
    expect(onTop.text()).toContain('1.350')

    // kerman keeps all three of its plans in their columns, one line each
    expect(cellText(wrapper, 'kerman', 'DAILY')).toContain('food')
    expect(cellText(wrapper, 'kerman', 'default')).toContain('0.2')
    expect(cellText(wrapper, 'kerman', 'WEEKLY')).toContain('foodZooket')
  })

  it('renders one card per plan when the city is expanded, ordered by plan type', async () => {
    const { wrapper } = await setup()
    await cityRow(wrapper, 'kerman').trigger('click')
    await flushPromises()

    expect(cardTexts(wrapper).length).toBe(3)
    expect(planCards(wrapper)[0].find('.plan-card-title').text()).toBe('DAILY')
    expect(planCards(wrapper)[0].find('.plan-card-entity').text()).toBe('food')
    expect(planCards(wrapper)[0].find('.plan-card-head .pill').text()).toBe('top')
    // DAILY → the unlisted default and WEEKLY last, alphabetically
    expect(planCards(wrapper).map((card) => card.find('.plan-card-title').text())).toEqual([
      'DAILY',
      'default',
      'WEEKLY',
    ])
  })

  it('shows target change, pr change, control bucket and updated at on a card', async () => {
    const { wrapper } = await setup()
    await cityRow(wrapper, 'kerman').trigger('click')
    await flushPromises()

    const card = planCards(wrapper).find((c) => c.find('.plan-card-title').text() === 'default')
    const labels = card.findAll('.plan-metrics dt').map((dt) => dt.text())
    expect(labels).toEqual(['Target change', 'PR change', 'Control bucket'])
    expect(card.findAll('.plan-metrics dd').map((dd) => dd.text())).toEqual([
      '1.000',
      '1.300',
      '0.2',
    ].map((value, index) => (index === 2 ? expect.stringContaining('0.2') : value)))
    const chips = card.findAll('.bucket-chip .bucket-value').map((c) => c.text())
    expect(chips).toEqual(['0.2', '0.2', '0.1'])
    expect(card.find('.plan-updated').text()).toContain('System')
    // the Details button opens the plan page of the mapping row
    expect(card.find('a.btn').attributes('href')).toBe('/plans/8')
  })

  it('flags a plan whose mapping is deactivated', async () => {
    const { wrapper } = await setup()
    await cityRow(wrapper, 'tehran').trigger('click')
    await flushPromises()
    const card = planCards(wrapper).find((c) => c.text().includes('ON-TOP-FOOD'))
    expect(card.find('.pill.plain').text()).toBe('mapping off')
    expect(card.classes()).toContain('is-mapping-off')
  })

  it('reorders the plan columns through the plan type order popup', async () => {
    const { wrapper } = await setup()
    await openOrderEditor(wrapper, 'Plan type order')
    expect(orderNames(wrapper)).toEqual(['DAILY', 'ON-TOP-FOOD', 'default', 'WEEKLY'])
    await moveInOrderEditor(wrapper, 'WEEKLY', 'up')
    await moveInOrderEditor(wrapper, 'WEEKLY', 'up')
    expect(orderNames(wrapper)).toEqual(['DAILY', 'WEEKLY', 'ON-TOP-FOOD', 'default'])
    await buttonWith(wrapper.find('.order-modal'), 'Done').trigger('click')
    await flushPromises()

    // the table columns follow the chosen order
    expect(planHeaders(wrapper)).toEqual(['DAILY', 'WEEKLY', 'ON-TOP-FOOD', 'default'])
    expect(cellText(wrapper, 'kerman', 'WEEKLY')).toContain('foodZooket')

    await cityRow(wrapper, 'kerman').trigger('click')
    await flushPromises()
    expect(planCards(wrapper).map((card) => card.find('.plan-card-title').text())).toEqual([
      'DAILY',
      'WEEKLY',
      'default',
    ])
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
    await buttonWith(wrapper.find('.order-modal'), '↺ Reset to default').trigger('click')
    await flushPromises()
    expect(orderNames(wrapper)).toEqual(['DAILY', 'ON-TOP-FOOD', 'default', 'WEEKLY'])
    expect(planHeaders(wrapper)).toEqual(['DAILY', 'ON-TOP-FOOD', 'default', 'WEEKLY'])
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
    // no plan type has a plan: the table keeps a single Plans column
    expect(planHeaders(second)).toEqual(['Plans'])
    expect(cityRow(second, 'kerman').find('.decisions-pill').text()).toBe('No plans')
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
