<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  suggestions: { type: Array, default: () => [] },
  placeholder: { type: String, default: 'Type and press Enter…' },
  // 'text' (delivery categories) or 'number' (customer ids)
  kind: { type: String, default: 'text' },
})

const emit = defineEmits(['update:modelValue'])

const inputValue = ref('')
const focused = ref(false)
const inputEl = ref(null)

const tags = computed(() => props.modelValue || [])

const availableSuggestions = computed(() => {
  const current = new Set(tags.value.map((t) => String(t)))
  const q = inputValue.value.trim().toLowerCase()
  return props.suggestions.filter((s) => {
    if (current.has(String(s))) return false
    if (!q) return true
    return String(s).toLowerCase().includes(q)
  })
})

function emitTags(next) {
  // de-duplicate while preserving order
  const seen = new Set()
  const out = []
  for (const t of next) {
    const key = String(t).trim()
    if (key === '' || seen.has(key)) continue
    seen.add(key)
    if (props.kind === 'number') {
      const n = Number(key)
      out.push(Number.isFinite(n) ? n : key)
    } else {
      out.push(key)
    }
  }
  emit('update:modelValue', out)
}

function addTag(raw) {
  const value = String(raw ?? '').trim()
  if (!value) return
  const parts = value
    .split(/[,\n]/)
    .map((p) => p.trim())
    .filter(Boolean)
  emitTags([...tags.value, ...parts])
  inputValue.value = ''
}

function removeTag(tag) {
  emitTags(tags.value.filter((t) => String(t) !== String(tag)))
}

function onKeydown(e) {
  if (e.key === 'Enter' || e.key === ',') {
    e.preventDefault()
    addTag(inputValue.value)
  } else if (e.key === 'Backspace' && !inputValue.value && tags.value.length) {
    removeTag(tags.value[tags.value.length - 1])
  }
}

function onBlur() {
  // keep the chip if the user typed something but didn't press Enter
  if (inputValue.value.trim()) addTag(inputValue.value)
  focused.value = false
}

function pickSuggestion(s) {
  addTag(s)
  inputEl.value?.focus()
}

function focusInput() {
  inputEl.value?.focus()
}
</script>

<template>
  <div class="tag-field" :class="{ active: focused }">
    <div class="tag-box" @click="focusInput">
      <span v-for="tag in tags" :key="tag" class="chip">
        {{ tag }}
        <button
          type="button"
          class="chip-x"
          title="Remove"
          @click.stop="removeTag(tag)"
        >
          ×
        </button>
      </span>
      <input
        ref="inputEl"
        v-model="inputValue"
        class="tag-input"
        :placeholder="tags.length ? '' : placeholder"
        @keydown="onKeydown"
        @focus="focused = true"
        @blur="onBlur"
      />
    </div>
    <div v-if="availableSuggestions.length" class="suggestions">
      <span class="suggest-label">Suggestions:</span>
      <button
        v-for="s in availableSuggestions.slice(0, 12)"
        :key="s"
        type="button"
        class="suggest-chip"
        @mousedown.prevent="pickSuggestion(s)"
      >
        + {{ s }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.tag-field {
  width: 100%;
}
.tag-box {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  min-height: 2.4rem;
  padding: 0.3rem 0.45rem;
  border: 1px solid var(--border);
  border-radius: 0.55rem;
  background: #fbfdfc;
  cursor: text;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
}
.tag-box.active,
.tag-box:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-ring);
  background: #fff;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.18rem 0.3rem 0.18rem 0.6rem;
  background: var(--accent-soft);
  color: var(--accent-strong);
  border: 1px solid #cfe3d9;
  border-radius: 999px;
  font-size: 0.85rem;
  font-weight: 600;
  line-height: 1.2;
}
.chip-x {
  border: none;
  background: transparent;
  color: var(--accent-strong);
  font-size: 0.95rem;
  line-height: 1;
  padding: 0 0.25rem;
  border-radius: 999px;
  cursor: pointer;
}
.chip-x:hover {
  background: #d3e6dd;
}
.tag-input {
  flex: 1;
  min-width: 120px;
  border: none;
  outline: none;
  background: transparent;
  font-size: 0.92rem;
  color: var(--text);
  padding: 0.2rem 0.25rem;
}
.suggestions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  margin-top: 0.45rem;
}
.suggest-label {
  font-size: 0.75rem;
  color: var(--muted);
  font-weight: 600;
}
.suggest-chip {
  border: 1px dashed #bcd6ca;
  background: #fff;
  color: var(--accent-strong);
  border-radius: 999px;
  padding: 0.15rem 0.6rem;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease;
}
.suggest-chip:hover {
  background: var(--accent-soft);
  border-style: solid;
  border-color: var(--accent);
}
</style>
