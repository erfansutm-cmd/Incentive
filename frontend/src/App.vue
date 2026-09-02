<template>
  <div class="app">
    <header class="topbar">
      <router-link to="/" class="brand">🌱 Incentive</router-link>
      <nav>
        <router-link to="/">Home</router-link>
        <router-link to="/cities">Cities</router-link>
      </nav>
    </header>
    <main class="page">
      <router-view />
    </main>
  </div>
</template>

<style>
:root {
  --green-50: #ecfdf5;
  --green-100: #d1fae5;
  --green-200: #a7f3d0;
  --green-400: #34d399;
  --green-500: #10b981;
  --green-600: #059669;
  --green-700: #047857;
  --green-800: #065f46;
  --green-900: #064e3b;
  --danger: #dc2626;
  --danger-dark: #b91c1c;
  --text: #064e3b;
  --muted: #6b7280;
  --card: #ffffff;
  --border: #d1fae5;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
  color: var(--text);
  background: linear-gradient(160deg, #f0fdf4, #d1fae5 60%, #a7f3d0);
  min-height: 100vh;
}

.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.topbar {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 0.9rem 2rem;
  background: var(--green-800);
  color: #fff;
  box-shadow: 0 2px 10px rgba(6, 78, 59, 0.25);
}
.topbar .brand {
  font-weight: 700;
  font-size: 1.15rem;
  color: #fff;
  text-decoration: none;
}
.topbar nav {
  display: flex;
  gap: 0.5rem;
}
.topbar nav a {
  color: var(--green-100);
  text-decoration: none;
  padding: 0.4rem 0.9rem;
  border-radius: 0.5rem;
  font-weight: 500;
  transition: background 0.15s ease;
}
.topbar nav a:hover {
  background: rgba(255, 255, 255, 0.12);
}
.topbar nav a.router-link-active {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
}

.page {
  flex: 1;
  width: 100%;
  max-width: 1100px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
}

.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 1rem;
  box-shadow: 0 6px 24px rgba(6, 78, 59, 0.08);
}

button {
  cursor: pointer;
  font-family: inherit;
}

.btn {
  border: none;
  border-radius: 0.6rem;
  padding: 0.55rem 1.1rem;
  font-size: 0.95rem;
  font-weight: 600;
  transition: transform 0.05s ease, background 0.15s ease;
}
.btn:active {
  transform: translateY(1px);
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--green-600);
  color: #fff;
}
.btn-primary:hover {
  background: var(--green-700);
}

.btn-ghost {
  background: #fff;
  color: var(--green-800);
  border: 1px solid var(--green-200);
}
.btn-ghost:hover {
  background: var(--green-50);
}

.btn-danger {
  background: var(--danger);
  color: #fff;
}
.btn-danger:hover {
  background: var(--danger-dark);
}

.btn-sm {
  padding: 0.35rem 0.7rem;
  font-size: 0.85rem;
  border-radius: 0.5rem;
}

/* toast message */
.toast {
  position: fixed;
  right: 1.5rem;
  bottom: 1.5rem;
  padding: 0.9rem 1.25rem;
  border-radius: 0.7rem;
  color: #fff;
  font-weight: 600;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
  z-index: 60;
}
.toast.ok {
  background: var(--green-600);
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
  background: #fee2e2;
  border: 1px solid #fca5a5;
  color: #7f1d1d;
}
.banner.error p {
  margin: 0.25rem 0 0.75rem;
}

/* modal overlay + popups */
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(6, 46, 35, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  z-index: 50;
}
.modal {
  background: #fff;
  border-radius: 1rem;
  width: 100%;
  max-width: 460px;
  padding: 1.5rem;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  max-height: 85vh;
  overflow-y: auto;
}
.modal h2 {
  margin: 0 0 1rem;
  color: var(--green-900);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin-bottom: 0.9rem;
}
.field span {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--green-900);
}
.field .opt {
  font-weight: 400;
  color: var(--muted);
}
.field input {
  padding: 0.55rem 0.7rem;
  border: 1px solid var(--green-200);
  border-radius: 0.55rem;
  font-size: 0.95rem;
  outline: none;
}
.field input:focus {
  border-color: var(--green-500);
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.15);
}

.modal .actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.6rem;
  margin-top: 1.25rem;
}
</style>
