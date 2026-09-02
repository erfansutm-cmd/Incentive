<script setup>
import { ref, computed, onMounted } from 'vue'

const columns = ref([])
const rows = ref([])
const loading = ref(true)
const error = ref('')

const showModal = ref(false)
const editing = ref(null)
const form = ref({})
const saving = ref(false)

const message = ref(null)
let msgTimer = null

const searchQuery = ref('')
const groupFilter = ref('')

const pkColumn = computed(() => columns.value.find((c) => c.key === 'PRI'))

// Columns the user should NOT see in the table or edit directly (system-managed).
const HIDDEN = new Set(['deactivated_at'])
const MANAGED = new Set(['created_at', 'deactivated_at'])

// Columns shown in the table (deactivated_at is hidden).
const tableColumns = computed(() => columns.value.filter((c) => !HIDDEN.has(c.name)))

// Editable columns = everything except the auto-increment PK and managed columns.
const editableColumns = computed(() =>
  columns.value.filter(
    (c) =>
      !(c.key === 'PRI' && (c.extra || '').includes('auto_increment')) &&
      !MANAGED.has(c.name)
  )
)

// Search matches the city-name and box-city-name columns, whatever the DB
// calls them (some schemas use "city", others "city_name").
const SEARCHABLE = ['city_name', 'city', 'box_city_name']
const searchColumns = computed(() => {
  const wanted = SEARCHABLE.filter((n) => columns.value.some((c) => c.name === n))
  return wanted.length ? wanted : tableColumns.value.map((c) => c.name)
})

// distinct city_group values for the filter dropdown
const groupOptions = computed(() => {
  const seen = new Set()
  for (const r of rows.value) {
    const v = r.city_group
    if (v !== null && v !== undefined && v !== '') seen.add(v)
  }
  return [...seen].sort((a, b) => String(a).localeCompare(String(b)))
})

const filteredRows = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  return rows.value.filter((row) => {
    if (groupFilter.value && String(row.city_group ?? '') !== groupFilter.value) return false
    if (!q) return true
    return searchColumns.value.some((name) =>
      String(row[name] ?? '').toLowerCase().includes(q)
    )
  })
})

function pkValue(row) {
  const pk = pkColumn.value
  return pk ? row[pk.name] : undefined
}

// "city_id" -> "City ID", "box_city_name" -> "Box City Name"
function colLabel(col) {
  return col.name
    .split('_')
    .map((w) => (w.toLowerCase() === 'id' ? 'ID' : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(' ')
}

// "2026-09-02T09:20:57" -> "Sep 2, 2026, 9:20 AM"
function formatDate(value) {
  if (!value) return ''
  const d = new Date(value)
  if (isNaN(d)) return value
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(d)
}

function cellValue(row, col) {
  const v = row[col.name]
  if (v === null || v === undefined) return ''
  if (col.name === 'created_at') return formatDate(v)
  return v
}

function inputType(col) {
  const t = (col.type || '').toLowerCase()
  if (/(int|decimal|float|double|real|numeric)/.test(t)) return 'number'
  return 'text'
}

function showMessage(type, text) {
  message.value = { type, text }
  if (msgTimer) clearTimeout(msgTimer)
  msgTimer = setTimeout(() => (message.value = null), 4000)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch('/api/cities')
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Failed to load cities')
    columns.value = data.columns || []
    rows.value = data.rows || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function openAdd() {
  editing.value = null
  form.value = {}
  for (const c of editableColumns.value) form.value[c.name] = c.default ?? ''
  showModal.value = true
}

function openEdit(row) {
  editing.value = row
  form.value = {}
  for (const c of editableColumns.value) form.value[c.name] = row[c.name] ?? ''
  showModal.value = true
}

async function save() {
  saving.value = true
  try {
    const payload = {}
    for (const c of editableColumns.value) payload[c.name] = form.value[c.name]

    const isEdit = Boolean(editing.value)
    const url = isEdit
      ? `/api/cities/${encodeURIComponent(pkValue(editing.value))}`
      : '/api/cities'

    const res = await fetch(url, {
      method: isEdit ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Save failed')

    showModal.value = false
    showMessage('ok', data.message || 'Saved')
    await load()
  } catch (e) {
    showMessage('error', e.message)
  } finally {
    saving.value = false
  }
}

function clearFilters() {
  searchQuery.value = ''
  groupFilter.value = ''
}

onMounted(load)
</script>

<template>
  <div>
    <div class="head">
      <div>
        <h1>Cities</h1>
        <p class="sub">Manage the <code>cities</code> table.</p>
      </div>
      <button class="btn btn-primary" @click="openAdd">+ Add city</button>
    </div>

    <div v-if="error" class="banner error">
      <strong>Could not load cities</strong>
      <p>{{ error }}</p>
      <button class="btn btn-ghost" @click="load">Retry</button>
    </div>

    <div v-else-if="loading" class="card empty">Loading…</div>

    <div v-else class="card table-card">
      <div class="toolbar">
        <div class="search-wrap">
          <span class="search-icon">🔎</span>
          <input
            v-model="searchQuery"
            type="search"
            class="search-input"
            placeholder="Search by city name or box city name…"
          />
        </div>

        <select v-model="groupFilter" class="group-select">
          <option value="">All groups</option>
          <option v-for="g in groupOptions" :key="g" :value="String(g)">{{ g }}</option>
        </select>

        <button
          v-if="searchQuery || groupFilter"
          class="btn btn-ghost btn-sm"
          @click="clearFilters"
        >
          Clear
        </button>

        <span class="result-count">
          {{ filteredRows.length }} of {{ rows.length }} cities
        </span>
      </div>

      <table>
        <thead>
          <tr>
            <th v-for="c in tableColumns" :key="c.name">{{ colLabel(c) }}</th>
            <th class="actions-col">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in filteredRows" :key="i">
            <td v-for="c in tableColumns" :key="c.name">{{ cellValue(row, c) }}</td>
            <td class="actions-col">
              <button class="btn btn-ghost btn-sm" @click="openEdit(row)">Edit</button>
            </td>
          </tr>
          <tr v-if="filteredRows.length === 0">
            <td class="empty" :colspan="tableColumns.length + 1">
              <template v-if="rows.length === 0">No cities yet — add the first one.</template>
              <template v-else>No cities match your search or filter.</template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- add / edit popup -->
    <div v-if="showModal" class="overlay" @click.self="showModal = false">
      <div class="modal">
        <h2>{{ editing ? 'Edit city' : 'Add city' }}</h2>
        <label v-for="c in editableColumns" :key="c.name" class="field">
          <span>
            {{ colLabel(c) }}
            <em v-if="c.nullable" class="opt">(optional)</em>
            <em class="opt type">{{ c.type }}</em>
          </span>
          <input v-model="form[c.name]" :type="inputType(c)" :placeholder="c.type" />
        </label>
        <div class="actions">
          <button class="btn btn-ghost" @click="showModal = false">Cancel</button>
          <button class="btn btn-primary" :disabled="saving" @click="save">
            {{ saving ? 'Saving…' : 'Save' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="message" class="toast" :class="message.type">{{ message.text }}</div>
  </div>
</template>

<style scoped>
.head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.25rem;
}
.head h1 {
  margin: 0;
  color: var(--text);
  font-size: 1.5rem;
}
.sub {
  margin: 0.3rem 0 0;
  color: var(--muted);
}
.sub code {
  background: var(--surface-2);
  padding: 0.1rem 0.4rem;
  border-radius: 0.3rem;
  color: var(--accent-strong);
}

.empty {
  padding: 3rem 1rem;
  text-align: center;
  color: var(--muted);
}

.table-card {
  overflow: hidden;
}

/* search + filter toolbar */
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  padding: 0.85rem 1rem;
  border-bottom: 1px solid var(--border);
  background: #fbfdfc;
}
.search-wrap {
  position: relative;
  flex: 1;
  min-width: 220px;
  max-width: 380px;
}
.search-icon {
  position: absolute;
  left: 0.65rem;
  top: 50%;
  transform: translateY(-50%);
  font-size: 0.85rem;
  opacity: 0.6;
  pointer-events: none;
}
.search-input {
  width: 100%;
  padding: 0.5rem 0.7rem 0.5rem 2rem;
  border: 1px solid var(--border);
  border-radius: 0.55rem;
  font-size: 0.92rem;
  outline: none;
  color: var(--text);
  background: #fff;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.search-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-ring);
}
.group-select {
  padding: 0.5rem 0.7rem;
  border: 1px solid var(--border);
  border-radius: 0.55rem;
  font-size: 0.92rem;
  background: #fff;
  color: var(--text);
  outline: none;
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.group-select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-ring);
}
.result-count {
  margin-left: auto;
  font-size: 0.82rem;
  color: var(--muted);
  white-space: nowrap;
}

table {
  width: 100%;
  border-collapse: collapse;
}
thead th {
  text-align: left;
  padding: 0.75rem 1rem;
  background: var(--surface-2);
  color: #4a6155;
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
  border-bottom: 1px solid var(--border);
}
tbody td {
  padding: 0.7rem 1rem;
  border-bottom: 1px solid #eef2ef;
  font-size: 0.94rem;
  color: var(--text);
}
tbody tr:last-child td {
  border-bottom: none;
}
tbody tr:hover {
  background: #f6faf8;
}
.actions-col {
  text-align: right;
  white-space: nowrap;
}
.actions-col .btn + .btn {
  margin-left: 0.4rem;
}

.field .type {
  margin-left: 0.4rem;
}
</style>
