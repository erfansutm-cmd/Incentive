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

const isActive = computed(() => {
  if (!plan.value) return false
  const v = plan.value.deactivated_at
  return v === null || v === undefined || v === ''
})

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

async function load() {
  loading.value = true
  error.value = ''
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
</style>
