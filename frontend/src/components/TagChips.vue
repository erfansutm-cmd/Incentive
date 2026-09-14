<script setup>
// Read-only view of a list-of-strings column (districts, vendors) as chips,
// instead of the raw JSON the database stores.
defineProps({
  items: { type: Array, default: () => [] },
  noun: { type: String, default: 'value' },
})
</script>

<template>
  <ul v-if="items.length" class="chips" :aria-label="noun">
    <li v-for="(item, i) in items" :key="`${item}-${i}`" class="chip">{{ item }}</li>
  </ul>
  <span v-else class="none">—</span>
</template>

<style scoped>
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.chip {
  padding: 0.15rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--accent-soft);
  font-size: 0.82rem;
  line-height: 1.5;
  color: var(--text);
  overflow-wrap: anywhere;
}
.none {
  color: var(--muted);
}
</style>
