<script setup>
import { ref, computed, onMounted } from 'vue'
import TagInput from '../components/TagInput.vue'

// Delivery categories currently used by the incentive service. Used as the
// baseline set of suggestions; anything found in the DB is merged in on load.
const KNOWN_CATEGORIES = [
  'bike',
  'bike-without-box',
  'carbox',
  'passenger',
  'big-box',
]

const columns = ref([])
const rows = ref([])
const loading = ref(true)
const error = ref('')

const showModal = ref(false)
const editing = ref(null)
const form = ref({})
const saving = ref(false)

const deactivateTarget = ref(null)
const deactivating = ref(false)
const deactivateError = ref('')
const showDeactivated = ref(false)
const managedColumns = new Set(['updated_at', 'deactivated_at'])
const activeRows = computed(() => rows.value.filter((r) => r.deactivated_at == null))
const deactivatedRows = computed(() => rows.value.filter((r) => r.deactivated_at != null))

const message = ref(null)
let msgTimer = null

const searchQuery = ref('')

const pkColumn = computed(() => columns.value.find((c) => c.key === 'PRI'))
const arrayColumns = computed(() => columns.value.filter((c) => c.json_array))
const textColumns = computed(() =>
  columns.value.filter(
    (c) =>
      !c.json_array &&
      !managedColumns.has(c.name) &&
      !(c.key === 'PRI' && (c.extra || '').includes('auto_increment'))
  )
)

function pkValue(row) {
  const pk = pkColumn.value
  return pk ? row[pk.name] : undefined
}

// "include_customer_id" -> "Include Customer ID"
function colLabel(name) {
  return name
    .split('_')
    .map((w) => (w.toLowerCase() === 'id' ? 'ID' : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(' ')
}

function asArray(v) {
  if (Array.isArray(v)) return v
  if (v === null || v === undefined || v === '') return []
  // numbers like 15300196 -> [15300196]
  if (typeof v === 'number') return [v]

  if (typeof v === 'string') {
    let cur = v.trim()
    if (cur === '' || cur.toLowerCase() === 'null') return []

    // Unwind up to 3 levels of JSON encoding:
    // '"[2, 11653225]"' -> "[2, 11653225]" -> [2, 11653225]
    for (let i = 0; i < 3; i++) {
      try {
        const parsed = JSON.parse(cur)
        if (Array.isArray(parsed)) return parsed
        if (typeof parsed === 'number') return [parsed]
        if (typeof parsed === 'string') {
          const s = parsed.trim()
          if (s === '' || s.toLowerCase() === 'null') return []
          cur = s
          continue
        }
        // if parsed is something else, break to fallback
        break
      } catch {
        break
      }
    }

    // Fallback: strip brackets and split by comma
    let tmp = cur
    if (tmp.startsWith('[') && tmp.endsWith(']')) {
      tmp = tmp.slice(1, -1)
    }
    return tmp
      .split(',')
      .map((s) => s.trim().replace(/^["']|["']$/g, '').trim())
      .filter(Boolean)
      .map((s) => {
        // keep numbers as numbers for nicer display/sorting
        if (/^-?\d+$/.test(s)) {
          const n = Number(s)
          return Number.isFinite(n) ? n : s
        }
        return s
      })
  }
  return [v]
}

const categoryColumns = new Set([
  'include_delivery_category',
  'exclude_delivery_category',
])
const customerColumns = new Set([
  'include_customer_id',
  'exclude_customer_id',
  'main_customer_id',
])

// Suggestion lists are built from known categories + every value already
// present in the table, so newly typed values stay available later.
const categorySuggestions = computed(() => {
  const set = new Set(KNOWN_CATEGORIES)
  for (const r of rows.value) {
    for (const name of categoryColumns) {
      for (const v of asArray(r[name])) set.add(String(v))
    }
  }
  return [...set].sort()
})

const customerSuggestions = computed(() => {
  const set = new Set()
  for (const r of rows.value) {
    for (const name of customerColumns) {
      for (const v of asArray(r[name])) set.add(String(v))
    }
  }
  return [...set].map(Number).filter((n) => !isNaN(n)).sort((a, b) => a - b)
})

function suggestionsFor(name) {
  if (categoryColumns.has(name)) return categorySuggestions.value
  if (customerColumns.has(name)) return customerSuggestions.value
  return []
}

function kindFor(name) {
  return customerColumns.has(name) ? 'number' : 'text'
}

function filterRows(visible) {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return visible
  return visible.filter((row) => {
    // search in name/fa_name
    if (['name', 'fa_name'].some((n) => String(row[n] ?? '').toLowerCase().includes(q))) return true
    // also search in main_customer_id and other customer ids for convenience
    for (const col of ['main_customer_id', 'include_customer_id', 'exclude_customer_id']) {
      if (asArray(row[col]).some((v) => String(v).toLowerCase().includes(q))) return true
    }
    return false
  })
}

function formatDate(value) {
  if (!value) return ''
  const d = new Date(value)
  if (isNaN(d)) return value
  const date = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(d)
  const time = new Intl.DateTimeFormat(undefined, { timeStyle: 'short' }).format(d)
  return `${date},\n${time}`
}

function cellText(row, col) {
  const v = row[col.name]
  if (v === null || v === undefined || v === '') return ''
  if (managedColumns.has(col.name)) return formatDate(v)
  if (col.json_array) {
    const list = asArray(v)
    return list.length ? list.join(', ') : ''
  }
  return String(v)
}

function chipClass(colName) {
  // keep all chips green as requested
  return 'mini-chip'
}

// Order columns for better UX: name, fa_name first, then customer ids (include, exclude, main), then categories, then rest
const tableColumns = computed(() => {
  const base = columns.value.filter((c) => c.name !== 'deactivated_at' && !(c.key === 'PRI' && (c.extra || '').includes('auto_increment')))
  const order = ['name', 'fa_name', 'include_customer_id', 'exclude_customer_id', 'main_customer_id', 'include_delivery_category', 'exclude_delivery_category']
  const ordered = []
  const remaining = [...base]
  for (const name of order) {
    const idx = remaining.findIndex((c) => c.name === name)
    if (idx !== -1) {
      ordered.push(remaining[idx])
      remaining.splice(idx, 1)
    }
  }
  // append any other columns that were not in the predefined order (future columns)
  return [...ordered, ...remaining]
})

const sections = computed(() => {
  const active = { key: 'active', title: 'Active entities', rows: filterRows(activeRows.value), columns: tableColumns.value, editable: true }
  if (!showDeactivated.value) return [active]
  const deactivatedAt = columns.value.find((c) => c.name === 'deactivated_at')
  return [active, {
    key: 'deactivated', title: 'Deactivated entities', rows: filterRows(deactivatedRows.value),
    columns: deactivatedAt ? [...tableColumns.value, deactivatedAt] : tableColumns.value,
    editable: false,
  }]
})
const visibleCount = computed(() => sections.value.reduce((count, section) => count + section.rows.length, 0))

function columnClass(name) {
  return {
    'timestamp-col': managedColumns.has(name),
    'include-customer-col': name === 'include_customer_id',
  }
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
    const res = await fetch('/api/business-entities')
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Failed to load business entities')
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
  for (const c of columns.value) {
    if (managedColumns.has(c.name) || (c.key === 'PRI' && (c.extra || '').includes('auto_increment'))) continue
    form.value[c.name] = c.json_array ? [] : c.default ?? ''
  }
  showModal.value = true
}

function openEdit(row) {
  if (row.deactivated_at != null) return
  editing.value = row
  form.value = {}
  for (const c of columns.value) {
    if (managedColumns.has(c.name) || (c.key === 'PRI' && (c.extra || '').includes('auto_increment'))) continue
    form.value[c.name] = c.json_array ? asArray(row[c.name]) : row[c.name] ?? ''
  }
  showModal.value = true
}

async function save() {
  saving.value = true
  try {
    const payload = {}
    for (const c of columns.value) {
      if (managedColumns.has(c.name) || (c.key === 'PRI' && (c.extra || '').includes('auto_increment'))) continue
      payload[c.name] = c.json_array ? form.value[c.name] || [] : form.value[c.name]
    }

    const isEdit = Boolean(editing.value)
    const url = isEdit
      ? `/api/business-entities/${encodeURIComponent(pkValue(editing.value))}`
      : '/api/business-entities'

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

function askDeactivate(row) {
  deactivateError.value = ''
  deactivateTarget.value = row
}

function cancelDeactivate() {
  if (!deactivating.value) deactivateTarget.value = null
}

async function confirmDeactivate() {
  if (deactivating.value || !deactivateTarget.value) return
  deactivating.value = true
  deactivateError.value = ''
  try {
    const res = await fetch(`/api/business-entities/${encodeURIComponent(pkValue(deactivateTarget.value))}/deactivate`, {
      method: 'POST',
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Deactivation failed')
    deactivateTarget.value = null
    showMessage('ok', data.message || 'Business entity deactivated.')
    await load()
  } catch (e) {
    deactivateError.value = e.message
  } finally {
    deactivating.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="head">
      <div>
        <h1>Business Entities</h1>
        <p class="sub">Manage the <code>business_entities</code> table.</p>
      </div>
      <button class="btn btn-primary" @click="openAdd">+ Add entity</button>
    </div>

    <div v-if="error" class="banner error">
      <strong>Could not load business entities</strong>
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
            placeholder="Search by name or customer ID…"
          />
        </div>
        <span class="entity-counts">{{ activeRows.length }} active · {{ deactivatedRows.length }} deactivated</span>
        <button v-if="deactivatedRows.length" class="btn btn-ghost btn-sm"
          :aria-pressed="showDeactivated" @click="showDeactivated = !showDeactivated">
          {{ showDeactivated ? 'Hide deactivated' : `Show deactivated (${deactivatedRows.length})` }}
        </button>
        <span class="result-count">
          {{ visibleCount }} of {{ rows.length }} entities
        </span>
      </div>

      <section v-for="section in sections" :key="section.key" class="entity-section" :aria-labelledby="`${section.key}-heading`">
        <h2 :id="`${section.key}-heading`" class="section-heading">{{ section.title }} ({{ section.rows.length }})</h2>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th
                v-for="c in section.columns"
                :key="c.name"
                :title="colLabel(c.name)"
                :class="columnClass(c.name)"
              >
                {{ colLabel(c.name) }}
              </th>
              <th v-if="section.editable" class="actions-col">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in section.rows" :key="pkValue(row)" :class="{ 'is-deactivated': row.deactivated_at != null }">
              <td
                v-for="c in section.columns"
                :key="c.name"
              >
                <div v-if="c.json_array" class="cell-chips">
                  <template v-if="asArray(row[c.name]).length">
                    <span
                      v-for="(v, i) in asArray(row[c.name])"
                      :key="i"
                      :class="chipClass(c.name)"
                      :title="String(v)"
                      >{{ v }}</span
                    >
                  </template>
                  <span v-else class="muted">—</span>
                </div>
                <span v-else class="cell-text" :class="{ 'timestamp': managedColumns.has(c.name) }">{{ cellText(row, c) || '—' }}</span>
              </td>
              <td v-if="section.editable" class="actions-col">
                <button class="btn btn-ghost btn-sm" @click="openEdit(row)">Edit</button>
                <button v-if="row.deactivated_at == null" class="btn btn-danger btn-sm"
                  @click="askDeactivate(row)">Deactivate</button>
              </td>
            </tr>
            <tr v-if="section.rows.length === 0">
              <td class="empty" :colspan="section.columns.length + (section.editable ? 1 : 0)">
                <template v-if="rows.length === 0">No business entities yet — add the first one.</template>
                <template v-else>No entities match your search and status filter.</template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      </section>
    </div>

    <!-- add / edit popup -->
    <div v-if="showModal" class="overlay" @click.self="showModal = false">
      <div class="modal modal-wide">
        <h2>{{ editing ? 'Edit business entity' : 'Add business entity' }}</h2>

        <label v-for="c in textColumns" :key="c.name" class="field">
          <span>
            {{ colLabel(c.name) }}
            <em v-if="c.nullable" class="opt">(optional)</em>
            <em class="opt type">{{ c.type }}</em>
          </span>
          <input v-model="form[c.name]" type="text" :placeholder="colLabel(c.name)" />
        </label>

        <div v-for="c in arrayColumns" :key="c.name" class="field">
          <span>
            {{ colLabel(c.name) }}
            <em v-if="c.nullable" class="opt">(optional)</em>
          </span>
          <TagInput
            v-model="form[c.name]"
            :suggestions="suggestionsFor(c.name)"
            :kind="kindFor(c.name)"
            :placeholder="
              categoryColumns.has(c.name)
                ? 'e.g. bike — pick a suggestion or type your own'
                : 'e.g. 15300196 — type a customer id and press Enter'
            "
          />
        </div>

        <div class="actions">
          <button class="btn btn-ghost" @click="showModal = false">Cancel</button>
          <button class="btn btn-primary" :disabled="saving" @click="save">
            {{ saving ? 'Saving…' : 'Save' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="deactivateTarget" class="overlay" @click.self="cancelDeactivate">
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="deactivate-title">
        <h2 id="deactivate-title">Deactivate business entity</h2>
        <p class="confirm-text">
          Deactivate <strong>{{ deactivateTarget.name }}</strong>
          <em v-if="deactivateTarget.fa_name"> ({{ deactivateTarget.fa_name }})</em>?
          It will move to the deactivated list. The entity will not be deleted.
        </p>
        <p v-if="deactivateError" role="alert">{{ deactivateError }}</p>
        <div class="actions">
          <button class="btn btn-ghost" :disabled="deactivating" @click="cancelDeactivate">Cancel</button>
          <button class="btn btn-danger" :disabled="deactivating" @click="confirmDeactivate">
            {{ deactivating ? 'Deactivating…' : 'Deactivate' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="message" class="toast" :class="message.type">{{ message.text }}</div>
  </div>
</template>

<style scoped>
.entity-counts { font-size: 0.82rem; color: var(--muted); }
.is-deactivated td { color: var(--muted); }

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
  width: 100%;
}

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
.result-count {
  margin-left: auto;
  font-size: 0.82rem;
  color: var(--muted);
  white-space: nowrap;
}

/* Wrap full labels and values; scroll on narrow screens rather than clip. */
.table-scroll {
  width: 100%;
  overflow-x: auto;
}
table {
  width: 100%;
  min-width: 1100px;
  table-layout: fixed;
  border-collapse: collapse;
}

/* Header: consistent alignment, centered vertically */
thead th {
  text-align: left;
  padding: 0.7rem 0.6rem;
  background: var(--surface-2);
  color: #4a6155;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  border-bottom: 1px solid var(--border);
  white-space: normal;
  overflow-wrap: anywhere;
  vertical-align: middle;
}

/* Reserve more space for customer IDs while keeping two-line timestamps compact. */
thead th.timestamp-col { width: 115px; }
thead th.include-customer-col { width: 210px; }
.entity-section + .entity-section { border-top: 2px solid var(--border); margin-top: 1rem; }
.section-heading { margin: 0; padding: 0.85rem 1rem; font-size: 0.9rem; color: var(--muted); }

/* Body: middle alignment for clean rows */
tbody td {
  padding: 0.6rem 0.6rem;
  border-bottom: 1px solid #eef2ef;
  font-size: 0.86rem;
  color: var(--text);
  vertical-align: middle;
  word-break: break-word;
  overflow-wrap: anywhere;
  line-height: 1.4;
}
tbody tr:last-child td {
  border-bottom: none;
}
tbody tr:hover {
  background: #f6faf8;
}
.muted {
  color: var(--muted);
}

.cell-text {
  display: inline-block;
  max-width: 100%;
  overflow-wrap: anywhere;
  vertical-align: middle;
}

.cell-text.timestamp {
  white-space: pre-line;
}

/* Chips: all green, aligned left, wrapped */
.cell-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  align-items: center;
  justify-content: flex-start;
  max-width: 100%;
}

/* All chips green as requested */
.mini-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.14rem 0.55rem;
  border-radius: 999px;
  font-size: 0.76rem;
  font-weight: 600;
  white-space: normal;
  overflow-wrap: anywhere;
  line-height: 1.3;
  max-width: 100%;
  background: var(--accent-soft);
  color: var(--accent-strong);
  border: 1px solid #cfe3d9;
}

/* Actions column: fixed width, right-aligned with proper spacing */
.actions-col {
  width: 180px;
  min-width: 180px;
  max-width: 180px;
  text-align: right;
  white-space: nowrap;
  vertical-align: middle;
  padding-right: 0.9rem;
  padding-left: 0.6rem;
}
.actions-col .btn {
  padding: 0.32rem 0.65rem;
  font-size: 0.78rem;
  vertical-align: middle;
}
/* Separate the edit and deactivate actions. */
.actions-col .btn + .btn {
  margin-left: 0.75rem;
}

@media (max-width: 1300px) {
  thead th {
    font-size: 0.66rem;
    padding: 0.55rem 0.45rem;
  }
  tbody td {
    font-size: 0.82rem;
    padding: 0.5rem 0.45rem;
  }
  .mini-chip {
    font-size: 0.71rem;
    padding: 0.12rem 0.45rem;
  }
  .actions-col {
    width: 180px;
    min-width: 180px;
    max-width: 180px;
    padding-right: 0.7rem;
  }
  .actions-col .btn + .btn {
    margin-left: 0.6rem;
  }
}
@media (max-width: 900px) {
  .table-scroll {
    overflow-x: auto;
  }
  .actions-col {
    white-space: normal;
  }
  .actions-col .btn {
    margin-bottom: 0.25rem;
  }
}

.modal-wide {
  max-width: 600px;
}
.field .type {
  margin-left: 0.4rem;
}
.confirm-text {
  color: var(--text);
  line-height: 1.5;
}
</style>
