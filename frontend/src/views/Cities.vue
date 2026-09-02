<script setup>
import { ref, computed, onMounted } from 'vue'

const columns = ref([])
const rows = ref([])
const loading = ref(true)
const error = ref('')

const showModal = ref(false)
const editing = ref(null)
const form = ref({})
const saving = ref(false)

const confirmDelete = ref(null)
const deleting = ref(false)

const message = ref(null)
let msgTimer = null

const pkColumn = computed(() => columns.value.find((c) => c.key === 'PRI'))

// Editable columns = everything except the auto-increment primary key.
const editableColumns = computed(() =>
  columns.value.filter(
    (c) => !(c.key === 'PRI' && (c.extra || '').includes('auto_increment'))
  )
)

function pkValue(row) {
  const pk = pkColumn.value
  return pk ? row[pk.name] : undefined
}

function inputType(col) {
  const t = (col.type || '').toLowerCase()
  if (/(int|decimal|float|double|real|numeric)/.test(t)) return 'number'
  return 'text'
}

function showMessage(type, text) {
  message.value = { type, text }
  if (msgTimer) clearTimeout(msgTimer)
  msgTimer = setTimeout(() => (message.value = null), 4000)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch('/api/cities')
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Failed to load cities')
    columns.value = data.columns || []
    rows.value = data.rows || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function openAdd() {
  editing.value = null
  form.value = {}
  for (const c of editableColumns.value) form.value[c.name] = c.default ?? ''
  showModal.value = true
}

function openEdit(row) {
  editing.value = row
  form.value = {}
  for (const c of editableColumns.value) form.value[c.name] = row[c.name] ?? ''
  showModal.value = true
}

async function save() {
  saving.value = true
  try {
    const payload = {}
    for (const c of editableColumns.value) payload[c.name] = form.value[c.name]

    const isEdit = Boolean(editing.value)
    const url = isEdit
      ? `/api/cities/${encodeURIComponent(pkValue(editing.value))}`
      : '/api/cities'

    const res = await fetch(url, {
      method: isEdit ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Save failed')

    showModal.value = false
    showMessage('ok', data.message || 'Saved')
    await load()
  } catch (e) {
    showMessage('error', e.message)
  } finally {
    saving.value = false
  }
}

function askDelete(row) {
  confirmDelete.value = row
}

async function doDelete() {
  const row = confirmDelete.value
  deleting.value = true
  try {
    const res = await fetch(`/api/cities/${encodeURIComponent(pkValue(row))}`, {
      method: 'DELETE',
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.message || data.detail || 'Delete failed')

    confirmDelete.value = null
    showMessage('ok', data.message || 'Deleted')
    await load()
  } catch (e) {
    confirmDelete.value = null
    showMessage('error', e.message)
  } finally {
    deleting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="head">
      <div>
        <h1>Cities</h1>
        <p class="sub">Manage the <code>cities</code> table — all columns are shown.</p>
      </div>
      <button class="btn btn-primary" @click="openAdd">+ Add city</button>
    </div>

    <div v-if="error" class="banner error">
      <strong>Could not load cities</strong>
      <p>{{ error }}</p>
      <button class="btn btn-ghost" @click="load">Retry</button>
    </div>

    <div v-else-if="loading" class="card empty">Loading…</div>

    <div v-else class="card table-card">
      <table>
        <thead>
          <tr>
            <th v-for="c in columns" :key="c.name">{{ c.name }}</th>
            <th class="actions-col">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="i">
            <td v-for="c in columns" :key="c.name">{{ row[c.name] ?? '' }}</td>
            <td class="actions-col">
              <button class="btn btn-ghost btn-sm" @click="openEdit(row)">Edit</button>
              <button class="btn btn-danger btn-sm" @click="askDelete(row)">Delete</button>
            </td>
          </tr>
          <tr v-if="rows.length === 0">
            <td class="empty" :colspan="columns.length + 1">No cities yet — add the first one.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- add / edit popup -->
    <div v-if="showModal" class="overlay" @click.self="showModal = false">
      <div class="modal">
        <h2>{{ editing ? 'Edit city' : 'Add city' }}</h2>
        <label v-for="c in editableColumns" :key="c.name" class="field">
          <span>
            {{ c.name }}
            <em v-if="c.nullable" class="opt">(optional)</em>
            <em class="opt type">{{ c.type }}</em>
          </span>
          <input v-model="form[c.name]" :type="inputType(c)" :placeholder="c.type" />
        </label>
        <div class="actions">
          <button class="btn btn-ghost" @click="showModal = false">Cancel</button>
          <button class="btn btn-primary" :disabled="saving" @click="save">
            {{ saving ? 'Saving…' : 'Save' }}
          </button>
        </div>
      </div>
    </div>

    <!-- delete confirm popup -->
    <div v-if="confirmDelete" class="overlay" @click.self="confirmDelete = null">
      <div class="modal">
        <h2>Delete city?</h2>
        <p>This will permanently remove this row from the database. Are you sure?</p>
        <div class="actions">
          <button class="btn btn-ghost" @click="confirmDelete = null">Cancel</button>
          <button class="btn btn-danger" :disabled="deleting" @click="doDelete">
            {{ deleting ? 'Deleting…' : 'Yes, delete' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="message" class="toast" :class="message.type">{{ message.text }}</div>
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
  color: var(--green-900);
}
.sub {
  margin: 0.3rem 0 0;
  color: var(--muted);
}
.sub code {
  background: var(--green-100);
  padding: 0.1rem 0.4rem;
  border-radius: 0.3rem;
  color: var(--green-800);
}

.empty {
  padding: 3rem 1rem;
  text-align: center;
  color: var(--muted);
}

.table-card {
  overflow: hidden;
}
table {
  width: 100%;
  border-collapse: collapse;
}
thead th {
  text-align: left;
  padding: 0.85rem 1rem;
  background: var(--green-700);
  color: #fff;
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  white-space: nowrap;
}
tbody td {
  padding: 0.7rem 1rem;
  border-top: 1px solid var(--green-100);
  font-size: 0.95rem;
}
tbody tr:nth-child(even) {
  background: var(--green-50);
}
tbody tr:hover {
  background: var(--green-100);
}
.actions-col {
  text-align: right;
  white-space: nowrap;
}
.actions-col .btn + .btn {
  margin-left: 0.4rem;
}
.field .type {
  margin-left: 0.4rem;
}
</style>
