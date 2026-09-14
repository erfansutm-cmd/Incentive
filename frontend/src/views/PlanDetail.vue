<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import LookupSelect from '../components/LookupSelect.vue'
import TagChips from '../components/TagChips.vue'
import TagEditor from '../components/TagEditor.vue'
import FreeCombo from '../components/FreeCombo.vue'
import FloatTriple from '../components/FloatTriple.vue'

const route = useRoute()
const planId = computed(() => route.params.id)

const plan = ref(null)
const loading = ref(true)
const error = ref('')
const typeName = ref('')
const cityName = ref('')

// --- base configs (incentive_base_configs) ----------------------------------
// One row per allocator of the plan, joined on plan_id. Only these fields are
// shown up front; the rest of a row sits behind its dropdown. listing_id is not
// among them: it is shared by the whole plan and shown once above the table.
const SUMMARY_FIELDS = ['allocator_id', 'rule_name', 'impact_ratio']
// listing_id and duration belong to the plan, not to a row: they are shown and
// edited once, for every allocator at once.
const SHARED_FIELDS = ['listing_id', 'duration']
// Columns a per-allocator change may set; the plan link is never shown per row.
const ROW_FIELDS = [
  'allocator_id', 'rule_name', 'impact_ratio', 'districts', 'vendors',
  'batch_size', 'clustering_method', 'sensitivity_id', 'sensitivity_group',
]
const REQUIRED_FIELDS = ['allocator_id', 'rule_name', 'impact_ratio']
// Clustering method is free text: these two are offered as a starting point,
// but anything the user types is stored as-is.
const CLUSTERING_OPTIONS = ['kmeans', 'rfmxs']
// sensitivity_group is either nothing or exactly three floats, stored as JSON.
const TRIPLE_FIELD = 'sensitivity_group'
// Columns holding a JSON list of strings (districts, vendors). The stored JSON
// can contain nulls, which are not values and are never shown or kept.
const LIST_FIELDS = ['districts', 'vendors']
// Log columns that only identify the entry; the header already shows changed_at.
const HISTORY_HIDDEN = ['log_id', 'config_id', 'changed_at']

const configs = ref([])
const configColumns = ref([])
const summaryColumns = ref([])
const impactRatioSum = ref(null)
const activeCount = ref(0)
const deactivatedCount = ref(0)
const showDeactivated = ref(false)
const configsLoading = ref(true)
const configsError = ref('')
const expanded = ref(new Set())
// row key -> { open, loading, error, rows, columns } of its logged versions
const histories = ref({})

// popups: plan-level edit, per-allocator add/edit, deactivate confirmation
const planForm = ref(null)
const configForm = ref(null)
const deactivateTarget = ref(null)
const saving = ref(false)
const formError = ref('')
const toast = ref(null)
let toastTimer = null

const isActive = computed(() => {
  if (!plan.value) return false
  const v = plan.value.deactivated_at
  return v === null || v === undefined || v === ''
})

// The table's columns in database order (falls back to the first row's keys).
const fieldNames = computed(() => {
  if (configColumns.value.length) return configColumns.value.map((c) => c.name)
  return Object.keys(configs.value[0] || {})
})

// Fields the table shows without expanding a row (the API reports which of
// them its table really has, so a missing column simply disappears).
const tableFields = computed(() =>
  (summaryColumns.value.length ? summaryColumns.value : SUMMARY_FIELDS).filter((name) =>
    fieldNames.value.includes(name)
  )
)

// Everything else of the row, in table order — what the dropdown reveals.
// plan_id is the plan itself and listing_id / duration are shown once above the
// table, so none of them is repeated on every allocator.
const detailFields = computed(() =>
  fieldNames.value.filter(
    (n) => !tableFields.value.includes(n) && n !== 'plan_id' && !SHARED_FIELDS.includes(n)
  )
)

// The per-allocator fields this table actually has, in a stable form order.
const formFields = computed(() => ROW_FIELDS.filter((f) => fieldNames.value.includes(f)))

const allExpanded = computed(
  () => configs.value.length > 0 && expanded.value.size === configs.value.length
)

const activeConfigs = computed(() => configs.value.filter((row) => !isDeactivated(row)))

// A plan's active allocators are meant to share the whole incentive between
// them, so their ratios should add up to 1 (100%).
const impactOffBy = computed(() => {
  if (impactRatioSum.value === null) return null
  const diff = Number(impactRatioSum.value) - 1
  // a rounding-sized difference is not worth shouting about
  return Math.abs(diff) < 0.00005 ? 0 : diff
})
const impactIsWrong = computed(() => impactOffBy.value !== null && impactOffBy.value !== 0)
const impactMessage = computed(() => {
  if (!impactIsWrong.value) return ''
  const short = impactOffBy.value > 0
    ? `${ratioText(impactOffBy.value)} too much`
    : `${ratioText(-impactOffBy.value)} short`
  return (
    `The impact ratios of this plan's active allocators add up to ` +
    `${ratioText(impactRatioSum.value)}, not 100% — ${short}.`
  )
})

// A plan has exactly one listing, so its allocators must all carry the same
// one. Derived from the loaded rows, so it re-checks on every refresh and
// after every change.
const listingValues = computed(() => {
  const seen = []
  for (const row of activeConfigs.value) {
    const value = String(row.listing_id ?? '').trim()
    if (value && !seen.includes(value)) seen.push(value)
  }
  return seen
})
const listingIsWrong = computed(() => listingValues.value.length > 1)
const listingMessage = computed(() => {
  if (!listingIsWrong.value) return ''
  return (
    `This plan's active allocators use ${listingValues.value.length} different listings ` +
    `(${listingValues.value.join(', ')}), but a plan has only one. ` +
    `Use \u201cEdit for all\u201d to set them all to the same listing.`
  )
})

// listing_id / duration are read off the plan's rows: they are the same on all
// of them, so the first active row is the plan's value.
const sharedValues = computed(() => {
  const source = activeConfigs.value[0] || configs.value[0] || {}
  return {
    listing_id: source.listing_id ?? '',
    duration: source.duration ?? '',
  }
})


function rowKey(row, i) {
  return row.id !== undefined && row.id !== null ? String(row.id) : `idx-${i}`
}

function isOpen(row, i) {
  return expanded.value.has(rowKey(row, i))
}

function toggleRow(row, i) {
  const key = rowKey(row, i)
  const next = new Set(expanded.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expanded.value = next
}

function toggleAll() {
  expanded.value = allExpanded.value
    ? new Set()
    : new Set(configs.value.map((row, i) => rowKey(row, i)))
}

function isDeactivated(row) {
  const v = row?.deactivated_at
  return v !== null && v !== undefined && v !== ''
}

function colLabel(name) {
  return String(name)
    .split('_')
    .map((w) => (w.toLowerCase() === 'id' ? 'ID' : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(' ')
}

// 0.4 -> "40%", 0.125 -> "12.5%" (raw value stays visible next to it).
function ratioText(value) {
  if (value === null || value === undefined || value === '') return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return cellText(value)
  return `${Number((n * 100).toFixed(2))}%`
}

function cellText(value) {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value) || (typeof value === 'object' && value !== null))
    return JSON.stringify(value)
  return String(value)
}

// "2026-09-14T10:11:16" -> "Sep 14, 2026, 10:11 AM"
function formatDate(value) {
  if (!value) return ''
  const d = new Date(value)
  if (isNaN(d)) return value
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(d)
}

// A list column back to its values: the stored JSON can be an array, a JSON
// string, or hold nulls, none of which should reach the UI.
function parseList(value) {
  let raw = value
  if (typeof raw === 'string') {
    const text = raw.trim()
    if (!text) return []
    try {
      raw = JSON.parse(text)
    } catch {
      return [text] // a plain string is a one-item list
    }
  }
  if (raw === null || raw === undefined || raw === '') return []
  const items = Array.isArray(raw) ? raw : [raw]
  return items
    .filter((item) => item !== null && item !== undefined && String(item).trim() !== '')
    .map((item) => String(item).trim())
}

// sensitivity_group is stored as a JSON list of up to three numbers.
function parseTriple(value) {
  let raw = value
  if (typeof raw === 'string') {
    const text = raw.trim()
    if (!text) return []
    try {
      raw = JSON.parse(text)
    } catch {
      return [text]
    }
  }
  if (raw === null || raw === undefined || raw === '') return []
  const items = (Array.isArray(raw) ? raw : [raw]).slice(0, 3)
  return items.map((item) => (item === null || item === undefined ? '' : String(item)))
}

// A triple is all three numbers or nothing; a partial set is not storable.
function formatTriple(values) {
  const items = (values || []).map((v) => String(v ?? '').trim())
  const filled = items.filter((v) => v !== '')
  if (!filled.length) return ''
  if (filled.length < 3) return null // incomplete: the form blocks the save
  const numbers = items.map(Number)
  if (numbers.some((n) => !Number.isFinite(n))) return null
  return JSON.stringify(numbers)
}

function isTripleField(field) {
  return String(field) === TRIPLE_FIELD
}

function isListField(field) {
  return LIST_FIELDS.includes(String(field))
}

// Timestamp columns read as dates, everything else as plain text.
function displayValue(field, value) {
  if (String(field).endsWith('_at')) return formatDate(value) || '—'
  // the three sensitivity groups read as labelled numbers, not as raw JSON
  if (isTripleField(field)) {
    const items = parseTriple(value).filter((v) => String(v).trim() !== '')
    if (!items.length) return '—'
    return items.map((v, i) => `G${i + 1} ${Number(v)}`).join('  ·  ')
  }
  return cellText(value)
}

function notify(text, kind = 'ok') {
  toast.value = { text, kind }
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toast.value = null
  }, 4000)
}

// Report the result of a write, plus a warning when the plan's active
// allocators no longer add up to 100%.
function notifyChange(text) {
  const warnings = [impactMessage.value, listingMessage.value].filter(Boolean)
  if (warnings.length) {
    notify(`${text} ${warnings.join(' ')}`, 'warn')
  } else {
    notify(text)
  }
}

// --- change history (incentive_base_configs_logs) ---------------------------
// Each logged row is the config as it was *before* a change. Loaded lazily the
// first time a row's history is opened.
function historyOf(row, i) {
  return histories.value[rowKey(row, i)]
}

function historyFields(entry) {
  const names = (entry?.columns || []).length
    ? entry.columns.map((c) => c.name)
    : Object.keys(entry?.rows?.[0] || {})
  return names.filter(
    (n) => !HISTORY_HIDDEN.includes(n) && n !== 'plan_id' && !SHARED_FIELDS.includes(n)
  )
}

function historyLabel(row, i) {
  const entry = historyOf(row, i)
  if (entry?.loading) return 'Loading history…'
  if (entry?.rows?.length) return entry.open ? 'Hide change history' : `Change history (${entry.rows.length})`
  return 'Change history'
}

function setHistory(key, entry) {
  histories.value = { ...histories.value, [key]: entry }
}

async function loadHistory(row, i) {
  const key = rowKey(row, i)
  setHistory(key, { open: true, loading: true, error: '', rows: [], columns: [] })
  try {
    const res = await fetch(`/api/incentive-base-configs/${encodeURIComponent(row.id)}/logs`)
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Failed to load change history')
    setHistory(key, {
      open: true,
      loading: false,
      error: '',
      rows: data.rows || [],
      columns: data.columns || [],
    })
  } catch (e) {
    setHistory(key, { open: true, loading: false, error: e.message, rows: [], columns: [] })
  }
}

async function toggleHistory(row, i) {
  if (row.id === undefined || row.id === null) return
  const key = rowKey(row, i)
  const entry = histories.value[key]
  if (entry?.loading) return
  // Closing a loaded panel never re-fetches.
  if (entry?.open && !entry.error) {
    setHistory(key, { ...entry, open: false })
    return
  }
  // A successful load is kept, so reopening is instant.
  if (entry && !entry.error) {
    setHistory(key, { ...entry, open: true })
    return
  }
  await loadHistory(row, i)
}

// Retry always goes back to the API, even with the panel already open.
function retryHistory(row, i) {
  if (row.id === undefined || row.id === null) return Promise.resolve()
  return loadHistory(row, i)
}

async function loadConfigs(includeDeactivated = false) {
  configsLoading.value = true
  configsError.value = ''
  expanded.value = new Set()
  histories.value = {}
  try {
    const params = new URLSearchParams({ plan_id: String(planId.value) })
    if (includeDeactivated) params.set('include_deactivated', 'true')
    const res = await fetch(`/api/incentive-base-configs?${params.toString()}`)
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Failed to load base configs')
    configs.value = data.rows || []
    configColumns.value = data.columns || []
    summaryColumns.value = data.summary_columns || []
    impactRatioSum.value = data.impact_ratio_sum ?? null
    activeCount.value = data.active_count ?? configs.value.length
    deactivatedCount.value = data.deactivated_count ?? 0
    showDeactivated.value = Boolean(data.include_deactivated)
  } catch (e) {
    configs.value = []
    configsError.value = e.message
  } finally {
    configsLoading.value = false
  }
}

function retryConfigs() {
  return loadConfigs(showDeactivated.value)
}

function toggleDeactivated() {
  return loadConfigs(!showDeactivated.value)
}

// --- popups -----------------------------------------------------------------
function openPlanEdit() {
  formError.value = ''
  planForm.value = {
    listing_id: sharedValues.value.listing_id,
    duration: sharedValues.value.duration,
  }
}

function openAdd() {
  formError.value = ''
  const template = activeConfigs.value[0] || {}
  const values = {}
  for (const field of formFields.value) {
    // a new allocator starts from the plan's usual settings, not from scratch
    if (isListField(field)) values[field] = []
    else if (isTripleField(field)) values[field] = parseTriple(template[field])
    else if (['batch_size', 'clustering_method'].includes(field)) values[field] = template[field] ?? ''
    else values[field] = ''
  }
  configForm.value = {
    mode: 'add',
    id: null,
    values,
    listing_id: sharedValues.value.listing_id,
    duration: sharedValues.value.duration,
  }
}

function openEdit(row) {
  formError.value = ''
  const values = {}
  for (const field of formFields.value) {
    const value = row[field]
    if (isListField(field)) values[field] = parseList(value)
    else if (isTripleField(field)) values[field] = parseTriple(value)
    else values[field] = value === null || value === undefined ? '' : value
  }
  configForm.value = { mode: 'edit', id: row.id, values, allocator: row.allocator_id }
}

function askDeactivate(row) {
  formError.value = ''
  deactivateTarget.value = row
}

function closePopups() {
  if (saving.value) return
  planForm.value = null
  configForm.value = null
  deactivateTarget.value = null
  formError.value = ''
}

function payloadFrom(values) {
  const payload = {}
  for (const [field, value] of Object.entries(values)) {
    if (isListField(field)) {
      const items = parseList(value)
      // an empty list is stored as NULL, not as "[]"
      payload[field] = items.length ? JSON.stringify(items) : ''
    } else if (isTripleField(field)) {
      // three floats or nothing at all; a partial set never reaches the API
      const encoded = formatTriple(value)
      payload[field] = encoded === null ? '' : encoded
    } else {
      payload[field] = typeof value === 'string' ? value.trim() : value
    }
  }
  return payload
}

// Only the fields that identify an allocator are required; the rest of a row
// may legitimately be empty, so an unchanged empty field is not a problem.
function validate(values) {
  for (const field of REQUIRED_FIELDS) {
    if (!formFields.value.includes(field)) continue
    const value = values[field]
    const empty =
      value === null ||
      value === undefined ||
      (Array.isArray(value) ? value.length === 0 : String(value).trim() === '')
    if (empty) return `'${colLabel(field)}' is required.`
  }
  if (formFields.value.includes('impact_ratio')) {
    const ratio = Number(values.impact_ratio)
    if (!Number.isFinite(ratio)) return "'Impact Ratio' must be a number."
  }
  if (formFields.value.includes(TRIPLE_FIELD)) {
    const items = (values[TRIPLE_FIELD] || []).map((v) => String(v ?? '').trim())
    const filled = items.filter((v) => v !== '')
    if (filled.length && filled.length < 3) {
      return `'Sensitivity Group' needs all three groups, or none.`
    }
    if (filled.length === 3 && items.some((v) => !Number.isFinite(Number(v)))) {
      return `'Sensitivity Group' groups must be numbers.`
    }
  }
  return ''
}

// Numeric columns go over the wire as numbers, not as the input's text.
function asNumber(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : value
}

async function savePlanForm() {
  const listing = String(planForm.value.listing_id ?? '').trim()
  const duration = String(planForm.value.duration ?? '').trim()
  if (!listing) {
    formError.value = "'Listing ID' is required."
    return
  }
  saving.value = true
  formError.value = ''
  try {
    const res = await fetch(
      `/api/incentive-base-configs/plan/${encodeURIComponent(planId.value)}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          listing_id: listing,
          duration: duration === '' ? '' : asNumber(duration),
        }),
      }
    )
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Failed to update the plan')
    planForm.value = null
    await loadConfigs(showDeactivated.value)
    notifyChange(
      data.updated
        ? `Updated ${data.updated} allocator${data.updated === 1 ? '' : 's'} of this plan.`
        : 'Nothing to change.'
    )
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function saveConfigForm() {
  const form = configForm.value
  // Validate the raw form values, not the payload: payloadFrom has already
  // collapsed an incomplete sensitivity triple into "none", which would let a
  // half-filled group wipe all three instead of being refused.
  const problem = validate(form.values)
  if (problem) {
    formError.value = problem
    return
  }
  const values = payloadFrom(form.values)
  saving.value = true
  formError.value = ''
  try {
    let res
    if (form.mode === 'add') {
      const body = { plan_id: String(planId.value), ...values }
      // the first allocator of a plan sets its listing and duration; later ones
      // inherit them, so they are not sent again
      if (!activeConfigs.value.length) {
        body.listing_id = String(form.listing_id ?? '').trim()
        const duration = String(form.duration ?? '').trim()
        if (duration !== '') body.duration = asNumber(duration)
        if (!body.listing_id) {
          formError.value = "'Listing ID' is required."
          saving.value = false
          return
        }
      }
      res = await fetch('/api/incentive-base-configs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    } else {
      res = await fetch(
        `/api/incentive-base-configs/${encodeURIComponent(form.id)}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(values),
        }
      )
    }
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Failed to save')
    configForm.value = null
    await loadConfigs(showDeactivated.value)
    if (form.mode === 'add') notifyChange('Allocator added.')
    else if (data.logged) notifyChange('Allocator updated.')
    else notifyChange('Nothing to change.')
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

// A deactivated row is never deleted and every change is logged, so it can be
// brought back later with its history intact.
async function confirmActivate(row) {
  saving.value = true
  formError.value = ''
  try {
    const res = await fetch(
      `/api/incentive-base-configs/${encodeURIComponent(row.id)}/activate`,
      { method: 'POST' }
    )
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Failed to activate')
    await loadConfigs(showDeactivated.value)
    notifyChange(data.logged ? 'Allocator activated.' : 'Allocator was already active.')
  } catch (e) {
    notify(e.message, 'error')
  } finally {
    saving.value = false
  }
}

async function confirmDeactivate() {
  const row = deactivateTarget.value
  saving.value = true
  formError.value = ''
  try {
    const res = await fetch(
      `/api/incentive-base-configs/${encodeURIComponent(row.id)}/deactivate`,
      { method: 'POST' }
    )
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Failed to deactivate')
    deactivateTarget.value = null
    await loadConfigs(showDeactivated.value)
    notifyChange(data.logged ? 'Allocator deactivated.' : 'Allocator was already deactivated.')
  } catch (e) {
    formError.value = e.message
  } finally {
    saving.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  // The base configs are a separate section: a failure there must not hide the
  // plan itself, so it is loaded on its own track.
  const configsPromise = loadConfigs(false)
  try {
    const [planRes, typesRes, citiesRes] = await Promise.all([
      fetch(`/api/city-plan-mappings/${encodeURIComponent(planId.value)}`),
      fetch('/api/incentive-types'),
      fetch('/api/cities'),
    ])
    const data = await planRes.json()
    if (!planRes.ok) throw new Error(data.message || data.detail || 'Failed to load plan')
    plan.value = data.row
    // Map incentive_type_id -> name; the page stays usable without it.
    if (typesRes.ok) {
      const tdata = await typesRes.json()
      const match = (tdata.rows || []).find(
        (t) => String(t.id) === String(plan.value?.incentive_type_id)
      )
      if (match) typeName.value = match.name
    }
    // Map city_id -> city name; the page stays usable without it.
    if (citiesRes.ok) {
      const cdata = await citiesRes.json()
      const cols = (cdata.columns || []).map((c) => c.name)
      const nameCol = ['city_name', 'city', 'name', 'correct_city'].find((n) =>
        cols.includes(n)
      )
      const idCol = ['city_id', 'correct_city_id', 'correct_id'].find((n) =>
        cols.includes(n)
      )
      if (nameCol && idCol) {
        const city = (cdata.rows || []).find(
          (r) => String(r[idCol]) === String(plan.value?.city_id)
        )
        if (city && city[nameCol] !== null && city[nameCol] !== undefined && city[nameCol] !== '') {
          cityName.value = city[nameCol]
        }
      }
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
  await configsPromise
}

onMounted(load)
</script>

<template>
  <div>
    <div class="head">
      <div>
        <h1>Plan #{{ planId }}</h1>
        <p class="sub">Plan details.</p>
      </div>
      <router-link to="/cities" class="btn btn-ghost">← Cities</router-link>
    </div>

    <div v-if="error" class="banner error">
      <strong>Could not load plan</strong>
      <p>{{ error }}</p>
      <button class="btn btn-ghost" @click="load">Retry</button>
    </div>

    <div v-else-if="loading" class="card empty">Loading…</div>

    <div v-else-if="plan" class="card detail-card">
      <div class="status-hero" :class="isActive ? 'is-active' : 'is-deactivated'">
        <span class="status-dot"></span>
        <div>
          <div class="status-label">Status</div>
          <div class="status-value">{{ isActive ? 'Active' : 'Deactivated' }}</div>
          <div v-if="!isActive && plan.deactivated_at" class="status-sub">
            since {{ formatDate(plan.deactivated_at) }}
          </div>
        </div>
      </div>

      <dl class="facts">
        <div>
          <dt>City</dt>
          <dd>{{ cityName || '—' }}</dd>
        </div>
        <div>
          <dt>Type</dt>
          <dd>
            {{
              typeName
                ? `${typeName} (#${plan.incentive_type_id})`
                : plan.incentive_type_id ?? '—'
            }}
          </dd>
        </div>
        <div>
          <dt>Business entity</dt>
          <dd>{{ plan.business_entity ?? '—' }}</dd>
        </div>
        <div>
          <dt>Created at</dt>
          <dd>{{ formatDate(plan.created_at) || '—' }}</dd>
        </div>
        <div v-if="!isActive">
          <dt>Deactivated at</dt>
          <dd>{{ formatDate(plan.deactivated_at) || '—' }}</dd>
        </div>
      </dl>
    </div>

    <!-- base configs of the plan (incentive_base_configs, joined on plan_id) -->
    <section class="card section-card config-section" role="region" aria-label="Base configs">
      <div class="card-head">
        <div class="card-head-text">
          <span class="icon-tile" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 6h16" />
              <path d="M4 12h10" />
              <path d="M4 18h6" />
            </svg>
          </span>
          <div>
            <p class="eyebrow">Base configs</p>
            <h2>Allocators</h2>
          </div>
        </div>
        <div class="card-head-actions">
          <span
            v-if="impactRatioSum !== null"
            class="pill"
            :class="impactIsWrong ? 'danger' : 'accent'"
            :title="impactIsWrong ? impactMessage : 'Active allocators add up to 100%'"
          >
            impact {{ ratioText(impactRatioSum) }}
          </span>
          <span
            v-if="listingIsWrong"
            class="pill danger"
            :title="listingMessage"
          >
            {{ listingValues.length }} listings
          </span>
          <span v-if="!configsLoading && !configsError" class="pill">
            {{ activeCount }} allocator{{ activeCount === 1 ? '' : 's' }}
          </span>
          <span v-if="showDeactivated && deactivatedCount" class="pill plain">
            {{ deactivatedCount }} deactivated
          </span>
          <button
            v-if="deactivatedCount && !configsLoading && !configsError"
            class="btn btn-ghost btn-sm"
            @click="toggleDeactivated"
          >
            {{ showDeactivated ? 'Hide deactivated' : `Show deactivated (${deactivatedCount})` }}
          </button>
          <button
            v-if="configs.length > 1"
            class="btn btn-ghost btn-sm"
            @click="toggleAll"
          >
            {{ allExpanded ? 'Collapse all' : 'Expand all' }}
          </button>
          <button
            v-if="!configsLoading && !configsError"
            class="btn btn-primary btn-sm"
            @click="openAdd"
          >
            + Add allocator
          </button>
        </div>
      </div>

      <!-- listing and duration are the plan's, shared by every allocator -->
      <div v-if="!configsLoading && !configsError" class="shared-bar">
        <dl class="shared-values">
          <div>
            <dt>Listing</dt>
            <dd>{{ cellText(sharedValues.listing_id) }}</dd>
          </div>
          <div>
            <dt>Duration</dt>
            <dd>{{ cellText(sharedValues.duration) }}</dd>
          </div>
        </dl>
        <div class="shared-actions">
          <span class="shared-note">Same for every allocator of this plan</span>
          <button
            v-if="activeConfigs.length"
            class="btn btn-ghost btn-sm"
            @click="openPlanEdit"
          >
            Edit for all
          </button>
        </div>
      </div>

      <p v-if="impactIsWrong && !configsLoading && !configsError" class="impact-warning">
        {{ impactMessage }}
      </p>
      <p v-if="listingIsWrong && !configsLoading && !configsError" class="impact-warning">
        {{ listingMessage }}
      </p>

      <div v-if="configsLoading" class="config-body">
        <p class="config-loading">Loading base configs…</p>
      </div>
      <div v-else-if="configsError" class="config-body">
        <div class="config-error">
          <span>{{ configsError }}</span>
          <button class="btn btn-ghost btn-sm" @click="retryConfigs">Retry</button>
        </div>
      </div>
      <div v-else-if="!configs.length" class="config-body">
        <p class="config-empty">
          {{
            deactivatedCount
              ? 'No active base configs for this plan.'
              : 'No base configs for this plan yet.'
          }}
        </p>
      </div>
      <div v-else class="table-scroll">
        <table class="config-table">
          <thead>
            <tr>
              <th class="expand-col"><span class="sr-only">Details</span></th>
              <th v-for="f in tableFields" :key="f">{{ colLabel(f) }}</th>
              <th class="actions-col">Actions</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(row, i) in configs" :key="rowKey(row, i)">
              <tr
                class="config-row"
                :class="{ expanded: isOpen(row, i), 'is-deactivated': isDeactivated(row) }"
                title="Click to see the other fields"
                @click="toggleRow(row, i)"
              >
                <td class="expand-col">
                  <button
                    type="button"
                    class="chevron-disc"
                    :class="{ open: isOpen(row, i) }"
                    :aria-expanded="isOpen(row, i)"
                    :aria-controls="`config-detail-${rowKey(row, i)}`"
                    :aria-label="`Toggle details of allocator ${cellText(row.allocator_id)}`"
                    @click.stop="toggleRow(row, i)"
                  >
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                      <path d="M9.5 5.5l6.5 6.5-6.5 6.5" />
                    </svg>
                  </button>
                </td>
                <td v-for="(f, fi) in tableFields" :key="f" :class="{ 'mono-cell': f !== 'impact_ratio' }">
                  <template v-if="f === 'impact_ratio'">
                    <span class="ratio">{{ ratioText(row[f]) }}</span>
                    <span v-if="row[f] !== null && row[f] !== undefined && row[f] !== ''" class="ratio-raw">
                      {{ row[f] }}
                    </span>
                  </template>
                  <template v-else>
                    {{ cellText(row[f]) }}
                    <span v-if="fi === 0 && isDeactivated(row)" class="tag-off">Deactivated</span>
                  </template>
                </td>
                <td class="actions-col" @click.stop>
                  <button
                    v-if="!isDeactivated(row)"
                    class="btn btn-ghost btn-sm"
                    @click="openEdit(row)"
                  >
                    Edit
                  </button>
                  <button
                    v-if="!isDeactivated(row)"
                    class="btn btn-danger-soft btn-sm"
                    @click="askDeactivate(row)"
                  >
                    Deactivate
                  </button>
                  <button
                    v-if="isDeactivated(row)"
                    class="btn btn-ghost btn-sm"
                    :disabled="saving"
                    @click="confirmActivate(row)"
                  >
                    Activate
                  </button>
                </td>
              </tr>
              <tr v-if="isOpen(row, i)" class="detail-row">
                <td :id="`config-detail-${rowKey(row, i)}`" :colspan="tableFields.length + 2" class="detail-cell" @click.stop>
                  <dl v-if="detailFields.length" class="detail-facts">
                    <div v-for="f in detailFields" :key="f">
                      <dt>{{ colLabel(f) }}</dt>
                      <dd>
                        <TagChips
                          v-if="isListField(f)"
                          :items="parseList(row[f])"
                          :noun="colLabel(f)"
                        />
                        <template v-else>{{ displayValue(f, row[f]) }}</template>
                      </dd>
                    </div>
                  </dl>
                  <p v-else class="config-loading">This row has no other fields.</p>

                  <!-- logged previous versions of this row -->
                  <div v-if="row.id !== undefined && row.id !== null" class="history">
                    <button
                      type="button"
                      class="btn btn-ghost btn-sm"
                      :aria-expanded="Boolean(historyOf(row, i)?.open)"
                      :disabled="Boolean(historyOf(row, i)?.loading)"
                      @click="toggleHistory(row, i)"
                    >
                      {{ historyLabel(row, i) }}
                    </button>

                    <p v-if="historyOf(row, i)?.loading" class="config-loading">
                      Loading change history…
                    </p>
                    <div v-else-if="historyOf(row, i)?.error" class="config-error">
                      <span>{{ historyOf(row, i).error }}</span>
                      <button class="btn btn-ghost btn-sm" @click="retryHistory(row, i)">
                        Retry
                      </button>
                    </div>
                    <template v-else-if="historyOf(row, i)?.open">
                      <p v-if="!historyOf(row, i).rows.length" class="config-loading">
                        No previous versions recorded yet.
                      </p>
                      <ol v-else class="history-list">
                        <li
                          v-for="(entry, li) in historyOf(row, i).rows"
                          :key="entry.log_id ?? li"
                          class="history-item"
                        >
                          <div class="history-head">
                            <span class="history-when">
                              {{ formatDate(entry.changed_at) || '—' }}
                            </span>
                            <span class="pill plain">previous values</span>
                          </div>
                          <dl class="detail-facts">
                            <div v-for="f in historyFields(historyOf(row, i))" :key="f">
                              <dt>{{ colLabel(f) }}</dt>
                              <dd>
                                <TagChips
                                  v-if="isListField(f)"
                                  :items="parseList(entry[f])"
                                  :noun="colLabel(f)"
                                />
                                <template v-else>{{ displayValue(f, entry[f]) }}</template>
                              </dd>
                            </div>
                          </dl>
                        </li>
                      </ol>
                    </template>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </section>

    <!-- edit listing / duration for every allocator of the plan -->
    <div v-if="planForm" class="overlay" @click.self="closePopups">
      <div class="modal">
        <h2 id="plan-form-title">Edit listing and duration</h2>
        <p class="modal-hint">
          Both are shared by every allocator of plan {{ planId }}, so saving
          updates all {{ activeConfigs.length }} of them. Each row keeps a log
          of its previous values.
        </p>
        <p v-if="formError" class="form-error">{{ formError }}</p>
        <label class="field" for="plan-listing">
          <span>Listing ID</span>
          <LookupSelect
            id="plan-listing"
            v-model="planForm.listing_id"
            source="listings"
            noun="listing"
            placeholder="Search the available listings…"
          />
        </label>
        <label class="field" for="plan-duration">
          <span>Duration</span>
          <input id="plan-duration" v-model="planForm.duration" type="number" step="1" />
        </label>
        <div class="actions">
          <button class="btn btn-ghost" :disabled="saving" @click="closePopups">Cancel</button>
          <button class="btn btn-primary" :disabled="saving" @click="savePlanForm">
            {{ saving ? 'Saving…' : 'Save for all allocators' }}
          </button>
        </div>
      </div>
    </div>

    <!-- add an allocator, or edit one of the plan's allocators -->
    <div v-if="configForm" class="overlay" @click.self="closePopups">
      <div class="modal">
        <h2 :id="configForm.mode === 'add' ? 'add-config-title' : 'edit-config-title'">
          {{ configForm.mode === 'add' ? 'Add allocator' : 'Edit allocator' }}
        </h2>
        <p v-if="configForm.mode === 'add'" class="modal-hint">
          <template v-if="activeConfigs.length">
            Added to plan {{ planId }} with its listing
            <code>{{ cellText(sharedValues.listing_id) }}</code> and duration
            <code>{{ cellText(sharedValues.duration) }}</code>.
          </template>
          <template v-else>
            This is the first allocator of plan {{ planId }}, so it also sets
            the listing and duration every later allocator inherits.
          </template>
        </p>
        <p v-else class="modal-hint">
          Editing
          <code>{{ cellText(configForm.allocator) }}</code> on plan
          {{ planId }}. Its values as they are now are written to the change log
          first, so the previous version stays readable. Listing and duration
          belong to the plan and are edited above the table.
        </p>
        <p v-if="formError" class="form-error">{{ formError }}</p>

        <template v-if="configForm.mode === 'add' && !activeConfigs.length">
          <label class="field" for="add-listing">
            <span>Listing ID</span>
            <LookupSelect
              id="add-listing"
              v-model="configForm.listing_id"
              source="listings"
              noun="listing"
              placeholder="Search the available listings…"
            />
          </label>
          <label class="field" for="add-duration">
            <span>Duration</span>
            <input id="add-duration" v-model="configForm.duration" type="number" step="1" />
          </label>
        </template>

        <label v-for="f in formFields" :key="f" class="field" :for="`config-${f}`">
          <span>
            {{ colLabel(f) }}
            <em v-if="!REQUIRED_FIELDS.includes(f)" class="opt">(optional)</em>
            <em v-else class="req">required</em>
          </span>
          <LookupSelect
            v-if="f === 'allocator_id'"
            :id="`config-${f}`"
            v-model="configForm.values[f]"
            source="allocators"
            noun="allocator"
            placeholder="Search the available allocators…"
          />
          <LookupSelect
            v-else-if="f === 'rule_name'"
            :id="`config-${f}`"
            v-model="configForm.values[f]"
            source="rules"
            noun="rule"
            placeholder="Search the available rules…"
          />
          <TagEditor
            v-else-if="isListField(f)"
            :id="`config-${f}`"
            v-model="configForm.values[f]"
            :noun="colLabel(f)"
          />
          <FreeCombo
            v-else-if="f === 'clustering_method'"
            :id="`config-${f}`"
            v-model="configForm.values[f]"
            :options="CLUSTERING_OPTIONS"
            noun="method"
            placeholder="Pick a method or type your own…"
          />
          <FloatTriple
            v-else-if="isTripleField(f)"
            :id="`config-${f}`"
            v-model="configForm.values[f]"
          />
          <input
            v-else
            :id="`config-${f}`"
            v-model="configForm.values[f]"
            :type="['impact_ratio'].includes(f) ? 'number' : ['batch_size', 'duration'].includes(f) ? 'number' : 'text'"
            :step="f === 'impact_ratio' ? '0.0001' : '1'"
          />
        </label>

        <div class="actions">
          <button class="btn btn-ghost" :disabled="saving" @click="closePopups">Cancel</button>
          <button class="btn btn-primary" :disabled="saving" @click="saveConfigForm">
            {{
              saving
                ? 'Saving…'
                : configForm.mode === 'add'
                  ? 'Add allocator'
                  : 'Save changes'
            }}
          </button>
        </div>
      </div>
    </div>

    <!-- deactivate confirmation -->
    <div v-if="deactivateTarget" class="overlay" @click.self="closePopups">
      <div class="modal">
        <h2 id="deactivate-title">Deactivate allocator</h2>
        <p v-if="formError" class="form-error">{{ formError }}</p>
        <p class="confirm-text">
          Deactivate
          <strong>{{ deactivateTarget.allocator_id }}</strong>
          (<code>{{ deactivateTarget.rule_name }}</code>,
          {{ ratioText(deactivateTarget.impact_ratio) }})
          on plan {{ planId }}?
        </p>
        <p class="modal-hint">
          It leaves the plan's active allocators and its values are kept in the
          change log. Nothing is deleted.
        </p>
        <div class="actions">
          <button class="btn btn-ghost" :disabled="saving" @click="closePopups">Cancel</button>
          <button class="btn btn-danger" :disabled="saving" @click="confirmDeactivate">
            {{ saving ? 'Working…' : 'Deactivate' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="toast" class="toast" :class="toast.kind">{{ toast.text }}</div>
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

.empty {
  padding: 3rem 1rem;
  text-align: center;
  color: var(--muted);
}

.detail-card {
  padding: 1.5rem;
}

.status-hero {
  display: flex;
  align-items: center;
  gap: 0.9rem;
  border-radius: 0.7rem;
  padding: 1rem 1.2rem;
  margin-bottom: 1.25rem;
  border: 1px solid var(--border);
}
.status-hero.is-active {
  background: var(--accent-soft);
  border-color: #cfdfd7;
}
.status-hero.is-deactivated {
  background: #f1f4f3;
}
.status-dot {
  width: 0.9rem;
  height: 0.9rem;
  border-radius: 999px;
  flex-shrink: 0;
}
.is-active .status-dot {
  background: var(--accent);
  box-shadow: 0 0 0 4px var(--accent-ring);
}
.is-deactivated .status-dot {
  background: #9aa8a2;
}
.status-label {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}
.status-value {
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--text);
}
.status-sub {
  font-size: 0.85rem;
  color: var(--muted);
}

.facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.75rem;
  margin: 0;
}
.facts > div {
  background: #fbfdfc;
  border: 1px solid var(--border);
  border-radius: 0.6rem;
  padding: 0.6rem 0.8rem;
}
.facts dt {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
  margin-bottom: 0.2rem;
}
.facts dd {
  margin: 0;
  font-size: 0.95rem;
  color: var(--text);
  overflow-wrap: anywhere;
}

/* --- base configs ------------------------------------------------------- */
.config-section {
  margin-top: 0.85rem;
  overflow: visible;
}
.config-section h2 {
  margin: 0;
  font-size: 1.05rem;
}
.config-body {
  padding: 1rem 1.25rem 1.25rem;
}
.config-loading {
  margin: 0;
  color: var(--muted);
  font-size: 0.9rem;
}
.config-empty {
  margin: 0;
  padding: 1.5rem 1rem;
  text-align: center;
  color: var(--muted);
  border: 1px dashed var(--border);
  border-radius: 0.6rem;
}
.config-error {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
  color: #8c3030;
  background: var(--danger-soft);
  border: 1px solid #f0caca;
  border-radius: 0.6rem;
  padding: 0.7rem 0.9rem;
  font-size: 0.88rem;
}

/* the plan's shared listing / duration */
.impact-warning {
  margin: 0.6rem 0 0;
  padding: 0.6rem 0.8rem;
  border: 1px solid var(--danger);
  border-left-width: 3px;
  border-radius: 0.55rem;
  background: var(--danger-soft);
  color: var(--danger-strong);
  font-size: 0.85rem;
  line-height: 1.5;
}
.shared-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  padding: 0.85rem 1.25rem;
  border-top: 1px solid var(--border);
  background: #fbfdfc;
}
.shared-values {
  display: flex;
  gap: 1.75rem;
  flex-wrap: wrap;
  margin: 0;
}
.shared-values dt {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
}
.shared-values dd {
  margin: 0.1rem 0 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text);
  overflow-wrap: anywhere;
}
.shared-actions {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  flex-wrap: wrap;
}
.shared-note {
  font-size: 0.78rem;
  color: var(--muted);
}

.table-scroll {
  width: 100%;
  overflow-x: auto;
}
table.config-table {
  width: 100%;
  border-collapse: collapse;
}
.config-table thead th {
  text-align: left;
  padding: 0.7rem 0.9rem;
  background: var(--surface-2);
  color: #4a6155;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  white-space: nowrap;
}
.config-table tbody td {
  padding: 0.7rem 0.9rem;
  border-top: 1px solid var(--border);
  font-size: 0.9rem;
  color: var(--text);
  overflow-wrap: anywhere;
}
.config-table tbody tr.config-row {
  cursor: pointer;
}
.config-table tbody tr.config-row:hover td {
  background: #f6faf8;
}
.config-table tbody tr.config-row.expanded td {
  background: var(--accent-soft);
}
.config-table tbody tr.config-row.expanded td:first-child {
  box-shadow: inset 3px 0 0 var(--accent);
}
.config-table tbody tr.config-row.is-deactivated td {
  color: var(--inactive-text);
}
.expand-col {
  width: 3rem;
  text-align: center;
}
thead th.expand-col {
  padding-left: 0.5rem;
  padding-right: 0.5rem;
}
tbody td.expand-col .chevron-disc {
  margin: 0 auto;
  padding: 0;
}
/* width:1% + nowrap makes the column exactly as wide as its widest set of
   buttons, so the actions sit flush right and line up down the whole table
   instead of drifting with the other columns. */
.actions-col {
  width: 1%;
  text-align: right;
  white-space: nowrap;
}
.actions-col .btn + .btn {
  margin-left: 0.4rem;
}
.mono-cell {
  font-variant-numeric: tabular-nums;
}
.ratio {
  font-weight: 650;
  color: var(--accent-strong);
  font-variant-numeric: tabular-nums;
}
.is-deactivated .ratio {
  color: var(--inactive-text);
}
.ratio-raw {
  margin-left: 0.4rem;
  color: var(--muted);
  font-size: 0.8rem;
  font-variant-numeric: tabular-nums;
}
.tag-off {
  display: inline-block;
  margin-left: 0.45rem;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  background: #eceff0;
  color: #6b7c78;
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

/* the dropdown under an open row, tinted like the other expansion panels */
tbody tr.detail-row:hover td {
  background: transparent;
}
.detail-cell {
  padding: 1rem 1.25rem 1.15rem;
  background: #f8faf9;
  border-top: 1px solid rgba(61, 139, 109, 0.22);
}
.detail-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 0.7rem;
  margin: 0;
  animation: slideDown 0.22s ease;
}
.detail-facts > div {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 0.6rem;
  padding: 0.55rem 0.75rem;
}
.detail-facts dt {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
  margin-bottom: 0.15rem;
}
.detail-facts dd {
  margin: 0;
  font-size: 0.9rem;
  color: var(--text);
  overflow-wrap: anywhere;
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
@media (prefers-reduced-motion: reduce) {
  .detail-facts {
    animation: none;
  }
}

/* change history: the row's logged previous versions */
.history {
  margin-top: 0.9rem;
  padding-top: 0.85rem;
  border-top: 1px dashed var(--border);
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  align-items: flex-start;
}
.history-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 0.7rem;
  width: 100%;
}
.history-item {
  background: #fff;
  border: 1px solid var(--border);
  border-left: 3px solid #cfe0d7;
  border-radius: 0.6rem;
  padding: 0.7rem 0.8rem;
}
.history-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 0.6rem;
}
.history-when {
  font-weight: 650;
  color: var(--text);
  font-size: 0.9rem;
}
.history .detail-facts {
  animation: none;
}

/* popups */
.modal code,
.modal-hint code {
  background: var(--surface-2);
  padding: 0.05rem 0.35rem;
  border-radius: 0.3rem;
  color: var(--accent-strong);
}
.modal-hint {
  margin: -0.4rem 0 1rem;
  font-size: 0.85rem;
  color: var(--muted);
  line-height: 1.45;
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
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.field .opt {
  font-weight: 400;
  color: var(--muted);
  font-style: normal;
}
.field .req {
  font-weight: 600;
  color: var(--accent);
  font-style: normal;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
button:focus-visible,
input:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}
@media (max-width: 640px) {
  .config-body,
  .detail-cell {
    padding: 0.85rem;
  }
  .shared-bar {
    padding: 0.85rem;
  }
}
</style>
