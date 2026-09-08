<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { scoreTypeLabel, scoreTypeOptions, scoreTypeValue } from '../lib/decisionMatrixScoreTypes'

const props = defineProps({
  id: { type: String, required: true },
  modelValue: { type: String, default: '' },
  maxlength: { type: Number, default: undefined },
  autofocus: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])
const text = ref(scoreTypeLabel(props.modelValue))
const root = ref(null)
const input = ref(null)
const open = ref(false)
const filter = ref('')
const highlighted = ref(-1)
const options = computed(() => {
  const query = filter.value.trim().toLowerCase()
  const items = scoreTypeOptions
    .filter((option) => option.label.toLowerCase().includes(query) || option.value.includes(query))
    .map((option) => ({ ...option, custom: false }))
  const custom = text.value.trim()
  if (custom && !scoreTypeOptions.some((option) => option.value === scoreTypeValue(custom))) {
    items.push({ value: custom, label: `Use “${custom}”`, custom: true })
  }
  return items
})
const listId = computed(() => `${props.id}-options`)
const activeDescendant = computed(() =>
  open.value && highlighted.value >= 0 && options.value[highlighted.value]
    ? `${listId.value}-${highlighted.value}` : undefined
)

// Keep typing/cursor position intact when our own input updates the model.
// External values and selected options are displayed using their UI captions.
watch(() => props.modelValue, (value) => {
  if (scoreTypeValue(text.value) !== value) text.value = scoreTypeLabel(value)
})

function close() {
  open.value = false
  highlighted.value = -1
}
function show() {
  if (props.disabled) return
  filter.value = ''
  highlighted.value = -1
  open.value = true
}
function toggle() {
  if (open.value) close()
  else {
    show()
    input.value?.focus()
  }
}
function change(event) {
  text.value = event.target.value
  filter.value = text.value
  emit('update:modelValue', scoreTypeValue(text.value))
  highlighted.value = -1
  open.value = true
}
function choose(option) {
  text.value = option.custom ? option.value : option.label
  emit('update:modelValue', option.value)
  filter.value = ''
  close()
}
function onKey(event) {
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (!open.value) show()
    const count = options.value.length
    if (!count) return
    highlighted.value = event.key === 'ArrowDown'
      ? (highlighted.value + 1) % count
      : (highlighted.value < 0 ? count - 1 : (highlighted.value - 1 + count) % count)
  } else if (event.key === 'Enter' && open.value) {
    event.preventDefault()
    const option = options.value[highlighted.value < 0 ? 0 : highlighted.value]
    if (option) choose(option)
    else close()
  } else if (event.key === 'Escape' && open.value) {
    // Close this dropdown first, not the surrounding dialog.
    event.preventDefault()
    event.stopPropagation()
    close()
  } else if (event.key === 'Tab') {
    close()
  }
}
function outside(event) {
  if (!root.value?.contains(event.target)) close()
}
onMounted(() => document.addEventListener('pointerdown', outside))
onBeforeUnmount(() => document.removeEventListener('pointerdown', outside))
</script>

<template>
  <div ref="root" class="score-picker">
    <div class="input-wrap">
      <input
        :id="id" ref="input" :value="text" type="text" role="combobox" required
        :maxlength="maxlength" :autofocus="autofocus" :disabled="disabled"
        :aria-expanded="open" :aria-controls="listId" :aria-activedescendant="activeDescendant"
        aria-autocomplete="list" aria-haspopup="listbox" autocomplete="off"
        placeholder="Select or write a new score type"
        @focus="show" @input="change" @blur="close" @keydown="onKey"
      />
      <button
        type="button" class="picker-toggle" :disabled="disabled"
        aria-label="Toggle score type choices" :aria-expanded="open" :aria-controls="listId"
        @pointerdown.prevent @click="toggle"
      >
        <svg :class="{ rotated: open }" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
          <path d="m4 6 4 4 4-4" />
        </svg>
      </button>
    </div>
    <Transition name="picker">
      <div v-show="open" class="picker-menu">
        <ul :id="listId" role="listbox" aria-label="Score type choices">
          <li
            v-for="(option, index) in options" :id="`${listId}-${index}`" :key="option.value"
            role="option" :aria-selected="highlighted === index" :class="{ highlighted: highlighted === index }"
            @pointerdown.prevent @mousemove="highlighted = index" @click="choose(option)"
          >
            {{ option.label }}
            <small v-if="option.custom">New score type</small>
          </li>
        </ul>
        <p>Select a suggestion or write your own name above.</p>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.score-picker { position: relative; }
.input-wrap { position: relative; }
.input-wrap input { width: 100%; padding-right: 2.75rem; }
.picker-toggle { position: absolute; top: 1px; right: 1px; bottom: 1px; width: 2.5rem; display: grid; place-items: center; padding: 0; border: 0; border-left: 1px solid var(--border); border-radius: 0 0.55rem 0.55rem 0; color: var(--accent-strong); background: var(--surface-2); }
.picker-toggle svg { display: block; width: 16px; height: 16px; transition: transform 0.15s; }
.picker-toggle .rotated { transform: rotate(180deg); }
.picker-toggle:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.picker-menu { position: absolute; top: calc(100% + 0.4rem); left: 0; right: 0; z-index: 5; border: 1px solid var(--border); border-radius: 0.6rem; background: var(--surface); box-shadow: 0 4px 12px rgba(20, 40, 30, 0.08); overflow: hidden; }
ul { max-height: 180px; overflow-y: auto; margin: 0; padding: 0.3rem; list-style: none; }
li { padding: 0.6rem 0.7rem; border-radius: 0.4rem; color: var(--text); font-size: 0.9rem; cursor: pointer; overflow-wrap: anywhere; }
li.highlighted, li:hover { background: var(--accent-soft); color: var(--accent-strong); }
li small { display: block; margin-top: 0.2rem; color: var(--muted); font-size: 0.73rem; }
p { margin: 0; padding: 0.6rem 1rem; color: var(--muted); background: #f8faf9; font-size: 0.76rem; border-top: 1px solid var(--border); }
.picker-enter-active, .picker-leave-active { transition: opacity 0.15s, transform 0.15s; transform-origin: top; }
.picker-enter-from, .picker-leave-to { opacity: 0; transform: translateY(-0.3rem); }
@media (prefers-reduced-motion: reduce) {
  .picker-enter-active, .picker-leave-active, .picker-toggle svg { transition: none; }
}
</style>
