<script setup>
// Sensitivity group: either nothing at all, or exactly three floats. The three
// are stored as a JSON list, and an incomplete set is not a valid value — the
// field is either empty or complete.
import { computed } from 'vue'

const props = defineProps({
  id: { type: String, required: true },
  // the parsed list of up to three numbers, as strings while being typed
  modelValue: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const LABELS = ['Group 1', 'Group 2', 'Group 3']

const items = computed(() => {
  const current = props.modelValue || []
  return LABELS.map((_, i) => {
    const value = current[i]
    return value === null || value === undefined ? '' : String(value)
  })
})

const filled = computed(() => items.value.filter((v) => String(v).trim() !== '').length)

const incomplete = computed(() => filled.value > 0 && filled.value < 3)

const invalid = computed(() =>
  items.value.some((v) => String(v).trim() !== '' && !Number.isFinite(Number(v)))
)

function update(index, event) {
  const next = [...items.value]
  next[index] = event.target.value
  emit('update:modelValue', next)
}
</script>

<template>
  <div class="triple" :class="{ 'is-invalid': invalid }">
    <label v-for="(label, i) in LABELS" :key="label" class="triple-field">
      <span>{{ label }}</span>
      <input
        :id="i === 0 ? id : `${id}-${i + 1}`"
        :value="items[i]"
        type="number"
        step="0.0001"
        :disabled="disabled"
        placeholder="0.0"
        @input="update(i, $event)"
      />
    </label>
  </div>
  <p v-if="invalid" class="hint warn">Each group must be a number.</p>
  <p v-else-if="incomplete" class="hint warn">
    All three groups are needed, or none — {{ filled }} of 3 filled.
  </p>
  <p v-else-if="filled === 0" class="hint">Leave all three empty for no sensitivity group.</p>
  <p v-else class="hint">Three groups set.</p>
</template>

<style scoped>
.triple {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.45rem;
}
.triple-field {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.triple-field span {
  font-size: 0.72rem;
  font-weight: 500;
  color: var(--muted);
}
.triple-field input {
  width: 100%;
  padding: 0.5rem 0.55rem;
  border: 1px solid var(--border);
  border-radius: 0.5rem;
  font-size: 0.92rem;
  outline: none;
  color: var(--text);
  background: #fbfdfc;
}
.triple-field input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-ring);
  background: #fff;
}
.triple.is-invalid input {
  border-color: var(--warning);
}
.hint {
  margin: 0.3rem 0 0;
  font-size: 0.78rem;
  color: var(--muted);
}
.hint.warn {
  color: var(--warning);
}
</style>
