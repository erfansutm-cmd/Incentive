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

const showDelete = ref(false)
const deletingRow = ref(null)
const deleting = ref(false)

const message = ref(null)
let msgTimer = null

const searchQuery = ref('')

const pkColumn = computed(() => columns.value.find((c) => c.key === 'PRI'))
const arrayColumns = computed(() => columns.value.filter((c) => c.json_array))
const textColumns = computed(() =>
  columns.value.filter(
    (c) =>
      !c.json_array &&
      !(c.key === 'PRI' && (c.extra || '').includes('auto_increment'))
  )
)

// Columns shown in the table: all except the raw id (kept for actions).
const tableColumns = computed(() =>
  columns.value.filter((c) => !(c.key === 'PRI' && (c.extra || '').includes('auto_increment')))
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
  if (typeof v === 'string') {
    try {
      const parsed = JSON.parse(v)
      if (Array.isArray(parsed)) return parsed
    } catch {
      /* fall through */
    }
    return v.split(',').map((s) => s.trim()).filter(Boolean)
  }
  return [v]
}

const categoryColumns = new Set([
  'include_delivery_category',
  'exclude_delivery_category',
])
const customerColumns = new Set(['include_customer_id', 'exclude_customer_id'])

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

const filteredRows = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return rows.value
  return rows.value.filter((row) =>
    ['name', 'fa_name'].some((n) => String(row[n] ?? '').toLowerCase().includes(q))
  )
})

function cellText(row, col) {
  const v = row[col.name]
  if (v === null || v === undefined || v === '') return ''
  if (col.json_array) {
    const list = asArray(v)
    return list.length ? list.join(', ') : ''
  }
  return String(v)
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
    if (c.key === 'PRI' && (c.extra || '').includes('auto_increment')) continue
    form.value[c.name] = c.json_array ? [] : c.default ?? ''
  }
  showModal.value = true
}

function openEdit(row) {
  editing.value = row
  form.value = {}
  for (const c of columns.value) {
    if (c.key === 'PRI' && (c.extra || '').includes('auto_increment')) continue
    form.value[c.name] = c.json_array ? asArray(row[c.name]) : row[c.name] ?? ''
  }
  showModal.value = true
}

async function save() {
  saving.value = true
  try {
    const payload = {}
    for (const c of columns.value) {
      if (c.key === 'PRI' && (c.extra || '').includes('auto_increment')) continue
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

function askDelete(row) {
  deletingRow.value = row
  showDelete.value = true
}

async function confirmDelete() {
  deleting.value = true
  try {
    const res = await fetch(
      `/api/business-entities/${encodeURIComponent(pkValue(deletingRow.value))}`,
      { method: 'DELETE' }
    )
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Delete failed')
    showDelete.value = false
    showMessage('ok', data.message || 'Deleted')
    await load()
  } catch (e) {
    showMessage('error', e.message)
  } finally {
    deleting.value = false
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
            placeholder="Search by name…"
          />
        </div>
        <span class="result-count">
          {{ filteredRows.length }} of {{ rows.length }} entities
        </span>
      </div>

      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th v-for="c in tableColumns" :key="c.name">{{ colLabel(c.name) }}</th>
              <th class="actions-col">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in filteredRows" :key="pkValue(row)">
              <td v-for="c in tableColumns" :key="c.name">
                <div v-if="c.json_array" class="cell-chips">
                  <template v-if="asArray(row[c.name]).length">
                    <span
                      v-for="(v, i) in asArray(row[c.name]).slice(0, 4)"
                      :key="i"
                      class="mini-chip"
                      >{{ v }}</span
                    >
                    <span
                      v-if="asArray(row[c.name]).length > 4"
                      class="mini-chip more"
                      :title="cellText(row, c)"
                    >
                      +{{ asArray(row[c.name]).length - 4 }}
                    </span>
                  </template>
                  <span v-else class="muted">—</span>
                </div>
                <span v-else>{{ cellText(row, c) || '—' }}</span>
              </td>
              <td class="actions-col">
                <button class="btn btn-ghost btn-sm" @click="openEdit(row)">Edit</button>
                <button class="btn btn-danger btn-sm" @click="askDelete(row)">Delete</button>
              </td>
            </tr>
            <tr v-if="filteredRows.length === 0">
              <td class="empty" :colspan="tableColumns.length + 1">
                <template v-if="rows.length === 0">No business entities yet — add the first one.</template>
                <template v-else>No entities match your search.</template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
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

    <!-- delete confirmation -->
    <div v-if="showDelete" class="overlay" @click.self="showDelete = false">
      <div class="modal">
        <h2>Delete business entity</h2>
        <p class="confirm-text">
          Are you sure you want to delete
          <strong>{{ deletingRow?.name }}</strong>
          <em v-if="deletingRow?.fa_name"> ({{ deletingRow.fa_name }})</em>?
          This cannot be undone.
        </p>
        <div class="actions">
          <button class="btn btn-ghost" @click="showDelete = false">Cancel</button>
          <button class="btn btn-danger" :disabled="deleting" @click="confirmDelete">
            {{ deleting ? 'Deleting…' : 'Delete' }}
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

.table-scroll {
  overflow-x: auto;
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
  font-size: 0.92rem;
  color: var(--text);
  vertical-align: top;
  max-width: 260px;
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

.cell-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}
.mini-chip {
  display: inline-block;
  padding: 0.1rem 0.5rem;
  background: var(--accent-soft);
  color: var(--accent-strong);
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
  white-space: nowrap;
}
.mini-chip.more {
  background: var(--surface-2);
  color: var(--muted);
  cursor: default;
}

.actions-col {
  text-align: right;
  white-space: nowrap;
}
.actions-col .btn + .btn {
  margin-left: 0.4rem;
}

.modal-wide {
  max-width: 560px;
}
.field .type {
  margin-left: 0.4rem;
}
.confirm-text {
  color: var(--text);
  line-height: 1.5;
}
</style>
