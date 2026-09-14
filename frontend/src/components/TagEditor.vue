<script setup>
// Editor for a list-of-strings column (districts, vendors): add a value by
// typing it and pressing Enter or comma, remove one with ×. The stored value
// stays the JSON array the database holds, so nothing about the column changes.
import { computed, ref, watch } from 'vue'

const props = defineProps({
  id: { type: String, required: true },
  // the parsed list, without the nulls the stored JSON can contain
  modelValue: { type: Array, default: () => [] },
  noun: { type: String, default: 'value' },
  placeholder: { type: String, default: 'Type a value and press Enter…' },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const draft = ref('')
const input = ref(null)

const items = computed(() => props.modelValue || [])

// Keep the box focused on the list rather than on the draft text.
watch(items, () => {
  draft.value = ''
})

function commit() {
  const value = draft.value.trim().replace(/,$/, '').trim()
  if (!value) return
  if (items.value.some((item) => item.toLowerCase() === value.toLowerCase())) {
    draft.value = ''
    return
  }
  emit('update:modelValue', [...items.value, value])
  draft.value = ''
}

function remove(index) {
  emit('update:modelValue', items.value.filter((_, i) => i !== index))
}

function onKeydown(event) {
  if (event.key === 'Enter' || event.key === ',') {
    event.preventDefault()
    commit()
  } else if (event.key === 'Backspace' && !draft.value && items.value.length) {
    event.preventDefault()
    remove(items.value.length - 1)
  }
}

function focusInput() {
  if (!props.disabled) input.value?.focus()
}
</script>

<template>
  <div class="tag-field" :class="{ disabled }" @click="focusInput">
    <ul v-if="items.length" class="chips">
      <li v-for="(item, i) in items" :key="`${item}-${i}`" class="chip">
        <span class="chip-name">{{ item }}</span>
        <button
          type="button"
          class="chip-x"
          :disabled="disabled"
          :aria-label="`Remove ${noun} ${item}`"
          @click.stop="remove(i)"
        >
          ×
        </button>
      </li>
    </ul>
    <input
      :id="id"
      ref="input"
      v-model="draft"
      type="text"
      :placeholder="items.length ? `Add another ${noun}…` : placeholder"
      :disabled="disabled"
      autocomplete="off"
      @keydown="onKeydown"
      @blur="commit"
    />
  </div>
</template>

<style scoped>
.tag-field {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.3rem;
  padding: 0.35rem 0.45rem;
  border: 1px solid var(--border);
  border-radius: 0.55rem;
  background: #fbfdfc;
  cursor: text;
}
.tag-field:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-ring);
  background: #fff;
}
.tag-field.disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
.tag-field input {
  flex: 1 1 8rem;
  min-width: 8rem;
  border: 0;
  outline: none;
  background: none;
  font-size: 0.92rem;
  color: var(--text);
  padding: 0.2rem 0.15rem;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.15rem 0.25rem 0.15rem 0.55rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--accent-soft);
  font-size: 0.85rem;
  color: var(--text);
}
.chip-name {
  overflow-wrap: anywhere;
}
.chip-x {
  border: 0;
  background: none;
  color: var(--muted);
  font-size: 0.95rem;
  line-height: 1;
  padding: 0.1rem 0.3rem;
  border-radius: 999px;
  cursor: pointer;
}
.chip-x:hover {
  background: rgba(0, 0, 0, 0.08);
  color: var(--text);
}
</style>
