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

const filteredRows = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return rows.value
  return rows.value.filter((row) => {
    // search in name/fa_name
    if (['name', 'fa_name'].some((n) => String(row[n] ?? '').toLowerCase().includes(q))) return true
    // also search in main_customer_id and other customer ids for convenience
    for (const col of ['main_customer_id', 'include_customer_id', 'exclude_customer_id']) {
      if (asArray(row[col]).some((v) => String(v).toLowerCase().includes(q))) return true
    }
    return false
  })
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

function chipClass(colName) {
  // keep all chips green as requested
  return 'mini-chip'
}

// Order columns for better UX: name, fa_name first, then customer ids (include, exclude, main), then categories, then rest
const tableColumns = computed(() => {
  const base = columns.value.filter((c) => !(c.key === 'PRI' && (c.extra || '').includes('auto_increment')))
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
            placeholder="Search by name or customer ID…"
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
              <th
                v-for="c in tableColumns"
                :key="c.name"
                :title="colLabel(c.name)"
              >
                {{ colLabel(c.name) }}
              </th>
              <th class="actions-col">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in filteredRows" :key="pkValue(row)">
              <td
                v-for="c in tableColumns"
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
                <span v-else class="cell-text">{{ cellText(row, c) || '—' }}</span>
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

/* === NO HORIZONTAL SLIDE + ALIGNMENT === */
.table-scroll {
  width: 100%;
  overflow-x: hidden;
}
table {
  width: 100%;
  max-width: 100%;
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
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
}

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
  white-space: nowrap;
  line-height: 1.3;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  background: var(--accent-soft);
  color: var(--accent-strong);
  border: 1px solid #cfe3d9;
}

/* Actions column: fixed width, right-aligned with proper spacing */
.actions-col {
  width: 132px;
  min-width: 132px;
  max-width: 132px;
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
/* delete button needs space to the left */
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
    width: 124px;
    min-width: 124px;
    max-width: 124px;
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
