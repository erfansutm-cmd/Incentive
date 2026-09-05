<template>
  <div class="app">
    <header class="topbar">
      <router-link to="/" class="brand">🌱 Incentive</router-link>
      <nav>
        <router-link to="/">Home</router-link>
        <router-link to="/cities">Cities</router-link>
        <router-link to="/business-entities">Business Entities</router-link>
      </nav>
    </header>
    <main class="page" :class="{ 'page-wide': $route.meta.wide }">
      <router-view />
    </main>
  </div>
</template>

<style>
:root {
  /* soft, low-saturation palette — easy on the eyes */
  --bg: #f5f7f6;
  --surface: #ffffff;
  --surface-2: #eef3f0;
  --border: #e3e9e5;
  --text: #34413b;
  --muted: #71847b;
  --accent: #3d8b6d;
  --accent-strong: #2f7057;
  --accent-soft: #e6f1ec;
  --accent-ring: rgba(61, 139, 109, 0.18);
  --ok-text: #2c7a58;
  --inactive-text: #7a8a82;
  --danger: #cf5a5a;
  --danger-strong: #b64949;
  --danger-soft: #f7e8e8;
  --warning: #b97f2e;
  --warning-soft: #f6edde;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  color: var(--text);
  background: var(--bg);
}

.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.topbar {
  position: sticky;
  top: 0;
  z-index: 40;
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 0.7rem 2rem;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border);
}
.topbar .brand {
  font-weight: 700;
  font-size: 1.1rem;
  color: var(--accent-strong);
  text-decoration: none;
  letter-spacing: -0.01em;
}
.topbar nav {
  display: flex;
  gap: 0.25rem;
}
.topbar nav a {
  color: var(--muted);
  text-decoration: none;
  padding: 0.4rem 0.9rem;
  border-radius: 999px;
  font-weight: 500;
  font-size: 0.9rem;
  transition: background 0.15s ease, color 0.15s ease;
}
.topbar nav a:hover {
  background: var(--surface-2);
  color: var(--text);
}
.topbar nav a.router-link-active {
  background: var(--accent-soft);
  color: var(--accent-strong);
}

.page {
  flex: 1;
  width: 100%;
  max-width: 1100px;
  margin: 0 auto;
  padding: 2rem 1.5rem 3rem;
}
/* wide tables (e.g. business entities with many columns) */
.page-wide {
  max-width: 1500px;
}

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 0.9rem;
  box-shadow: 0 1px 2px rgba(20, 40, 30, 0.04), 0 8px 24px rgba(20, 40, 30, 0.05);
}

button {
  cursor: pointer;
  font-family: inherit;
}

.btn {
  border: none;
  border-radius: 0.6rem;
  padding: 0.55rem 1.1rem;
  font-size: 0.92rem;
  font-weight: 600;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.05s ease;
}
.btn:active {
  transform: translateY(1px);
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--accent);
  color: #fff;
}
.btn-primary:hover {
  background: var(--accent-strong);
}

.btn-ghost {
  background: #fff;
  color: var(--text);
  border: 1px solid var(--border);
}
.btn-ghost:hover {
  background: var(--surface-2);
}

.btn-danger {
  background: var(--danger);
  color: #fff;
}
.btn-danger:hover {
  background: var(--danger-strong);
}

.btn-danger-soft {
  background: var(--danger-soft);
  color: var(--danger-strong);
  border: 1px solid #eecdcd;
}
.btn-danger-soft:hover {
  background: #f3dcdc;
  border-color: #e5b8b8;
}

.btn-sm {
  padding: 0.32rem 0.7rem;
  font-size: 0.82rem;
  border-radius: 0.5rem;
}

/* toast message */
.toast {
  position: fixed;
  right: 1.5rem;
  bottom: 1.5rem;
  padding: 0.8rem 1.15rem;
  border-radius: 0.6rem;
  color: #fff;
  font-weight: 600;
  font-size: 0.9rem;
  box-shadow: 0 8px 24px rgba(20, 40, 30, 0.18);
  z-index: 60;
}
.toast.ok {
  background: var(--accent);
}
.toast.error {
  background: var(--danger);
}

/* error banner */
.banner {
  padding: 1rem 1.25rem;
  border-radius: 0.8rem;
  margin-bottom: 1.25rem;
}
.banner.error {
  background: var(--danger-soft);
  border: 1px solid #f0caca;
  color: #8c3030;
}
.banner.error p {
  margin: 0.25rem 0 0.75rem;
}

/* modal overlay + popups */
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(30, 42, 36, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  z-index: 50;
}
.modal {
  background: #fff;
  border-radius: 0.9rem;
  width: 100%;
  max-width: 460px;
  padding: 1.5rem;
  box-shadow: 0 20px 60px rgba(20, 40, 30, 0.25);
  max-height: 85vh;
  overflow-y: auto;
}
.modal h2 {
  margin: 0 0 1rem;
  color: var(--text);
  font-size: 1.15rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin-bottom: 0.85rem;
}
.field span {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text);
}
.field .opt {
  font-weight: 400;
  color: var(--muted);
  font-style: normal;
}
.field input {
  padding: 0.55rem 0.7rem;
  border: 1px solid var(--border);
  border-radius: 0.55rem;
  font-size: 0.95rem;
  outline: none;
  color: var(--text);
  background: #fbfdfc;
}
.field input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-ring);
  background: #fff;
}

.modal .actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.6rem;
  margin-top: 1.25rem;
}
</style>
