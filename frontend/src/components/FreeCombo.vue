<script setup>
// A combo that both offers a known list and accepts anything typed: the stored
// value is free text, so an unlisted method is as valid as a listed one.
import { computed, ref, watch } from 'vue'

const props = defineProps({
  id: { type: String, required: true },
  modelValue: { type: [String, Number], default: '' },
  options: { type: Array, default: () => [] },
  noun: { type: String, default: 'value' },
  placeholder: { type: String, default: 'Select or type…' },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const asText = (v) => (v === null || v === undefined ? '' : String(v))

const open = ref(false)
const highlight = ref(-1)
const filter = ref('')
const listId = computed(() => `${props.id}-options`)
const selected = computed(() => asText(props.modelValue))

// What is offered: everything matching what has been typed, plus — when the
// typed text is new — an explicit "use this" entry so free text is a choice.
// The query is the typed filter, not the stored value, so opening a field that
// already holds a method still offers the whole list to switch to.
const matches = computed(() => {
  const query = filter.value.trim().toLowerCase()
  return props.options.filter((o) => asText(o).toLowerCase().includes(query))
})
const isListed = computed(() =>
  props.options.some((o) => asText(o).toLowerCase() === filter.value.trim().toLowerCase())
)
const canAdd = computed(() => filter.value.trim() !== '' && !isListed.value)

function onInput(event) {
  filter.value = event.target.value
  emit('update:modelValue', event.target.value)
  highlight.value = -1
  open.value = true
}

function onFocus() {
  filter.value = ''
  open.value = true
  highlight.value = -1
}

function pick(name) {
  filter.value = ''
  emit('update:modelValue', name)
  open.value = false
  highlight.value = -1
}

function clear() {
  filter.value = ''
  emit('update:modelValue', '')
  highlight.value = -1
}

function onBlur() {
  open.value = false
  filter.value = ''
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    open.value = false
    return
  }
  if (!open.value) return
  const count = matches.value.length + (canAdd.value ? 1 : 0)
  if (!count) return
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    highlight.value = (highlight.value + 1) % count
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    highlight.value = (highlight.value + count - 1) % count
  } else if (event.key === 'Enter') {
    if (highlight.value >= 0) {
      event.preventDefault()
      const choice =
        highlight.value < matches.value.length
          ? asText(matches.value[highlight.value])
          : filter.value.trim()
      pick(choice)
    }
  } else if (event.key === 'Tab') {
    open.value = false
  }
}
</script>

<template>
  <div class="combo">
    <div class="combo-box">
      <input
        :id="id"
        :value="selected"
        type="text"
        autocomplete="off"
        role="combobox"
        :aria-expanded="open && (matches.length > 0 || canAdd)"
        :aria-controls="listId"
        :aria-autocomplete="'list'"
        :placeholder="placeholder"
        :disabled="disabled"
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
    <ul
      v-if="open && (matches.length || canAdd)"
      :id="listId"
      role="listbox"
      class="suggest"
    >
      <li
        v-for="(name, i) in matches"
        :key="`opt-${name}`"
        role="option"
        :aria-selected="i === highlight"
        :class="{ active: i === highlight, chosen: asText(name) === selected.trim() }"
        @mousedown.prevent="pick(asText(name))"
        @mouseenter="highlight = i"
      >
        <span class="opt-name">{{ name }}</span>
        <span v-if="asText(name).toLowerCase() === selected.trim().toLowerCase()" class="opt-tick">
          selected
        </span>
      </li>
      <li
        v-if="canAdd"
        role="option"
        :aria-selected="highlight === matches.length"
        :class="{ active: highlight === matches.length, custom: true }"
        @mousedown.prevent="pick(filter.trim())"
        @mouseenter="highlight = matches.length"
      >
        <span class="opt-name">Use “{{ filter.trim() }}”</span>
      </li>
    </ul>
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
.suggest li.custom {
  color: var(--muted);
  font-style: italic;
}
.opt-tick {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
}
</style>
