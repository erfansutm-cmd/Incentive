<script setup>
// A search-and-select combo fed by /api/incentive-lookups. The value is always
// free text as well: if the upstream service is unreachable the field stays
// usable, it just stops suggesting.
import { computed, ref, watch } from 'vue'

const props = defineProps({
  id: { type: String, required: true },
  modelValue: { type: [String, Number], default: '' },
  // 'allocators' | 'rules' | 'listings'
  source: { type: String, required: true },
  noun: { type: String, default: 'value' },
  placeholder: { type: String, default: 'Start typing to search…' },
  disabled: { type: Boolean, default: false },
  autofocus: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const text = ref(props.modelValue === null || props.modelValue === undefined ? '' : String(props.modelValue))
const open = ref(false)
const loading = ref(false)
const error = ref('')
const options = ref([])
const highlight = ref(-1)
let timer = null
let seq = 0

// Keep an externally set value in sync without fighting the user's typing.
watch(
  () => props.modelValue,
  (value) => {
    const next = value === null || value === undefined ? '' : String(value)
    if (next !== text.value) text.value = next
  }
)

const listId = computed(() => `${props.id}-options`)

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
  } catch (e) {
    if (mine === seq) {
      options.value = []
      error.value = e.message
      open.value = false
    }
  } finally {
    if (mine === seq) loading.value = false
  }
}

function onInput() {
  emit('update:modelValue', text.value)
  highlight.value = -1
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => search(text.value.trim()), 200)
}

function onFocus() {
  if (!options.value.length) search(text.value.trim())
  else open.value = true
}

function pick(name) {
  text.value = name
  emit('update:modelValue', name)
  open.value = false
  highlight.value = -1
}

function onKeydown(event) {
  if (!open.value || !options.value.length) {
    if (event.key === 'Escape') open.value = false
    return
  }
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    highlight.value = (highlight.value + 1) % options.value.length
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    highlight.value = (highlight.value + options.value.length - 1) % options.value.length
  } else if (event.key === 'Enter') {
    if (highlight.value >= 0) {
      event.preventDefault()
      pick(options.value[highlight.value])
    } else {
      open.value = false
    }
  } else if (event.key === 'Escape' || event.key === 'Tab') {
    open.value = false
  }
}
</script>

<template>
  <div class="combo">
    <input
      :id="id"
      v-model="text"
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
      @blur="open = false"
    />
    <ul v-if="open && options.length" :id="listId" role="listbox" class="suggest">
      <li
        v-for="(name, i) in options"
        :key="name"
        role="option"
        :aria-selected="i === highlight"
        :class="{ active: i === highlight }"
        @mousedown.prevent="pick(name)"
        @mouseenter="highlight = i"
      >
        {{ name }}
      </li>
    </ul>
    <p v-if="error" class="hint warn">
      {{ noun }} lookup unavailable — type the {{ noun }} manually.
    </p>
    <p v-else-if="loading" class="hint">Searching {{ noun }}s…</p>
  </div>
</template>

<style scoped>
.combo {
  position: relative;
}
.combo input {
  width: 100%;
  padding: 0.55rem 0.7rem;
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
.hint {
  margin: 0.3rem 0 0;
  font-size: 0.78rem;
  color: var(--muted);
}
.hint.warn {
  color: var(--warning);
}
</style>
