<script setup>
// A select fed by /api/incentive-lookups: typing only *filters* the offered
// names, the value itself always comes from the list. Nothing typed by hand
// becomes a value, so a row can never hold a name the service does not have.
import { computed, ref, watch } from 'vue'

const props = defineProps({
  id: { type: String, required: true },
  modelValue: { type: [String, Number], default: '' },
  // 'allocators' | 'rules' | 'listings'
  source: { type: String, required: true },
  noun: { type: String, default: 'value' },
  placeholder: { type: String, default: 'Select…' },
  disabled: { type: Boolean, default: false },
  autofocus: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const asText = (v) => (v === null || v === undefined ? '' : String(v))

// What the box shows: the chosen name, or the filter being typed while open.
const filter = ref('')
const open = ref(false)
const loading = ref(false)
const error = ref('')
const options = ref([])
const highlight = ref(-1)
let timer = null
let seq = 0

const selected = computed(() => asText(props.modelValue))
const shown = computed(() => (open.value ? filter.value : selected.value))
const listId = computed(() => `${props.id}-options`)

// Keep an externally set value in sync with the box.
watch(
  () => props.modelValue,
  () => {
    if (!open.value) filter.value = ''
  }
)

async function search(term) {
  const mine = ++seq
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ q: term, limit: '50' })
    const res = await fetch(`/api/incentive-lookups/${props.source}?${params.toString()}`)
    const data = await res.json()
    if (mine !== seq) return // a newer keystroke already won
    if (!res.ok) throw new Error(data.message || data.detail || 'Lookup failed')
    options.value = (data.rows || []).map((row) => row.name)
    open.value = true
    highlight.value = options.value.indexOf(selected.value)
  } catch (e) {
    if (mine === seq) {
      options.value = []
      error.value = e.message
    }
  } finally {
    if (mine === seq) loading.value = false
  }
}

function onInput(event) {
  filter.value = event.target.value
  highlight.value = -1
  open.value = true
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => search(filter.value.trim()), 200)
}

function onFocus() {
  filter.value = ''
  open.value = true
  if (!options.value.length) search('')
}

// Leaving the box without picking reverts to the chosen name: a typed string
// is a filter, never a value.
function onBlur() {
  open.value = false
  filter.value = ''
}

function pick(name) {
  emit('update:modelValue', name)
  filter.value = ''
  open.value = false
  highlight.value = -1
}

function clear() {
  emit('update:modelValue', '')
  filter.value = ''
  highlight.value = -1
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    open.value = false
    filter.value = ''
    return
  }
  if (!open.value || !options.value.length) return
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    highlight.value = (highlight.value + 1) % options.value.length
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    highlight.value = (highlight.value + options.value.length - 1) % options.value.length
  } else if (event.key === 'Enter') {
    event.preventDefault()
    if (highlight.value >= 0) pick(options.value[highlight.value])
    else open.value = false
  } else if (event.key === 'Tab') {
    open.value = false
  }
}
</script>

<template>
  <div class="combo" :class="{ 'has-error': Boolean(error) }">
    <div class="combo-box">
      <input
        :id="id"
        :value="shown"
        type="text"
        autocomplete="off"
        role="combobox"
        :aria-expanded="open && options.length > 0"
        :aria-controls="listId"
        :aria-autocomplete="'list'"
        :placeholder="placeholder"
        :disabled="disabled"
        :autofocus="autofocus"
        @input="onInput"
        @focus="onFocus"
        @keydown="onKeydown"
        @blur="onBlur"
      />
      <button
        v-if="selected && !disabled"
        type="button"
        class="clear"
        :aria-label="`Clear ${noun}`"
        @mousedown.prevent="clear"
      >
        ×
      </button>
    </div>
    <ul v-if="open && options.length" :id="listId" role="listbox" class="suggest">
      <li
        v-for="(name, i) in options"
        :key="name"
        role="option"
        :aria-selected="i === highlight"
        :class="{ active: i === highlight, chosen: name === selected }"
        @mousedown.prevent="pick(name)"
        @mouseenter="highlight = i"
      >
        <span class="opt-name">{{ name }}</span>
        <span v-if="name === selected" class="opt-tick">selected</span>
      </li>
    </ul>
    <p v-if="open && !loading && !options.length && !error" class="hint">
      No {{ noun }} matches “{{ filter }}”.
    </p>
    <p v-if="error" class="hint warn">
      {{ noun }} lookup unavailable — the list cannot be loaded.
    </p>
    <p v-else-if="loading" class="hint">Searching {{ noun }}s…</p>
  </div>
</template>

<style scoped>
.combo {
  position: relative;
}
.combo-box {
  position: relative;
  display: flex;
  align-items: center;
}
.combo input {
  width: 100%;
  padding: 0.55rem 2rem 0.55rem 0.7rem;
  border: 1px solid var(--border);
  border-radius: 0.55rem;
  font-size: 0.95rem;
  outline: none;
  color: var(--text);
  background: #fbfdfc;
}
.combo input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-ring);
  background: #fff;
}
.combo input:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
.combo.has-error input {
  border-color: var(--warning);
}
.clear {
  position: absolute;
  right: 0.4rem;
  border: 0;
  background: none;
  color: var(--muted);
  font-size: 1.05rem;
  line-height: 1;
  padding: 0.2rem 0.35rem;
  border-radius: 0.4rem;
  cursor: pointer;
}
.clear:hover {
  background: var(--accent-soft);
  color: var(--text);
}
.suggest {
  position: absolute;
  z-index: 60;
  top: calc(100% + 0.25rem);
  left: 0;
  right: 0;
  margin: 0;
  padding: 0.25rem;
  list-style: none;
  max-height: 15rem;
  overflow-y: auto;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 0.55rem;
  box-shadow: 0 12px 30px rgba(20, 40, 30, 0.16);
}
.suggest li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.45rem 0.6rem;
  border-radius: 0.4rem;
  cursor: pointer;
  font-size: 0.92rem;
  color: var(--text);
  overflow-wrap: anywhere;
}
.suggest li:hover,
.suggest li.active {
  background: var(--accent-soft);
}
.suggest li.chosen {
  font-weight: 600;
}
.opt-tick {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
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
