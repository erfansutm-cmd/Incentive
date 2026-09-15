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
  // Bigger scores are worse → red; smaller → green (inverted)
  if (n <= 1) return 'high'
  if (n <= 2) return 'med'
  if (n <= 3) return 'low'
  return 'very-low'
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

const totalCities = computed(() => cities.value.length)
const totalEntities = computed(() => cities.value.reduce((sum, c) => sum + (c.entity_count || 0), 0))
const visibleCount = computed(() => filteredCities.value.length)

const allExpanded = computed(
  () => filteredCities.value.length > 0 && filteredCities.value.every((c) => expanded.value.has(String(c.city_id_raw ?? c.city_id)))
)

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
  for (const c of filteredCities.value) next.add(cityKey(c))
  expanded.value = next
}
function collapseAll() {
  const next = new Set(expanded.value)
  for (const c of filteredCities.value) next.delete(cityKey(c))
  expanded.value = next
}
function clearSearch() {
  searchQuery.value = ''
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

function citySubtitle(c) {
  const parts = []
  if (c.city_group) parts.push(c.city_group)
  if (c.box_city_name && c.box_city_name !== c.city) parts.push(c.box_city_name)
  return parts.join(' · ')
}
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
          v-if="filteredCities.length"
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

      <span class="pill spacer">
        <template v-if="loading">Loading…</template>
        <template v-else>{{ visibleCount }} of {{ totalCities }} cities</template>
      </span>
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

    <template v-else-if="!filteredCities.length">
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
                <th colspan="5" class="group-header scores-header">
                  <span class="group-label">
                    <span class="icon-tile sm accent" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z" />
                      </svg>
                    </span>
                    Scores
                  </span>
                </th>
                <th class="group-header decisions-header">
                  <span class="group-label">
                    <span class="icon-tile sm neutral" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9 5H7a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-2" />
                        <path d="M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2h-2a2 2 0 0 1-2-2V5z" />
                        <path d="M9 12l2 2 4-4" />
                      </svg>
                    </span>
                    Decisions
                  </span>
                </th>
              </tr>
              <tr>
                <th class="th-expand"><span class="sr-only">Expand</span></th>
                <th>City</th>
                <th>Business Entity</th>
                <th class="score-th">Performance</th>
                <th class="score-th">Order Level</th>
                <th class="score-th">Weather</th>
                <th class="decisions-th">Plans</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="city in filteredCities" :key="cityKey(city)">
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
                    <span v-if="city.primary_entity" class="entity-name">{{ city.primary_entity.business_entity }}</span>
                    <span v-else class="muted">—</span>
                  </td>
                  <td class="score-cell">
                    <span v-if="city.primary_entity" class="score-badge" :class="scoreBadgeClass(city.primary_entity.scores.performance)">
                      {{ formatScore(city.primary_entity.scores.performance) }}
                    </span>
                    <span v-else class="muted">—</span>
                  </td>
                  <td class="score-cell">
                    <span v-if="city.primary_entity" class="score-badge" :class="scoreBadgeClass(city.primary_entity.scores.order_level_increase)">
                      {{ formatScore(city.primary_entity.scores.order_level_increase) }}
                    </span>
                    <span v-else class="muted">—</span>
                  </td>
                  <td class="score-cell">
                    <span v-if="city.primary_entity" class="score-badge" :class="scoreBadgeClass(city.primary_entity.scores.weather)">
                      {{ formatScore(city.primary_entity.scores.weather) }}
                    </span>
                    <span v-else class="muted">—</span>
                  </td>
                  <td class="decisions-cell">
                    <span class="decisions-placeholder">
                      <span class="pill plain decisions-pill">
                        <span class="dot" aria-hidden="true" />
                        {{ isExpanded(city) ? 'Expanded below' : '—' }}
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
                            <thead>
                              <tr>
                                <th>Business Entity</th>
                                <th class="num">Performance</th>
                                <th class="num">Order Level</th>
                                <th class="num">Weather</th>
                              </tr>
                            </thead>
                            <tbody>
                              <tr
                                v-for="be in city.business_entities"
                                :key="be.business_entity"
                              >
                                <td class="mini-entity">
                                  <span class="entity-name">{{ be.business_entity }}</span>
                                </td>
                                <td class="num">
                                  <span class="score-badge small" :class="scoreBadgeClass(be.scores.performance)">{{ formatScore(be.scores.performance) }}</span>
                                </td>
                                <td class="num">
                                  <span class="score-badge small" :class="scoreBadgeClass(be.scores.order_level_increase)">{{ formatScore(be.scores.order_level_increase) }}</span>
                                </td>
                                <td class="num">
                                  <span class="score-badge small" :class="scoreBadgeClass(be.scores.weather)">{{ formatScore(be.scores.weather) }}</span>
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
.toolbar-card .toolbar-hint {
  display: none;
}
@media (min-width: 860px) {
  .toolbar-card .toolbar-hint {
    display: inline;
  }
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
  min-width: 860px;
  table-layout: fixed;
}
.col-expand {
  width: 48px;
}
.col-city {
  width: 184px;
}
.col-entity {
  width: 164px;
}
.col-score {
  width: 108px;
}
.col-decisions {
  width: 140px;
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
  padding: 0.55rem 0.9rem;
  font-size: 0.72rem;
  letter-spacing: 0.04em;
}
.group-header {
  font-weight: 700;
}
.group-header .group-label {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}
.scores-header {
  background: linear-gradient(90deg, #eef3f0, #f6faf8);
  color: var(--accent-strong);
  border-right: 1px solid var(--border);
}
.decisions-header {
  background: #f8faf9;
  color: var(--muted);
}
.final-table thead tr:not(.group-head-row) th {
  padding-top: 0.65rem;
  padding-bottom: 0.65rem;
}
.th-expand {
  width: 3rem;
  text-align: center;
}
.score-th {
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

.expand-col {
  width: 3rem;
  text-align: center;
}
.expand-col .chevron-disc {
  margin: 0 auto;
}

.city-cell {
  min-width: 170px;
  text-align: left;
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
  flex-wrap: wrap;
  margin-top: 0.2rem;
}
.city-id {
  font-size: 0.76rem;
  color: var(--muted);
  background: var(--surface-2);
  padding: 0.1rem 0.4rem;
  border-radius: 0.35rem;
}
.box-name {
  font-size: 0.78rem;
  color: var(--muted);
}
.city-sub {
  margin-top: 0.18rem;
  font-size: 0.76rem;
  color: var(--muted);
}

.entity-cell {
  white-space: nowrap;
  text-align: left;
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
}
.decisions-cell {
  text-align: center;
}
.score-badge {
  display: inline-grid;
  place-items: center;
  min-width: 2.2rem;
  padding: 0.24rem 0.5rem;
  border-radius: 0.5rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  font-size: 0.86rem;
  border: 1px solid var(--border);
  background: #fff;
  color: var(--text);
  margin: 0 auto;
}
.score-badge.small {
  min-width: 1.9rem;
  padding: 0.18rem 0.42rem;
  font-size: 0.82rem;
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
  gap: 0.35rem;
}
.decisions-pill .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--muted);
  display: inline-block;
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
  background: #f8faf9;
  border-top: 1px solid rgba(61, 139, 109, 0.22);
}
.integrated-panel {
  display: grid;
  grid-template-columns: 1.15fr 1fr;
  gap: 1rem;
  padding: 1.1rem 1.25rem 1.25rem;
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
.mini-table-wrap {
  overflow-x: auto;
}
.mini-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.86rem;
}
.mini-table thead th {
  padding: 0.55rem 0.65rem;
  background: var(--surface-2);
  color: #4a6155;
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  white-space: nowrap;
}
.mini-table thead th.num {
  text-align: center;
}
.mini-table tbody td {
  padding: 0.6rem 0.65rem;
  border-top: 1px solid var(--border);
}
.mini-table tbody td.num {
  text-align: center;
}
/* hover kept subtle — no green wash that makes badges look patchy */
.mini-table tbody tr:hover td {
  background: #fff;
}
.mini-table tbody tr:hover {
  box-shadow: inset 0 0 0 1px var(--border);
}
.mini-entity {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
  text-align: left;
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

.combined-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
  padding: 0.75rem 1.1rem;
  border-top: 1px solid var(--border);
  background: #fbfdfc;
}
.combined-foot .hint {
  margin: 0;
  font-size: 0.8rem;
  color: var(--muted);
}

/* Responsive */
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
  .combined-foot {
    padding: 0.7rem 0.85rem;
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
