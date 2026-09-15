// Final Decisions tab — the plans of every city.
//
// The whole /api surface is mocked, so the tests need no backend, no database
// and no browser: they drive the real FinalDecisions.vue (and the shared
// OrderEditor popup) against the sample payload below.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import FinalDecisions from '../../src/views/FinalDecisions.vue'

// incentive_type: 1 = DAILY, 2 = default, 3 = ON-TOP-FOOD, 4 = WEEKLY
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

const response = {
  incentive_date: '2026-09-16',
  score_types: ['performance', 'order_level_increase', 'weather'],
  plan_type_order: ['default', 'DAILY', 'ON-TOP-FOOD'],
  plans_error: null,
  total_plans: 5,
  generated_at: '2026-09-15T13:17:22Z',
  cities: [
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
        plan({ id: 1, plan_mapping_id: 122, incentive_type_id: 4, incentive_type: 'WEEKLY', incentive_type_label: 'WEEKLY', business_entity: 'foodZooket', pr_change: 1.1, control_bucket: null, type_rank: 103 }),
        plan({ id: 2, plan_mapping_id: 8, incentive_type_id: 2, incentive_type: 'default', business_entity: 'food' }),
        plan({ id: 4, plan_mapping_id: 132, incentive_type_id: 1, incentive_type: 'DAILY', incentive_type_label: 'DAILY', business_entity: 'food', pr_change: 1.2, control_bucket: null, type_rank: 1 }),
      ],
      top_plan: plan({ id: 2 }),
    },
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
          type_rank: 2,
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
          type_rank: 1,
        }),
      ],
      top_plan: plan({ id: 5, city_id: 10 }),
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
const planCards = (wrapper) => wrapper.findAll('.plan-card')
const cardTexts = (wrapper) => planCards(wrapper).map((card) => card.text())
const buttonWith = (scope, label) =>
  scope.findAll('button').find((b) => b.text().trim() === label)

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
  it('counts the plans of the date in the header and per city', async () => {
    const { wrapper } = await setup()
    expect(wrapper.find('.head-sub').text()).toContain('5 plans')
    expect(cityRow(wrapper, 'kerman').find('.preview-more').text()).toBe('+2 more')
    expect(cityRow(wrapper, 'kerman').find('.type-chip').text()).toBe('default')
  })

  it('shows the top plan of a city in the collapsed row: type, entity, changes, bucket and update', async () => {
    const { wrapper } = await setup()
    const row = cityRow(wrapper, 'tehran')
    // teheran has DAILY + ON-TOP-FOOD: DAILY is the top one, not the first row of the API
    expect(row.find('.type-chip').text()).toBe('DAILY')
    expect(row.find('.preview-entity').text()).toBe('foodZooket')
    const metrics = row.findAll('.preview-metric')
    expect(metrics[0].text()).toContain('Target')
    expect(metrics[0].text()).toContain('1.000')
    expect(metrics[1].text()).toContain('1.200')
    expect(metrics[2].text()).toContain('—')
    expect(row.find('.preview-updated').text()).toContain('System')
  })

  it('renders one card per plan when the city is expanded, ordered by plan type', async () => {
    const { wrapper } = await setup()
    await cityRow(wrapper, 'kerman').trigger('click')
    await flushPromises()

    expect(cardTexts(wrapper).length).toBe(3)
    expect(planCards(wrapper)[0].find('.plan-card-title').text()).toBe('default')
    expect(planCards(wrapper)[0].find('.plan-card-entity').text()).toBe('food')
    expect(planCards(wrapper)[0].find('.plan-card-head .pill').text()).toBe('top')
    // default → DAILY → WEEKLY (not listed in the order: last)
    expect(planCards(wrapper).map((card) => card.find('.plan-card-title').text())).toEqual([
      'default',
      'DAILY',
      'WEEKLY',
    ])
  })

  it('shows target change, pr change, control bucket and updated at on a card', async () => {
    const { wrapper } = await setup()
    await cityRow(wrapper, 'kerman').trigger('click')
    await flushPromises()

    const labels = planCards(wrapper)[0].findAll('.plan-metrics dt').map((dt) => dt.text())
    expect(labels).toEqual(['Target change', 'PR change', 'Control bucket'])
    expect(planCards(wrapper)[0].findAll('.plan-metrics dd').map((dd) => dd.text())).toEqual([
      '1.000',
      '1.300',
      '0.2',
    ].map((value, index) => (index === 2 ? expect.stringContaining('0.2') : value)))
    const chips = planCards(wrapper)[0].findAll('.bucket-chip .bucket-value').map((c) => c.text())
    expect(chips).toEqual(['0.2', '0.2', '0.1'])
    expect(planCards(wrapper)[0].find('.plan-updated').text()).toContain('System')
    // the Details button opens the plan page of the mapping row
    expect(planCards(wrapper)[0].find('a.btn').attributes('href')).toBe('/plans/8')
  })

  it('flags a plan whose mapping is deactivated', async () => {
    const { wrapper } = await setup()
    await cityRow(wrapper, 'tehran').trigger('click')
    await flushPromises()
    const card = planCards(wrapper).find((c) => c.text().includes('ON-TOP-FOOD'))
    expect(card.find('.pill.plain').text()).toBe('mapping off')
    expect(card.classes()).toContain('is-mapping-off')
  })

  it('reorders the plans through the plan type order popup', async () => {
    const { wrapper } = await setup()
    await cityRow(wrapper, 'kerman').trigger('click')
    await flushPromises()

    await openOrderEditor(wrapper, 'Plan type order')
    expect(orderNames(wrapper)).toEqual(['default', 'DAILY', 'ON-TOP-FOOD', 'WEEKLY'])
    await moveInOrderEditor(wrapper, 'WEEKLY', 'up')
    await moveInOrderEditor(wrapper, 'WEEKLY', 'up')
    expect(orderNames(wrapper)).toEqual(['default', 'WEEKLY', 'DAILY', 'ON-TOP-FOOD'])
    await buttonWith(wrapper.find('.order-modal'), 'Done').trigger('click')
    await flushPromises()

    expect(planCards(wrapper).map((card) => card.find('.plan-card-title').text())).toEqual([
      'default',
      'WEEKLY',
      'DAILY',
    ])
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
    expect(orderNames(wrapper)).toEqual(['default', 'ON-TOP-FOOD', 'DAILY', 'WEEKLY'])
    await buttonWith(wrapper.find('.order-modal'), '↺ Reset to default').trigger('click')
    await flushPromises()
    expect(orderNames(wrapper)).toEqual(['default', 'DAILY', 'ON-TOP-FOOD', 'WEEKLY'])
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
    empty.cities = [empty.cities[0]]
    empty.cities[0].plans = []
    empty.cities[0].plan_count = 0
    empty.cities[0].top_plan = null
    empty.total_plans = 0
    const { wrapper: second } = await setup(empty)
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
      'default',
      'DAILY',
      'WEEKLY',
      'ON-TOP-FOOD',
    ])
    wrapper.unmount()

    // a reload (fresh mount) keeps the user's order for both popups
    const { wrapper: reloaded } = await setup()
    await openOrderEditor(reloaded, 'Plan type order')
    expect(orderNames(reloaded)).toEqual(['default', 'DAILY', 'WEEKLY', 'ON-TOP-FOOD'])
    await buttonWith(reloaded.find('.order-modal'), '↺ Reset to default').trigger('click')
    await flushPromises()
    expect(orderNames(reloaded)).toEqual(['default', 'DAILY', 'ON-TOP-FOOD', 'WEEKLY'])
    expect(window.localStorage.getItem('finalDecisions.planTypeOrder')).toBeNull()
  })
})
