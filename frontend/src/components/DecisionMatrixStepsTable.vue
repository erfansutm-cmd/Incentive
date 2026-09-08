<script setup>
defineProps({
  steps: { type: Array, required: true },
  label: { type: String, required: true },
  deactivated: { type: Boolean, default: false },
})
const emit = defineEmits(['deactivate'])
function formatBucketValue(value) {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return String(value)
    return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(6)))
  }
  return String(value)
}
const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })
function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : dateFormat.format(date)
}
</script>

<template>
  <div class="table-scroll" :class="{ history: deactivated }" tabindex="0" role="region" :aria-label="label">
    <table>
      <caption class="sr-only">{{ label }}</caption>
      <thead>
        <tr>
          <th scope="col">Score</th>
          <th scope="col">Target increase</th>
          <th scope="col">PR increase</th>
          <th scope="col">Control bucket</th>
          <th scope="col">Created at</th>
          <th v-if="deactivated" scope="col">Deactivated at</th>
          <th v-else scope="col" class="actions-col">Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in steps" :key="row.id">
          <th scope="row" class="score-cell"><strong>{{ row.score }}</strong><small>ID {{ row.id }}</small></th>
          <td class="numeric">{{ row.target_increase ?? '—' }}</td>
          <td class="numeric">{{ row.pr_increase ?? '—' }}</td>
          <td>
            <div v-if="Array.isArray(row.control_bucket)" class="bucket">
              <span v-for="(value, index) in row.control_bucket" :key="index" class="bucket-chip">
                <span class="bucket-key" aria-hidden="true">{{ index + 1 }}</span>
                <span class="bucket-value">{{ formatBucketValue(value) }}</span>
              </span>
            </div>
            <span v-else class="muted">—</span>
          </td>
          <td class="date-cell">{{ formatDate(row.created_at) }}</td>
          <td v-if="deactivated" class="date-cell">{{ formatDate(row.deactivated_at) }}</td>
          <td v-else class="actions-col">
            <button class="btn btn-danger-soft btn-sm" :aria-label="`Deactivate score ${row.score}`" @click="emit('deactivate', row)">Deactivate</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.table-scroll { overflow-x: auto; }
.table-scroll:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
table { width: 100%; border-collapse: collapse; font-size: 0.86rem; }
thead th { padding: 0.75rem 0.9rem; text-align: left; background: var(--surface-2); color: #4a6155; font-size: 0.72rem; letter-spacing: 0.03em; text-transform: uppercase; white-space: nowrap; }
tbody td, tbody th { padding: 0.8rem 0.9rem; border-top: 1px solid var(--border); text-align: left; font-weight: 400; }
tbody tr:hover { background: #f6faf8; }
.score-cell { min-width: 75px; }
.score-cell strong { display: inline-grid; place-items: center; min-width: 1.7rem; padding: 0.2rem 0.35rem; border-radius: 0.4rem; background: var(--accent-soft); color: var(--accent-strong); font-weight: 700; font-variant-numeric: tabular-nums; }
.score-cell small { display: block; margin-top: 0.25rem; color: var(--muted); white-space: nowrap; font-size: 0.65rem; }
.numeric { font-variant-numeric: tabular-nums; }
.bucket { display: inline-flex; align-items: stretch; gap: 0.25rem; flex-wrap: wrap; }
.bucket-chip { display: inline-flex; align-items: center; overflow: hidden; border: 1px solid var(--border); border-radius: 0.45rem; background: #fbfdfc; }
.bucket-key { padding: 0.15rem 0.4rem; background: var(--surface-2); color: var(--muted); font-size: 0.65rem; font-weight: 700; line-height: 1.4; border-right: 1px solid var(--border); }
.bucket-value { padding: 0.15rem 0.55rem; font-variant-numeric: tabular-nums; font-weight: 600; color: var(--text); }
.muted { color: var(--muted); }
.date-cell { white-space: nowrap; color: var(--muted); font-size: 0.78rem; }
.actions-col { text-align: right; white-space: nowrap; }
.history { background: #fafbfa; color: var(--inactive-text); }
.history .score-cell strong { background: var(--surface-2); color: var(--inactive-text); }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
</style>
