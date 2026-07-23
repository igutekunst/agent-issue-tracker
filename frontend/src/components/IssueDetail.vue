<script setup>
import { computed, ref } from 'vue'
import { store } from '../api.js'

const props = defineProps({ issueId: Number })
const emit = defineEmits(['close', 'select'])

const issue = computed(() => store.issueById(props.issueId))
const editing = ref(false)
const draft = ref({})
const newBlockerId = ref(null)

const blockers = computed(() =>
  store.dependencies
    .filter((d) => d.blocked_id === props.issueId)
    .map((d) => d.blocker_id),
)
const blocks = computed(() =>
  store.dependencies
    .filter((d) => d.blocker_id === props.issueId)
    .map((d) => d.blocked_id),
)
const children = computed(() =>
  store.issues.filter((i) => i.parent_id === props.issueId),
)

function startEdit() {
  const i = issue.value
  draft.value = {
    title: i.title,
    description: i.description,
    priority: i.priority,
    status: i.status,
    branch: i.branch || '',
    worktree: i.worktree || '',
    assignee: i.assignee || '',
  }
  editing.value = true
}

async function save() {
  try {
    await store.updateIssue(props.issueId, { ...draft.value })
    editing.value = false
  } catch (e) {
    store.error = e.message
  }
}

async function addBlocker() {
  if (!newBlockerId.value) return
  try {
    await store.addDependency(newBlockerId.value, props.issueId)
    newBlockerId.value = null
  } catch (e) {
    store.error = e.message
  }
}

async function removeBlocker(blockerId) {
  try {
    await store.removeDependency(blockerId, props.issueId)
  } catch (e) {
    store.error = e.message
  }
}

async function del() {
  if (!confirm(`Delete issue #${props.issueId}?`)) return
  try {
    await store.deleteIssue(props.issueId)
    emit('close')
  } catch (e) {
    store.error = e.message
  }
}

function title(id) {
  const i = store.issueById(id)
  return i ? i.title : '(deleted)'
}
</script>

<template>
  <aside class="detail" v-if="issue">
    <div class="detail-head">
      <span class="mono muted">#{{ issue.id }}</span>
      <div class="spacer"></div>
      <button class="ghost" @click="emit('close')">✕</button>
    </div>

    <div v-if="!editing">
      <h2>{{ issue.title }}</h2>
      <div class="chips">
        <span class="chip" :class="'pri-' + issue.priority">{{ issue.priority }}</span>
        <span class="chip st" :class="'st-' + issue.status">{{ issue.status }}</span>
        <span v-if="issue.actionable" class="chip ready">ready</span>
      </div>
      <p class="desc" v-if="issue.description">{{ issue.description }}</p>
      <p class="desc muted" v-else>No description.</p>

      <dl>
        <template v-if="issue.parent_id">
          <dt>parent</dt>
          <dd>
            <a @click="emit('select', issue.parent_id)">#{{ issue.parent_id }} {{ title(issue.parent_id) }}</a>
          </dd>
        </template>
        <template v-if="issue.assignee"><dt>assignee</dt><dd>{{ issue.assignee }}</dd></template>
        <template v-if="issue.branch"><dt>branch</dt><dd class="mono">{{ issue.branch }}</dd></template>
        <template v-if="issue.worktree"><dt>worktree</dt><dd class="mono">{{ issue.worktree }}</dd></template>
      </dl>

      <div class="section">
        <h3>Blocked by</h3>
        <ul class="deps">
          <li v-for="b in blockers" :key="b">
            <a @click="emit('select', b)">#{{ b }} {{ title(b) }}</a>
            <button class="ghost tiny danger" @click="removeBlocker(b)">remove</button>
          </li>
          <li v-if="!blockers.length" class="muted">Nothing — unblocked.</li>
        </ul>
        <div class="add-dep">
          <select v-model.number="newBlockerId">
            <option :value="null">add blocker…</option>
            <option
              v-for="i in store.issues.filter((x) => x.id !== issue.id && !blockers.includes(x.id))"
              :key="i.id"
              :value="i.id"
            >
              #{{ i.id }} {{ i.title }}
            </option>
          </select>
          <button class="ghost" :disabled="!newBlockerId" @click="addBlocker">add</button>
        </div>
      </div>

      <div class="section" v-if="blocks.length">
        <h3>Blocks</h3>
        <ul class="deps">
          <li v-for="b in blocks" :key="b">
            <a @click="emit('select', b)">#{{ b }} {{ title(b) }}</a>
          </li>
        </ul>
      </div>

      <div class="section" v-if="children.length">
        <h3>Sub-issues</h3>
        <ul class="deps">
          <li v-for="c in children" :key="c.id">
            <a @click="emit('select', c.id)">
              <span class="chip" :class="'pri-' + c.priority">{{ c.priority }}</span>
              #{{ c.id }} {{ c.title }}
            </a>
          </li>
        </ul>
      </div>

      <div class="actions">
        <button class="primary" @click="startEdit">Edit</button>
        <button class="ghost danger" @click="del">Delete</button>
      </div>
    </div>

    <!-- Edit mode -->
    <div v-else class="edit">
      <label>Title<input v-model="draft.title" /></label>
      <label>Description<textarea v-model="draft.description" rows="4"></textarea></label>
      <div class="grid2">
        <label>Priority
          <select v-model="draft.priority">
            <option v-for="p in store.meta.priorities" :key="p" :value="p">{{ p }}</option>
          </select>
        </label>
        <label>Status
          <select v-model="draft.status">
            <option v-for="s in store.meta.statuses" :key="s" :value="s">{{ s }}</option>
          </select>
        </label>
      </div>
      <label>Assignee<input v-model="draft.assignee" placeholder="agent / human" /></label>
      <div class="grid2">
        <label>Branch<input v-model="draft.branch" class="mono" /></label>
        <label>Worktree<input v-model="draft.worktree" class="mono" /></label>
      </div>
      <div class="actions">
        <button class="primary" @click="save">Save</button>
        <button class="ghost" @click="editing = false">Cancel</button>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.detail {
  width: 380px;
  flex-shrink: 0;
  border-left: 1px solid var(--border);
  background: var(--bg-elev);
  overflow-y: auto;
  padding: 14px 16px 30px;
}
.detail-head {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}
.detail-head .spacer { flex: 1; }
h2 {
  font-size: 17px;
  margin: 4px 0 10px;
}
h3 {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--text-dim);
  margin: 0 0 6px;
}
.chips {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}
.chip.st { border-color: currentColor; }
.chip.ready { color: var(--status-done); border-color: var(--status-done); }
.desc {
  white-space: pre-wrap;
  line-height: 1.5;
  margin: 0 0 14px;
}
dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 12px;
  margin: 0 0 14px;
  font-size: 13px;
}
dt { color: var(--text-dim); }
dd { margin: 0; }
.section {
  border-top: 1px solid var(--border);
  padding-top: 12px;
  margin-top: 12px;
}
ul.deps {
  list-style: none;
  padding: 0;
  margin: 0 0 8px;
}
ul.deps li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 3px 0;
}
a {
  color: var(--accent);
  cursor: pointer;
  text-decoration: none;
}
a:hover { text-decoration: underline; }
.add-dep {
  display: flex;
  gap: 6px;
}
.add-dep button { width: auto; }
.tiny {
  padding: 1px 7px;
  font-size: 11px;
}
.actions {
  display: flex;
  gap: 8px;
  margin-top: 18px;
}
.actions button { width: auto; }
.edit label {
  display: block;
  margin-bottom: 10px;
  font-size: 12px;
  color: var(--text-dim);
}
.edit label input,
.edit label textarea,
.edit label select {
  margin-top: 4px;
}
.grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
