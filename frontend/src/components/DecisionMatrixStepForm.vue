<script setup>
import { computed, reactive, ref, watch } from 'vue'
import ModalDialog from './ModalDialog.vue'
import ScoreTypeSelect from './ScoreTypeSelect.vue'

const props = defineProps({
  context: { type: Object, required: true },
  columns: { type: Array, required: true },
  types: { type: Array, default: () => [] },
  steps: { type: Array, default: () => [] },
  existingScoreTypes: { type: Array, default: () => [] },
  saving: { type: Boolean, default: false },
  error: { type: String, default: '' },
})
const emit = defineEmits(['save', 'close'])
const floatFields = [
  { name: 'target_increase', label: 'Target increase' },
  { name: 'pr_increase', label: 'PR increase' },
]
const form = reactive({
  incentive_type: props.context.incentiveType ?? '',
  score_type: String(props.context.scoreType ?? ''),
  score: String(props.context.nextScore ?? 1),
  target_increase: '',
  pr_increase: '',
  control_bucket: ['', '', ''],
})
const edited = reactive({ target_increase: false, pr_increase: false })
const validationError = ref('')
const title = computed(() => ({ type: 'Add incentive type', scoreType: 'Add score type', step: 'Add step' })[props.context.mode])
const scoreTypeColumn = computed(() => props.columns.find((col) => col.name === 'score_type'))
const score = computed(() => Number(form.score))
const validScore = computed(() => String(form.score).trim() !== '' && Number.isSafeInteger(score.value) && score.value > 0)
const normalize = (value) => String(value ?? '').trim().toLowerCase()
const activeSteps = computed(() => props.steps.filter((row) =>
  normalize(row.city_group) === normalize(props.context.cityGroup) &&
  String(row.incentive_type) === String(form.incentive_type) &&
  normalize(row.score_type) === normalize(form.score_type) &&
  (row.deactivated_at === null || row.deactivated_at === undefined) &&
  Number.isFinite(Number(row.score)) && Number(row.score) > 0
))
const nearestStep = computed(() => {
  if (!validScore.value) return null
  return [...activeSteps.value].sort((a, b) =>
    Math.abs(Number(a.score) - score.value) - Math.abs(Number(b.score) - score.value) ||
    Number(a.score) - Number(b.score)
  )[0] || null
})
const duplicateType = computed(() => props.context.mode === 'scoreType' &&
  props.existingScoreTypes.some((name) => normalize(name) === normalize(form.score_type))
)
const scoreConflict = computed(() => validScore.value && activeSteps.value.some((row) => Number(row.score) === score.value))
const bucketHasValues = computed(() => form.control_bucket.some((value) => String(value).trim() !== ''))
const canSubmit = computed(() =>
  String(form.incentive_type) !== '' && form.score_type.trim() !== '' && validScore.value &&
  !duplicateType.value && !scoreConflict.value &&
  (props.context.mode !== 'type' || props.types.some((type) => String(type.id) === String(form.incentive_type)))
)

function numberText(value) {
  if (value === null || value === undefined || String(value).trim() === '') return ''
  return Number.isFinite(Number(value)) ? String(value) : ''
}
// Follow the nearest active step while fields are untouched. A tie uses the
// lower score. Never replace a value the user has deliberately entered.
watch(nearestStep, (nearest) => {
  for (const { name } of floatFields) {
    if (!edited[name]) form[name] = numberText(nearest?.[name])
  }
}, { immediate: true })

function useNearest() {
  for (const { name } of floatFields) {
    edited[name] = false
    form[name] = numberText(nearestStep.value?.[name])
  }
}
function changeFloat(name, value) {
  edited[name] = true
  form[name] = value
}
function maxLength(col) {
  const match = /^(?:var)?char\((\d+)\)/i.exec(col?.type || '')
  return match ? Number(match[1]) : undefined
}
function requiredFloat(value, label) {
  if (value === null || value === undefined || typeof value === 'boolean' || String(value).trim() === '' || !Number.isFinite(Number(value))) {
    throw new Error(`${label} is required and must be a finite number.`)
  }
  return Number(value)
}
function submit() {
  if (props.saving || !canSubmit.value) return
  validationError.value = ''
  try {
    const payload = {
      city_group: props.context.cityGroup,
      incentive_type: form.incentive_type,
      score_type: form.score_type.trim(),
      score: score.value,
      target_increase: requiredFloat(form.target_increase, 'Target increase'),
      pr_increase: requiredFloat(form.pr_increase, 'PR increase'),
      control_bucket: bucketHasValues.value
        ? form.control_bucket.map((value) => requiredFloat(value, 'Each control bucket value'))
        : null,
    }
    // Once submitted, keep the reviewed values even if a conflict refreshes the
    // matrix. The user can explicitly copy a new neighbor with "Use its values".
    for (const { name } of floatFields) edited[name] = true
    emit('save', payload)
  } catch (error) {
    validationError.value = error.message
  }
}
</script>

<template>
  <ModalDialog title-id="matrix-form-title" :busy="saving" @close="emit('close')">
    <form @submit.prevent="submit" @input="validationError = ''">
      <h2 id="matrix-form-title">{{ title }}</h2>
      <p class="context">
        <strong>{{ context.cityGroup }}</strong>
        <template v-if="context.typeName"> <span aria-hidden="true">/</span> {{ context.typeName }}</template>
        <template v-if="context.mode === 'step'"> <span aria-hidden="true">/</span> {{ context.scoreType }}</template>
      </p>
      <p v-if="context.mode === 'type'" class="hint intro">Choose an incentive type and save its first score step.</p>
      <p v-else-if="context.mode === 'scoreType'" class="hint intro">Select or write a score type and set its first step.</p>

      <fieldset :disabled="saving">
        <label v-if="context.mode === 'type'" class="field">
          <span>Incentive type</span>
          <select v-model="form.incentive_type" required autofocus>
            <option value="" disabled>Select an incentive type…</option>
            <option v-for="type in types" :key="type.id" :value="type.id">{{ type.name }} (#{{ type.id }})</option>
          </select>
        </label>
        <div v-if="context.mode !== 'step'" class="field">
          <label class="field-label" for="matrix-score-type">Score type</label>
          <ScoreTypeSelect
            id="matrix-score-type" v-model="form.score_type" :disabled="saving"
            :maxlength="maxLength(scoreTypeColumn)" :autofocus="context.mode === 'scoreType'"
          />
        </div>
        <label class="field">
          <span>Score</span>
          <input
            v-model="form.score" type="number" min="1" :max="Number.MAX_SAFE_INTEGER" step="1" required
            aria-describedby="matrix-score-hint"
          />
          <small id="matrix-score-hint" class="hint">Suggested from active steps. You can choose another unused positive whole number.</small>
        </label>
        <p v-if="duplicateType" class="form-error" role="alert">This score type already exists. Open its panel to add a step.</p>
        <p v-else-if="scoreConflict" class="form-error" role="alert">Score {{ form.score }} is already active for this score type. Choose another score.</p>

        <div class="prefill-note">
          <template v-if="nearestStep">
            <span>Nearest active step: score {{ nearestStep.score }}.</span>
            <button type="button" class="copy-values" @click="useNearest">Use its values</button>
          </template>
          <span v-else>No active step to copy from. Enter target and PR increases.</span>
        </div>
        <div class="value-fields">
          <label v-for="(field, index) in floatFields" :key="field.name" class="field">
            <span>{{ field.label }}</span>
            <input
              :value="form[field.name]" @input="changeFloat(field.name, $event.target.value)"
              type="number" step="any" required placeholder="Enter a float"
              :autofocus="context.mode === 'step' && index === 0"
            />
          </label>
        </div>
        <fieldset class="bucket-field">
          <legend>Control bucket <span class="hint">(optional)</span></legend>
          <p class="hint">Leave all three blank for null, or enter three float values.</p>
          <div class="bucket-values">
            <label v-for="(_, index) in form.control_bucket" :key="index" class="field">
              <span>Value {{ index + 1 }}</span>
              <input
                :value="form.control_bucket[index]" @input="form.control_bucket[index] = $event.target.value"
                type="number" step="any" :required="bucketHasValues" placeholder="Not set"
                :aria-label="`Control bucket value ${index + 1}`"
              />
            </label>
          </div>
          <button v-if="bucketHasValues" type="button" class="copy-values" @click="form.control_bucket = ['', '', '']">Clear control bucket</button>
        </fieldset>
      </fieldset>
      <p v-if="validationError || error" class="form-error" role="alert">{{ validationError || error }}</p>
      <div class="actions">
        <button type="button" class="btn btn-ghost" :disabled="saving" @click="emit('close')">Cancel</button>
        <button type="submit" class="btn btn-primary" :disabled="saving || !canSubmit">
          {{ saving ? 'Saving…' : context.mode === 'step' ? 'Save step' : 'Save first step' }}
        </button>
      </div>
    </form>
  </ModalDialog>
</template>

<style scoped>
.context { display: flex; align-items: baseline; flex-wrap: wrap; gap: 0.45rem; padding: 0.65rem 0.8rem; background: var(--accent-soft); border: 1px solid #cfdfd7; border-radius: 0.6rem; font-size: 0.88rem; overflow-wrap: anywhere; }
.context span { color: var(--muted); }
.hint { color: var(--muted); font-size: 0.8rem; line-height: 1.5; }
.intro { margin: 0 0 1rem; }
fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }
.field-label { font-size: 0.82rem; font-weight: 600; color: var(--text); }
.field select { width: 100%; padding: 0.55rem 0.7rem; border: 1px solid var(--border); border-radius: 0.55rem; font: inherit; color: var(--text); background: #fbfdfc; }
.field select:focus-visible, .copy-values:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.value-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 1rem; }
.value-fields input, .bucket-values input { width: 100%; }
.prefill-note { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 0.4rem; padding: 0.65rem 0.75rem; margin: 0 0 0.85rem; border-radius: 0.5rem; background: var(--surface-2); color: var(--muted); font-size: 0.8rem; }
.copy-values { border: 0; padding: 0; background: transparent; color: var(--accent-strong); text-decoration: underline; font-size: 0.8rem; }
.bucket-field { padding: 0.9rem; margin: 0.2rem 0 0; border: 1px solid var(--border); border-radius: 0.6rem; }
.bucket-field legend { padding: 0 0.3rem; font-size: 0.85rem; font-weight: 600; }
.bucket-field > .hint { margin: 0 0 0.7rem; }
.bucket-values { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.6rem; }
.bucket-values .field { margin-bottom: 0; }
.bucket-field .copy-values { margin-top: 0.65rem; }
.form-error { padding: 0.65rem 0.8rem; border-radius: 0.55rem; background: var(--danger-soft); color: #8c3030; font-size: 0.85rem; }
@media (max-width: 480px) {
  .value-fields { grid-template-columns: 1fr; }
  .bucket-values { gap: 0.35rem; }
  .bucket-values input { padding: 0.55rem 0.4rem; }
}
</style>
