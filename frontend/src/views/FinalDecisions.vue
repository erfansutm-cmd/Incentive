<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { requestJson } from '../lib/api'

const SCORE_TYPES = [
  { value: 'performance', label: 'Performance' },
  { value: 'order_level_increase', label: 'Order Level' },
  { value: 'weather', label: 'Weather' },
]

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

function scoreStyle(v, key, ranges) {
  const n = Number(v)
  if (v === null || v === undefined || v === '' || !Number.isFinite(n)) return {}
  const range = ranges?.[key] || { min: 0, max: 0 }
  const { min, max } = range
  let t = max > min ? (n - min) / (max - min) : 0
  t = Math.max(0, Math.min(1, t))
  // 0 -> green (lowest score), 1 -> red (highest score)
  const hue = 142 - t * 142
  return {
    backgroundColor: `hsl(${hue}, 62%, 93%)`,
    borderColor: `hsl(${hue}, 42%, 76%)`,
    color: `hsl(${hue}, 55%, 30%)`,
  }
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

const expanded = ref(new Set())
const sortKey = ref(null)
const sortDir = ref('asc')
const showPriorityEditor = ref(false)
const DEFAULT_PRIORITY = ['foodZooket', 'food', 'Zooket']
const priorityOrder = ref([...DEFAULT_PRIORITY])
const message = ref(null)
let messageTimer = null
let controller = null
let disposed = false

const groupOptions = computed(() => {
  const seen = new Set()
  for (const c of cities.value) {
    const g = c.city_group
    if (g !== null && g !== undefined && String(g).trim() !== '') seen.add(String(g))
  }
  return [...seen].sort((a, b) => String(a).localeCompare(String(b)))
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
    if (an === bn) return String(a.city).localeCompare(String(b.city))
    return (an - bn) * dir
  })
})

const totalCities = computed(() => cities.value.length)
const totalEntities = computed(() => cities.value.reduce((sum, c) => sum + (c.entity_count || 0), 0))
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
const draggedIdx = ref(null)
const dragOverIdx = ref(null)
function movePriority(index, dir) {
  const next = [...priorityOrder.value]
  const target = index + dir
  if (target < 0 || target >= next.length) return
  const tmp = next[index]
  next[index] = next[target]
  next[target] = tmp
  priorityOrder.value = next
}
function onDragStart(idx, evt) {
  draggedIdx.value = idx
  if (evt?.dataTransfer) {
    evt.dataTransfer.effectAllowed = 'move'
    try {
      evt.dataTransfer.setData('text/plain', String(idx))
    } catch (e) {
      // some browsers require this call to enable drag; ignore failures
    }
  }
}
function onDragOver(idx) {
  if (dragOverIdx.value !== idx) dragOverIdx.value = idx
}
function onDragLeave() {
  dragOverIdx.value = null
}
function onDrop(targetIdx) {
  const from = draggedIdx.value
  if (from === null || from === targetIdx) {
    draggedIdx.value = null
    dragOverIdx.value = null
    return
  }
  const next = [...priorityOrder.value]
  const [moved] = next.splice(from, 1)
  next.splice(targetIdx, 0, moved)
  priorityOrder.value = next
  draggedIdx.value = null
  dragOverIdx.value = null
}
function onDragEnd() {
  draggedIdx.value = null
  dragOverIdx.value = null
}
function resetPriority() {
  priorityOrder.value = [...DEFAULT_PRIORITY]
  // re-add any other entities that were added?
  ensurePriorityCoversAll()
}
function ensurePriorityCoversAll() {
  const seen = new Set(priorityOrder.value)
  const all = new Set()
  for (const c of cities.value) {
    for (const be of c.business_entities || []) all.add(be.business_entity)
  }
  for (const name of [...all].sort((a, b) => a.localeCompare(b))) {
    if (!seen.has(name)) {
      priorityOrder.value = [...priorityOrder.value, name]
      seen.add(name)
    }
  }
}
const allKnownEntities = computed(() => {
  const set = new Set(priorityOrder.value)
  for (const c of cities.value) for (const be of c.business_entities || []) set.add(be.business_entity)
  return [...set]
})

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
    const valid = new Set(cities.value.map((c) => String(c.city_id_raw ?? c.city_id)))
    const pruned = new Set([...expanded.value].filter((k) => valid.has(k)))
    expanded.value = pruned
    ensurePriorityCoversAll()
  } catch (e) {
    if (!ctrl.signal.aborted) {
      error.value = e.message
      cities.value = []
    }
  } finally {
    if (!ctrl.signal.aborted) loading.value = false
  }
}

function onDateChange() {
  expanded.value = new Set()
  load()
}

onMounted(load)
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
          <template v-if="cities.length"> · {{ totalCities }} cities · {{ totalEntities }} business entities</template>
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

      <button class="btn btn-ghost btn-sm" @click="showPriorityEditor = !showPriorityEditor">
        {{ showPriorityEditor ? 'Hide entity order' : 'Entity order' }}
      </button>

      <span class="pill spacer">
        <template v-if="loading">Loading…</template>
        <template v-else>{{ visibleCount }} of {{ totalCities }} cities</template>
      </span>
      <button
        v-if="sortKey"
        class="btn btn-ghost btn-sm sort-clear"
        @click="clearSort"
        title="Remove city sort — back to default (active city id)"
      >
        ↺ Default order
      </button>
    </div>

    <div v-if="showPriorityEditor" class="priority-modal-overlay" @click.self="showPriorityEditor = false">
      <div class="priority-modal" role="dialog" aria-modal="true" aria-label="Entity priority order">
        <div class="priority-modal-head">
          <div>
            <h4 style="margin:0; font-size:1rem">Entity order</h4>
            <p class="hint" style="margin:0.2rem 0 0">
              Drag to reorder · top is shown in collapsed rows<br />
              Default: foodZooket &gt; food &gt; Zooket &gt; others
            </p>
          </div>
          <button class="btn btn-ghost btn-sm" @click="showPriorityEditor = false">✕</button>
        </div>
        <transition-group
          tag="div"
          name="pri-move"
          class="priority-list"
          @dragover.prevent="onDragOver(priorityOrder.length)"
          @drop.prevent="onDrop(priorityOrder.length)"
        >
          <div
            v-for="(name, i) in priorityOrder"
            :key="name"
            class="priority-row"
            :class="{ dragging: draggedIdx === i, 'drag-over-top': dragOverIdx === i && draggedIdx !== null && draggedIdx !== i }"
            draggable="true"
            @dragstart="onDragStart(i, $event)"
            @dragover.prevent.stop="onDragOver(i)"
            @dragleave="onDragLeave()"
            @drop.prevent.stop="onDrop(i)"
            @dragend="onDragEnd()"
          >
            <span class="drag-handle" aria-hidden="true">⋮⋮</span>
            <span class="pri-rank">{{ i + 1 }}</span>
            <span class="entity-name flex-1">{{ name }}</span>
            <div class="pri-actions">
              <button class="btn btn-ghost tiny" :disabled="i === 0" @click.stop="movePriority(i, -1)" title="Move up">↑</button>
              <button class="btn btn-ghost tiny" :disabled="i === priorityOrder.length - 1" @click.stop="movePriority(i, 1)" title="Move down">↓</button>
            </div>
          </div>
          <div
            key="__end_zone"
            class="drop-end-zone"
            :class="{ 'drag-over-top': dragOverIdx === priorityOrder.length && draggedIdx !== null }"
          ></div>
        </transition-group>
        <div v-if="allKnownEntities.filter(n => !priorityOrder.includes(n)).length" class="priority-add-row">
          <span class="hint" style="font-size:0.78rem">Others (after): {{ allKnownEntities.filter(n => !priorityOrder.includes(n)).join(', ') }}</span>
          <button class="btn btn-ghost btn-sm" @click="ensurePriorityCoversAll" style="white-space:nowrap">Add all</button>
        </div>
        <div class="priority-foot">
          <button class="btn btn-ghost btn-sm" @click="resetPriority">↺ Reset to default</button>
          <button class="btn btn-primary btn-sm" @click="showPriorityEditor = false">Done</button>
          <span class="hint priority-foot-hint">Entities are shown in this order inside each city<br />(when not sorted by scores)</span>
        </div>
      </div>
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
              <col class="col-decisions" />
            </colgroup>
            <thead>
              <tr class="group-head-row">
                <th class="th-expand"></th>
                <th colspan="5" class="group-header scores-header scores-header-divider">
                  <span class="group-label">Scores</span>
                </th>
                <th class="group-header decisions-header decisions-header-divider">
                  <span class="group-label">Decisions</span>
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
                <th class="decisions-th decisions-header-divider">Plans</th>
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
                  <td class="decisions-cell decisions-cell-divider">
                    <span class="decisions-placeholder">
                      <span class="pill plain decisions-pill" :class="{ 'is-expanded': isExpanded(city) }">
                        <span class="dot" aria-hidden="true" />
                        {{ isExpanded(city) ? 'Expanded below' : 'No plans yet' }}
                      </span>
                    </span>
                  </td>
                </tr>

                <tr v-if="isExpanded(city)" class="detail-row">
                  <td :colspan="7" class="detail-cell" @click.stop>
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
                            Decisions
                            <span class="pill plain">coming soon</span>
                          </h4>
                          <p class="hint">4–5 plans per city will render here — integrated with the scores above</p>
                        </div>

                        <div class="decisions-empty">
                          <div class="decisions-grid-placeholder">
                            <div v-for="i in 4" :key="i" class="plan-card muted">
                              <span class="plan-card-title">Plan {{ i }}</span>
                              <span class="plan-card-sub">for {{ city.city }}</span>
                              <span class="pill tiny plain">placeholder</span>
                            </div>
                          </div>
                          <p class="hint decisions-hint">This area is prepared for plan integration. Each city will list its plans and stay synchronized with the expanded scores.</p>
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
  border-collapse: collapse;
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
.col-decisions {
  width: 50%;
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
.decisions-th {
  text-align: center;
  color: var(--muted);
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
.final-table tbody tr.city-row.expanded td:first-child {
  box-shadow: inset 3px 0 0 var(--accent);
}
.final-table tbody tr.city-row.expanded td {
  border-bottom: 2px solid var(--accent);
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
.decisions-cell {
  text-align: center;
  padding: 0.6rem 0.9rem !important;
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

/* Expanded integrated panel */
.detail-row:hover {
  background: transparent;
}
.detail-cell {
  padding: 0 !important;
  background: #fff;
}
.integrated-panel {
  display: grid;
  grid-template-columns: 40fr 60fr;
  gap: 1.15rem;
  margin: 0.9rem 1rem 1.1rem;
  padding: 1.1rem 1.1rem 1.2rem;
  border: 1px solid #cfe0d7;
  border-radius: 0.9rem;
  background: #f2f7f4;
  box-shadow: 0 2px 6px rgba(20, 40, 30, 0.05);
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
.decisions-grid-placeholder {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.55rem;
  margin-bottom: 0.85rem;
}
.plan-card {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 0.75rem 0.85rem;
  border-radius: 0.6rem;
  border: 1px dashed var(--border);
  background: #fafbfa;
  min-height: 72px;
}
.plan-card.muted {
  color: var(--muted);
}
.plan-card-title {
  font-weight: 700;
  font-size: 0.88rem;
  color: var(--text);
}
.plan-card-sub {
  font-size: 0.78rem;
  color: var(--muted);
}
.decisions-hint {
  font-size: 0.82rem;
  line-height: 1.5;
  color: var(--muted);
  margin: 0;
}
.priority-editor {
  padding: 0.9rem 1rem 1rem;
}
.priority-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 0.75rem;
}
.priority-list {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}
.priority-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.5rem 0.65rem;
  border: 1px solid var(--border);
  border-radius: 0.6rem;
  background: #fbfdfc;
  cursor: grab;
  transition: transform 0.22s cubic-bezier(0.2, 0, 0, 1), box-shadow 0.18s ease, opacity 0.18s ease,
    background 0.18s ease, border-color 0.18s ease, box-shadow 0.15s ease;
  will-change: transform;
}
.pri-move-move {
  transition: transform 0.28s cubic-bezier(0.2, 0, 0, 1);
}
.priority-row:active {
  cursor: grabbing;
}
.priority-row:hover:not(.dragging) {
  border-color: #cfe0d7;
  box-shadow: 0 2px 6px rgba(20, 40, 30, 0.06);
}
.pri-rank {
  width: 1.6rem;
  height: 1.6rem;
  display: grid;
  place-items: center;
  background: var(--accent-soft);
  color: var(--accent-strong);
  border-radius: 50%;
  font-weight: 700;
  font-size: 0.78rem;
  flex-shrink: 0;
  transition: background 0.18s ease, color 0.18s ease;
}
.priority-row .entity-name {
  font-weight: 600;
  font-size: 0.86rem;
}
.pri-actions {
  display: flex;
  gap: 0.25rem;
  margin-left: auto;
}
.btn.tiny {
  padding: 0.18rem 0.4rem;
  font-size: 0.78rem;
  line-height: 1;
}
.priority-add-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  padding: 0.5rem 0.6rem;
  border: 1px dashed var(--border);
  border-radius: 0.55rem;
  background: #fff;
  margin-top: 0.3rem;
}
.priority-foot {
  display: flex;
  align-items: center;
  gap: 0.6rem 0.75rem;
  margin-top: 0.75rem;
  flex-wrap: wrap;
}
.priority-foot-hint {
  flex-basis: 100%;
  order: 3;
  font-size: 0.78rem;
  line-height: 1.45;
}
.flex-1 {
  flex: 1;
}
.priority-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(16, 32, 24, 0.38);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
  backdrop-filter: blur(2px);
}
.priority-modal {
  background: #fff;
  border-radius: 0.9rem;
  width: min(460px, 100%);
  max-height: 85vh;
  overflow: auto;
  box-shadow: 0 12px 40px rgba(16, 32, 24, 0.24), 0 2px 8px rgba(16, 32, 24, 0.08);
  padding: 1rem 1.15rem 1rem;
  border: 1px solid #e6ece9;
}
.priority-modal-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 0.85rem;
}
.drag-handle {
  cursor: grab;
  color: #9ab0a8;
  font-size: 0.9rem;
  letter-spacing: 0.08em;
  user-select: none;
  padding: 0 0.15rem;
  line-height: 1;
  transition: color 0.15s ease;
}
.priority-row:hover .drag-handle {
  color: var(--accent-strong);
}
.drag-handle:active {
  cursor: grabbing;
}
.priority-row.dragging {
  opacity: 0.45;
  transform: scale(0.97);
  box-shadow: 0 8px 20px rgba(20, 40, 30, 0.14);
  border-color: var(--accent);
  background: #f3faf6;
}
.priority-row.drag-over-top {
  box-shadow: inset 0 3px 0 0 var(--accent);
  background: #f0faf6;
}
.drop-end-zone {
  height: 0.65rem;
  border-radius: 0.5rem;
  transition: height 0.18s cubic-bezier(0.2, 0, 0, 1), box-shadow 0.15s ease, background 0.15s ease;
}
.drop-end-zone.drag-over-top {
  height: 2.4rem;
  box-shadow: inset 0 0 0 1.5px var(--accent);
  background: #eefaf5;
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