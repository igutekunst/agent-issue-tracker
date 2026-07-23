<script setup>
import { computed, ref, watch, onMounted } from 'vue'
import { renderMarkdown } from '../markdown.js'
import { store } from '../api.js'

const props = defineProps({
  issueId: Number,
  fullscreen: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'select'])

const issue = computed(() => store.issueById(props.issueId))

const renderedDescription = computed(() => renderMarkdown(issue.value?.description))
const editing = ref(false)
const draft = ref({})
const newBlockerId = ref(null)

// --- Comments -------------------------------------------------------------
const comments = ref([])
const newComment = ref('')
const commentAuthor = ref('human')

async function loadComments() {
  if (props.issueId == null) {
    comments.value = []
    return
  }
  try {
    comments.value = await store.getComments(props.issueId)
  } catch (e) {
    store.error = e.message
  }
}

async function postComment() {
  const body = newComment.value.trim()
  if (!body) return
  try {
    await store.addComment(props.issueId, {
      body,
      author: commentAuthor.value.trim() || 'human',
    })
    newComment.value = ''
    await loadComments()
  } catch (e) {
    store.error = e.message
  }
}

async function removeComment(id) {
  try {
    await store.deleteComment(id)
    await loadComments()
  } catch (e) {
    store.error = e.message
  }
}

onMounted(loadComments)
// Refetch when switching issues or when any change event arrives (live updates).
watch(() => [props.issueId, store.changeVersion], loadComments)

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
  <aside class="detail" :class="{ 'detail--full': fullscreen }" v-if="issue">
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
      <div
        class="desc markdown-body"
        v-if="renderedDescription"
        v-html="renderedDescription"
      ></div>
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

      <div class="section comments">
        <h3>
          Notes / comments
          <span v-if="comments.length" class="muted">({{ comments.length }})</span>
        </h3>
        <div v-for="c in comments" :key="c.id" class="comment">
          <div class="chead">
            <span class="cauthor">{{ c.author }}</span>
            <span class="muted small">{{ c.created_at.replace('T', ' ') }}</span>
            <span class="cspacer"></span>
            <button
              class="ghost tiny danger"
              title="delete comment"
              @click="removeComment(c.id)"
            >
              ✕
            </button>
          </div>
          <div class="cbody markdown-body" v-html="renderMarkdown(c.body)"></div>
        </div>
        <p v-if="!comments.length" class="muted">No comments yet.</p>

        <div class="add-comment">
          <textarea
            v-model="newComment"
            placeholder="Add a note… (markdown supported · ⌘/Ctrl+Enter to post)"
            rows="3"
            @keydown.meta.enter="postComment"
            @keydown.ctrl.enter="postComment"
          ></textarea>
          <div class="add-comment-row">
            <input v-model="commentAuthor" class="author-input" placeholder="author" />
            <button class="primary" :disabled="!newComment.trim()" @click="postComment">
              Comment
            </button>
          </div>
        </div>
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
.detail--full {
  position: fixed;
  inset: 0;
  width: 100%;
  border-left: none;
  z-index: 50;
  padding-bottom: 60px;
}
/* On genuinely small screens, the sidebar always goes full-screen. */
@media (max-width: 760px) {
  .detail {
    position: fixed;
    inset: 0;
    width: 100%;
    border-left: none;
    z-index: 50;
    padding-bottom: 60px;
  }
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
  line-height: 1.55;
  margin: 0 0 14px;
}
.desc.muted {
  white-space: pre-wrap;
}
/* Markdown element styles live in styles.css (.markdown-body). */
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

/* Comments */
.comment {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-elev2);
  padding: 8px 10px;
  margin-bottom: 8px;
}
.chead {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.cauthor {
  font-weight: 600;
  color: var(--accent);
  font-size: 13px;
}
.cspacer { flex: 1; }
.chead .tiny { opacity: 0; transition: opacity 0.12s; }
.comment:hover .chead .tiny { opacity: 1; }
.cbody { font-size: 13px; }
.add-comment {
  margin-top: 10px;
}
.add-comment textarea {
  margin-bottom: 6px;
}
.add-comment-row {
  display: flex;
  gap: 6px;
}
.author-input {
  width: 110px;
  flex-shrink: 0;
  font-size: 12px;
}
.add-comment-row button {
  width: auto;
  flex: 1;
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
