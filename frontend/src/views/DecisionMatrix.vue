<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import DecisionMatrixStepForm from '../components/DecisionMatrixStepForm.vue'
import DecisionMatrixStepsTable from '../components/DecisionMatrixStepsTable.vue'
import ModalDialog from '../components/ModalDialog.vue'
import { requestJson } from '../lib/api'

const groups = ref([])
const groupsLoading = ref(true)
const groupsError = ref('')
const search = ref('')
const selectedGroup = ref(null)
const types = ref([])
const typesLoading = ref(false)
const typesError = ref('')
const rows = ref([])
const series = ref([])
const columns = ref([])
const matrixLoading = ref(false)
const matrixError = ref('')
const expandedType = ref(null)
const openScores = ref(new Set())
const historyShown = ref(new Set())
const formContext = ref(null)
const saving = ref(false)
const formError = ref('')
const deactivateTarget = ref(null)
const deactivating = ref(false)
const deactivateError = ref('')
const message = ref(null)
let messageTimer
let groupsController
let typesController
let matrixController
let disposed = false

const groupCollator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })
function groupRank(group) {
  const name = group.trim().toLowerCase()
  if (/^top[\s_-]*4$/.test(name)) return -1
  if (/^tiers?(?:$|[\s_-]|\d)/.test(name)) return 0
  if (name === 'tehran' || name === 'تهران') return 1
  return 2
}
function groupSortName(group) {
  // Sort Tier 2 before Tier 10 even when separators/capitalization differ.
  return group.trim().replace(/^tiers?[\s_-]*(?=\d)/i, 'Tier ')
}
const filteredGroups = computed(() => groups.value
  .filter((group) => group.toLowerCase().includes(search.value.trim().toLowerCase()))
  .sort((a, b) => groupRank(a) - groupRank(b) || groupCollator.compare(groupSortName(a), groupSortName(b)))
)
const typeNames = computed(() => {
  const names = new Map()
  for (const row of rows.value) {
    if (row.incentive_type_name) names.set(String(row.incentive_type), row.incentive_type_name)
  }
  for (const type of types.value) names.set(String(type.id), type.name)
  return names
})
const validTypeIds = computed(() => new Set(types.value.map((type) => String(type.id))))
function seriesKey(typeId, scoreType) {
  return JSON.stringify([String(typeId), String(scoreType)])
}
function isActive(row) {
  return row.deactivated_at === null || row.deactivated_at === undefined
}

const configuredTypes = computed(() => {
  const stepsBySeries = new Map()
  for (const row of rows.value) {
    const key = seriesKey(row.incentive_type, row.score_type)
    if (!stepsBySeries.has(key)) stepsBySeries.set(key, [])
    stepsBySeries.get(key).push(row)
  }
  const grouped = new Map()
  for (const item of series.value) {
    const id = String(item.incentive_type)
    if (!grouped.has(id)) grouped.set(id, {
      id, name: typeNames.value.get(id) || `Type #${id}`,
      canAdd: validTypeIds.value.has(id), scoreTypes: [], activeCount: 0, deactivatedCount: 0,
    })
    const type = grouped.get(id)
    const key = seriesKey(id, item.score_type)
    const steps = (stepsBySeries.get(key) || []).sort((a, b) =>
      Number(a.score) - Number(b.score) || Number(a.id) - Number(b.id)
    )
    type.scoreTypes.push({
      ...item, key,
      activeSteps: steps.filter(isActive),
      deactivatedSteps: steps.filter((row) => !isActive(row)),
    })
    type.activeCount += item.active_count
    type.deactivatedCount += item.deactivated_count
  }
  return [...grouped.values()].sort((a, b) => a.name.localeCompare(b.name))
})
const availableTypes = computed(() => {
  const configured = new Set(configuredTypes.value.map((type) => type.id))
  return types.value.filter((type) => !configured.has(String(type.id)))
})
const activeCount = computed(() => configuredTypes.value.reduce((sum, type) => sum + type.activeCount, 0))
function countLabel(count, noun) {
  return `${count} ${noun}${count === 1 ? '' : 's'}`
}
const existingScoreTypes = computed(() => configuredTypes.value
  .find((type) => type.id === String(formContext.value?.incentiveType))
  ?.scoreTypes.map((item) => item.score_type) || []
)
const busy = computed(() => groupsLoading.value || matrixLoading.value || typesLoading.value || saving.value || deactivating.value)
const canAddType = computed(() => !busy.value && !matrixError.value && !typesError.value && availableTypes.value.length > 0)

function toggleSet(state, key) {
  if (state.has(key)) state.delete(key)
  else state.add(key)
}
function showMessage(text) {
  if (disposed) return
  clearTimeout(messageTimer)
  message.value = text
  messageTimer = setTimeout(() => { message.value = null }, 4500)
}

async function loadGroups() {
  groupsController?.abort()
  const controller = new AbortController()
  groupsController = controller
  groupsLoading.value = true
  groupsError.value = ''
  try {
    const data = await requestJson('/api/decision-matrix/city-groups', { signal: controller.signal })
    if (controller.signal.aborted) return
    groups.value = [...new Set((data.rows || [])
      .map((row) => row.city_group)
      .filter((value) => value !== null && value !== undefined && String(value).trim() !== '')
      .map(String))]
  } catch (error) {
    if (!controller.signal.aborted) groupsError.value = error.message
  } finally {
    if (!controller.signal.aborted) groupsLoading.value = false
  }
}
async function loadTypes() {
  typesController?.abort()
  const controller = new AbortController()
  typesController = controller
  typesLoading.value = true
  typesError.value = ''
  try {
    const data = await requestJson('/api/incentive-types', { signal: controller.signal })
    if (!controller.signal.aborted) types.value = data.rows || []
  } catch (error) {
    if (!controller.signal.aborted) {
      types.value = []
      typesError.value = error.message
    }
  } finally {
    if (!controller.signal.aborted) typesLoading.value = false
  }
}
async function loadMatrix() {
  if (selectedGroup.value === null || disposed) return
  matrixController?.abort()
  const controller = new AbortController()
  matrixController = controller
  matrixLoading.value = true
  matrixError.value = ''
  const params = new URLSearchParams({ city_group: selectedGroup.value, include_deactivated: 'true' })
  try {
    const data = await requestJson(`/api/decision-matrix?${params}`, { signal: controller.signal })
    if (controller.signal.aborted) return
    rows.value = data.rows || []
    series.value = data.series || []
    columns.value = data.columns || []
  } catch (error) {
    if (!controller.signal.aborted) matrixError.value = error.message
  } finally {
    if (!controller.signal.aborted) matrixLoading.value = false
  }
}
function selectGroup(group) {
  if (selectedGroup.value === group) {
    collapseGroup()
    return
  }
  selectedGroup.value = group
  rows.value = []
  series.value = []
  columns.value = []
  expandedType.value = null
  openScores.value = new Set()
  historyShown.value = new Set()
  loadMatrix()
}
function collapseGroup() {
  matrixController?.abort()
  selectedGroup.value = null
  expandedType.value = null
  matrixLoading.value = false
  matrixError.value = ''
}
function refresh() {
  loadTypes()
  loadGroups()
  if (selectedGroup.value !== null) loadMatrix()
}
watch(filteredGroups, (visible) => {
  if (selectedGroup.value !== null && !visible.includes(selectedGroup.value)) collapseGroup()
})

function openForm(mode, type = null, item = null) {
  if (selectedGroup.value === null) return
  formError.value = ''
  formContext.value = {
    mode, cityGroup: selectedGroup.value,
    incentiveType: type?.id, typeName: type?.name,
    scoreType: item?.score_type, nextScore: item?.next_score ?? 1,
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
    expandedType.value = String(data.row.incentive_type)
    openScores.value.add(seriesKey(data.row.incentive_type, data.row.score_type))
    showMessage(data.message || 'Score step added successfully.')
    await loadMatrix()
  } catch (error) {
    formError.value = error.message
    if (error.status === 409) {
      // Refresh occupied scores, but never replace the user's chosen score or values.
      await loadMatrix()
    }
  } finally {
    saving.value = false
  }
}
function askDeactivate(type, item, row) {
  deactivateError.value = ''
  deactivateTarget.value = { typeName: type.name, scoreType: item.score_type, row }
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
    await loadMatrix()
  } catch (error) {
    deactivateError.value = error.message
  } finally {
    deactivating.value = false
  }
}

onMounted(() => { loadGroups(); loadTypes() })
onBeforeUnmount(() => {
  disposed = true
  groupsController?.abort()
  typesController?.abort()
  matrixController?.abort()
  clearTimeout(messageTimer)
})
</script>

<template>
  <div class="decision-matrix">
    <div class="head">
      <h1>Decision Matrix</h1>
      <button class="btn btn-ghost" :disabled="busy" @click="refresh">Refresh</button>
    </div>

    <div v-if="typesError" class="banner error" role="alert">
      <strong>Incentive type lookup unavailable</strong>
      <p>{{ typesError }} Adding steps is disabled until the lookup is available.</p>
      <button class="btn btn-ghost btn-sm" :disabled="typesLoading" @click="loadTypes">Retry types</button>
    </div>

    <div v-if="groupsError" class="banner error" role="alert">
      <strong>Could not load city groups</strong>
      <p>{{ groupsError }}</p>
      <button class="btn btn-ghost" @click="loadGroups">Retry city groups</button>
    </div>
    <div v-else-if="groupsLoading" class="card empty" role="status">Loading city groups…</div>
    <section v-else class="card group-directory" aria-labelledby="groups-heading">
      <div class="directory-head">
        <div>
          <h2 id="groups-heading">Select a city group</h2>
          <p class="hint">Click a group to expand its incentive types below.</p>
        </div>
        <span class="badge">{{ countLabel(groups.length, 'group') }}</span>
      </div>
      <label class="search-field">
        <span class="sr-only">Search city groups</span>
        <input v-model="search" type="search" placeholder="Search city groups…" />
      </label>
      <div v-if="!groups.length" class="empty">
        <h3>No city groups found</h3>
        <p>Add city groups to the active cities table to get started.</p>
      </div>
      <div v-else-if="!filteredGroups.length" class="empty">
        <p>No city groups match “{{ search }}”.</p>
        <button class="btn btn-ghost btn-sm" @click="search = ''">Clear search</button>
      </div>
      <ul v-else class="group-list" aria-label="City groups">
        <li v-for="(group, groupIndex) in filteredGroups" :key="group" class="group-item">
          <button
            class="group-button" :aria-label="`City group ${group}`" :aria-expanded="selectedGroup === group"
            :aria-controls="selectedGroup === group ? `matrix-group-${groupIndex}` : undefined"
            @click="selectGroup(group)"
          >
            <span class="chevron" :class="{ open: selectedGroup === group }" aria-hidden="true">›</span>
            <span class="group-label">{{ group }}</span>
            <span class="group-hint">{{ selectedGroup === group ? 'Hide incentive types' : 'View incentive types' }}</span>
          </button>
          <Transition name="group-slide">
            <div
              v-if="selectedGroup === group" :id="`matrix-group-${groupIndex}`" class="group-panel"
              role="region" :aria-label="`${group} decision matrix`"
            >
              <div class="group-panel-inner">
                <div class="group-content">
                  <div class="group-head">
                    <div>
                      <h3>Incentive types</h3>
                      <p v-if="!matrixLoading && !matrixError" class="hint">
                        {{ countLabel(configuredTypes.length, 'incentive type') }} · {{ countLabel(series.length, 'score type') }} · {{ countLabel(activeCount, 'active step') }}
                      </p>
                    </div>
                    <button class="btn btn-primary" :disabled="!canAddType" @click="openForm('type')">+ Add incentive type</button>
                  </div>

                  <div v-if="matrixError" class="banner error" role="alert">
                    <strong>Could not load the matrix</strong>
                    <p>{{ matrixError }}</p>
                    <button class="btn btn-ghost" @click="loadMatrix">Retry matrix</button>
                  </div>
                  <div v-else-if="matrixLoading" class="card empty" role="status">Loading score steps…</div>
                  <template v-else>
                    <p v-if="!typesLoading && !typesError && !types.length" class="notice">
                      No incentive types are available in the reference table. An existing type is required to add a step.
                    </p>
                    <div v-if="!configuredTypes.length" class="card empty">
                      <span class="empty-mark" aria-hidden="true">＋</span>
                      <h3>No incentive types configured yet</h3>
                      <p>Use <strong>Add incentive type</strong> to choose a type and create its first score step.</p>
                    </div>
                    <div v-else class="type-list">
                      <section v-for="(type, typeIndex) in configuredTypes" :key="type.id" class="card type-card">
                        <h3 class="accordion-heading">
                          <button
                            class="accordion-trigger type-trigger"
                            :aria-expanded="expandedType === type.id" :aria-controls="`matrix-type-${groupIndex}-${typeIndex}`"
                            @click="expandedType = expandedType === type.id ? null : type.id"
                          >
                            <span class="chevron" :class="{ open: expandedType === type.id }" aria-hidden="true">›</span>
                            <span class="type-label">{{ type.name }} <small>#{{ type.id }}</small></span>
                            <span class="counts">{{ countLabel(type.scoreTypes.length, 'score type') }} <span aria-hidden="true">·</span> {{ countLabel(type.activeCount, 'active step') }}</span>
                          </button>
                        </h3>
                        <div v-if="expandedType === type.id" :id="`matrix-type-${groupIndex}-${typeIndex}`" class="type-body">
                          <div class="section-toolbar">
                            <span class="eyebrow">Score types</span>
                            <button class="btn btn-ghost btn-sm" :disabled="!type.canAdd || typesLoading" @click="openForm('scoreType', type)">
                              + Add score type
                            </button>
                          </div>
                          <p v-if="!type.canAdd && !typesLoading" class="notice">
                            This incentive type is not available in the reference lookup. Active steps can be deactivated, but no new steps can be added.
                          </p>
                          <section v-for="(item, scoreIndex) in type.scoreTypes" :key="item.key" class="score-card">
                            <h4 class="accordion-heading">
                              <button
                                class="accordion-trigger score-trigger"
                                :aria-expanded="openScores.has(item.key)" :aria-controls="`matrix-score-${groupIndex}-${typeIndex}-${scoreIndex}`"
                                @click="toggleSet(openScores, item.key)"
                              >
                                <span class="chevron" :class="{ open: openScores.has(item.key) }" aria-hidden="true">›</span>
                                <span class="score-name">{{ item.score_type }}</span>
                                <span class="counts">{{ item.active_count }} active <span v-if="item.deactivated_count">· {{ item.deactivated_count }} deactivated</span></span>
                              </button>
                            </h4>
                            <div v-if="openScores.has(item.key)" :id="`matrix-score-${groupIndex}-${typeIndex}-${scoreIndex}`" class="score-body">
                              <div class="section-toolbar step-toolbar">
                                <h5 class="steps-heading">Active steps</h5>
                                <button class="btn btn-primary btn-sm" :disabled="!type.canAdd || typesLoading" @click="openForm('step', type, item)">
                                  + Add step ({{ item.next_score }})
                                </button>
                              </div>
                              <p v-if="!item.activeSteps.length" class="steps-empty">
                                No active steps. Add a new step to start again.
                              </p>
                              <DecisionMatrixStepsTable
                                v-else :steps="item.activeSteps" :label="`${item.score_type} active steps`"
                                @deactivate="askDeactivate(type, item, $event)"
                              />
                              <section v-if="item.deactivated_count" class="history-section" :aria-label="`${item.score_type} deactivated history`">
                                <div class="section-toolbar history-toolbar">
                                  <h5 class="steps-heading">Deactivated steps</h5>
                                  <button
                                    class="btn btn-ghost btn-sm" :aria-expanded="historyShown.has(item.key)"
                                    @click="toggleSet(historyShown, item.key)"
                                  >{{ historyShown.has(item.key) ? 'Hide deactivated' : `Show deactivated (${item.deactivated_count})` }}</button>
                                </div>
                                <DecisionMatrixStepsTable
                                  v-if="historyShown.has(item.key)" :steps="item.deactivatedSteps"
                                  :label="`${item.score_type} deactivated steps`" deactivated
                                />
                              </section>
                            </div>
                          </section>
                        </div>
                      </section>
                      <p v-if="types.length && !availableTypes.length && !typesLoading && !typesError" class="hint all-added">
                        All available incentive types have been added to this city group.
                      </p>
                    </div>
                  </template>
                </div>
              </div>
            </div>
          </Transition>
        </li>
      </ul>
    </section>

    <DecisionMatrixStepForm
      v-if="formContext" :context="formContext" :columns="columns" :types="availableTypes"
      :existing-score-types="existingScoreTypes" :steps="rows" :saving="saving" :error="formError"
      @save="saveStep" @close="closeForm"
    />
    <ModalDialog v-if="deactivateTarget" title-id="deactivate-score-title" :busy="deactivating" @close="closeDeactivate">
      <h2 id="deactivate-score-title">Deactivate score {{ deactivateTarget.row.score }}?</h2>
      <p class="confirm-text">
        Deactivate this step for <strong>{{ selectedGroup }} / {{ deactivateTarget.typeName }} / {{ deactivateTarget.scoreType }}</strong>?
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
.head, .group-head, .directory-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}
.head { margin-bottom: 1.25rem; }
h1 { margin: 0; font-size: 1.5rem; }
h2 { margin: 0; font-size: 1.2rem; overflow-wrap: anywhere; }
h3 { font-size: 1.05rem; }
.hint { margin: 0; font-size: 0.83rem; line-height: 1.5; color: var(--muted); }
.eyebrow { margin: 0 0 0.25rem; color: var(--muted); font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; }
.group-directory { padding: 1.3rem; }
.directory-head { margin-bottom: 1rem; }
.directory-head .hint { margin-top: 0.35rem; }
.search-field { display: block; max-width: 360px; margin-bottom: 1.1rem; }
.search-field input { width: 100%; padding: 0.65rem 0.8rem; font: inherit; font-size: 0.9rem; border: 1px solid var(--border); border-radius: 0.55rem; background: #fbfdfc; color: var(--text); }
.group-list { list-style: none; padding: 0; margin: 0; }
.group-button { display: flex; align-items: center; gap: 1rem; width: 100%; padding: 1rem 0.7rem; border: 0; border-bottom: 1px solid var(--border); background: transparent; text-align: left; color: var(--text); transition: background 0.15s; }
.group-list li:last-child .group-button { border-bottom: 0; }
.group-button:hover { background: #f6faf8; }
.group-button:focus-visible { outline-offset: -3px; }
.group-label { flex: 1; min-width: 0; font-size: 0.95rem; font-weight: 600; overflow-wrap: anywhere; }
.group-hint { color: var(--muted); font-size: 0.8rem; }
.empty { padding: 3.5rem 1.2rem; text-align: center; color: var(--muted); }
.empty h3 { color: var(--text); margin: 0.8rem 0 0.4rem; }
.empty p { margin: 0.45rem 0 1rem; font-size: 0.9rem; line-height: 1.6; }
.empty-mark { display: inline-grid; place-items: center; width: 3rem; height: 3rem; background: var(--accent-soft); border-radius: 0.9rem; color: var(--accent); font-size: 1.7rem; }
.group-head { margin-bottom: 1rem; }
.group-head h3 { margin: 0; }
.group-button[aria-expanded="true"] { background: var(--accent-soft); color: var(--accent-strong); }
.group-panel { display: grid; grid-template-rows: 1fr; opacity: 1; }
.group-panel-inner { min-height: 0; overflow: hidden; }
.group-content { padding: 1.1rem; background: #f8faf9; border-bottom: 1px solid var(--border); }
.group-slide-enter-active, .group-slide-leave-active { transition: grid-template-rows 0.22s ease, opacity 0.22s ease; }
.group-slide-enter-from, .group-slide-leave-to { grid-template-rows: 0fr; opacity: 0; }
.group-slide-leave-active { pointer-events: none; }
.group-head .hint { margin-top: 0.35rem; }
.type-list { display: grid; gap: 1rem; }
.type-card { overflow: hidden; }
.accordion-heading { margin: 0; font-size: 1rem; }
.accordion-trigger { width: 100%; display: flex; align-items: center; gap: 0.8rem; border: 0; background: transparent; color: var(--text); font: inherit; text-align: left; cursor: pointer; }
.type-trigger { padding: 1.1rem 1.25rem; }
.accordion-trigger:hover { background: #f6faf8; }
.accordion-trigger[aria-expanded="true"] { background: #f6faf8; }
.chevron { color: var(--muted); font-size: 1.5rem; line-height: 1; transition: transform 0.15s; }
.chevron.open { transform: rotate(90deg); }
.type-label { font-weight: 700; overflow-wrap: anywhere; min-width: 0; }
.type-label small { margin-left: 0.5rem; font-size: 0.78rem; font-weight: 400; color: var(--muted); }
.counts { margin-left: auto; font-size: 0.8rem; color: var(--muted); font-weight: 400; }
.type-body { padding: 1rem 1.25rem 1.25rem; border-top: 1px solid var(--border); }
.section-toolbar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.65rem; margin-bottom: 0.8rem; }
.section-toolbar .eyebrow { margin: 0; }
.score-card { border: 1px solid var(--border); border-radius: 0.6rem; overflow: hidden; margin-top: 0.75rem; }
.score-trigger { padding: 0.85rem 1rem; font-size: 0.93rem; }
.score-name { font-weight: 600; overflow-wrap: anywhere; min-width: 0; }
.score-body { border-top: 1px solid var(--border); }
.step-toolbar { margin: 0; padding: 0.9rem 1rem; }
.steps-heading { margin: 0; color: var(--text); font-size: 0.85rem; font-weight: 600; }
.history-section { margin-top: 0.8rem; border-top: 1px solid var(--border); background: #fafbfa; }
.history-toolbar { margin: 0; padding: 0.9rem 1rem; }
.steps-empty { margin: 0; padding: 1.5rem 1rem; text-align: center; color: var(--muted); font-size: 0.88rem; border-top: 1px solid var(--border); }
.badge { display: inline-block; padding: 0.22rem 0.6rem; border-radius: 999px; font-size: 0.74rem; font-weight: 600; background: var(--surface-2); color: var(--muted); white-space: nowrap; }
.notice { padding: 0.8rem 1rem; background: var(--warning-soft); color: #886027; border-radius: 0.6rem; font-size: 0.85rem; line-height: 1.5; }
.all-added { text-align: center; }
.confirm-text { line-height: 1.6; overflow-wrap: anywhere; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
button:focus-visible, input:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.accordion-trigger:focus-visible { outline-offset: -3px; }
@media (max-width: 640px) {
  .head, .group-head, .directory-head { align-items: flex-start; flex-wrap: wrap; }
  .group-directory { padding: 0.9rem; }
  .group-content, .type-body { padding: 0.65rem; }
  .group-head > .btn { width: 100%; }
  .accordion-trigger { flex-wrap: wrap; gap: 0.5rem; }
  .counts { width: 100%; margin-left: 1.1rem; }
  .type-trigger { padding: 1rem; }
  .step-toolbar, .history-toolbar { padding: 0.8rem; }
  .group-hint { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .group-slide-enter-active, .group-slide-leave-active { transition: none; }
}
</style>
