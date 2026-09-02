<script setup>
import { ref, onMounted } from 'vue'

const apiStatus = ref('checking...')

onMounted(async () => {
  try {
    const res = await fetch('/api/health')
    const data = await res.json()
    apiStatus.value = data.status
  } catch {
    apiStatus.value = 'unreachable'
  }
})
</script>

<template>
  <main class="container">
    <h1>Incentive</h1>
    <p>FastAPI + Vue starter</p>
    <p>Backend status: <strong>{{ apiStatus }}</strong></p>
  </main>
</template>

<style>
body {
  margin: 0;
  font-family: system-ui, sans-serif;
  background: #0f172a;
  color: #e2e8f0;
}
.container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}
</style>
