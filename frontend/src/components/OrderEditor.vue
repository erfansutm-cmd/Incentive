<script setup>
// A reusable "show this before that" popup: a drag-and-drop (plus ↑ / ↓) list of
// names whose order decides how rows are sorted in a table. The Final Decisions
// tab uses it twice — once for the business entities of a city, once for the
// plan (incentive) types — and any "top item first" list can reuse it.
//
// The component is controlled: `items` is the order to show, every change is
// emitted as a new array through `update:items`, `reset` asks the parent to go
// back to its default (the parent owns that default), and the parent keeps the
// state.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  hint: { type: String, default: '' },
  // The current order, top first.
  items: { type: Array, required: true },
  // Names that are known but not part of the order yet (shown as "others").
  extra: { type: Array, default: () => [] },
  // Wording of the footer / add-all row, e.g. "entity" / "plan type".
  noun: { type: String, default: 'item' },
  nounPlural: { type: String, default: '' },
  topNote: { type: String, default: '' },
})

const emit = defineEmits(['update:items', 'reset', 'close'])

const plural = computed(() => props.nounPlural || `${props.noun}s`)
const dialog = ref(null)
const draggedIdx = ref(null)
const dragOverIdx = ref(null)

// A native <dialog> traps focus, closes on Escape and restores focus on close.
// Very old browsers — and jsdom in the unit tests — have no showModal(), so the
// popup falls back to a plain (non-modal) open dialog instead of not opening.
onMounted(() => {
  const element = dialog.value
  if (!element) return
  if (typeof element.showModal === 'function') element.showModal()
  else element.setAttribute('open', '')
})
onBeforeUnmount(() => {
  const element = dialog.value
  if (!element) return
  if (typeof element.close === 'function') element.close()
  else element.removeAttribute('open')
})

function onBackdrop(event) {
  if (event.target !== dialog.value) return
  const rect = dialog.value.getBoundingClientRect()
  if (
    event.clientX < rect.left || event.clientX > rect.right ||
    event.clientY < rect.top || event.clientY > rect.bottom
  ) {
    emit('close')
  }
}

function reorder(from, to) {
  const next = [...props.items]
  if (from < 0 || from >= next.length || to === from) return
  const target = Math.max(0, Math.min(next.length - 1, to))
  const [moved] = next.splice(from, 1)
  next.splice(target, 0, moved)
  emit('update:items', next)
}

function move(index, dir) {
  reorder(index, index + dir)
}

function onDragStart(index, event) {
  draggedIdx.value = index
  if (event?.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    try {
      event.dataTransfer.setData('text/plain', String(index))
    } catch {
      // some browsers only start a drag once data is set; a failure is harmless
    }
  }
}

function onDragOver(index) {
  if (dragOverIdx.value !== index) dragOverIdx.value = index
}

function onDragLeave(index) {
  if (dragOverIdx.value === index) dragOverIdx.value = null
}

function onDrop(index) {
  const from = draggedIdx.value
  draggedIdx.value = null
  dragOverIdx.value = null
  if (from === null) return
  // dropping on the end zone appends instead of swapping with that row
  if (index >= props.items.length) reorder(from, props.items.length - 1)
  else reorder(from, index)
}

function onDragEnd() {
  draggedIdx.value = null
  dragOverIdx.value = null
}

function reset() {
  emit('reset')
}

function addAll() {
  emit('update:items', [...props.items, ...props.extra])
}
</script>

<template>
  <dialog
    ref="dialog"
    class="order-modal"
    :aria-label="`${title} order`"
    @cancel.prevent="emit('close')"
    @click="onBackdrop"
  >
    <div class="order-head">
      <div>
        <h4>{{ title }}</h4>
        <p v-if="hint" class="hint">{{ hint }}</p>
      </div>
      <button class="btn btn-ghost btn-sm" :aria-label="`Close ${title}`" @click="emit('close')">✕</button>
    </div>

    <transition-group
      tag="div"
      name="order-move"
      class="order-list"
      @dragover.prevent="onDragOver(items.length)"
      @drop.prevent="onDrop(items.length)"
    >
      <div
        v-for="(name, i) in items"
        :key="name"
        class="order-row"
        :class="{
          dragging: draggedIdx === i,
          'drag-over-top': dragOverIdx === i && draggedIdx !== null && draggedIdx !== i,
        }"
        draggable="true"
        @dragstart="onDragStart(i, $event)"
        @dragover.prevent.stop="onDragOver(i)"
        @dragleave="onDragLeave(i)"
        @drop.prevent.stop="onDrop(i)"
        @dragend="onDragEnd"
      >
        <span class="drag-handle" aria-hidden="true">⋮⋮</span>
        <span class="order-rank">{{ i + 1 }}</span>
        <span class="order-name flex-1">{{ name }}</span>
        <span v-if="i === 0" class="pill tiny accent">top</span>
        <div class="order-actions">
          <button
            class="btn btn-ghost tiny"
            :disabled="i === 0"
            :aria-label="`Move ${name} up`"
            title="Move up"
            @click.stop="move(i, -1)"
          >↑</button>
          <button
            class="btn btn-ghost tiny"
            :disabled="i === items.length - 1"
            :aria-label="`Move ${name} down`"
            title="Move down"
            @click.stop="move(i, 1)"
          >↓</button>
        </div>
      </div>
      <div
        key="__end_zone"
        class="drop-end-zone"
        :class="{ 'drag-over-end': dragOverIdx === items.length && draggedIdx !== null }"
      ></div>
    </transition-group>

    <div v-if="extra.length" class="order-extra">
      <span class="hint">
        {{ extra.length }} more {{ plural }} (after the list): {{ extra.join(', ') }}
      </span>
      <button class="btn btn-ghost btn-sm" @click="addAll">Add all</button>
    </div>

    <p v-if="topNote" class="hint order-top-note">{{ topNote }}</p>

    <div class="order-foot">
      <button class="btn btn-ghost btn-sm" @click="reset">↺ Reset to default</button>
      <button class="btn btn-primary btn-sm" @click="emit('close')">Done</button>
    </div>
  </dialog>
</template>

<style scoped>
dialog.order-modal {
  background: #fff;
  border: 1px solid #e6ece9;
  border-radius: 0.9rem;
  margin: auto;
  width: min(460px, calc(100% - 2rem));
  max-height: 85vh;
  overflow: auto;
  color: var(--text);
  box-shadow: 0 12px 40px rgba(16, 32, 24, 0.24), 0 2px 8px rgba(16, 32, 24, 0.08);
  padding: 1rem 1.15rem 1rem;
}
dialog.order-modal::backdrop {
  background: rgba(30, 42, 36, 0.4);
}
.order-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 0.85rem;
}
.order-head h4 {
  margin: 0;
  font-size: 1rem;
}
.order-head .hint {
  margin: 0.2rem 0 0;
}
.order-list {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}
.order-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.5rem 0.65rem;
  border: 1px solid var(--border);
  border-radius: 0.6rem;
  background: #fbfdfc;
  cursor: grab;
  transition: transform 0.22s cubic-bezier(0.2, 0, 0, 1), box-shadow 0.18s ease, opacity 0.18s ease,
    background 0.18s ease, border-color 0.18s ease;
  will-change: transform;
}
.order-row:active {
  cursor: grabbing;
}
.order-row:hover:not(.dragging) {
  border-color: #cfe0d7;
  box-shadow: 0 2px 6px rgba(20, 40, 30, 0.06);
}
.order-name {
  font-weight: 600;
  font-size: 0.86rem;
  overflow-wrap: anywhere;
}
.order-rank {
  width: 1.6rem;
  height: 1.6rem;
  display: grid;
  place-items: center;
  background: var(--accent-soft);
  color: var(--accent-strong);
  border-radius: 50%;
  font-weight: 700;
  font-size: 0.78rem;
  flex-shrink: 0;
}
.order-actions {
  display: flex;
  gap: 0.25rem;
  margin-left: auto;
}
.order-row.dragging {
  opacity: 0.45;
  transform: scale(0.97);
  box-shadow: 0 8px 20px rgba(20, 40, 30, 0.14);
  border-color: var(--accent);
  background: #f3faf6;
}
.order-row.drag-over-top {
  box-shadow: inset 0 3px 0 0 var(--accent);
  background: #f0faf6;
}
.drop-end-zone {
  height: 0.65rem;
  border-radius: 0.5rem;
  transition: height 0.18s cubic-bezier(0.2, 0, 0, 1), box-shadow 0.15s ease, background 0.15s ease;
}
.drop-end-zone.drag-over-end {
  height: 2.4rem;
  box-shadow: inset 0 0 0 1.5px var(--accent);
  background: #eefaf5;
}
.order-move-move {
  transition: transform 0.28s cubic-bezier(0.2, 0, 0, 1);
}
.order-extra {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  padding: 0.5rem 0.6rem;
  border: 1px dashed var(--border);
  border-radius: 0.55rem;
  background: #fff;
  margin-top: 0.3rem;
}
.order-extra .hint {
  font-size: 0.78rem;
  overflow-wrap: anywhere;
}
.order-top-note {
  margin: 0.6rem 0 0;
  font-size: 0.78rem;
}
.order-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  margin-top: 0.85rem;
  flex-wrap: wrap;
}
.drag-handle {
  cursor: grab;
  color: #9ab0a8;
  font-size: 0.9rem;
  letter-spacing: 0.08em;
  user-select: none;
  padding: 0 0.15rem;
  line-height: 1;
  transition: color 0.15s ease;
}
.order-row:hover .drag-handle {
  color: var(--accent-strong);
}
.drag-handle:active {
  cursor: grabbing;
}
.btn.tiny {
  padding: 0.18rem 0.4rem;
  font-size: 0.78rem;
  line-height: 1;
}
.pill.tiny {
  font-size: 0.66rem;
  padding: 0.14rem 0.42rem;
}
.flex-1 {
  flex: 1;
}
button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}
@media (prefers-reduced-motion: reduce) {
  .order-row,
  .order-move-move,
  .drop-end-zone {
    transition: none;
  }
}
</style>
