<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import DecisionMatrixStepForm from '../components/DecisionMatrixStepForm.vue'
import DecisionMatrixStepsTable from '../components/DecisionMatrixStepsTable.vue'
import ModalDialog from '../components/ModalDialog.vue'
import { requestJson } from '../lib/api'
import { scoreTypeLabel, scoreTypeValue } from '../lib/decisionMatrixScoreTypes'

const route = useRoute()
const cityGroup = computed(() => String(route.query.city_group ?? '').trim())
const typeId = computed(() => String(route.query.type ?? '').trim())

const rows = ref([])
const series = ref([])
const columns = ref([])
const types = ref([])
const loading = ref(true)
const error = ref('')
const historyShown = ref(new Set())
const formContext = ref(null)
const saving = ref(false)
const formError = ref('')
const deactivateTarget = ref(null)
const deactivating = ref(false)
const deactivateError = ref('')
const message = ref(null)
let messageTimer
let controller
let disposed = false

const missingParams = computed(() => !cityGroup.value || !typeId.value)

const typeName = computed(() => {
  const found = types.value.find((type) => String(type.id) === typeId.value)
  return found?.name || `Type #${typeId.value}`
})

function isActive(row) {
  return row.deactivated_at === null || row.deactivated_at === undefined
}
function seriesKey(typeId, scoreType) {
  return JSON.stringify([String(typeId), scoreTypeValue(scoreType)])
}

const scoreTypes = computed(() => {
  const stepsBySeries = new Map()
  for (const row of rows.value) {
    const key = seriesKey(row.incentive_type, row.score_type)
    if (!stepsBySeries.has(key)) stepsBySeries.set(key, [])
    stepsBySeries.get(key).push(row)
  }
  const grouped = new Map()
  for (const item of series.value) {
    const key = seriesKey(item.incentive_type, item.score_type)
    const steps = (stepsBySeries.get(key) || []).sort(
      (a, b) => Number(a.score) - Number(b.score) || Number(a.id) - Number(b.id)
    )
    grouped.set(key, {
      ...item, key, label: scoreTypeLabel(item.score_type),
      activeSteps: steps.filter(isActive),
      deactivatedSteps: steps.filter((row) => !isActive(row)),
    })
  }
  return [...grouped.values()].sort((a, b) => a.label.localeCompare(b.label))
})

const activeCount = computed(() => scoreTypes.value.reduce((sum, item) => sum + item.activeSteps.length, 0))
const deactivatedCount = computed(() => scoreTypes.value.reduce((sum, item) => sum + item.deactivatedSteps.length, 0))
// A score type can only be added when this incentive type exists in the
// reference lookup, mirroring the main Decision Matrix page.
const canAddScoreType = computed(() =>
  !loading.value && !error.value && !saving.value &&
  types.value.some((type) => String(type.id) === typeId.value)
)
const existingScoreTypes = computed(() => scoreTypes.value.map((item) => item.score_type))

function countLabel(count, noun) {
  return `${count} ${noun}${count === 1 ? '' : 's'}`
}
function showMessage(text) {
  if (disposed) return
  clearTimeout(messageTimer)
  message.value = text
  messageTimer = setTimeout(() => { message.value = null }, 4500)
}

async function load() {
  controller?.abort()
  const ctrl = new AbortController()
  controller = ctrl
  loading.value = true
  error.value = ''
  if (missingParams.value) {
    loading.value = false
    return
  }
  try {
    const params = new URLSearchParams({ city_group: cityGroup.value, include_deactivated: 'true' })
    const [matrixData, typesData] = await Promise.all([
      requestJson(`/api/decision-matrix?${params}`, { signal: ctrl.signal }),
      requestJson('/api/incentive-types', { signal: ctrl.signal }),
    ])
    if (ctrl.signal.aborted) return
    rows.value = (matrixData.rows || []).filter((row) => String(row.incentive_type) === typeId.value)
    series.value = (matrixData.series || []).filter((item) => String(item.incentive_type) === typeId.value)
    columns.value = matrixData.columns || []
    types.value = typesData.rows || []
  } catch (e) {
    if (!ctrl.signal.aborted) error.value = e.message
  } finally {
    if (!ctrl.signal.aborted) loading.value = false
  }
}

function toggleHistory(key) {
  if (historyShown.value.has(key)) historyShown.value.delete(key)
  else historyShown.value.add(key)
}

function openScoreTypeForm() {
  if (loading.value || !canAddScoreType.value) return
  formError.value = ''
  formContext.value = {
    mode: 'scoreType', cityGroup: cityGroup.value,
    incentiveType: typeId.value, typeName: typeName.value,
    scoreType: undefined, nextScore: 1,
  }
}
function openStepForm(item) {
  formError.value = ''
  formContext.value = {
    mode: 'step', cityGroup: cityGroup.value,
    incentiveType: typeId.value, typeName: typeName.value,
    scoreType: item.score_type, nextScore: item.next_score ?? 1,
  }
}
function closeForm() {
  if (!saving.value) formContext.value = null
}
async function saveStep(payload) {
  if (saving.value || !formContext.value) return
  saving.value = true
  formError.value = ''
  try {
    const data = await requestJson('/api/decision-matrix', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    })
    if (disposed) return
    formContext.value = null
    historyShown.value = new Set()
    showMessage(data.message || 'Score step added successfully.')
    await load()
  } catch (e) {
    formError.value = e.message
    if (e.status === 409) {
      // Refresh occupied scores, but never replace the user's chosen values.
      await load()
    }
  } finally {
    saving.value = false
  }
}

function askDeactivate(item, row) {
  deactivateError.value = ''
  deactivateTarget.value = { label: item.label, row }
}
function closeDeactivate() {
  if (!deactivating.value) deactivateTarget.value = null
}
async function confirmDeactivate() {
  if (!deactivateTarget.value || deactivating.value) return
  deactivating.value = true
  deactivateError.value = ''
  try {
    const data = await requestJson(
      `/api/decision-matrix/${encodeURIComponent(deactivateTarget.value.row.id)}/deactivate`,
      { method: 'POST' }
    )
    if (disposed) return
    deactivateTarget.value = null
    showMessage(data.message || 'Score step deactivated successfully.')
    await load()
  } catch (e) {
    deactivateError.value = e.message
  } finally {
    deactivating.value = false
  }
}

onMounted(load)
onBeforeUnmount(() => {
  disposed = true
  controller?.abort()
  clearTimeout(messageTimer)
})
</script>

<template>
  <div class="type-detail">
    <div class="head">
      <div>
        <router-link to="/decision-matrix" class="back-link">← Decision Matrix</router-link>
        <h1>{{ typeName }} <small>#{{ typeId }}</small></h1>
        <p class="sub">City group <strong>{{ cityGroup }}</strong></p>
      </div>
      <div class="head-actions">
        <button class="btn btn-ghost" :disabled="loading" @click="load">Refresh</button>
        <button class="btn btn-primary" :disabled="!canAddScoreType" @click="openScoreTypeForm">+ Add score type</button>
      </div>
    </div>

    <div v-if="missingParams" class="card empty">
      <h3>Missing parameters</h3>
      <p>This page needs a city group and an incentive type to show.</p>
      <router-link to="/decision-matrix" class="btn btn-ghost">Back to Decision Matrix</router-link>
    </div>

    <div v-else-if="error" class="banner error" role="alert">
      <strong>Could not load this incentive type</strong>
      <p>{{ error }}</p>
      <button class="btn btn-ghost" @click="load">Retry</button>
    </div>

    <div v-else-if="loading" class="card empty" role="status">Loading score steps…</div>

    <template v-else>
      <div class="summary card">
        <div class="stat">
          <span class="stat-value">{{ scoreTypes.length }}</span>
          <span class="stat-label">{{ scoreTypes.length === 1 ? 'score type' : 'score types' }}</span>
        </div>
        <div class="stat">
          <span class="stat-value">{{ activeCount }}</span>
          <span class="stat-label">{{ activeCount === 1 ? 'active step' : 'active steps' }}</span>
        </div>
        <div class="stat">
          <span class="stat-value">{{ deactivatedCount }}</span>
          <span class="stat-label">{{ deactivatedCount === 1 ? 'deactivated step' : 'deactivated steps' }}</span>
        </div>
      </div>

      <div v-if="!scoreTypes.length" class="card empty">
        <span class="empty-mark" aria-hidden="true">＋</span>
        <h3>No score steps yet</h3>
        <p>This incentive type has no steps configured for {{ cityGroup }}.</p>
      </div>

      <section v-for="item in scoreTypes" :key="item.key" class="card score-card">
        <div class="score-head">
          <div>
            <h2>{{ item.label }}</h2>
            <p class="hint">
              {{ countLabel(item.activeSteps.length, 'active step') }}
              <span v-if="item.deactivatedSteps.length" aria-hidden="true">·</span>
              <span v-if="item.deactivatedSteps.length">{{ countLabel(item.deactivatedSteps.length, 'deactivated step') }}</span>
            </p>
          </div>
          <button class="btn btn-primary btn-sm" :disabled="!canAddScoreType" @click="openStepForm(item)">+ Add step</button>
        </div>

        <p v-if="!item.activeSteps.length" class="steps-empty">No active steps. Add a new step to start again.</p>
        <DecisionMatrixStepsTable
          v-else :steps="item.activeSteps" :label="`${item.label} active steps`"
          @deactivate="askDeactivate(item, $event)"
        />

        <section v-if="item.deactivatedSteps.length" class="history-section">
          <div class="history-toolbar">
            <h3 class="history-title">Deactivated steps</h3>
            <button
              class="btn btn-ghost btn-sm" :aria-expanded="historyShown.has(item.key)"
              @click="toggleHistory(item.key)"
            >{{ historyShown.has(item.key) ? 'Hide deactivated' : `Show deactivated (${item.deactivatedSteps.length})` }}</button>
          </div>
          <DecisionMatrixStepsTable
            v-if="historyShown.has(item.key)" :steps="item.deactivatedSteps"
            :label="`${item.label} deactivated steps`" deactivated
          />
        </section>
      </section>
    </template>

    <DecisionMatrixStepForm
      v-if="formContext" :context="formContext" :columns="columns" :types="[]"
      :existing-score-types="existingScoreTypes" :steps="rows" :saving="saving" :error="formError"
      @save="saveStep" @close="closeForm"
    />
    <ModalDialog v-if="deactivateTarget" title-id="deactivate-score-title" :busy="deactivating" @close="closeDeactivate">
      <h2 id="deactivate-score-title">Deactivate score {{ deactivateTarget.row.score }}?</h2>
      <p class="confirm-text">
        Deactivate this step for <strong>{{ cityGroup }} / {{ typeName }} / {{ deactivateTarget.label }}</strong>?
      </p>
      <p class="hint">It will be kept in the deactivated history. Other steps and their score numbers will not change.</p>
      <p v-if="deactivateError" class="banner error" role="alert">{{ deactivateError }}</p>
      <div class="actions">
        <button class="btn btn-ghost" :disabled="deactivating" autofocus @click="closeDeactivate">Cancel</button>
        <button class="btn btn-danger" :disabled="deactivating" @click="confirmDeactivate">
          {{ deactivating ? 'Deactivating…' : 'Deactivate step' }}
        </button>
      </div>
    </ModalDialog>
    <div v-if="message" class="toast ok" role="status">{{ message }}</div>
  </div>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; margin-bottom: 1.25rem; }
.head h1 { margin: 0.15rem 0 0; font-size: 1.5rem; overflow-wrap: anywhere; }
.head h1 small { margin-left: 0.5rem; font-size: 0.85rem; font-weight: 400; color: var(--muted); }
.head-actions { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
.back-link { display: inline-block; color: var(--accent-strong); text-decoration: none; font-size: 0.85rem; font-weight: 600; margin-bottom: 0.3rem; }
.back-link:hover { text-decoration: underline; }
.sub { margin: 0.3rem 0 0; color: var(--muted); }
.sub strong { color: var(--text); }
.hint { margin: 0.25rem 0 0; font-size: 0.83rem; color: var(--muted); }
.empty { padding: 3.5rem 1.2rem; text-align: center; color: var(--muted); }
.empty h3 { color: var(--text); margin: 0.8rem 0 0.4rem; }
.empty p { margin: 0.45rem 0 1rem; font-size: 0.9rem; line-height: 1.6; }
.empty-mark { display: inline-grid; place-items: center; width: 3rem; height: 3rem; background: var(--accent-soft); border-radius: 0.9rem; color: var(--accent); font-size: 1.7rem; }

.summary { display: flex; flex-wrap: wrap; gap: 1.5rem; padding: 1rem 1.25rem; margin-bottom: 1.25rem; }
.stat { display: flex; align-items: baseline; gap: 0.5rem; }
.stat-value { font-size: 1.4rem; font-weight: 700; color: var(--accent-strong); font-variant-numeric: tabular-nums; }
.stat-label { color: var(--muted); font-size: 0.85rem; }

.score-card { padding: 1.25rem; }
.score-card + .score-card { margin-top: 1.25rem; }
.score-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 0.9rem; }
.score-head h2 { margin: 0; font-size: 1.1rem; overflow-wrap: anywhere; }
.steps-empty { margin: 0; padding: 1.5rem 1rem; text-align: center; color: var(--muted); font-size: 0.88rem; border: 1px dashed var(--border); border-radius: 0.6rem; }

.history-section { margin-top: 1rem; border-top: 1px solid var(--border); padding-top: 0.9rem; }
.history-toolbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.65rem; margin-bottom: 0.7rem; }
.history-title { margin: 0; font-size: 0.85rem; font-weight: 600; }
.confirm-text { line-height: 1.6; overflow-wrap: anywhere; }

@media (max-width: 640px) {
  .head { flex-wrap: wrap; align-items: flex-start; }
  .summary { gap: 1rem; }
  .score-card { padding: 0.9rem; }
}
</style>
