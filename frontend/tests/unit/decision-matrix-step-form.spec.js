// Decision Matrix — adding a step.
//
// A score is a whole number of 0 or more: the first step of a series may be
// score 0. These tests mount the real add form (no browser, no backend) and
// check that 0 is accepted, kept in the payload, and still guarded against an
// active duplicate — the guards used to ignore a stored 0 as if it were empty.
import { describe, it, expect } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import DecisionMatrixStepForm from '../../src/components/DecisionMatrixStepForm.vue'

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

function step(overrides = {}) {
  return {
    id: 1,
    incentive_type: 1,
    city_group: 'Group A',
    score_type: 'Delivery',
    score: 0,
    target_increase: 0.125,
    pr_increase: 1.75,
    control_bucket: null,
    created_at: '2026-09-08T12:00:00',
    deactivated_at: null,
    ...overrides,
  }
}

function mountForm({ steps = [], nextScore = 1 } = {}) {
  return mount(DecisionMatrixStepForm, {
    props: {
      context: {
        mode: 'step', cityGroup: 'Group A', incentiveType: 1, typeName: 'DAILY',
        scoreType: 'Delivery', nextScore,
      },
      columns,
      types: [{ id: 1, name: 'DAILY' }],
      steps,
    },
    attachTo: document.body,
  })
}

const fieldByLabel = (wrapper, label) =>
  wrapper.findAll('label').find((el) => el.find('span').exists() && el.find('span').text() === label)
    .find('input')
const buttonWithText = (wrapper, text) =>
  wrapper.findAll('button').find((button) => button.text() === text)

describe('Decision Matrix add form — a score of 0', () => {
  it('accepts 0 and sends it as the score', async () => {
    const wrapper = mountForm({ nextScore: 0 })
    await flushPromises()

    const scoreInput = fieldByLabel(wrapper, 'Score')
    expect(scoreInput.attributes('min')).toBe('0')
    expect(wrapper.text()).toContain('another unused whole number (0 or more)')
    // The suggestion for a series with no steps yet is what the context says.
    expect(scoreInput.element.value).toBe('0')
    expect(wrapper.text()).not.toContain('is already active')

    await fieldByLabel(wrapper, 'Target increase').setValue('0.4')
    await fieldByLabel(wrapper, 'PR increase').setValue('1.9')
    await buttonWithText(wrapper, 'Save step').trigger('click')

    expect(wrapper.emitted('save')[0][0]).toEqual({
      city_group: 'Group A', incentive_type: 1, score_type: 'Delivery', score: 0,
      target_increase: 0.4, pr_increase: 1.9, control_bucket: null,
    })
  })

  it('treats an active step with score 0 as taken, and refuses a negative score', async () => {
    const wrapper = mountForm({ steps: [step({ score: 0 })], nextScore: 1 })
    await flushPromises()

    await fieldByLabel(wrapper, 'Target increase').setValue('0.4')
    await fieldByLabel(wrapper, 'PR increase').setValue('1.9')
    await fieldByLabel(wrapper, 'Score').setValue('0')
    expect(wrapper.text()).toContain('Score 0 is already active for this score type')
    expect(buttonWithText(wrapper, 'Save step').attributes('disabled')).toBeDefined()

    await fieldByLabel(wrapper, 'Score').setValue('1')
    expect(wrapper.text()).not.toContain('is already active')
    expect(buttonWithText(wrapper, 'Save step').attributes('disabled')).toBeUndefined()

    await fieldByLabel(wrapper, 'Score').setValue('-1')
    expect(buttonWithText(wrapper, 'Save step').attributes('disabled')).toBeDefined()
    await fieldByLabel(wrapper, 'Score').setValue('1.5')
    expect(buttonWithText(wrapper, 'Save step').attributes('disabled')).toBeDefined()
  })

  it('copies the values of the nearest active step when that step is score 0', async () => {
    const wrapper = mountForm({
      steps: [step({ score: 0, target_increase: 0.05, pr_increase: 1.1 }),
        step({ id: 2, score: 4, target_increase: 0.9, pr_increase: 3.5 })],
      nextScore: 1,
    })
    await flushPromises()

    // Score 1 sits next to the score-0 step, so its values are prefilled.
    expect(wrapper.text()).toContain('Nearest active step: score 0')
    expect(fieldByLabel(wrapper, 'Target increase').element.value).toBe('0.05')
    expect(fieldByLabel(wrapper, 'PR increase').element.value).toBe('1.1')

    await fieldByLabel(wrapper, 'Score').setValue('4')
    expect(wrapper.text()).toContain('Nearest active step: score 4')
    expect(fieldByLabel(wrapper, 'Target increase').element.value).toBe('0.9')
    expect(wrapper.text()).toContain('Score 4 is already active')
  })
})
