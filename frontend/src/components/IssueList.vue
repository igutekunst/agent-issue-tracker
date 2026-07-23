<script setup>
import { ref } from 'vue'
import { store } from '../api.js'

const emit = defineEmits(['select'])
const showNew = ref(false)
const draft = ref(newDraft())

function newDraft() {
  return { title: '', description: '', priority: 'P2', parent_id: null }
}

async function create() {
  if (!draft.value.title.trim()) return
  try {
    const payload = { ...draft.value }
    if (!payload.parent_id) delete payload.parent_id
    await store.createIssue(payload)
    draft.value = newDraft()
    showNew.value = false
  } catch (e) {
    store.error = e.message
  }
}

async function setStatus(issue, status) {
  try {
    await store.updateIssue(issue.id, { status })
  } catch (e) {
    store.error = e.message
  }
}
</script>

<template>
  <div class="list-wrap">
    <div class="list-head">
      <h2>Issues <span class="muted">({{ store.issues.length }})</span></h2>
      <button class="primary" @click="showNew = !showNew">
        {{ showNew ? 'Cancel' : '+ New issue' }}
      </button>
    </div>

    <div v-if="showNew" class="new-form">
      <input v-model="draft.title" placeholder="Title" @keyup.enter="create" />
      <textarea
        v-model="draft.description"
        placeholder="Description (optional)"
        rows="2"
      ></textarea>
      <div class="row">
        <select v-model="draft.priority">
          <option v-for="p in store.meta.priorities" :key="p" :value="p">{{ p }}</option>
        </select>
        <select v-model.number="draft.parent_id">
          <option :value="null">— no parent —</option>
          <option v-for="i in store.issues" :key="i.id" :value="i.id">
            #{{ i.id }} {{ i.title }}
          </option>
        </select>
        <button class="primary" @click="create">Create</button>
      </div>
    </div>

    <table class="issues">
      <thead>
        <tr>
          <th>#</th>
          <th>pri</th>
          <th>title</th>
          <th>status</th>
          <th>deps</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="i in store.issues" :key="i.id" @click="emit('select', i.id)">
          <td class="mono">#{{ i.id }}</td>
          <td><span class="chip" :class="'pri-' + i.priority">{{ i.priority }}</span></td>
          <td>
            <span :class="{ done: i.status === 'done' }">{{ i.title }}</span>
            <span v-if="i.parent_id" class="muted"> ↳ #{{ i.parent_id }}</span>
          </td>
          <td>
            <select
              class="status-sel"
              :class="'st-' + i.status"
              :value="i.status"
              @click.stop
              @change="setStatus(i, $event.target.value)"
            >
              <option v-for="s in store.meta.statuses" :key="s" :value="s">{{ s }}</option>
            </select>
          </td>
          <td>
            <span v-if="i.blocked_count" class="chip pri-P0" title="incomplete blockers">
              ⛔ {{ i.blocked_count }}
            </span>
            <span v-else-if="i.actionable" class="chip" style="color: var(--status-done); border-color: var(--status-done)">
              ready
            </span>
          </td>
          <td class="mono muted">{{ i.assignee || '' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.list-wrap {
  padding: 16px 20px;
  max-width: 1000px;
}
.list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
h2 {
  margin: 4px 0 12px;
  font-size: 18px;
}
.new-form {
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.new-form .row {
  display: flex;
  gap: 8px;
}
.new-form .row select {
  flex: 1;
}
.new-form .row button {
  width: auto;
  white-space: nowrap;
}
table.issues {
  width: 100%;
  border-collapse: collapse;
}
th {
  text-align: left;
  color: var(--text-dim);
  font-weight: 600;
  font-size: 12px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}
td {
  padding: 7px 8px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
tbody tr {
  cursor: pointer;
}
tbody tr:hover {
  background: var(--bg-elev);
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.done {
  text-decoration: line-through;
  color: var(--text-dim);
}
.status-sel {
  width: auto;
  padding: 2px 6px;
  font-size: 12px;
  font-weight: 600;
}
</style>
