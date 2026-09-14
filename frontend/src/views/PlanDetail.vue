<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const planId = computed(() => route.params.id)

const plan = ref(null)
const loading = ref(true)
const error = ref('')
const typeName = ref('')
const cityName = ref('')

// --- base configs (incentive_base_configs) ----------------------------------
// One row per allocator of the plan, joined on plan_id. Only the four summary
// fields are shown up front; the rest of a row sits behind its dropdown.
const SUMMARY_FIELDS = ['listing_id', 'allocator_id', 'rule_name', 'impact_ratio']

const configs = ref([])
const configColumns = ref([])
const summaryColumns = ref([])
const impactRatioSum = ref(null)
const configsLoading = ref(true)
const configsError = ref('')
const expanded = ref(new Set())

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
const detailFields = computed(() => fieldNames.value.filter((n) => !tableFields.value.includes(n)))

const allExpanded = computed(
  () => configs.value.length > 0 && expanded.value.size === configs.value.length
)

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

// "2026-09-02T15:40:50" -> "Sep 2, 2026, 3:40 PM"
function formatDate(value) {
  if (!value) return ''
  const d = new Date(value)
  if (isNaN(d)) return value
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(d)
}

async function loadConfigs() {
  configsLoading.value = true
  configsError.value = ''
  expanded.value = new Set()
  try {
    const res = await fetch(
      `/api/incentive-base-configs?plan_id=${encodeURIComponent(planId.value)}`
    )
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Failed to load base configs')
    configs.value = data.rows || []
    configColumns.value = data.columns || []
    summaryColumns.value = data.summary_columns || []
    impactRatioSum.value = data.impact_ratio_sum ?? null
  } catch (e) {
    configs.value = []
    configsError.value = e.message
  } finally {
    configsLoading.value = false
  }
}

async function load() {
  loading.value = true
  error.value = ''
  // The base configs are a separate section: a failure there must not hide the
  // plan itself, so it is loaded on its own track.
  const configsPromise = loadConfigs()
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

      <!-- more sections will be added here later -->
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
            <p class="hint">
              Rows of <code>incentive_base_configs</code> for plan_id
              {{ planId }} — open a row to see its other fields.
            </p>
          </div>
        </div>
        <div class="card-head-actions">
          <span v-if="impactRatioSum !== null" class="pill accent">
            impact {{ ratioText(impactRatioSum) }}
          </span>
          <span v-if="!configsLoading && !configsError" class="pill">
            {{ configs.length }} allocator{{ configs.length === 1 ? '' : 's' }}
          </span>
          <button
            v-if="configs.length > 1"
            class="btn btn-ghost btn-sm"
            @click="toggleAll"
          >
            {{ allExpanded ? 'Collapse all' : 'Expand all' }}
          </button>
        </div>
      </div>

      <div v-if="configsLoading" class="config-body">
        <p class="config-loading">Loading base configs…</p>
      </div>
      <div v-else-if="configsError" class="config-body">
        <div class="config-error">
          <span>{{ configsError }}</span>
          <button class="btn btn-ghost btn-sm" @click="loadConfigs">Retry</button>
        </div>
      </div>
      <div v-else-if="!configs.length" class="config-body">
        <p class="config-empty">No base configs for this plan yet.</p>
      </div>
      <div v-else class="table-scroll">
        <table class="config-table">
          <thead>
            <tr>
              <th class="expand-col"><span class="sr-only">Details</span></th>
              <th v-for="f in tableFields" :key="f">{{ colLabel(f) }}</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(row, i) in configs" :key="rowKey(row, i)">
              <tr
                class="config-row"
                :class="{ expanded: isOpen(row, i) }"
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
                <td v-for="f in tableFields" :key="f" :class="{ 'mono-cell': f !== 'impact_ratio' }">
                  <template v-if="f === 'impact_ratio'">
                    <span class="ratio">{{ ratioText(row[f]) }}</span>
                    <span v-if="row[f] !== null && row[f] !== undefined && row[f] !== ''" class="ratio-raw">
                      {{ row[f] }}
                    </span>
                  </template>
                  <template v-else>{{ cellText(row[f]) }}</template>
                </td>
              </tr>
              <tr v-if="isOpen(row, i)" class="detail-row">
                <td :id="`config-detail-${rowKey(row, i)}`" :colspan="tableFields.length + 1" class="detail-cell" @click.stop>
                  <dl v-if="detailFields.length" class="detail-facts">
                    <div v-for="f in detailFields" :key="f">
                      <dt>{{ colLabel(f) }}</dt>
                      <dd>{{ cellText(row[f]) }}</dd>
                    </div>
                  </dl>
                  <p v-else class="config-loading">This row has no other fields.</p>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </section>
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
  overflow: hidden;
}
.config-section h2 {
  margin: 0;
  font-size: 1.05rem;
}
.config-section code {
  background: var(--surface-2);
  padding: 0.05rem 0.35rem;
  border-radius: 0.3rem;
  color: var(--accent-strong);
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
.mono-cell {
  font-variant-numeric: tabular-nums;
}
.ratio {
  font-weight: 650;
  color: var(--accent-strong);
  font-variant-numeric: tabular-nums;
}
.ratio-raw {
  margin-left: 0.4rem;
  color: var(--muted);
  font-size: 0.8rem;
  font-variant-numeric: tabular-nums;
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
button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}
@media (max-width: 640px) {
  .config-body,
  .detail-cell {
    padding: 0.85rem;
  }
}
</style>
