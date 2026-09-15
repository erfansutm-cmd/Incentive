<script setup>
// Editing one score step. A row is never updated in place: saving deactivates
// the row being edited and adds a new active row with the new values, so the
// history of the series stays complete. The **score never changes** — it
// identifies the step inside its series — and neither do the city group, the
// incentive type and the score type; only the values below are editable.
import { computed, reactive } from 'vue'
import ModalDialog from './ModalDialog.vue'
import { scoreTypeLabel } from '../lib/decisionMatrixScoreTypes'

const props = defineProps({
  // The row being edited, as the API returns it.
  row: { type: Object, required: true },
  cityGroup: { type: String, required: true },
  typeName: { type: String, default: '' },
  saving: { type: Boolean, default: false },
  error: { type: String, default: '' },
})
const emit = defineEmits(['save', 'close'])

const floatFields = [
  { name: 'target_increase', label: 'Target increase' },
  { name: 'pr_increase', label: 'PR increase' },
]

function numberText(value) {
  if (value === null || value === undefined || String(value).trim() === '') return ''
  return Number.isFinite(Number(value)) ? String(Number(value)) : ''
}

// The score is kept: it is shown, never edited, and never sent to the API.
const score = computed(() => props.row.score)
const originalBucket = computed(() =>
  Array.isArray(props.row.control_bucket)
    ? props.row.control_bucket.map((value) => numberText(value))
    : ['', '', '']
)
const form = reactive({
  target_increase: numberText(props.row.target_increase),
  pr_increase: numberText(props.row.pr_increase),
  control_bucket: [...originalBucket.value],
})
const localError = reactive({ message: '' })
const bucketHasValues = computed(() => form.control_bucket.some((value) => String(value).trim() !== ''))
// Nothing to save while every value still matches the row being edited: the
// edit would archive it and add an identical step.
// "0.500" and "0.5" are the same value, so they do not count as a change.
function sameNumber(value, original) {
  const entered = Number(value)
  const before = Number(numberText(original))
  if (String(value).trim() !== '' && Number.isFinite(entered) && Number.isFinite(before)) {
    return entered === before
  }
  return String(value).trim() === numberText(original)
}
const bucketChanged = computed(() => {
  if (!bucketHasValues.value) return originalBucket.value.some((value) => String(value).trim() !== '')
  return form.control_bucket.some((value, index) => !sameNumber(value, props.row.control_bucket?.[index]))
})
const changed = computed(
  () =>
    !sameNumber(form.target_increase, props.row.target_increase) ||
    !sameNumber(form.pr_increase, props.row.pr_increase) ||
    bucketChanged.value
)
const canSubmit = computed(() => changed.value)

function requiredFloat(value, label) {
  if (
    value === null || value === undefined || typeof value === 'boolean' ||
    String(value).trim() === '' || !Number.isFinite(Number(value))
  ) {
    throw new Error(`${label} is required and must be a finite number.`)
  }
  return Number(value)
}
function clearBucket() {
  form.control_bucket = ['', '', '']
  localError.message = ''
}
function submit() {
  if (props.saving || !canSubmit.value) return
  localError.message = ''
  try {
    // The score is fixed, so it is not part of the payload.
    emit('save', {
      target_increase: requiredFloat(form.target_increase, 'Target increase'),
      pr_increase: requiredFloat(form.pr_increase, 'PR increase'),
      control_bucket: bucketHasValues.value
        ? form.control_bucket.map((value) => requiredFloat(value, 'Each control bucket value'))
        : null,
    })
  } catch (error) {
    localError.message = error.message
  }
}
</script>

<template>
  <ModalDialog title-id="matrix-edit-title" :busy="saving" @close="emit('close')">
    <form @submit.prevent="submit" @input="localError.message = ''">
      <h2 id="matrix-edit-title">Edit score {{ score }}</h2>
      <p class="context">
        <strong>{{ cityGroup }}</strong>
        <template v-if="typeName"> <span aria-hidden="true">/</span> {{ typeName }}</template>
        <span aria-hidden="true">/</span> {{ scoreTypeLabel(row.score_type) }}
      </p>
      <p class="hint intro">
        Saving <strong>deactivates this step</strong> and <strong>adds a new step</strong> with the
        values below. The row as it is now stays in the deactivated history.
      </p>

      <fieldset :disabled="saving">
        <div class="score-fixed">
          <span class="score-fixed-label">Score</span>
          <span class="score-fixed-value">{{ score }}</span>
          <span class="hint">stays the same — editing changes the values, not the step's score</span>
        </div>

        <div class="value-fields">
          <label v-for="field in floatFields" :key="field.name" class="field">
            <span>{{ field.label }}</span>
            <input
              v-model="form[field.name]" type="number" step="any" required placeholder="Enter a float"
            />
          </label>
        </div>

        <fieldset class="bucket-field">
          <legend>Control bucket <span class="hint">(optional)</span></legend>
          <p class="hint">Leave all three blank for null, or enter three float values.</p>
          <div class="bucket-values">
            <label v-for="(_, index) in form.control_bucket" :key="index" class="field">
              <span>Group {{ index + 1 }}</span>
              <input
                :value="form.control_bucket[index]" @input="form.control_bucket[index] = $event.target.value"
                type="number" step="any" :required="bucketHasValues" placeholder="Not set"
                :aria-label="`Control bucket group ${index + 1}`"
              />
            </label>
          </div>
          <button
            v-if="bucketHasValues" type="button" class="copy-values" @click="clearBucket"
          >Clear control bucket</button>
        </fieldset>
      </fieldset>

      <div class="preview" aria-live="polite">
        <span class="preview-label">After saving</span>
        <span class="preview-line">
          Score {{ score }} → deactivated
          <span aria-hidden="true">·</span>
          score {{ score }} active again with the new values
        </span>
      </div>

      <p v-if="!canSubmit" class="hint keep-hint">
        Change at least one value before saving — the edit would create an identical step.
      </p>
      <p v-if="localError.message || error" class="form-error" role="alert">
        {{ localError.message || error }}
      </p>
      <div class="actions">
        <button type="button" class="btn btn-ghost" :disabled="saving" @click="emit('close')">Cancel</button>
        <button type="submit" class="btn btn-primary" :disabled="saving || !canSubmit">
          {{ saving ? 'Saving…' : 'Save new values' }}
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
.score-fixed { display: flex; align-items: baseline; flex-wrap: wrap; gap: 0.3rem 0.6rem; padding: 0.6rem 0.75rem; margin: 0 0 0.85rem; border: 1px solid var(--border); border-radius: 0.55rem; background: #fbfdfc; }
.score-fixed-label { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted); }
.score-fixed-value { display: inline-grid; place-items: center; min-width: 1.8rem; padding: 0.15rem 0.5rem; border-radius: 0.45rem; background: var(--surface-2); color: var(--accent-strong); font-weight: 700; font-variant-numeric: tabular-nums; }
.value-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 1rem; }
.value-fields input, .bucket-values input { width: 100%; }
.bucket-field { padding: 0.9rem; margin: 0.2rem 0 0; border: 1px solid var(--border); border-radius: 0.6rem; }
.bucket-field legend { padding: 0 0.3rem; font-size: 0.85rem; font-weight: 600; }
.bucket-field > .hint { margin: 0 0 0.7rem; }
.bucket-values { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.6rem; }
.bucket-values .field { margin-bottom: 0; }
.bucket-field .copy-values { margin-top: 0.65rem; }
.copy-values { border: 0; padding: 0; background: transparent; color: var(--accent-strong); text-decoration: underline; font-size: 0.8rem; }
.preview { display: flex; flex-wrap: wrap; align-items: center; gap: 0.35rem 0.6rem; padding: 0.65rem 0.75rem; margin: 0.9rem 0 0; border: 1px dashed var(--border); border-radius: 0.55rem; background: #fbfdfc; font-size: 0.82rem; }
.preview-label { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted); }
.preview-line { color: var(--text); font-weight: 600; display: flex; flex-wrap: wrap; gap: 0.35rem; }
.keep-hint { margin: 0.75rem 0 0; }
.form-error { padding: 0.65rem 0.8rem; border-radius: 0.55rem; background: var(--danger-soft); color: #8c3030; font-size: 0.85rem; margin: 0.9rem 0 0; }
button:focus-visible, input:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
@media (max-width: 480px) {
  .value-fields { grid-template-columns: 1fr; }
  .bucket-values { gap: 0.35rem; }
  .bucket-values input { padding: 0.55rem 0.4rem; }
}
</style>
