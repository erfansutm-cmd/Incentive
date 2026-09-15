<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { requestJson } from '../lib/api'
import OrderEditor from '../components/OrderEditor.vue'
import { clearStoredOrder, readStoredOrder, storeOrder } from '../lib/storedOrder'

const SCORE_TYPES = [
  { value: 'performance', label: 'Performance' },
  { value: 'order_level_increase', label: 'Order Level' },
  { value: 'weather', label: 'Weather' },
]

// Order the plans of a city are shown in, top first. Kept identical to the
// backend default so the table is right even if the API omits the order.
// "default" is not a plan type of this database, so it is not part of the order.
const DEFAULT_PLAN_TYPE_ORDER = ['DAILY', 'ON-TOP-FOOD']
// Order the cities are listed in, by their city group; the API sorts them the
// same way and sends the order back for the toolbar hint.
const DEFAULT_GROUP_ORDER = ['Tehran Group', 'Top 4', 'Tier 1', 'Tier 2', 'Tier 3']
// Both orders are remembered in the browser (see lib/storedOrder.js).
const ENTITY_ORDER_KEY = 'finalDecisions.entityOrder'
const PLAN_TYPE_ORDER_KEY = 'finalDecisions.planTypeOrder'

function tomorrowISO() {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  return d.toISOString().slice(0, 10)
}

function formatScore(v) {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  if (Number.isFinite(n)) {
    return Number.isInteger(n) ? String(n) : String(Number(n.toFixed(4))).replace(/\.?0+$/, (m) => m)
  }
  return String(v)
}

function scoreBadgeClass(v) {
  if (v === null || v === undefined || v === '') return 'muted'
  const n = Number(v)
  if (!Number.isFinite(n)) return 'muted'
  return ''
}

// Min/max per score type across all loaded entities, used to build a
// green (lowest) -> red (highest) color scale for each score badge.
function computeScoreRanges(cityList) {
  const ranges = {}
  for (const key of ['performance', 'order_level_increase', 'weather']) {
    let min = Infinity
    let max = -Infinity
    for (const c of cityList) {
      for (const be of c.business_entities || []) {
        const n = Number(be.scores?.[key])
        if (Number.isFinite(n)) {
          if (n < min) min = n
          if (n > max) max = n
        }
      }
    }
    ranges[key] = Number.isFinite(min) ? { min, max } : { min: 0, max: 0 }
  }
  return ranges
}

// Green (lowest) -> red (highest) for one value inside a min/max range. Used by
// both the score badges and the plan numbers (target / PR change).
function heatStyle(value, range) {
  const n = Number(value)
  if (value === null || value === undefined || value === '' || !Number.isFinite(n)) return {}
  const { min, max } = range || { min: 0, max: 0 }
  let t = max > min ? (n - min) / (max - min) : 0
  t = Math.max(0, Math.min(1, t))
  const hue = 142 - t * 142
  return {
    backgroundColor: `hsl(${hue}, 62%, 93%)`,
    borderColor: `hsl(${hue}, 42%, 76%)`,
    color: `hsl(${hue}, 55%, 30%)`,
  }
}

function scoreStyle(v, key, ranges) {
  return heatStyle(v, ranges?.[key])
}

const stampFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })

function formatStamp(value) {
  if (!value) return '—'
  const raw = String(value)
  // MySQL hands out "2026-09-15 13:17:22"; make it parseable in every browser.
  const date = new Date(raw.includes('T') ? raw : raw.replace(' ', 'T'))
  return Number.isNaN(date.getTime()) ? raw : stampFormat.format(date)
}

// target_change / pr_change are ratios stored with three decimals (1.000, 1.100).
function formatChange(value) {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return String(value)
  return number.toFixed(3)
}

function formatBucketValue(value) {
  if (value === null || value === undefined) return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return String(value)
  return Number.isInteger(number) ? String(number) : String(Number(number.toFixed(4)))
}

const selectedDate = ref(tomorrowISO())
const searchQuery = ref('')
const groupFilter = ref('')
const loading = ref(false)
const error = ref('')
const cities = ref([])
const scoreTypes = ref(SCORE_TYPES.map((s) => s.value))
const generatedAt = ref('')
const incentiveDate = ref('')
const plansError = ref('')
const groupOrder = ref([...DEFAULT_GROUP_ORDER])
const plansWithoutScores = ref(0)
const plansWithoutScoresCities = ref([])

const expanded = ref(new Set())
const sortKey = ref(null)
const sortDir = ref('asc')
const showPriorityEditor = ref(false)
const DEFAULT_PRIORITY = ['foodZooket', 'food', 'Zooket']
const storedPriorityOrder = readStoredOrder(ENTITY_ORDER_KEY, [])
const priorityOrder = ref(storedPriorityOrder.length ? storedPriorityOrder : [...DEFAULT_PRIORITY])
// A stored order is the user's, so loading data must not overwrite the keys.
const priorityOrderTouched = ref(storedPriorityOrder.length > 0)

// Plan (incentive) type order, top first, and the name lookup used as a
// fallback when a plan arrives without its resolved type name.
const showTypeOrderEditor = ref(false)
const storedPlanTypeOrder = readStoredOrder(PLAN_TYPE_ORDER_KEY, [])
const defaultPlanTypeOrder = ref([...DEFAULT_PLAN_TYPE_ORDER])
const planTypeOrder = ref(
  storedPlanTypeOrder.length ? storedPlanTypeOrder : [...DEFAULT_PLAN_TYPE_ORDER],
)
// A stored order is the user's, so the API order must not overwrite it.
const planTypeOrderTouched = ref(storedPlanTypeOrder.length > 0)
const typeNamesById = ref({})
const typeNamesLoaded = ref(false)

const message = ref(null)
let messageTimer = null
let controller = null
let disposed = false

// The API lists cities by group priority, so first appearance is that order.
const groupOptions = computed(() => {
  const seen = new Set()
  for (const c of cities.value) {
    const g = c.city_group
    if (g !== null && g !== undefined && String(g).trim() !== '') seen.add(String(g))
  }
  return [...seen]
})

const filteredCities = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  return cities.value.filter((c) => {
    if (groupFilter.value && String(c.city_group ?? '') !== groupFilter.value) return false
    if (!q) return true
    const hay = [c.city, c.box_city_name].filter(Boolean).join(' ').toLowerCase()
    return hay.includes(q)
  })
})

const sortedCities = computed(() => {
  if (!sortKey.value) return filteredCities.value
  const key = sortKey.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  // touch priorityOrder so sort re-evaluates when priority changes
  const _po = priorityOrder.value.slice()
  return [...filteredCities.value].sort((a, b) => {
    const av = (prioritySortedEntities(a)[0] || a.primary_entity)?.scores?.[key]
    const bv = (prioritySortedEntities(b)[0] || b.primary_entity)?.scores?.[key]
    const aNull = av === null || av === undefined || av === ''
    const bNull = bv === null || bv === undefined || bv === ''
    if (aNull && bNull) return 0
    if (aNull) return 1
    if (bNull) return -1
    const an = Number(av)
    const bn = Number(bv)
    if (!Number.isFinite(an) && !Number.isFinite(bn)) return 0
    if (!Number.isFinite(an)) return 1
    if (!Number.isFinite(bn)) return -1
    // Equal scores keep the API (group) order — the sort is stable.
    if (an === bn) return 0
    return (an - bn) * dir
  })
})

const totalCities = computed(() => cities.value.length)
const totalEntities = computed(() => cities.value.reduce((sum, c) => sum + (c.entity_count || 0), 0))
const totalPlans = computed(() => cities.value.reduce((sum, c) => sum + cityPlans(c).length, 0))
const visibleCount = computed(() => filteredCities.value.length)
const scoreRanges = computed(() => computeScoreRanges(cities.value))

const allExpanded = computed(
  () => sortedCities.value.length > 0 && sortedCities.value.every((c) => expanded.value.has(String(c.city_id_raw ?? c.city_id)))
)

function toggleSort(key) {
  if (sortKey.value !== key) {
    sortKey.value = key
    sortDir.value = 'asc'
  } else if (sortDir.value === 'asc') {
    sortDir.value = 'desc'
  } else {
    sortKey.value = null
  }
}
function clearSort() {
  sortKey.value = null
}
function sortLabel(key) {
  if (sortKey.value !== key) return ''
  return sortDir.value === 'asc' ? '▲' : '▼'
}
function priorityRank(name) {
  const idx = priorityOrder.value.indexOf(name)
  if (idx !== -1) return idx
  return priorityOrder.value.length + 100
}
function prioritySortedEntities(city) {
  const list = city.business_entities || []
  return [...list].sort((a, b) => {
    const ra = priorityRank(a.business_entity)
    const rb = priorityRank(b.business_entity)
    if (ra !== rb) return ra - rb
    return String(a.business_entity).localeCompare(String(b.business_entity))
  })
}
function displayPrimary(city) {
  const sorted = prioritySortedEntities(city)
  return sorted[0] || city.primary_entity || null
}
function sortedEntities(city) {
  return prioritySortedEntities(city)
}
function setPriorityOrder(next) {
  priorityOrderTouched.value = true
  priorityOrder.value = [...next]
  ensurePriorityCoversAll()
  storeOrder(ENTITY_ORDER_KEY, priorityOrder.value)
}
function resetPriority() {
  priorityOrderTouched.value = false
  priorityOrder.value = [...DEFAULT_PRIORITY]
  clearStoredOrder(ENTITY_ORDER_KEY)
  ensurePriorityCoversAll()
}
function ensurePriorityCoversAll() {
  const seen = new Set(priorityOrder.value)
  const all = new Set()
  for (const c of cities.value) {
    for (const be of c.business_entities || []) all.add(be.business_entity)
  }
  let added = false
  for (const name of [...all].sort((a, b) => a.localeCompare(b))) {
    if (!seen.has(name)) {
      priorityOrder.value = [...priorityOrder.value, name]
      seen.add(name)
      added = true
    }
  }
  if (added && priorityOrderTouched.value) storeOrder(ENTITY_ORDER_KEY, priorityOrder.value)
}
const allKnownEntities = computed(() => {
  const set = new Set(priorityOrder.value)
  for (const c of cities.value) for (const be of c.business_entities || []) set.add(be.business_entity)
  return [...set]
})
// Known entities that are not part of the order yet (shown in the popup footer).
const unlistedEntities = computed(() =>
  allKnownEntities.value
    .filter((name) => !priorityOrder.value.includes(name))
    .sort((a, b) => a.localeCompare(b))
)

// --- plans of a city ---------------------------------------------------------
// Every plan carries the city, incentive type and business entity of its
// mapping row. The type name is resolved by the API through
// `mafsho.incentive_type` (same lookup the Cities tab uses); /api/incentive-types
// is only a fallback for plans that arrive without a name.
function planTypeName(plan) {
  if (!plan) return ''
  const direct = plan.incentive_type
  if (direct !== null && direct !== undefined && String(direct).trim() !== '') return String(direct).trim()
  const id = plan.incentive_type_id
  if (id === null || id === undefined || id === '') return ''
  return typeNamesById.value[String(id)] || ''
}
function planTypeLabel(plan) {
  if (!plan) return '—'
  const name = planTypeName(plan)
  if (name) return name
  const id = plan?.incentive_type_id
  return id === null || id === undefined || id === '' ? 'Unknown type' : `Type #${id}`
}
const knownPlanTypes = computed(() => {
  const set = new Set()
  for (const c of cities.value) {
    for (const plan of cityPlans(c)) {
      const name = planTypeName(plan)
      if (name) set.add(name)
    }
  }
  return [...set]
})
const unlistedPlanTypes = computed(() => {
  const listed = new Set(planTypeOrder.value.map((name) => name.toLowerCase()))
  return knownPlanTypes.value
    .filter((name) => !listed.has(name.toLowerCase()))
    .sort((a, b) => a.localeCompare(b))
})
function planTypeRank(plan) {
  const name = (planTypeName(plan) || planTypeLabel(plan)).trim().toLowerCase()
  const index = planTypeOrder.value.findIndex((known) => known.trim().toLowerCase() === name)
  return index === -1 ? planTypeOrder.value.length + 100 : index
}
function ensurePlanTypesCovered() {
  const missing = unlistedPlanTypes.value
  if (!missing.length) return
  planTypeOrder.value = [...planTypeOrder.value, ...missing]
  if (planTypeOrderTouched.value) storeOrder(PLAN_TYPE_ORDER_KEY, planTypeOrder.value)
}
function setPlanTypeOrder(next) {
  planTypeOrderTouched.value = true
  planTypeOrder.value = [...next]
  ensurePlanTypesCovered()
  storeOrder(PLAN_TYPE_ORDER_KEY, planTypeOrder.value)
}
function resetPlanTypeOrder() {
  planTypeOrderTouched.value = false
  planTypeOrder.value = [...defaultPlanTypeOrder.value]
  clearStoredOrder(PLAN_TYPE_ORDER_KEY)
  ensurePlanTypesCovered()
}
function cityPlans(city) {
  return Array.isArray(city?.plans) ? city.plans : []
}
// One table column per plan type, in the plan-type order the user chose. Only
// types that actually have plans get a column, so the table stays as narrow as
// the data. Types missing from the order are appended (order covers them anyway).
const planColumns = computed(() => {
  const present = new Map()
  for (const city of cities.value) {
    for (const plan of cityPlans(city)) {
      const label = planTypeLabel(plan)
      const key = label.trim().toLowerCase()
      if (!present.has(key)) present.set(key, label)
    }
  }
  const columns = []
  const used = new Set()
  for (const name of planTypeOrder.value) {
    const key = String(name).trim().toLowerCase()
    if (present.has(key) && !used.has(key)) {
      used.add(key)
      columns.push({ key, label: present.get(key) })
    }
  }
  for (const [key, label] of present) {
    if (!used.has(key)) columns.push({ key, label })
  }
  return columns
})
// Without plans at all the table keeps a single "Plans" column for the status pill.
const planColumnsOrPill = computed(() =>
  planColumns.value.length ? planColumns.value : [{ key: '__plans__', label: 'Plans' }]
)
const planColumnCount = computed(() => planColumnsOrPill.value.length)
// Plans of a city: plan type first (the configured order), then the entity order
// — two plans of the same type belong to different entities, and the first one
// is the top plan of that column.
function sortedPlans(city) {
  return [...cityPlans(city)].sort((a, b) => {
    const rankA = planTypeRank(a)
    const rankB = planTypeRank(b)
    if (rankA !== rankB) return rankA - rankB
    // unlisted plan types come last alphabetically among themselves
    const typeA = planTypeLabel(a).trim().toLowerCase()
    const typeB = planTypeLabel(b).trim().toLowerCase()
    if (typeA !== typeB) return typeA < typeB ? -1 : 1
    const entityA = priorityRank(a.business_entity ?? '')
    const entityB = priorityRank(b.business_entity ?? '')
    if (entityA !== entityB) return entityA - entityB
    const nameA = String(a.business_entity ?? '').toLowerCase()
    const nameB = String(b.business_entity ?? '').toLowerCase()
    if (nameA !== nameB) return nameA < nameB ? -1 : 1
    return Number(a.id ?? 0) - Number(b.id ?? 0)
  })
}
function topPlan(city) {
  return sortedPlans(city)[0] || null
}
function plansOfType(city, key) {
  return sortedPlans(city).filter((plan) => planTypeLabel(plan).trim().toLowerCase() === key)
}
function isTopPlan(city, plan) {
  const top = topPlan(city)
  return Boolean(top) && String(top.id) === String(plan.id)
}
// Min/max of target and PR change across every plan of the date, so the numbers
// can carry the same green -> red scale as the scores (more number, more red).
const planHeatRanges = computed(() => {
  const range = { target: null, pr: null }
  for (const metric of ['target', 'pr']) {
    let min = Infinity
    let max = -Infinity
    for (const city of cities.value) {
      for (const plan of cityPlans(city)) {
        const n = Number(metric === 'target' ? plan.target_change : plan.pr_change)
        if (Number.isFinite(n)) {
          if (n < min) min = n
          if (n > max) max = n
        }
      }
    }
    range[metric] = Number.isFinite(min) ? { min, max } : null
  }
  return range
})
function planNumberStyle(plan, metric) {
  const value = metric === 'target' ? plan?.target_change : plan?.pr_change
  return heatStyle(value, planHeatRanges.value[metric])
}
function planBuckets(plan) {
  return Array.isArray(plan?.control_bucket) ? plan.control_bucket : []
}
function planBucketText(plan) {
  const buckets = planBuckets(plan)
  if (buckets.length) return buckets.map((value) => formatBucketValue(value)).join(' · ')
  if (plan?.control_bucket === null || plan?.control_bucket === undefined) return '—'
  return String(plan.control_bucket)
}

function cityKey(c) {
  return String(c.city_id_raw ?? c.city_id)
}
function isExpanded(c) {
  return expanded.value.has(cityKey(c))
}
function toggleCity(c) {
  const k = cityKey(c)
  if (expanded.value.has(k)) expanded.value.delete(k)
  else expanded.value.add(k)
  expanded.value = new Set(expanded.value)
}
function expandAll() {
  const next = new Set(expanded.value)
  for (const c of sortedCities.value) next.add(cityKey(c))
  expanded.value = next
}
function collapseAll() {
  const next = new Set(expanded.value)
  for (const c of sortedCities.value) next.delete(cityKey(c))
  expanded.value = next
}
function clearFilters() {
  searchQuery.value = ''
  groupFilter.value = ''
}

async function load() {
  if (disposed) return
  controller?.abort()
  const ctrl = new AbortController()
  controller = ctrl
  loading.value = true
  error.value = ''
  const date = selectedDate.value
  try {
    const data = await requestJson(`/api/final-decisions?incentive_date=${encodeURIComponent(date)}`, {
      signal: ctrl.signal,
    })
    if (ctrl.signal.aborted) return
    cities.value = data.cities || []
    scoreTypes.value = data.score_types || SCORE_TYPES.map((s) => s.value)
    incentiveDate.value = data.incentive_date || date
    generatedAt.value = data.generated_at || ''
    plansError.value = data.plans_error || ''
    plansWithoutScores.value = Number(data.plans_without_scores) || 0
    plansWithoutScoresCities.value = data.plans_without_scores_cities || []
    const apiGroupOrder = (data.group_order || []).map((name) => String(name).trim()).filter(Boolean)
    if (apiGroupOrder.length) groupOrder.value = apiGroupOrder
    const apiOrder = (data.plan_type_order || [])
      .map((name) => String(name).trim())
      .filter(Boolean)
    if (apiOrder.length) {
      defaultPlanTypeOrder.value = apiOrder
      // A user-made order survives a refresh; otherwise follow the API order.
      if (!planTypeOrderTouched.value) planTypeOrder.value = [...apiOrder]
    }
    const valid = new Set(cities.value.map((c) => String(c.city_id_raw ?? c.city_id)))
    const pruned = new Set([...expanded.value].filter((k) => valid.has(k)))
    expanded.value = pruned
    ensurePriorityCoversAll()
    ensurePlanTypesCovered()
  } catch (e) {
    if (!ctrl.signal.aborted) {
      error.value = e.message
      cities.value = []
      plansError.value = ''
      plansWithoutScores.value = 0
      plansWithoutScoresCities.value = []
    }
  } finally {
    if (!ctrl.signal.aborted) loading.value = false
  }
}

// Fallback name lookup for the incentive types (the plans endpoint resolves
// them itself, so a failure here only leaves "Type #<id>" captions).
async function loadTypeNames() {
  if (typeNamesLoaded.value) return
  try {
    const data = await requestJson('/api/incentive-types')
    const map = {}
    for (const row of data.rows || []) {
      if (row.id !== null && row.id !== undefined && row.name) map[String(row.id)] = String(row.name)
    }
    typeNamesById.value = map
    typeNamesLoaded.value = true
  } catch {
    // not fatal: the scores and plans still render with what they carry
  }
}

function onDateChange() {
  expanded.value = new Set()
  load()
}

onMounted(() => {
  load()
  loadTypeNames()
})
onBeforeUnmount(() => {
  disposed = true
  controller?.abort()
  clearTimeout(messageTimer)
})
</script>

<template>
  <div class="final-decisions">
    <div class="page-head">
      <div>
        <p class="eyebrow">Final Decisions</p>
        <h1>City Scores & Decisions</h1>
        <p class="head-sub">
          <template v-if="incentiveDate">Showing <strong>{{ incentiveDate }}</strong></template>
          <template v-else>Select an incentive date</template>
          <template v-if="cities.length">
            · {{ totalCities }} cities · {{ totalEntities }} business entities ·
            {{ totalPlans }} {{ totalPlans === 1 ? 'plan' : 'plans' }}
          </template>
          <span v-if="generatedAt" class="head-sub-extra"> · updated {{ new Date(generatedAt).toLocaleString() }}</span>
        </p>
      </div>
      <div class="head-actions">
        <label class="date-field">
          <span class="sr-only">Incentive date</span>
          <input type="date" v-model="selectedDate" class="select-field" @change="onDateChange" />
        </label>
        <button class="btn btn-ghost" :disabled="loading" @click="load">Refresh</button>
        <button
          v-if="sortedCities.length"
          class="btn btn-ghost"
          :disabled="loading"
          @click="allExpanded ? collapseAll() : expandAll()"
        >
          {{ allExpanded ? 'Collapse all' : 'Expand all' }}
        </button>
      </div>
    </div>

    <div class="card toolbar-card">
      <label class="search-field">
        <span class="sr-only">Search cities</span>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
          <circle cx="11" cy="11" r="6.5" />
          <path d="M16 16l4 4" />
        </svg>
        <input v-model="searchQuery" type="search" placeholder="Search by city or box city name…" />
      </label>

      <label class="sr-only" for="group-filter">City group</label>
      <select id="group-filter" v-model="groupFilter" class="select-field">
        <option value="">All groups</option>
        <option v-for="g in groupOptions" :key="g" :value="g">{{ g }}</option>
      </select>

      <button v-if="searchQuery || groupFilter" class="btn btn-ghost btn-sm" @click="clearFilters">Clear</button>

      <button class="btn btn-ghost btn-sm" @click="showPriorityEditor = true">
        Entity order
      </button>

      <button class="btn btn-ghost btn-sm" @click="showTypeOrderEditor = true">
        Plan type order
      </button>

      <span class="pill spacer">
        <template v-if="loading">Loading…</template>
        <template v-else>{{ visibleCount }} of {{ totalCities }} cities</template>
      </span>
      <button
        v-if="sortKey"
        class="btn btn-ghost btn-sm sort-clear"
        @click="clearSort"
        :title="`Remove city sort — back to the group order (${groupOrder.join(' → ')} → others)`"
      >
        ↺ Default order
      </button>
    </div>

    <OrderEditor
      v-if="showPriorityEditor"
      title="Entity order"
      hint="Default: foodZooket > food > Zooket > others"
      :items="priorityOrder"
      :extra="unlistedEntities"
      noun="business entity"
      noun-plural="business entities"
      top-note="The first entity of a city is the one shown in the collapsed row and used when sorting cities by score."
      @update:items="setPriorityOrder"
      @reset="resetPriority"
      @close="showPriorityEditor = false"
    />

    <OrderEditor
      v-if="showTypeOrderEditor"
      title="Plan type order"
      hint="Default: DAILY > ON-TOP-FOOD > others"
      :items="planTypeOrder"
      :extra="unlistedPlanTypes"
      noun="plan type"
      top-note="Plans of a city are listed in this order: the first plan of each city is shown in the collapsed row and carries the top badge."
      @update:items="setPlanTypeOrder"
      @reset="resetPlanTypeOrder"
      @close="showTypeOrderEditor = false"
    />

    <div v-if="!error && plansWithoutScores" class="banner notice" role="status">
      <strong>
        {{ plansWithoutScores }} {{ plansWithoutScores === 1 ? 'plan is' : 'plans are' }} not listed
      </strong>
      <p>
        {{ plansWithoutScores === 1 ? 'It belongs' : 'They belong' }} to a city without scores on
        {{ incentiveDate }}<template v-if="plansWithoutScoresCities.length">
          ({{ plansWithoutScoresCities.join(', ') }})</template>,
        so {{ plansWithoutScores === 1 ? 'it does' : 'they do' }} not appear below.
      </p>
    </div>

    <div v-if="error" class="banner error" role="alert">
      <strong>Could not load final decisions</strong>
      <p>{{ error }}</p>
      <button class="btn btn-ghost btn-sm" @click="load">Retry</button>
    </div>

    <div v-else-if="loading" class="card empty" role="status">
      <div class="empty-mark" aria-hidden="true"><span class="spinner" /></div>
      <h3>Loading scores for {{ selectedDate }}…</h3>
      <p>Fetching scores and city names.</p>
    </div>

    <template v-else-if="!cities.length">
      <div class="card empty final-empty">
        <div class="empty-illust" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="4" width="18" height="16" rx="2" ry="2" />
            <path d="M16 2v4M8 2v4M3 10h18" />
            <path d="M9 15l2 2 4-4" />
          </svg>
        </div>
        <h3>No scores for {{ selectedDate }}</h3>
        <p>There’s nothing to show for this incentive date. Pick another date to explore city scores.</p>
      </div>
    </template>

    <template v-else-if="!sortedCities.length">
      <div class="card empty">
        <h3>No cities match your search</h3>
        <p>{{ totalCities }} cities have scores for {{ selectedDate }}, but none match your filter.</p>
        <button class="btn btn-ghost btn-sm" @click="clearFilters">Clear filter</button>
      </div>
    </template>

    <template v-else>
      <section class="card combined-card" aria-label="Final decisions table">
        <div class="table-scroll">
          <table class="final-table">
            <colgroup>
              <col class="col-expand" />
              <col class="col-city" />
              <col class="col-entity" />
              <col class="col-score" />
              <col class="col-score" />
              <col class="col-score" />
              <col v-for="column in planColumnsOrPill" :key="column.key" class="col-plan" />
            </colgroup>
            <thead>
              <tr class="group-head-row">
                <th class="th-expand"></th>
                <th colspan="5" class="group-header scores-header scores-header-divider">
                  <span class="group-label">Scores</span>
                </th>
                <th :colspan="planColumnCount" class="group-header decisions-header decisions-header-divider">
                  <span class="group-label">Plans</span>
                </th>
              </tr>
              <tr>
                <th class="th-expand"><span class="sr-only">Expand</span></th>
                <th class="city-th">City</th>
                <th class="entity-th">Business Entity</th>
                <th class="score-th" :class="{ 'is-sorted': sortKey === 'performance' }">
                  <button class="sort-btn" @click="toggleSort('performance')">
                    Performance <span class="sort-arrow" :class="{ active: sortKey === 'performance' }">{{ sortLabel('performance') || '↕' }}</span>
                  </button>
                </th>
                <th class="score-th" :class="{ 'is-sorted': sortKey === 'order_level_increase' }">
                  <button class="sort-btn" @click="toggleSort('order_level_increase')">
                    Order Level <span class="sort-arrow" :class="{ active: sortKey === 'order_level_increase' }">{{ sortLabel('order_level_increase') || '↕' }}</span>
                  </button>
                </th>
                <th class="score-th score-th-divider" :class="{ 'is-sorted': sortKey === 'weather' }">
                  <button class="sort-btn" @click="toggleSort('weather')">
                    Weather <span class="sort-arrow" :class="{ active: sortKey === 'weather' }">{{ sortLabel('weather') || '↕' }}</span>
                  </button>
                </th>
                <th
                  v-for="(column, index) in planColumnsOrPill" :key="column.key"
                  class="plan-th" :class="{ 'decisions-header-divider': index === 0 }"
                >{{ column.label }}</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="city in sortedCities" :key="cityKey(city)">
                <tr class="city-row" :class="{ expanded: isExpanded(city) }" @click="toggleCity(city)">
                  <td class="expand-col">
                    <span class="chevron-disc" :class="{ open: isExpanded(city) }" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9.5 5.5l6.5 6.5-6.5 6.5" />
                      </svg>
                    </span>
                  </td>
                  <td class="city-cell">
                    <div class="city-name">{{ city.city }}</div>
                    <div v-if="city.box_city_name && city.box_city_name !== city.city" class="city-meta">
                      <span class="box-name">{{ city.box_city_name }}</span>
                    </div>
                  </td>
                  <td class="entity-cell">
                    <span v-if="displayPrimary(city)" class="entity-name">{{ displayPrimary(city).business_entity }}</span>
                    <span v-else class="muted">—</span>
                  </td>
                  <td class="score-cell">
                    <span v-if="displayPrimary(city)" class="score-badge" :class="scoreBadgeClass(displayPrimary(city).scores.performance)" :style="scoreStyle(displayPrimary(city).scores.performance, 'performance', scoreRanges)">
                      {{ formatScore(displayPrimary(city).scores.performance) }}
                    </span>
                    <span v-else class="muted">—</span>
                  </td>
                  <td class="score-cell">
                    <span v-if="displayPrimary(city)" class="score-badge" :class="scoreBadgeClass(displayPrimary(city).scores.order_level_increase)" :style="scoreStyle(displayPrimary(city).scores.order_level_increase, 'order_level_increase', scoreRanges)">
                      {{ formatScore(displayPrimary(city).scores.order_level_increase) }}
                    </span>
                    <span v-else class="muted">—</span>
                  </td>
                  <td class="score-cell score-cell-divider">
                    <span v-if="displayPrimary(city)" class="score-badge" :class="scoreBadgeClass(displayPrimary(city).scores.weather)" :style="scoreStyle(displayPrimary(city).scores.weather, 'weather', scoreRanges)">
                      {{ formatScore(displayPrimary(city).scores.weather) }}
                    </span>
                    <span v-else class="muted">—</span>
                  </td>
                  <template v-if="!planColumns.length">
                    <td class="plan-cell plans-none decisions-cell-divider">
                      <span class="decisions-placeholder">
                        <span class="pill plain decisions-pill" :class="{ 'is-expanded': isExpanded(city) }">
                          <span class="dot" aria-hidden="true" />
                          {{ plansError ? 'Plans unavailable' : 'No plans' }}
                        </span>
                      </span>
                    </td>
                  </template>
                  <template v-else-if="!cityPlans(city).length">
                    <td :colspan="planColumns.length" class="plan-cell plans-none decisions-cell-divider">
                      <span class="decisions-placeholder">
                        <span class="pill plain decisions-pill" :class="{ 'is-expanded': isExpanded(city) }">
                          <span class="dot" aria-hidden="true" />
                          {{ plansError ? 'Plans unavailable' : 'No plans' }}
                        </span>
                      </span>
                    </td>
                  </template>
                  <template v-else>
                    <td
                      v-for="(column, index) in planColumns" :key="column.key"
                      class="plan-cell" :class="{ 'decisions-cell-divider': index === 0 }"
                    >
                      <template v-if="plansOfType(city, column.key).length">
                        <div
                          v-for="plan in plansOfType(city, column.key)" :key="plan.id"
                          class="plan-row" :class="{ 'is-top': isTopPlan(city, plan) }"
                          :title="`${planTypeLabel(plan)} · ${plan.business_entity || '—'} · updated ${formatStamp(plan.updated_at)}${plan.updated_by ? ` · ${plan.updated_by}` : ''}`"
                        >
                          <span class="plan-entity">{{ plan.business_entity || '—' }}</span>
                          <span v-if="isTopPlan(city, plan)" class="plan-flag top-flag" title="Top plan of this city">top</span>
                          <span
                            v-if="!plan.mapping_active" class="plan-flag off-flag"
                            title="The plan mapping of this plan is deactivated"
                          >off</span>
                          <span
                            class="plan-number" title="Target change"
                            :style="planNumberStyle(plan, 'target')"
                          >{{ formatChange(plan.target_change) }}</span>
                          <span
                            class="plan-number" title="PR change"
                            :style="planNumberStyle(plan, 'pr')"
                          >{{ formatChange(plan.pr_change) }}</span>
                          <span class="plan-bucket" :title="`Control bucket: ${planBucketText(plan)}`">
                            {{ planBucketText(plan) }}
                          </span>
                          <a
                            v-if="plan.plan_mapping_id !== null && plan.plan_mapping_id !== undefined"
                            :href="`/plans/${plan.plan_mapping_id}`"
                            target="_blank"
                            rel="noopener"
                            class="plan-link"
                            @click.stop
                          >Details</a>
                        </div>
                      </template>
                      <span v-else class="muted">—</span>
                    </td>
                  </template>
                </tr>

                <tr v-if="isExpanded(city)" class="detail-row">
                  <td :colspan="6 + planColumnCount" class="detail-cell" @click.stop>
                    <div class="integrated-panel">
                      <div class="panel-block scores-block">
                        <div class="mini-table-wrap">
                          <table class="mini-table">
                            <colgroup>
                              <col style="width: 46%" />
                              <col style="width: 20%" />
                              <col style="width: 20%" />
                              <col style="width: 14%" />
                            </colgroup>
                            <thead>
                              <tr>
                                <th>Business Entity</th>
                                <th class="num">Perf.</th>
                                <th class="num">Order</th>
                                <th class="num">Weather</th>
                              </tr>
                            </thead>
                            <tbody>
                              <tr v-for="be in sortedEntities(city)" :key="be.business_entity">
                                <td class="mini-entity">
                                  <span class="entity-name">{{ be.business_entity }}</span>
                                </td>
                                <td class="num">
                                  <span class="score-badge small" :class="scoreBadgeClass(be.scores.performance)" :style="scoreStyle(be.scores.performance, 'performance', scoreRanges)">{{ formatScore(be.scores.performance) }}</span>
                                </td>
                                <td class="num">
                                  <span class="score-badge small" :class="scoreBadgeClass(be.scores.order_level_increase)" :style="scoreStyle(be.scores.order_level_increase, 'order_level_increase', scoreRanges)">{{ formatScore(be.scores.order_level_increase) }}</span>
                                </td>
                                <td class="num">
                                  <span class="score-badge small" :class="scoreBadgeClass(be.scores.weather)" :style="scoreStyle(be.scores.weather, 'weather', scoreRanges)">{{ formatScore(be.scores.weather) }}</span>
                                </td>
                              </tr>
                            </tbody>
                          </table>
                        </div>
                      </div>

                      <div class="panel-block decisions-block">
                        <div class="panel-block-head">
                          <h4>
                            <span class="icon-tile sm neutral" aria-hidden="true">
                              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M12 3.6l8.4 4.2-8.4 4.2-8.4-4.2z" />
                                <path d="M4.4 12.4L12 16.2l7.6-3.8" />
                                <path d="M4.4 16.6L12 20.4l7.6-3.8" />
                              </svg>
                            </span>
                            Plans
                            <span class="pill plain">
                              {{ cityPlans(city).length }}
                              {{ cityPlans(city).length === 1 ? 'plan' : 'plans' }}
                            </span>
                          </h4>
                          <p class="hint">
                            Ordered by plan type (top first) for {{ incentiveDate }}
                            <template v-if="cityPlans(city).length > 1">
                              · <button class="link-btn" @click="showTypeOrderEditor = true">change order</button>
                            </template>
                          </p>
                        </div>

                        <div v-if="plansError" class="plan-warning" role="status">
                          <span>
                            Plans could not be loaded — {{ plansError }}
                          </span>
                          <button class="btn btn-ghost btn-sm" :disabled="loading" @click="load">Retry</button>
                        </div>

                        <div v-else-if="!cityPlans(city).length" class="decisions-empty">
                          <p class="hint decisions-hint">
                            No plans for {{ city.city }} on {{ incentiveDate }}. Plans are added per city in the
                            Cities tab (<em>Add plan</em>) and land here on their incentive date.
                          </p>
                        </div>

                        <div v-else class="plan-cards">
                          <article
                            v-for="(plan, pi) in sortedPlans(city)"
                            :key="plan.id"
                            class="plan-card"
                            :class="{ 'is-top': pi === 0, 'is-mapping-off': !plan.mapping_active }"
                          >
                            <header class="plan-card-head">
                              <span class="plan-rank" aria-hidden="true">{{ pi + 1 }}</span>
                              <span class="plan-card-title">{{ planTypeLabel(plan) }}</span>
                              <span v-if="plan.incentive_type_id !== null && plan.incentive_type_id !== undefined" class="type-id">
                                #{{ plan.incentive_type_id }}
                              </span>
                              <span v-if="pi === 0" class="pill tiny accent">top</span>
                            </header>

                            <div class="plan-card-entity">{{ plan.business_entity || '—' }}</div>

                            <dl class="plan-metrics">
                              <div>
                                <dt>Target change</dt>
                                <dd>{{ formatChange(plan.target_change) }}</dd>
                              </div>
                              <div>
                                <dt>PR change</dt>
                                <dd>{{ formatChange(plan.pr_change) }}</dd>
                              </div>
                              <div class="plan-metric-wide">
                                <dt>Control bucket</dt>
                                <dd>
                                  <span v-if="planBuckets(plan).length" class="bucket-values">
                                    <span v-for="(value, bi) in planBuckets(plan)" :key="bi" class="bucket-chip">
                                      <span class="bucket-value">{{ formatBucketValue(value) }}</span>
                                    </span>
                                  </span>
                                  <span v-else class="muted">{{ planBucketText(plan) }}</span>
                                </dd>
                              </div>
                            </dl>

                            <footer class="plan-card-foot">
                              <span class="plan-updated">
                                Updated {{ formatStamp(plan.updated_at) }}
                                <template v-if="plan.updated_by"> · {{ plan.updated_by }}</template>
                              </span>
                              <span v-if="!plan.mapping_active" class="pill tiny plain" title="The plan mapping of this plan is deactivated">
                                mapping off
                              </span>
                              <a
                                v-if="plan.plan_mapping_id !== null && plan.plan_mapping_id !== undefined"
                                :href="`/plans/${plan.plan_mapping_id}`"
                                target="_blank"
                                rel="noopener"
                                class="btn btn-ghost btn-sm"
                                @click.stop
                              >Details</a>
                            </footer>
                          </article>
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </section>
    </template>

    <div v-if="message" class="toast ok" role="status">{{ message }}</div>
  </div>
</template>

<style scoped>
.final-decisions {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 1rem;
}
.page-head h1 {
  margin: 0;
  font-size: 1.5rem;
}
.head-sub {
  margin: 0.35rem 0 0;
  font-size: 0.83rem;
  line-height: 1.5;
  color: var(--muted);
}
.head-sub strong {
  color: var(--text);
}
.head-sub-extra {
  opacity: 0.8;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.date-field input[type='date'] {
  min-width: 160px;
}
.empty {
  padding: 3.5rem 1.2rem;
  text-align: center;
  color: var(--muted);
}
.empty h3 {
  color: var(--text);
  margin: 0.8rem 0 0.4rem;
}
.empty p {
  margin: 0.45rem 0 1rem;
  font-size: 0.9rem;
  line-height: 1.6;
}
.empty-mark {
  display: inline-grid;
  place-items: center;
  width: 3rem;
  height: 3rem;
  background: var(--accent-soft);
  border-radius: 0.9rem;
  color: var(--accent);
  font-size: 1.7rem;
}
.empty-illust {
  display: inline-grid;
  place-items: center;
  width: 3.2rem;
  height: 3.2rem;
  background: var(--accent-soft);
  border-radius: 0.9rem;
  color: var(--accent);
}
.empty-illust svg {
  display: block;
}
.final-empty {
  border: 1px dashed var(--border);
  background: #fbfdfc;
}
.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation: none;
  }
}

/* Combined two-part table */
.combined-card {
  overflow: hidden;
  padding: 0;
}
.table-scroll {
  width: 100%;
  overflow-x: auto;
}
.final-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  min-width: 900px;
  table-layout: fixed;
}
.col-expand {
  width: 40px;
}
.col-city {
  width: 92px;
}
.col-entity {
  width: 128px;
}
.col-score {
  width: 82px;
}
.col-plan {
  width: 210px;
}
.final-table thead th {
  text-align: left;
  padding: 0.72rem 0.9rem;
  background: var(--surface-2);
  color: #4a6155;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  white-space: nowrap;
  border-bottom: 1px solid var(--border);
}
.final-table thead .group-head-row th {
  padding: 0.75rem 0.9rem;
  font-size: 0.86rem;
  letter-spacing: 0.05em;
}
.group-header {
  font-weight: 800;
  text-align: center;
}
.group-header .group-label {
  display: block;
  text-align: center;
  width: 100%;
}
.scores-header {
  background: var(--accent-strong);
  color: #fff;
}
.scores-header-divider {
  border-right: 2px solid #cfe0d7;
}
.decisions-header {
  background: #4a5b54;
  color: #fff;
}
.decisions-header-divider {
  border-left: 2px solid #cfe0d7;
}
.score-th-divider {
  border-right: 2px solid #cfe0d7;
}
.score-cell-divider {
  border-right: 2px solid #e3ece7;
}
.decisions-cell-divider {
  border-left: 2px solid #e3ece7;
}
.final-table thead tr:not(.group-head-row) th {
  padding-top: 0.65rem;
  padding-bottom: 0.65rem;
}
.th-expand {
  width: 3rem;
  text-align: center;
}
.city-th,
.entity-th {
  text-align: center !important;
}
.score-th {
  text-align: center;
  padding: 0 !important;
  white-space: normal;
}
.score-th .sort-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.3rem;
  padding: 0.65rem 0.4rem;
  border: 0;
  background: transparent;
  font: inherit;
  color: inherit;
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  font-weight: 700;
  font-size: 0.66rem;
  text-align: center;
  line-height: 1.25;
  border-radius: 0.4rem;
  transition: background 0.15s ease, color 0.15s ease;
}
.score-th .sort-btn:hover {
  background: rgba(61, 139, 109, 0.1);
  color: var(--accent-strong);
}
.score-th.is-sorted .sort-btn {
  color: var(--accent-strong);
  background: rgba(61, 139, 109, 0.08);
}
.sort-arrow {
  font-size: 0.68rem;
  line-height: 1;
  opacity: 0.35;
  min-width: 0.7em;
}
.sort-arrow.active {
  opacity: 1;
  color: var(--accent-strong);
}
.select-sm {
  padding: 0.38rem 0.6rem;
  font-size: 0.82rem;
  min-width: 148px;
}
.sort-clear {
  white-space: nowrap;
}
.toolbar-card {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.mini-table thead th.num {
  text-align: center;
}
.plan-th {
  text-align: center;
  color: var(--accent-strong);
  background: var(--accent-soft) !important;
  border-bottom: 1px solid var(--border);
}

.final-table tbody td {
  padding: 0.78rem 0.9rem;
  border-top: 1px solid var(--border);
  font-size: 0.9rem;
  vertical-align: middle;
}
.final-table tbody tr.city-row {
  cursor: pointer;
  transition: background 0.15s ease;
}
.final-table tbody tr.city-row:hover {
  background: #f6faf8;
}
.final-table tbody tr.city-row.expanded {
  background: var(--accent-soft);
}
.final-table tbody tr.city-row.expanded:hover {
  background: #dceee4;
}
.final-table tbody tr.city-row.expanded td {
  border-top: 2px solid var(--accent);
  border-bottom: 0;
}
.final-table tbody tr.city-row.expanded td:first-child {
  border-left: 2px solid var(--accent);
  border-top-left-radius: 0.85rem;
  box-shadow: none;
}
.final-table tbody tr.city-row.expanded td:last-child {
  border-right: 2px solid var(--accent);
  border-top-right-radius: 0.85rem;
}
/* Remove top border of the next city after an expanded group so the accent border is the separator */
.detail-row + .city-row:not(.expanded) td {
  border-top: 0;
}

.expand-col {
  width: 3rem;
  text-align: center;
}
.expand-col .chevron-disc {
  margin: 0 auto;
}

.city-cell {
  min-width: 170px;
  text-align: center;
}
.city-name {
  font-weight: 700;
  color: var(--text);
  line-height: 1.2;
}
.city-meta {
  display: flex;
  gap: 0.45rem;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  margin-top: 0.2rem;
}
.box-name {
  font-size: 0.78rem;
  color: var(--muted);
}

.entity-cell {
  white-space: nowrap;
  text-align: center;
}
.entity-name {
  font-weight: 600;
  color: var(--text);
}
.tiny {
  font-size: 0.66rem;
  padding: 0.14rem 0.42rem;
  margin-left: 0.4rem;
}
.score-cell {
  text-align: center;
  white-space: nowrap;
  vertical-align: middle;
}
.plan-cell {
  text-align: center;
  padding: 0.6rem 0.7rem !important;
  vertical-align: top;
}
.plan-cell.plans-none {
  padding: 0.9rem 0.9rem !important;
}
.banner.notice {
  background: #fdf7ec;
  border: 1px solid #f0d9b5;
  color: #8a5a1a;
  margin-bottom: 0;
}
.banner.notice p {
  margin: 0.25rem 0 0;
}

/* --- plans: one column per plan type, one plain row per plan -------------- */
.plan-row {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.28rem 0.4rem;
  padding: 0.12rem 0;
  min-width: 0;
}
.plan-row + .plan-row {
  margin-top: 0.18rem;
  padding-top: 0.32rem;
  border-top: 1px dashed #e3ece7;
}
.plan-entity {
  font-size: 0.79rem;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 9rem;
}
.plan-row.is-top .plan-entity {
  font-weight: 800;
}
.plan-flag {
  font-size: 0.56rem;
  font-weight: 800;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  padding: 0.06rem 0.3rem;
  border-radius: 0.3rem;
}
.plan-flag.top-flag {
  background: var(--accent);
  color: #fff;
}
.plan-flag.off-flag {
  background: var(--surface-2);
  color: var(--inactive-text);
}
.plan-number {
  display: inline-grid;
  place-items: center;
  min-width: 2.7rem;
  padding: 0.1rem 0.35rem;
  border: 1px solid var(--border);
  border-radius: 0.35rem;
  background: #fbfdfc;
  font-size: 0.75rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text);
}
.plan-bucket {
  font-size: 0.72rem;
  font-variant-numeric: tabular-nums;
  color: var(--muted);
}
.plan-link {
  margin-left: auto;
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--accent-strong);
  text-decoration: underline;
}
.link-btn {
  border: 0;
  background: none;
  padding: 0;
  color: var(--accent-strong);
  font: inherit;
  text-decoration: underline;
  cursor: pointer;
}

.decisions-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
}
.score-badge {
  display: grid;
  place-items: center;
  min-width: 1.65rem;
  padding: 0.14rem 0.32rem;
  border-radius: 0.45rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  font-size: 0.78rem;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--text);
  margin: 0 auto;
  width: fit-content;
  line-height: 1.1;
}
.score-badge.small {
  min-width: 1.55rem;
  padding: 0.12rem 0.28rem;
  font-size: 0.73rem;
}
.score-badge.muted {
  background: #fbfdfc;
  color: var(--muted);
}
.score-badge.very-low {
  background: #f7e8e8;
  color: #8c3030;
  border-color: #f0caca;
}
.score-badge.low {
  background: #fdf1e6;
  color: #8a5a1a;
  border-color: #f3ddba;
}
.score-badge.med {
  background: #eef3f0;
  color: var(--accent-strong);
}
.score-badge.high {
  background: var(--accent-soft);
  color: var(--accent-strong);
  border-color: #cfe0d7;
}
.decisions-pill {
  gap: 0.4rem;
  padding: 0.3rem 0.85rem;
  border: 1px dashed #d9e2de;
  background: #fbfdfc;
  color: var(--muted);
  font-weight: 600;
}
.decisions-pill .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--muted);
  display: inline-block;
}
.decisions-pill.is-expanded {
  border-style: solid;
  border-color: #cfe0d7;
  background: var(--accent-soft);
  color: var(--accent-strong);
}
.decisions-pill.is-expanded .dot {
  background: var(--accent-strong);
}
.muted {
  color: var(--muted);
}

/* Expanded integrated panel — outer border from top of city row to bottom of detail */
.detail-row:hover {
  background: transparent;
}
.detail-cell {
  padding: 0 !important;
  background: #f2f7f4;
  border-top: 0;
  border-left: 2px solid var(--accent);
  border-right: 2px solid var(--accent);
  border-bottom: 2px solid var(--accent);
  border-bottom-left-radius: 0.85rem;
  border-bottom-right-radius: 0.85rem;
  box-shadow: 0 4px 14px rgba(20, 40, 30, 0.06);
}
.integrated-panel {
  display: grid;
  grid-template-columns: 40fr 60fr;
  gap: 1.15rem;
  margin: 0;
  padding: 1rem 1.1rem 1.15rem;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  animation: slideDown 0.22s ease;
}
@media (prefers-reduced-motion: reduce) {
  .integrated-panel {
    animation: none;
  }
}
@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
.panel-block {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 0.8rem;
  padding: 1rem 1.1rem 1.1rem;
  box-shadow: 0 1px 2px rgba(20, 40, 30, 0.04), 0 8px 24px rgba(20, 40, 30, 0.05);
}
.panel-block.scores-block {
  padding: 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.panel-block-head h4 {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 0.55rem;
  font-size: 0.95rem;
}
.panel-block-head .hint {
  margin: 0.35rem 0 0.85rem;
  font-size: 0.8rem;
  color: var(--muted);
}
.scores-caption {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.78rem;
  color: var(--muted);
}
.scores-caption .caption-label {
  font-weight: 700;
  color: var(--text);
  font-size: 0.84rem;
}
.scores-caption .caption-sort {
  color: var(--accent-strong);
  font-weight: 600;
}
.mini-table-wrap {
  overflow: hidden;
  border: 1px solid #e9efec;
  border-radius: 10px;
  background: #fff;
}
.mini-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.84rem;
  table-layout: fixed;
}
.mini-table thead th {
  padding: 0.62rem 0.4rem;
  background: #f6f9f8;
  color: #3a524a;
  font-size: 0.64rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  white-space: normal;
  line-height: 1.25;
  border-bottom: 1px solid #e3ece9;
}
.mini-table thead th.num {
  text-align: center;
}
.mini-table thead th:first-child {
  text-align: center;
  padding-left: 0.6rem;
}
.mini-table tbody td {
  padding: 0.56rem 0.6rem;
  border: none;
}
.mini-table tbody td:first-child {
  padding-left: 0.85rem;
}
.mini-table tbody td.num {
  text-align: center;
}
.mini-table tbody tr + tr td {
  border: none;
}
.mini-table tbody tr:hover td {
  background: #f6f9f8;
}
.mini-entity {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  text-align: center;
  min-width: 0;
}
.mini-entity .entity-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.decisions-block {
  display: flex;
  flex-direction: column;
}
.decisions-empty {
  flex: 1;
}
.plan-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(215px, 1fr));
  gap: 0.6rem;
  align-content: start;
}
.plan-card {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  padding: 0.7rem 0.8rem 0.55rem;
  border: 1px solid var(--border);
  border-radius: 0.7rem;
  background: #fff;
}
.plan-card.is-top {
  border-color: #bcdccb;
  background: linear-gradient(180deg, #f4fbf7 0%, #ffffff 65%);
}
.plan-card.is-mapping-off {
  opacity: 0.74;
}
.plan-card-head {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex-wrap: wrap;
}
.plan-rank {
  display: grid;
  place-items: center;
  width: 1.15rem;
  height: 1.15rem;
  border-radius: 50%;
  background: var(--surface-2);
  color: var(--muted);
  font-size: 0.65rem;
  font-weight: 700;
  flex-shrink: 0;
}
.plan-card.is-top .plan-rank {
  background: var(--accent);
  color: #fff;
}
.plan-card-title {
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--text);
}
.type-id {
  font-size: 0.66rem;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.plan-card-entity {
  font-size: 0.8rem;
  font-weight: 600;
  color: #4a6155;
  overflow-wrap: anywhere;
}
.plan-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.35rem 0.5rem;
  margin: 0;
}
.plan-metrics > div {
  display: flex;
  flex-direction: column;
  gap: 0.05rem;
  min-width: 0;
}
.plan-metrics dt {
  font-size: 0.6rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--muted);
}
.plan-metrics dd {
  margin: 0;
  font-size: 0.82rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.plan-metric-wide {
  grid-column: 1 / -1;
}
.bucket-values {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  flex-wrap: wrap;
}
.bucket-chip {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 0.4rem;
  background: #fbfdfc;
}
.bucket-chip .bucket-value {
  padding: 0.1rem 0.45rem;
  font-size: 0.76rem;
}
.plan-card-foot {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex-wrap: wrap;
  margin-top: auto;
  padding-top: 0.4rem;
  border-top: 1px dashed var(--border);
}
.plan-updated {
  font-size: 0.68rem;
  color: var(--muted);
  margin-right: auto;
}
.plan-warning {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  flex-wrap: wrap;
  padding: 0.6rem 0.7rem;
  border: 1px solid #f0d9b5;
  border-radius: 0.6rem;
  background: #fdf7ec;
  color: #8a5a1a;
  font-size: 0.8rem;
  line-height: 1.45;
}
.decisions-hint {
  font-size: 0.82rem;
  line-height: 1.5;
  color: var(--muted);
  margin: 0;
}
@media (max-width: 980px) {
  .integrated-panel {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 760px) {
  .page-head {
    align-items: flex-start;
    flex-wrap: wrap;
  }
  .head-actions {
    width: 100%;
  }
  .head-actions .btn {
    flex: 1 1 auto;
  }
  .date-field {
    flex: 1 1 auto;
  }
  .date-field input[type='date'] {
    width: 100%;
  }
  .final-table {
    min-width: 640px;
  }
  .integrated-panel {
    padding: 0.8rem;
  }
  .panel-block {
    padding: 0.9rem;
  }
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
input:focus-visible,
select:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}
</style>