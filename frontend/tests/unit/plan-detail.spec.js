import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import PlanDetail from '../../src/views/PlanDetail.vue'
import { installMockApi, wait, text, button } from './api-mock'

async function setup(options = {}) {
  const api = installMockApi(options)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/cities', component: { template: '<div />' } },
      { path: '/plans/:id', component: PlanDetail },
    ],
  })
  router.push('/plans/1')
  await router.isReady()
  const wrapper = mount(PlanDetail, {
    global: { plugins: [router] },
    attachTo: document.body,
  })
  await flushPromises()
  return { wrapper, ...api }
}

const rows = (wrapper) => wrapper.findAll('tbody tr.config-row')
const rowButtons = (wrapper, index = 0) => rows(wrapper)[index].findAll('td.actions-col button')
const modal = (wrapper) => wrapper.find('.modal')
const modalButton = (wrapper, label) => button(modal(wrapper), label)
const field = (scope, label) =>
  scope.findAll('.detail-facts > div').find((d) => d.find('dt').text() === label)
const toastText = (wrapper) => (wrapper.find('.toast').exists() ? wrapper.find('.toast').text() : '')
// an option's name only; its row also carries a "selected" mark
const optionNames = (wrapper) =>
  wrapper.findAll('li[role=option]').map((o) => o.find('.opt-name').text())
// open a lookup's list and pick one of its names
async function choose(wrapper, inputSelector, name) {
  const input = modal(wrapper).find(inputSelector)
  await input.trigger('focus')
  await flushPromises()
  const option = wrapper
    .findAll('li[role=option]')
    .find((o) => o.text().includes(name))
  expect(option, `no option "${name}"`).toBeTruthy()
  await option.trigger('mousedown')
  await flushPromises()
  return input
}

beforeEach(() => {
  global.fetch = vi.fn()
  document.body.innerHTML = ''
})

describe('PlanDetail base configs', () => {
  it('shows the shared listing and duration once, for the whole plan', async () => {
    const { wrapper } = await setup()
    const bar = wrapper.find('.shared-bar')
    expect(text(bar.findAll('.shared-values dt'))).toEqual(['Listing', 'Duration'])
    expect(text(bar.findAll('.shared-values dd'))).toEqual(['kerman-daily-foodZooket', '1'])
    expect(bar.text()).toContain('Same for every allocator of this plan')

    // listing_id is shared, so it is not repeated as a column of every allocator
    expect(text(wrapper.findAll('thead th'))).toEqual([
      'Details', 'Allocator ID', 'Rule Name', 'Impact Ratio', 'Actions',
    ])
    const first = rows(wrapper)[0]
    expect(first.find('.ratio').text()).toBe('60%')
    expect(first.find('.ratio-raw').text()).toBe('0.6')
    expect(wrapper.text()).toContain('2 allocators')

    // the rest of the row stays hidden until it is opened
    expect(wrapper.find('tbody tr.detail-row').exists()).toBe(false)
  })

  it('keeps plan_id, listing and duration out of the row dropdown', async () => {
    const { wrapper } = await setup()
    await rows(wrapper)[0].find('button.chevron-disc').trigger('click')
    const detail = wrapper.find('tbody tr.detail-row')
    const labels = text(detail.findAll('.detail-facts dt'))

    // all three are shown once at plan level, not per allocator
    for (const label of ['Plan ID', 'Listing ID', 'Duration']) {
      expect(labels).not.toContain(label)
    }
    for (const label of ['ID', 'Batch Size', 'Clustering Method', 'Districts', 'Vendors', 'Created At', 'Updated At', 'Deactivated At']) {
      expect(labels).toContain(label)
    }
    // dates are rendered, never left as raw ISO strings
    expect(detail.text()).not.toContain('2026-09-14T10:11:16')
    expect(field(detail, 'Updated At').find('dd').text()).toContain('2026')
    expect(field(detail, 'Deactivated At').find('dd').text()).toBe('—')
  })

  it('shows a list column as chips, without the nulls the JSON holds', async () => {
    const { wrapper } = await setup()
    await rows(wrapper)[0].find('button.chevron-disc').trigger('click')
    const detail = wrapper.find('tbody tr.detail-row')

    // districts is stored as ["Sadra", null]: one chip, no "null" anywhere
    const districts = field(detail, 'Districts').find('dd')
    expect(text(districts.findAll('.chip'))).toEqual(['Sadra'])
    expect(detail.text()).not.toContain('null')
    expect(detail.text()).not.toContain('[')

    // vendors is null: an empty dash rather than an empty chip list
    expect(field(detail, 'Vendors').find('dd').text()).toBe('—')
    expect(field(detail, 'Vendors').findAll('.chip')).toHaveLength(0)
  })

  it('edits listing and duration for every allocator of the plan', async () => {
    const { wrapper, state } = await setup()
    await button(wrapper, 'Edit for all').trigger('click')
    expect(modal(wrapper).text()).toContain('updates all 2 of them')

    const listing = await choose(wrapper, '#plan-listing', 'kerman-weekly-foodZooket')
    expect(listing.element.value).toBe('kerman-weekly-foodZooket')
    await modal(wrapper).find('#plan-duration').setValue('30')
    await modalButton(wrapper, 'Save for all allocators').trigger('click')
    await flushPromises()

    expect(modal(wrapper).exists()).toBe(false)
    expect(state.writes).toEqual([
      { kind: 'plan', plan_id: '1', body: { listing_id: 'kerman-weekly-foodZooket', duration: 30 } },
    ])
    expect(toastText(wrapper)).toBe('Updated 2 allocators of this plan.')
    expect(text(wrapper.findAll('.shared-values dd'))).toEqual(['kerman-weekly-foodZooket', '30'])
    expect(state.configs.every((r) => r.listing_id === 'kerman-weekly-foodZooket')).toBe(true)
  })

  it('takes the listing from the list only, never from typing', async () => {
    const { wrapper, state } = await setup()
    await button(wrapper, 'Edit for all').trigger('click')
    const listing = modal(wrapper).find('#plan-listing')

    // typing filters the offered names but does not become the value
    await listing.setValue('tehran')
    await wait(260)
    await flushPromises()
    expect(optionNames(wrapper)).toEqual(['tehran-daily-foodZooket'])

    await modal(wrapper).find('#plan-duration').setValue('30')
    await modalButton(wrapper, 'Save for all allocators').trigger('click')
    await flushPromises()

    // the plan's own listing went out, not the typed text
    expect(state.writes[0].body.listing_id).toBe('kerman-daily-foodZooket')
    expect(state.writes[0].body.listing_id).not.toBe('tehran')
  })

  it('refuses to save the shared bar without a listing', async () => {
    const { wrapper, state } = await setup()
    await button(wrapper, 'Edit for all').trigger('click')
    // the chosen listing is cleared with its own button, not by overtyping it
    await modal(wrapper).find('button[aria-label="Clear listing"]').trigger('mousedown')
    await flushPromises()
    await modalButton(wrapper, 'Save for all allocators').trigger('click')
    await flushPromises()
    expect(modal(wrapper).find('.form-error').text()).toBe("'Listing ID' is required.")
    expect(state.writes).toEqual([])
  })

  it('edits an allocator in place and logs its previous values', async () => {
    const { wrapper, state } = await setup()
    await rowButtons(wrapper).find((b) => b.text() === 'Edit').trigger('click')
    expect(modal(wrapper).find('h2').text()).toBe('Edit allocator')
    expect(modal(wrapper).text()).toContain('written to the change log')

    await modal(wrapper).find('#config-impact_ratio').setValue('0.75')
    await modalButton(wrapper, 'Save changes').trigger('click')
    await flushPromises()

    expect(modal(wrapper).exists()).toBe(false)
    expect(toastText(wrapper)).toBe('Allocator updated.')
    expect(state.writes).toHaveLength(1)
    expect(state.writes[0]).toMatchObject({ kind: 'edit', id: 2 })
    expect(state.writes[0].body.impact_ratio).toBe(0.75)
    // the plan link and the shared columns are never sent per allocator
    for (const key of ['plan_id', 'listing_id', 'duration']) {
      expect(state.writes[0].body).not.toHaveProperty(key)
    }
    // the row kept its identity: no new row, nothing deactivated
    expect(rows(wrapper)).toHaveLength(2)
    expect(state.configs.map((r) => r.id).sort()).toEqual([1, 2])
    expect(state.deactivated).toEqual([])
    expect(rows(wrapper)[0].find('.ratio').text()).toBe('75%')
  })

  it('marks the identifying fields as required, not optional', async () => {
    const { wrapper } = await setup()
    await rowButtons(wrapper).find((b) => b.text() === 'Edit').trigger('click')
    const labels = modal(wrapper).findAll('.field > span')
    const byLabel = (name) => labels.find((l) => l.text().startsWith(name))

    for (const name of ['Allocator ID', 'Rule Name', 'Impact Ratio']) {
      expect(byLabel(name).text()).toContain('required')
      expect(byLabel(name).text()).not.toContain('(optional)')
    }
    for (const name of ['Districts', 'Vendors', 'Batch Size', 'Clustering Method']) {
      expect(byLabel(name).text()).toContain('(optional)')
    }
  })

  it('edits a list column by adding and removing values', async () => {
    const { wrapper, state } = await setup()
    await rowButtons(wrapper).find((b) => b.text() === 'Edit').trigger('click')

    // the stored ["Sadra", null] arrives as one editable chip
    const districts = modal(wrapper).find('#config-districts')
    expect(text(modal(wrapper).findAll('.tag-field .chip .chip-name'))).toEqual(['Sadra'])

    await districts.setValue('District 9')
    await districts.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(text(modal(wrapper).findAll('.tag-field .chip .chip-name'))).toEqual([
      'Sadra', 'District 9',
    ])

    await modal(wrapper).find('button[aria-label="Remove Districts Sadra"]').trigger('click')
    await flushPromises()
    expect(text(modal(wrapper).findAll('.tag-field .chip .chip-name'))).toEqual(['District 9'])

    await modalButton(wrapper, 'Save changes').trigger('click')
    await flushPromises()
    // stored back as the JSON list the column holds, without the null
    expect(state.writes[0].body.districts).toBe('["District 9"]')
  })

  it('stores an emptied list as no value at all', async () => {
    const { wrapper, state } = await setup()
    await rowButtons(wrapper).find((b) => b.text() === 'Edit').trigger('click')
    await modal(wrapper).find('button[aria-label="Remove Districts Sadra"]').trigger('click')
    await flushPromises()
    await modalButton(wrapper, 'Save changes').trigger('click')
    await flushPromises()
    expect(state.writes[0].body.districts).toBe('')
  })

  it('deactivates a row behind a confirmation', async () => {
    const { wrapper, state } = await setup()
    await rowButtons(wrapper).find((b) => b.text() === 'Deactivate').trigger('click')
    expect(modal(wrapper).find('h2').text()).toBe('Deactivate allocator')
    expect(modal(wrapper).text()).toContain('foodZooket-kerman-3T-range-base-20260905')
    expect(modal(wrapper).text()).toContain('Nothing is deleted.')

    await modalButton(wrapper, 'Deactivate').trigger('click')
    await flushPromises()

    expect(modal(wrapper).exists()).toBe(false)
    expect(toastText(wrapper)).toBe('Allocator deactivated.')
    expect(state.writes).toEqual([{ kind: 'deactivate', id: 2 }])
    expect(rows(wrapper)).toHaveLength(1)
  })

  it('adds an allocator, choosing the allocator and rule from the lists', async () => {
    const { wrapper, state, calls } = await setup()
    await button(wrapper, '+ Add allocator').trigger('click')
    expect(modal(wrapper).find('h2').text()).toBe('Add allocator')
    // the plan has allocators already, so listing and duration are inherited
    expect(modal(wrapper).text()).toContain('kerman-daily-foodZooket')
    expect(modal(wrapper).find('#add-listing').exists()).toBe(false)

    const allocator = await choose(wrapper, '#config-allocator_id', 'foodZooket-kish-1T-base')
    expect(allocator.attributes('role')).toBe('combobox')
    expect(allocator.element.value).toBe('foodZooket-kish-1T-base')
    await choose(wrapper, '#config-rule_name', 'foodZooket-kish-1step-base')

    await modal(wrapper).find('#config-impact_ratio').setValue('0.25')
    await modalButton(wrapper, 'Add allocator').trigger('click')
    await flushPromises()

    expect(modal(wrapper).exists()).toBe(false)
    expect(toastText(wrapper)).toBe('Allocator added.')
    expect(state.writes).toHaveLength(1)
    expect(state.writes[0]).toMatchObject({
      kind: 'add',
      body: {
        plan_id: '1',
        allocator_id: 'foodZooket-kish-1T-base',
        rule_name: 'foodZooket-kish-1step-base',
        impact_ratio: 0.25,
      },
    })
    expect(state.writes[0].body).not.toHaveProperty('listing_id')
    expect(state.writes[0].body).not.toHaveProperty('duration')
    // the search went to the lookup endpoints, never to the services directly
    expect(calls.filter((c) => c.includes('/api/incentive-lookups/')).length).toBeGreaterThan(0)
  })

  it('asks for the listing and duration on the first allocator of a plan', async () => {
    const { wrapper, state } = await setup({ configs: [] })
    expect(wrapper.find('.config-empty').text()).toBe('No base configs for this plan yet.')
    await button(wrapper, '+ Add allocator').trigger('click')
    expect(modal(wrapper).text()).toContain('first allocator of plan 1')
    expect(modal(wrapper).find('#add-listing').exists()).toBe(true)
    expect(modal(wrapper).find('#add-duration').exists()).toBe(true)

    // required fields are checked before anything is sent
    await modalButton(wrapper, 'Add allocator').trigger('click')
    await flushPromises()
    expect(modal(wrapper).find('.form-error').text()).toBe("'Allocator ID' is required.")
    expect(state.writes).toEqual([])

    await choose(wrapper, '#add-listing', 'kerman-daily-foodZooket')
    await modal(wrapper).find('#add-duration').setValue('1')
    await choose(wrapper, '#config-allocator_id', 'foodZooket-kish-1T-base')
    await choose(wrapper, '#config-rule_name', 'foodZooket-kish-1step-base')
    await modal(wrapper).find('#config-impact_ratio').setValue('1')
    await modalButton(wrapper, 'Add allocator').trigger('click')
    await flushPromises()

    expect(modal(wrapper).exists()).toBe(false)
    expect(state.writes[0].body).toMatchObject({
      plan_id: '1',
      listing_id: 'kerman-daily-foodZooket',
      duration: 1,
      impact_ratio: 1,
    })
  })

  it('offers every listing from one endpoint, with no city parameter', async () => {
    const { wrapper, calls } = await setup()
    await button(wrapper, 'Edit for all').trigger('click')
    const listing = modal(wrapper).find('#plan-listing')

    // opening the list offers every listing, whatever the plan's city is
    await listing.trigger('focus')
    await flushPromises()
    expect(optionNames(wrapper)).toEqual([
      'kerman-daily-foodZooket', 'kerman-weekly-foodZooket', 'tehran-daily-foodZooket',
    ])

    // typing narrows that one list
    await listing.setValue('kerman')
    await wait(260)
    await flushPromises()
    expect(optionNames(wrapper)).toEqual([
      'kerman-daily-foodZooket', 'kerman-weekly-foodZooket',
    ])

    const listingCalls = calls.filter((c) => c.includes('/api/incentive-lookups/listings'))
    for (const call of listingCalls) expect(call).not.toContain('city=')
    expect(listingCalls).toEqual([
      'GET /api/incentive-lookups/listings?q=&limit=50',
      'GET /api/incentive-lookups/listings?q=kerman&limit=50',
    ])
  })

  it('offers the whole list again after a filter was typed and dropped', async () => {
    const { wrapper } = await setup()
    await button(wrapper, 'Edit for all').trigger('click')
    const listing = modal(wrapper).find('#plan-listing')

    await listing.trigger('focus')
    await flushPromises()
    expect(optionNames(wrapper)).toHaveLength(3)

    // narrow it down, then leave without picking anything
    await listing.setValue('tehran')
    await wait(260)
    await flushPromises()
    expect(optionNames(wrapper)).toEqual(['tehran-daily-foodZooket'])
    await listing.trigger('blur')
    await flushPromises()
    expect(wrapper.findAll('li[role=option]')).toHaveLength(0)
    // leaving without picking reverts the box to the plan's own value
    expect(listing.element.value).toBe('kerman-daily-foodZooket')

    // reopening must not keep the abandoned filter
    await listing.trigger('focus')
    await flushPromises()
    expect(optionNames(wrapper)).toHaveLength(3)
  })

  it('says when a lookup is down instead of letting a name be typed in', async () => {
    const { wrapper, state } = await setup({ lookupError: 'Could not reach the allocators service' })
    await button(wrapper, '+ Add allocator').trigger('click')
    const allocator = modal(wrapper).find('#config-allocator_id')
    await allocator.trigger('focus')
    await flushPromises()
    expect(modal(wrapper).text()).toContain('allocator lookup unavailable')

    // a typed name is a filter, not a value, so the field stays empty
    await allocator.setValue('typed-by-hand')
    await wait(260)
    await flushPromises()
    expect(allocator.element.value).toBe('typed-by-hand')
    await modal(wrapper).find('#config-impact_ratio').setValue('0.5')
    await modalButton(wrapper, 'Add allocator').trigger('click')
    await flushPromises()

    expect(modal(wrapper).find('.form-error').text()).toBe("'Allocator ID' is required.")
    expect(state.writes).toEqual([])
  })

  it('shows a write failure inside the popup and keeps it open', async () => {
    const { wrapper, state } = await setup({ writeError: 'Cannot connect to the database' })
    await button(wrapper, 'Edit for all').trigger('click')
    await modalButton(wrapper, 'Save for all allocators').trigger('click')
    await flushPromises()

    expect(modal(wrapper).find('.form-error').text()).toBe('Cannot connect to the database')
    expect(modal(wrapper).exists()).toBe(true)
    expect(toastText(wrapper)).toBe('')
    expect(state.writes).toHaveLength(1)
  })

  it('loads a row change history on demand', async () => {
    const { wrapper } = await setup()
    await rows(wrapper)[0].find('button.chevron-disc').trigger('click')
    const detail = wrapper.find('tbody tr.detail-row')
    await button(detail, 'Change history').trigger('click')
    await flushPromises()

    const entries = detail.findAll('.history-item')
    expect(entries).toHaveLength(1)
    expect(entries[0].text()).toContain('previous values')
    expect(entries[0].text()).not.toContain('2026-09-14T10:11:16')
    expect(field(entries[0], 'Impact Ratio').find('dd').text()).toBe('0.7')
    expect(field(entries[0], 'Clustering Method').find('dd').text()).toBe('dbscan')
    // the logged list values read as chips too, nulls dropped
    expect(text(field(entries[0], 'Districts').findAll('.chip'))).toEqual(['Sadra', 'District 3'])
    // identifying columns and plan-level ones are not repeated as fields
    for (const label of ['Log ID', 'Config ID', 'Changed At', 'Plan ID', 'Listing ID', 'Duration']) {
      expect(text(entries[0].findAll('.detail-facts dt'))).not.toContain(label)
    }

    await button(detail, 'Hide change history').trigger('click')
    await flushPromises()
    expect(detail.findAll('.history-item')).toHaveLength(0)
  })

  it('retries a failed change history instead of closing the panel', async () => {
    const { wrapper, state } = await setup({ logError: 'Could not read the log table' })
    await rows(wrapper)[0].find('button.chevron-disc').trigger('click')
    const detail = wrapper.find('tbody tr.detail-row')
    await button(detail, 'Change history').trigger('click')
    await flushPromises()
    expect(detail.text()).toContain('Could not read the log table')

    // fixing the upstream and retrying re-reads it, rather than just hiding it
    state.logError = ''
    await button(detail, 'Retry').trigger('click')
    await flushPromises()
    expect(detail.findAll('.history-item')).toHaveLength(1)
  })

  it('keeps deactivated rows out of the list until asked for', async () => {
    const { wrapper } = await setup({
      deactivated: [{ id: 9, plan_id: 1, allocator_id: 'old-allocator', rule_name: 'old-rule', impact_ratio: 0.2, deactivated_at: '2026-09-12T08:00:00' }],
    })
    expect(rows(wrapper)).toHaveLength(2)
    await button(wrapper, 'Show deactivated (1)').trigger('click')
    await flushPromises()
    expect(rows(wrapper)).toHaveLength(3)
    expect(rows(wrapper)[2].text()).toContain('Deactivated')
    // a deactivated row offers no actions
    expect(rowButtons(wrapper, 2)).toHaveLength(0)
    await button(wrapper, 'Hide deactivated').trigger('click')
    await flushPromises()
    expect(rows(wrapper)).toHaveLength(2)
  })

  it('expands and collapses every row at once', async () => {
    const { wrapper } = await setup()
    await button(wrapper, 'Expand all').trigger('click')
    expect(wrapper.findAll('tbody tr.detail-row')).toHaveLength(2)
    await button(wrapper, 'Collapse all').trigger('click')
    expect(wrapper.findAll('tbody tr.detail-row')).toHaveLength(0)
  })

  it('keeps the plan on screen when the base-config lookup fails', async () => {
    const { wrapper } = await setup({
      configError: "Table 'incentive/incentive_base_configs' does not exist in the database.",
    })
    expect(wrapper.find('h1').text()).toContain('1')
    expect(rows(wrapper)).toHaveLength(0)
    expect(wrapper.find('.config-error').text()).toContain('does not exist in the database')
    await button(wrapper.find('.config-error'), 'Retry').trigger('click')
    await flushPromises()
    expect(wrapper.find('.config-error').text()).toContain('does not exist in the database')
  })
})
