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

// --- city-name lookup (city_mapping) --------------------------------------
// The "add city" form auto-fills its other columns from the mapping table:
//   select distinct correct_city, correct_city_id, box_city_name, city_group
//   from mafsho.city_mapping
// The cities table is introspected, so the mapping columns are matched to
// whatever the local columns happen to be called.
const CITY_NAME_COLUMNS = ['city_name', 'city', 'name', 'correct_city']
const MAPPING_TARGETS = {
  correct_city: ['city_name', 'city', 'name', 'correct_city'],
  correct_city_id: ['city_id', 'correct_city_id', 'correct_id'],
  box_city_name: ['box_city_name'],
  city_group: ['city_group', 'group'],
}
const MAPPING_FIELDS = Object.keys(MAPPING_TARGETS)

const suggestions = ref([])
const suggestOpen = ref(false)
const suggestLoading = ref(false)
const noMatches = ref(false)
const highlight = ref(-1)
const autoFilled = ref(new Set())
const selectedMapping = ref(null)
const lookupError = ref('')
let lookupTimer = null
let lookupSeq = 0

// The column of the cities table that holds the city name.
const cityNameColumn = computed(() => {
  for (const name of CITY_NAME_COLUMNS) {
    const col = columns.value.find((c) => c.name === name)
    if (col) return col
  }
  return null
})

// Which local column a mapping column fills (null when there is no match).
function targetColumn(mappingField) {
  for (const name of MAPPING_TARGETS[mappingField] || []) {
    if (form.value && !(name in form.value)) continue
    if (editableColumns.value.some((c) => c.name === name)) return name
  }
  return null
}

function isCityNameColumn(col) {
  return !editing.value && cityNameColumn.value && col.name === cityNameColumn.value.name
}

async function fetchSuggestions(term) {
  const seq = ++lookupSeq
  suggestLoading.value = true
  lookupError.value = ''
  try {
    const res = await fetch(`/api/cities/lookup?q=${encodeURIComponent(term)}&limit=20`)
    const data = await res.json()
    if (seq !== lookupSeq) return // a newer keystroke already won
    if (!res.ok) throw new Error(data.message || data.detail || 'Lookup failed')
    // The backend already hides cities that are in the table and collapses
    // duplicate mapping rows; keep it unique here too, just in case.
    const seen = new Set()
    suggestions.value = (data.rows || []).filter((r) => {
      const key = String(r.correct_city ?? '').trim().toLowerCase()
      if (!key || seen.has(key)) return false
      seen.add(key)
      return true
    })
    noMatches.value = suggestions.value.length === 0
    highlight.value = -1
    suggestOpen.value = true
  } catch (e) {
    if (seq === lookupSeq) {
      suggestions.value = []
      suggestOpen.value = false
      noMatches.value = false
      lookupError.value = e.message
    }
  } finally {
    if (seq === lookupSeq) suggestLoading.value = false
  }
}

function onCityInput() {
  // Typing a fresh name unlocks whatever was auto-filled before.
  releaseAutoFill()
  highlight.value = -1
  if (lookupTimer) clearTimeout(lookupTimer)
  const nameCol = cityNameColumn.value?.name
  const term = nameCol ? String(form.value[nameCol] ?? '').trim() : ''
  if (!term) {
    if (lookupTimer) clearTimeout(lookupTimer)
    suggestions.value = []
    suggestOpen.value = false
    suggestLoading.value = false
    noMatches.value = false
    return
  }
  suggestOpen.value = false
  lookupTimer = setTimeout(() => fetchSuggestions(term), 250)
}

function onCityFocus() {
  const nameCol = cityNameColumn.value?.name
  const term = nameCol ? String(form.value[nameCol] ?? '').trim() : ''
  if (term && !selectedMapping.value) fetchSuggestions(term)
}

function onCityKey(e) {
  if (!suggestOpen.value || !suggestions.value.length) {
    if (e.key === 'Escape') suggestOpen.value = false
    return
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    highlight.value = (highlight.value + 1) % suggestions.value.length
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    highlight.value =
      (highlight.value + suggestions.value.length - 1) % suggestions.value.length
  } else if (e.key === 'Enter') {
    if (highlight.value >= 0) {
      e.preventDefault()
      pickSuggestion(suggestions.value[highlight.value])
    } else {
      suggestOpen.value = false
    }
  } else if (e.key === 'Escape') {
    suggestOpen.value = false
  } else if (e.key === 'Tab') {
    suggestOpen.value = false
  }
}

function pickSuggestion(s) {
  const nameCol = cityNameColumn.value?.name
  if (nameCol) form.value[nameCol] = s.correct_city ?? ''

  const filled = new Set()
  for (const field of MAPPING_FIELDS) {
    const target = targetColumn(field)
    if (!target || target === nameCol) continue
    form.value[target] = s[field] ?? ''
    filled.add(target)
  }
  autoFilled.value = filled
  selectedMapping.value = s
  suggestions.value = []
  suggestOpen.value = false
  noMatches.value = false
  if (lookupTimer) clearTimeout(lookupTimer)
}

function releaseAutoFill() {
  autoFilled.value = new Set()
  selectedMapping.value = null
}

function enableManual(columnName) {
  const next = new Set(autoFilled.value)
  next.delete(columnName)
  autoFilled.value = next
  if (!next.size) selectedMapping.value = null
}

function suggestLabel(s) {
  const bits = []
  if (s.correct_city_id !== null && s.correct_city_id !== undefined && s.correct_city_id !== '')
    bits.push(`#${s.correct_city_id}`)
  if (s.box_city_name) bits.push(s.box_city_name)
  if (s.city_group) bits.push(s.city_group)
  return bits.join(' · ')
}

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

function resetLookup() {
  if (lookupTimer) clearTimeout(lookupTimer)
  lookupSeq++
  suggestions.value = []
  suggestOpen.value = false
  suggestLoading.value = false
  highlight.value = -1
  autoFilled.value = new Set()
  selectedMapping.value = null
  lookupError.value = ''
  noMatches.value = false
}

function openAdd() {
  editing.value = null
  form.value = {}
  for (const c of editableColumns.value) form.value[c.name] = c.default ?? ''
  resetLookup()
  showModal.value = true
}

function openEdit(row) {
  editing.value = row
  form.value = {}
  for (const c of editableColumns.value) form.value[c.name] = row[c.name] ?? ''
  resetLookup()
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
      <div class="modal" :class="{ 'lookup-open': suggestOpen && suggestions.length > 0 }">
        <h2>{{ editing ? 'Edit city' : 'Add city' }}</h2>
        <p v-if="!editing && cityNameColumn" class="modal-hint">
          Start typing a city name — the other fields are filled from
          <code>city_mapping</code>.
        </p>
        <label v-for="c in editableColumns" :key="c.name" class="field">
          <span>
            {{ colLabel(c) }}
            <em v-if="c.nullable" class="opt">(optional)</em>
            <em class="opt type">{{ c.type }}</em>
          </span>

          <!-- city name: autocomplete fed by the mapping table -->
          <div v-if="isCityNameColumn(c)" class="combo">
            <input
              v-model="form[c.name]"
              type="text"
              autocomplete="off"
              placeholder="Start typing a city name…"
              @input="onCityInput"
              @focus="onCityFocus"
              @keydown="onCityKey"
              @blur="suggestOpen = false"
            />
            <ul v-if="suggestOpen && suggestions.length" class="suggest">
              <li
                v-for="(s, i) in suggestions"
                :key="i"
                :class="{ active: i === highlight }"
                @mousedown.prevent="pickSuggestion(s)"
                @mouseenter="highlight = i"
              >
                <span class="s-name">{{ s.correct_city }}</span>
                <span v-if="suggestLabel(s)" class="s-meta">{{ suggestLabel(s) }}</span>
              </li>
            </ul>
            <p v-if="lookupError" class="hint warn">
              Name lookup unavailable — fill the fields manually.
            </p>
            <p v-else-if="suggestLoading" class="hint">Searching…</p>
            <p v-else-if="noMatches" class="hint warn">
              No match — either it is already in the table or it is missing from
              <code>city_mapping</code>.
            </p>
            <p v-else-if="selectedMapping" class="hint ok">
              Matched in <code>city_mapping</code> — fields filled automatically.
            </p>
          </div>

          <!-- every other column: plain input, read-only once auto-filled -->
          <template v-else>
            <input
              v-model="form[c.name]"
              :type="inputType(c)"
              :placeholder="c.type"
              :readonly="autoFilled.has(c.name)"
              :class="{ 'auto-filled': autoFilled.has(c.name) }"
            />
            <button
              v-if="autoFilled.has(c.name)"
              type="button"
              class="link"
              @click="enableManual(c.name)"
            >
              edit manually
            </button>
          </template>
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

/* modal hint + city-name autocomplete */
.modal-hint {
  margin: -0.4rem 0 1rem;
  font-size: 0.85rem;
  color: var(--muted);
  line-height: 1.45;
}
.modal-hint code {
  background: var(--surface-2);
  padding: 0.05rem 0.35rem;
  border-radius: 0.3rem;
  color: var(--accent-strong);
}

/* let the suggestion dropdown escape the modal's scroll box */
.modal.lookup-open {
  overflow: visible;
}

.combo {
  position: relative;
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
  flex-direction: column;
  gap: 0.1rem;
  padding: 0.45rem 0.6rem;
  border-radius: 0.4rem;
  cursor: pointer;
}
.suggest li:hover,
.suggest li.active {
  background: var(--accent-soft);
}
.s-name {
  font-size: 0.92rem;
  color: var(--text);
}
.s-meta {
  font-size: 0.78rem;
  color: var(--muted);
}

.hint {
  margin: 0.35rem 0 0;
  font-size: 0.78rem;
  color: var(--muted);
}
.hint.ok {
  color: var(--ok-text);
}
.hint.warn {
  color: var(--warning);
}
.hint code {
  background: var(--surface-2);
  padding: 0.05rem 0.3rem;
  border-radius: 0.3rem;
}

.auto-filled {
  background: var(--accent-soft);
  color: var(--accent-strong);
  cursor: default;
}

.link {
  align-self: flex-start;
  margin-top: 0.25rem;
  padding: 0;
  border: none;
  background: none;
  color: var(--accent-strong);
  font-size: 0.78rem;
  text-decoration: underline;
  cursor: pointer;
}
</style>
