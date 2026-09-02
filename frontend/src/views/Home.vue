<script setup>
import { ref, onMounted } from 'vue'

const apiStatus = ref('checking...')
const db = ref(null)

onMounted(async () => {
  try {
    const res = await fetch('/api/health')
    const data = await res.json()
    apiStatus.value = data.status
  } catch {
    apiStatus.value = 'unreachable'
  }

  try {
    const res = await fetch('/api/health/db')
    const data = await res.json()
    db.value = { ok: res.ok, detail: data.detail || data.message || 'error' }
  } catch {
    db.value = { ok: false, detail: 'backend unreachable' }
  }
})
</script>

<template>
  <div class="card home">
    <h1>Welcome to Incentive</h1>
    <p>FastAPI + Vue starter with MySQL.</p>
    <div class="status">
      <span>API: <strong>{{ apiStatus }}</strong></span>
      <span v-if="db">
        Database:
        <strong :class="db.ok ? 'ok' : 'err'">{{ db.ok ? 'connected' : db.detail }}</strong>
      </span>
    </div>
    <div class="links">
      <router-link to="/cities" class="btn btn-primary">Go to Cities →</router-link>
      <router-link to="/business-entities" class="btn btn-ghost">Business Entities →</router-link>
    </div>
  </div>
</template>

<style scoped>
.home {
  padding: 2rem;
  max-width: 560px;
}
.home h1 {
  margin: 0 0 0.4rem;
  color: var(--text);
}
.home p {
  color: var(--muted);
  margin: 0.3rem 0;
}
.status {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin: 1.25rem 0;
}
.links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin-top: 0.5rem;
}
.home .btn {
  display: inline-block;
  text-decoration: none;
}
.ok {
  color: var(--ok-text);
}
.err {
  color: var(--danger);
}
</style>
