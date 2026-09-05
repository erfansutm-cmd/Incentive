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
    suggestions.value = data.rows || []
    highlight.value = -1
    suggestOpen.value = true
  } catch (e) {
    if (seq === lookupSeq) {
      suggestions.value = []
      suggestOpen.value = false
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

// --- plans slide-down (incentive_city_plan_mapping) ----------------
// Clicking a city row expands a panel with that city's plans,
// matched on `city_id`. Active mappings (deactivated_at IS NULL) show first;
// a button reveals the deactivated ones. Fetched from the dedicated
// /api/city-plan-mappings endpoint (see backend/app/city_plan_mappings.py).
const CITY_ID_COLUMNS = ['city_id', 'correct_city_id', 'correct_id']
const expandedKey = ref(null)
const planCache = ref({}) // expand-key -> { loading, error, active, deactivated, showDeactivated, cityId }

function cityIdOf(row) {
  for (const name of CITY_ID_COLUMNS) {
    const v = row[name]
    if (v !== null && v !== undefined && v !== '') return v
  }
  return null
}

function expandKeyOf(row, i) {
  const pk = pkValue(row)
  if (pk !== null && pk !== undefined && pk !== '') return `pk:${pk}`
  const cityId = cityIdOf(row)
  if (cityId !== null) return `city:${cityId}`
  return `idx:${i}`
}

function isExpanded(row, i) {
  return expandedKey.value === expandKeyOf(row, i)
}

function plansFor(row, i) {
  return planCache.value[expandKeyOf(row, i)]
}

function rowCityName(row) {
  const nameCol = cityNameColumn.value?.name
  if (nameCol && row[nameCol] !== null && row[nameCol] !== undefined && row[nameCol] !== '')
    return row[nameCol]
  return row.city_name ?? row.city ?? row.correct_city ?? `City #${cityIdOf(row) ?? ''}`
}

function planTitle(row) {
  return `${rowCityName(row)} · city_id ${cityIdOf(row) ?? '—'}`
}

function planCountsText(entry) {
  const a = entry.active.length
  const d = entry.deactivated.length
  return d ? `${a} active · ${d} deactivated` : `${a} active`
}

function toggleExpand(row, i) {
  const key = expandKeyOf(row, i)
  if (expandedKey.value === key) {
    expandedKey.value = null // collapse
    return
  }
  expandedKey.value = key
  if (!planCache.value[key]) fetchPlans(row, key)
}

function toggleDeactivated(row, i) {
  const entry = plansFor(row, i)
  if (entry) entry.showDeactivated = !entry.showDeactivated
}

function retryPlans(row, i) {
  fetchPlans(row, expandKeyOf(row, i))
}

// --- incentive types (mafsho.incentive_type): id -> name --------------------
// Loaded once; used to show type names in the panel and to fill the "Add plan"
// type dropdown. If the lookup fails the panel falls back to raw type ids.
const planTypes = ref([])
const planTypesLoading = ref(false)
const planTypesError = ref('')

const typeNameById = computed(() => {
  const map = {}
  for (const t of planTypes.value) map[String(t.id)] = t.name
  return map
})

function typeDisplay(typeId) {
  if (typeId === null || typeId === undefined || typeId === '') return ''
  return typeNameById.value[String(typeId)] || ''
}

async function loadTypes() {
  planTypesLoading.value = true
  planTypesError.value = ''
  try {
    const res = await fetch('/api/incentive-types')
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Failed to load incentive types')
    planTypes.value = data.rows || []
  } catch (e) {
    planTypesError.value = e.message
  } finally {
    planTypesLoading.value = false
  }
}

// --- business entities (incentive.business_entities) --------------------------
// Loaded lazily when the "Add plan" popup opens. The entity must be picked
// from the dropdown — nothing new can be added from here.
const beNames = ref([])
const beNamesLoading = ref(false)
const beNamesLoaded = ref(false)
const beNamesError = ref('')

async function loadBeNames() {
  if (beNamesLoaded.value || beNamesLoading.value) return
  beNamesLoading.value = true
  beNamesError.value = ''
  try {
    const res = await fetch('/api/business-entities')
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Failed to load business entities')
    const cols = (data.columns || []).map((c) => c.name)
    if (cols.includes('name')) {
      const seen = new Set()
      for (const r of data.rows || []) {
        const v = r.name
        if (v !== null && v !== undefined && v !== '') seen.add(String(v))
      }
      beNames.value = [...seen].sort((a, b) => a.localeCompare(b))
    }
    beNamesLoaded.value = true
  } catch (e) {
    beNamesError.value = e.message
  } finally {
    beNamesLoading.value = false
  }
}

// --- add plan popup ---------------------------------------------------------
const showAddPlan = ref(false)
const addPlanCity = ref(null) // { key, row, i, cityId, label }
const addPlanForm = ref({ incentive_type_id: '', business_entity: '' })
const addPlanSaving = ref(false)
const addPlanError = ref('')

function openAddPlan(row, i) {
  addPlanCity.value = {
    key: expandKeyOf(row, i),
    row,
    i,
    cityId: cityIdOf(row),
    label: planTitle(row),
  }
  addPlanForm.value = { incentive_type_id: '', business_entity: '' }
  addPlanError.value = ''
  showAddPlan.value = true
  if (!planTypes.value.length && !planTypesLoading.value) loadTypes()
  loadBeNames()
}

function closeAddPlan() {
  showAddPlan.value = false
}

async function saveAddPlan() {
  const city = addPlanCity.value
  if (!city || addPlanSaving.value) return
  const typeId = String(addPlanForm.value.incentive_type_id ?? '').trim()
  const business = String(addPlanForm.value.business_entity ?? '').trim()
  if (!typeId) {
    addPlanError.value = 'Please select a type.'
    return
  }
  if (!business) {
    addPlanError.value = 'Please select a business entity.'
    return
  }
  if (city.cityId === null || city.cityId === undefined || city.cityId === '') {
    addPlanError.value = 'This city has no city_id.'
    return
  }
  addPlanSaving.value = true
  addPlanError.value = ''
  try {
    const res = await fetch('/api/city-plan-mappings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        city_id: city.cityId,
        incentive_type_id: typeId,
        business_entity: business,
      }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Save failed')
    showAddPlan.value = false
    showMessage('ok', data.message || 'Plan added successfully.')
    await fetchPlans(city.row, city.key)
  } catch (e) {
    addPlanError.value = e.message
  } finally {
    addPlanSaving.value = false
  }
}

// --- deactivate plan mapping (with confirmation) ----------------------------
const deactivateTarget = ref(null) // { key, row, i, mapping, cityLabel }
const deactivating = ref(false)

function askDeactivate(row, i, mapping) {
  deactivateTarget.value = {
    key: expandKeyOf(row, i),
    row,
    i,
    mapping,
    cityLabel: planTitle(row),
  }
}

function cancelDeactivate() {
  deactivateTarget.value = null
}

async function confirmDeactivate() {
  const t = deactivateTarget.value
  if (!t || deactivating.value) return
  deactivating.value = true
  try {
    const res = await fetch(
      `/api/city-plan-mappings/${encodeURIComponent(t.mapping.id)}/deactivate`,
      { method: 'POST' }
    )
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Deactivate failed')
    deactivateTarget.value = null
    showMessage('ok', data.message || 'Plan deactivated successfully.')
    await fetchPlans(t.row, t.key)
  } catch (e) {
    showMessage('error', e.message)
  } finally {
    deactivating.value = false
  }
}

async function fetchPlans(row, key) {
  const cityId = cityIdOf(row)
  if (cityId === null) {
    planCache.value[key] = {
      loading: false,
      error: 'This row has no city_id, so plan mappings cannot be looked up.',
      active: [],
      deactivated: [],
      showDeactivated: false,
      cityId: null,
    }
    return
  }
  planCache.value[key] = {
    loading: true,
    error: '',
    active: [],
    deactivated: [],
    showDeactivated: false,
    cityId,
  }
  try {
    // Fetch everything once; the panel shows active first and reveals
    // deactivated rows only when the button is pressed.
    const res = await fetch(
      `/api/city-plan-mappings?city_id=${encodeURIComponent(cityId)}&include_deactivated=true`
    )
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Failed to load plans')
    const active = []
    const deactivated = []
    for (const r of data.rows || []) {
      if (r.deactivated_at === null || r.deactivated_at === undefined || r.deactivated_at === '')
        active.push(r)
      else deactivated.push(r)
    }
    planCache.value[key] = {
      loading: false,
      error: '',
      active,
      deactivated,
      showDeactivated: false,
      cityId,
    }
  } catch (e) {
    planCache.value[key] = {
      loading: false,
      error: e.message,
      active: [],
      deactivated: [],
      showDeactivated: false,
      cityId,
    }
  }
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
  expandedKey.value = null
  planCache.value = {}
  showAddPlan.value = false
  deactivateTarget.value = null
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

onMounted(() => {
  load()
  loadTypes()
})
</script>

<template>
  <div>
    <div class="head">
      <div>
        <h1>Cities</h1>
        <p class="sub">Manage the <code>cities</code> table. Click a city to see its plans.</p>
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
            <th class="expand-col"><span class="sr-only">Expand</span></th>
            <th v-for="c in tableColumns" :key="c.name">{{ colLabel(c) }}</th>
            <th class="actions-col">Actions</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(row, i) in filteredRows" :key="expandKeyOf(row, i)">
            <tr
              class="city-row"
              :class="{ expanded: isExpanded(row, i) }"
              :title="cityIdOf(row) === null ? '' : 'Click to see plan mappings'"
              @click="toggleExpand(row, i)"
            >
              <td class="expand-col"><span class="chevron">❯</span></td>
              <td v-for="c in tableColumns" :key="c.name">{{ cellValue(row, c) }}</td>
              <td class="actions-col">
                <button class="btn btn-ghost btn-sm" @click.stop="openEdit(row)">Edit</button>
              </td>
            </tr>
            <tr v-if="isExpanded(row, i)" class="detail-row">
              <td :colspan="tableColumns.length + 2" class="detail-cell" @click.stop>
                <div class="slide-wrap">
                  <div class="plan-panel">
                    <div class="plan-head">
                      <strong>Plans</strong>
                      <span class="plan-city">{{ planTitle(row) }}</span>
                      <template
                        v-if="plansFor(row, i) && !plansFor(row, i).loading && !plansFor(row, i).error"
                      >
                        <span class="plan-counts">{{ planCountsText(plansFor(row, i)) }}</span>
                        <button
                          v-if="plansFor(row, i).deactivated.length"
                          class="btn btn-ghost btn-sm"
                          @click.stop="toggleDeactivated(row, i)"
                        >
                          {{
                            plansFor(row, i).showDeactivated
                              ? 'Hide deactivated'
                              : `Show deactivated (${plansFor(row, i).deactivated.length})`
                          }}
                        </button>
                        <button
                          class="btn btn-primary btn-sm"
                          @click.stop="openAddPlan(row, i)"
                        >
                          + Add plan
                        </button>
                      </template>
                    </div>


                    <div
                      v-if="!plansFor(row, i) || plansFor(row, i).loading"
                      class="plan-loading"
                    >
                      Loading plans…
                    </div>
                    <div v-else-if="plansFor(row, i).error" class="plan-error">
                      <span>{{ plansFor(row, i).error }}</span>
                      <button class="btn btn-ghost btn-sm" @click.stop="retryPlans(row, i)">
                        Retry
                      </button>
                    </div>
                    <template v-else>
                      <div v-if="!plansFor(row, i).active.length" class="plan-empty">
                        No active plans for this city.
                      </div>
                      <table v-else class="plan-table">
                        <thead>
                          <tr>
                            <th>Plan ID</th>
                            <th>Type</th>
                            <th>Business Entity</th>
                            <th>Created At</th>
                            <th class="actions-col">Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr
                            v-for="(m, mi) in plansFor(row, i).active"
                            :key="m.id ?? mi"
                          >
                            <td>{{ m.id ?? '—' }}</td>
                            <td>{{ typeDisplay(m.incentive_type_id) || m.incentive_type_id || '—' }}<span v-if="typeDisplay(m.incentive_type_id)" class="type-id"> #{{ m.incentive_type_id }}</span></td>
                            <td>{{ m.business_entity ?? '—' }}</td>
                            <td>{{ formatDate(m.created_at) || '—' }}</td>
                            <td class="actions-col">
                              <a
                                :href="`/plans/${m.id}`"
                                target="_blank"
                                rel="noopener"
                                class="btn btn-ghost btn-sm"
                                @click.stop
                              >
                                Details
                              </a>
                              <button class="btn btn-danger-soft btn-sm" @click.stop="askDeactivate(row, i, m)">
                                Deactivate
                              </button>
                            </td>
                          </tr>
                        </tbody>
                      </table>

                      <div
                        v-if="
                          plansFor(row, i).showDeactivated &&
                          plansFor(row, i).deactivated.length
                        "
                        class="deactivated-block"
                      >
                        <div class="plan-subhead">Deactivated</div>
                        <table class="plan-table">
                          <thead>
                            <tr>
                              <th>Plan ID</th>
                              <th>Type</th>
                              <th>Business Entity</th>
                              <th>Created At</th>
                              <th>Deactivated At</th>
                              <th class="actions-col">Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            <tr
                              v-for="(m, mi) in plansFor(row, i).deactivated"
                              :key="m.id ?? mi"
                              class="is-deactivated"
                            >
                              <td>{{ m.id ?? '—' }}</td>
                              <td>{{ typeDisplay(m.incentive_type_id) || m.incentive_type_id || '—' }}<span v-if="typeDisplay(m.incentive_type_id)" class="type-id"> #{{ m.incentive_type_id }}</span></td>
                              <td>{{ m.business_entity ?? '—' }}</td>
                              <td>{{ formatDate(m.created_at) || '—' }}</td>
                              <td>{{ formatDate(m.deactivated_at) || '—' }}</td>
                              <td class="actions-col">
                                <a
                                  :href="`/plans/${m.id}`"
                                  target="_blank"
                                  rel="noopener"
                                  class="btn btn-ghost btn-sm"
                                  @click.stop
                                >
                                  Details
                                </a>
                              </td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </template>
                  </div>
                </div>
              </td>
            </tr>
          </template>
          <tr v-if="filteredRows.length === 0">
            <td class="empty" :colspan="tableColumns.length + 2">
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

    <!-- add plan popup -->
    <div v-if="showAddPlan" class="overlay" @click.self="closeAddPlan">
      <div class="modal">
        <h2>Add plan</h2>
        <div v-if="addPlanCity" class="plan-city-chip">
          <span class="chip-label">City</span>
          <strong>{{ addPlanCity.label }}</strong>
          <span class="chip-id">city_id {{ addPlanCity.cityId }}</span>
        </div>
        <div class="field">
          <span>Type</span>
          <select v-model="addPlanForm.incentive_type_id" :disabled="planTypesLoading">
            <option value="" disabled>Select a type…</option>
            <option v-for="t in planTypes" :key="t.id" :value="t.id">
              {{ t.name }} (#{{ t.id }})
            </option>
          </select>
          <p v-if="planTypesLoading" class="hint">Loading types…</p>
          <p v-else-if="planTypesError" class="hint warn">
            Could not load types —
            <button type="button" class="link" @click="loadTypes">retry</button>
          </p>
          <p v-else-if="planTypes.length" class="hint">
            {{ planTypes.length }} types from <code>incentive_type</code>
          </p>
        </div>
        <div class="field">
          <span>Business entity</span>
          <select v-model="addPlanForm.business_entity" :disabled="beNamesLoading">
            <option value="" disabled>Select a business entity…</option>
            <option v-for="name in beNames" :key="name" :value="name">
              {{ name }}
            </option>
          </select>
          <p v-if="beNamesLoading" class="hint">Loading business entities…</p>
          <p v-else-if="beNamesError" class="hint warn">
            Could not load business entities —
            <button type="button" class="link" @click="loadBeNames">retry</button>
          </p>
          <p v-else-if="beNames.length" class="hint">
            {{ beNames.length }} entities from <code>business_entities</code>
          </p>
          <p v-else-if="beNamesLoaded" class="hint warn">No business entities found.</p>
        </div>
        <p v-if="addPlanError" class="form-error">{{ addPlanError }}</p>
        <div class="actions">
          <button class="btn btn-ghost" @click="closeAddPlan">Cancel</button>
          <button class="btn btn-primary" :disabled="addPlanSaving" @click="saveAddPlan">
            {{ addPlanSaving ? 'Saving…' : 'Save plan' }}
          </button>
        </div>
      </div>
    </div>

    <!-- deactivate plan mapping confirmation -->
    <div v-if="deactivateTarget" class="overlay" @click.self="cancelDeactivate">
      <div class="modal">
        <h2>Deactivate plan</h2>
        <p class="confirm-text">
          Deactivate
          <strong>{{
            typeDisplay(deactivateTarget.mapping.incentive_type_id) ||
            deactivateTarget.mapping.incentive_type_id
          }}</strong>
          ({{ deactivateTarget.mapping.business_entity }}) for
          <strong>{{ deactivateTarget.cityLabel }}</strong>? It will move to the
          deactivated list.
        </p>
        <div class="actions">
          <button class="btn btn-ghost" @click="cancelDeactivate">Cancel</button>
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
.actions-col a.btn {
  display: inline-block;
  text-decoration: none;
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

/* expandable rows + slide-down plan mappings */
.city-row {
  cursor: pointer;
}
.city-row.expanded {
  background: #f0f7f3;
}
.expand-col {
  width: 2.4rem;
  text-align: center;
}
thead th.expand-col {
  padding-left: 0.5rem;
  padding-right: 0.5rem;
}
.chevron {
  display: inline-block;
  font-size: 0.75rem;
  color: var(--muted);
  transition: transform 0.2s ease, color 0.2s ease;
}
.city-row.expanded .chevron {
  transform: rotate(90deg);
  color: var(--accent-strong);
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

tbody tr.detail-row:hover {
  background: #fbfdfc;
}
.detail-cell {
  padding: 0;
  background: #fbfdfc;
}
.slide-wrap {
  overflow: hidden;
  animation: slideDown 0.25s ease;
}
@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-6px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
.plan-panel {
  padding: 1rem 1.25rem 1.25rem;
  border-top: 1px dashed var(--border);
}
.plan-head {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
  margin-bottom: 0.7rem;
}
.plan-head strong {
  color: var(--accent-strong);
  font-size: 0.95rem;
}
.plan-city {
  color: var(--muted);
  font-size: 0.85rem;
}
.plan-counts {
  font-size: 0.82rem;
  color: var(--muted);
}
.plan-head .btn {
  margin-left: auto;
}

.plan-loading,
.plan-empty {
  color: var(--muted);
  font-size: 0.9rem;
  padding: 0.6rem 0;
}
.plan-error {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
  color: #8c3030;
  background: var(--danger-soft);
  border: 1px solid #f0caca;
  border-radius: 0.6rem;
  padding: 0.6rem 0.8rem;
  font-size: 0.88rem;
}

table.plan-table {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 0.6rem;
  overflow: hidden;
}
table.plan-table thead th {
  font-size: 0.72rem;
  padding: 0.5rem 0.7rem;
}
table.plan-table tbody td {
  font-size: 0.87rem;
  padding: 0.5rem 0.7rem;
  background: #fff;
}
table.plan-table tbody tr:hover {
  background: #f6faf8;
}
table.plan-table tbody tr.is-deactivated td {
  color: var(--muted);
}

.deactivated-block {
  margin-top: 0.9rem;
}
.plan-subhead {
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
  margin-bottom: 0.45rem;
}

.badge {
  display: inline-block;
  padding: 0.12rem 0.55rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 700;
  white-space: nowrap;
}
.badge.active {
  background: var(--accent-soft);
  color: var(--accent-strong);
}
.badge.deactivated {
  background: #eceff0;
  color: #687876;
}

/* plans slide-down: type names, add-plan popup, deactivate popup */
.type-id {
  color: var(--muted);
  font-size: 0.78rem;
  margin-left: 0.3rem;
  white-space: nowrap;
}
.plan-city-chip {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  background: var(--accent-soft);
  border: 1px solid #cfdfd7;
  border-radius: 0.6rem;
  padding: 0.55rem 0.75rem;
  margin-bottom: 1rem;
  font-size: 0.88rem;
}
.chip-label {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--accent-strong);
}
.plan-city-chip strong {
  color: var(--text);
}
.chip-id {
  margin-left: auto;
  color: var(--muted);
  font-size: 0.8rem;
}
.field select {
  padding: 0.55rem 0.7rem;
  border: 1px solid var(--border);
  border-radius: 0.55rem;
  font-size: 0.95rem;
  outline: none;
  color: var(--text);
  background: #fbfdfc;
  cursor: pointer;
}
.field select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-ring);
  background: #fff;
}
.field select:disabled {
  opacity: 0.6;
  cursor: wait;
}
.form-error {
  color: #8c3030;
  background: var(--danger-soft);
  border: 1px solid #f0caca;
  border-radius: 0.55rem;
  padding: 0.5rem 0.7rem;
  font-size: 0.85rem;
  margin: 0 0 0.6rem;
}
.confirm-text {
  color: var(--text);
  line-height: 1.5;
}
</style>
