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
    <p>API status: <strong>{{ apiStatus }}</strong></p>
    <p v-if="db">
      Database:
      <strong :class="db.ok ? 'ok' : 'err'">{{ db.ok ? 'connected' : db.detail }}</strong>
    </p>
    <router-link to="/cities" class="btn btn-primary">Go to Cities →</router-link>
  </div>
</template>

<style scoped>
.home {
  padding: 2rem;
  max-width: 560px;
}
.home h1 {
  margin-top: 0;
  color: var(--green-900);
}
.home .btn {
  display: inline-block;
  margin-top: 1rem;
  text-decoration: none;
}
.ok {
  color: var(--green-600);
}
.err {
  color: var(--danger);
}
</style>
