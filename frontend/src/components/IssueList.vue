<script setup>
import { ref, computed } from 'vue'
import { store } from '../api.js'

const emit = defineEmits(['select'])
const showNew = ref(false)
const draft = ref(newDraft())
const collapsed = ref(new Set())

const PRI_RANK = { P0: 0, P1: 1, P2: 2, P3: 3 }

// Flatten the parent/child hierarchy into ordered rows carrying a depth, so the
// table can render as an indented tree. Siblings are ordered by priority then id.
const rows = computed(() => {
  const byParent = new Map()
  for (const i of store.issues) {
    const p = i.parent_id ?? null
    if (!byParent.has(p)) byParent.set(p, [])
    byParent.get(p).push(i)
  }
  for (const arr of byParent.values()) {
    arr.sort(
      (a, b) => PRI_RANK[a.priority] - PRI_RANK[b.priority] || a.id - b.id,
    )
  }
  const out = []
  const walk = (parentId, depth) => {
    for (const issue of byParent.get(parentId) || []) {
      const kids = byParent.get(issue.id) || []
      out.push({ issue, depth, childCount: kids.length })
      if (kids.length && !collapsed.value.has(issue.id)) walk(issue.id, depth + 1)
    }
  }
  walk(null, 0)
  return out
})

function toggle(id) {
  const next = new Set(collapsed.value)
  next.has(id) ? next.delete(id) : next.add(id)
  collapsed.value = next
}

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
        <tr
          v-for="row in rows"
          :key="row.issue.id"
          @click="emit('select', row.issue.id)"
        >
          <td class="mono">#{{ row.issue.id }}</td>
          <td>
            <span class="chip" :class="'pri-' + row.issue.priority">
              {{ row.issue.priority }}
            </span>
          </td>
          <td>
            <span class="title-cell" :style="{ paddingLeft: row.depth * 20 + 'px' }">
              <button
                v-if="row.childCount"
                class="twisty"
                :title="collapsed.has(row.issue.id) ? 'expand' : 'collapse'"
                @click.stop="toggle(row.issue.id)"
              >
                {{ collapsed.has(row.issue.id) ? '▸' : '▾' }}
              </button>
              <span v-else class="twisty-spacer"></span>
              <span :class="{ done: row.issue.status === 'done' }">
                {{ row.issue.title }}
              </span>
              <span v-if="row.childCount" class="muted cc" title="sub-issues">
                ({{ row.childCount }})
              </span>
              <span v-if="row.issue.comment_count" class="muted cc" title="comments">
                💬 {{ row.issue.comment_count }}
              </span>
            </span>
          </td>
          <td>
            <select
              class="status-sel"
              :class="'st-' + row.issue.status"
              :value="row.issue.status"
              @click.stop
              @change="setStatus(row.issue, $event.target.value)"
            >
              <option v-for="s in store.meta.statuses" :key="s" :value="s">{{ s }}</option>
            </select>
          </td>
          <td>
            <span
              v-if="row.issue.blocked_count"
              class="chip pri-P0"
              title="incomplete blockers"
            >
              ⛔ {{ row.issue.blocked_count }}
            </span>
            <span
              v-else-if="row.issue.actionable"
              class="chip"
              style="color: var(--status-done); border-color: var(--status-done)"
            >
              ready
            </span>
          </td>
          <td class="mono muted">{{ row.issue.assignee || '' }}</td>
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
.cc {
  font-size: 12px;
  margin-left: 6px;
}
.title-cell {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.twisty {
  width: 18px;
  height: 18px;
  padding: 0;
  margin-right: 4px;
  border: none;
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  line-height: 1;
  flex-shrink: 0;
}
.twisty:hover {
  color: var(--text);
}
.twisty-spacer {
  display: inline-block;
  width: 18px;
  margin-right: 4px;
  flex-shrink: 0;
}
.status-sel {
  width: auto;
  padding: 2px 6px;
  font-size: 12px;
  font-weight: 600;
}
</style>
