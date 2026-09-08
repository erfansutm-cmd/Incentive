<script setup>
import { computed, reactive, ref } from 'vue'
import ModalDialog from './ModalDialog.vue'

const props = defineProps({
  context: { type: Object, required: true },
  columns: { type: Array, required: true },
  types: { type: Array, default: () => [] },
  existingScoreTypes: { type: Array, default: () => [] },
  saving: { type: Boolean, default: false },
  error: { type: String, default: '' },
})
const emit = defineEmits(['save', 'close'])
const valueLabels = {
  target_increase: 'Target increase',
  pr_increase: 'PR increase',
  control_bucket: 'Control bucket',
}
const values = computed(() => Object.entries(valueLabels).map(([name, label]) => ({
  ...props.columns.find((col) => col.name === name), name, label,
})))
const form = reactive({
  incentive_type: props.context.incentiveType ?? '',
  score_type: String(props.context.scoreType ?? ''),
  ...Object.fromEntries(values.value.map((col) => [col.name, col.default ?? ''])),
})
const validationError = ref('')
const title = computed(() => ({
  type: 'Add incentive type',
  scoreType: 'Add score type',
  step: `Add score ${props.context.nextScore}`,
})[props.context.mode])
const scoreTypeColumn = computed(() => props.columns.find((col) => col.name === 'score_type'))
const canSubmit = computed(() =>
  String(form.incentive_type) !== '' && form.score_type.trim() !== '' &&
  (props.context.mode !== 'type' || props.types.some((type) => String(type.id) === String(form.incentive_type)))
)

function isNumber(col) {
  return /^(tinyint|smallint|mediumint|int|integer|bigint|decimal|numeric|float|double|real)\b/i.test(col?.type || '')
}
function inputStep(col) {
  return /^(tinyint|smallint|mediumint|int|integer|bigint)\b/i.test(col?.type || '') ? '1' : 'any'
}
function maxLength(col) {
  const match = /^(?:var)?char\((\d+)\)/i.exec(col?.type || '')
  return match ? Number(match[1]) : undefined
}
function required(col) {
  return !col.nullable && (col.default === null || col.default === undefined)
}

function submit() {
  if (props.saving || !canSubmit.value) return
  validationError.value = ''
  const scoreType = form.score_type.trim()
  if (props.context.mode === 'scoreType' && props.existingScoreTypes.some(
    (name) => String(name).toLowerCase() === scoreType.toLowerCase()
  )) {
    validationError.value = 'This score type already exists. Open its panel to add the next step.'
    return
  }
  emit('save', {
    city_group: props.context.cityGroup,
    incentive_type: form.incentive_type,
    score_type: scoreType,
    score: props.context.nextScore,
    ...Object.fromEntries(values.value.map((col) => [col.name, form[col.name] === '' ? null : form[col.name]])),
  })
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
      <p v-if="context.mode === 'type'" class="hint intro">
        Add an existing incentive type by saving its first score type and score 1.
      </p>
      <p v-else-if="context.mode === 'scoreType'" class="hint intro">
        Name the new score type and set the values for its first step.
      </p>

      <fieldset :disabled="saving">
        <label v-if="context.mode === 'type'" class="field">
          <span>Incentive type</span>
          <select v-model="form.incentive_type" required autofocus>
            <option value="" disabled>Select an incentive type…</option>
            <option v-for="type in types" :key="type.id" :value="type.id">
              {{ type.name }} (#{{ type.id }})
            </option>
          </select>
          <small class="hint">Only existing types are available. The ID is saved, not the name.</small>
        </label>
        <label v-if="context.mode !== 'step'" class="field">
          <span>Score type</span>
          <input
            v-model="form.score_type"
            type="text"
            required
            :maxlength="maxLength(scoreTypeColumn)"
            :autofocus="context.mode === 'scoreType'"
            placeholder="Enter a score type"
            autocomplete="off"
          />
        </label>
        <label class="field">
          <span>Score</span>
          <input :value="context.nextScore" type="number" readonly aria-describedby="matrix-score-hint" />
          <small id="matrix-score-hint" class="hint">
            Assigned automatically: starts at 1, then increases by 1. Deactivated scores are not reused.
          </small>
        </label>
        <div class="value-fields">
          <label v-for="(col, index) in values" :key="col.name" class="field">
            <span>{{ col.label }} <em v-if="col.nullable" class="opt">(optional)</em></span>
            <input
              :value="form[col.name]"
              @input="form[col.name] = $event.target.value"
              :type="isNumber(col) ? 'number' : 'text'"
              :step="isNumber(col) ? inputStep(col) : undefined"
              :min="/unsigned/i.test(col.type || '') ? 0 : undefined"
              :maxlength="maxLength(col)"
              :required="required(col)"
              :autofocus="context.mode === 'step' && index === 0"
              :placeholder="col.nullable ? 'Not set' : 'Enter a value'"
            />
          </label>
        </div>
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
.context {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.45rem;
  padding: 0.65rem 0.8rem;
  background: var(--accent-soft);
  border: 1px solid #cfdfd7;
  border-radius: 0.6rem;
  font-size: 0.88rem;
  overflow-wrap: anywhere;
}
.context span { color: var(--muted); }
.hint { color: var(--muted); font-size: 0.8rem; line-height: 1.5; }
.intro { margin: 0 0 1rem; }
fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }
.field select {
  width: 100%;
  padding: 0.55rem 0.7rem;
  border: 1px solid var(--border);
  border-radius: 0.55rem;
  font: inherit;
  color: var(--text);
  background: #fbfdfc;
}
.field select:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.field input[readonly] { background: var(--surface-2); color: var(--muted); }
.value-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 1rem; }
.value-fields .field:last-child { grid-column: 1 / -1; }
.value-fields input { width: 100%; }
.form-error {
  padding: 0.65rem 0.8rem;
  border-radius: 0.55rem;
  background: var(--danger-soft);
  color: #8c3030;
  font-size: 0.85rem;
}
@media (max-width: 480px) {
  .value-fields { grid-template-columns: 1fr; }
}
</style>
