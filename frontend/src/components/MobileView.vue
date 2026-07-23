<script setup>
import { computed } from 'vue'
import { store } from '../api.js'

// A touch-friendly drill-down navigator. The root level shows epics (top-level
// issues); one tap on an issue that has sub-issues drills down a level; tapping
// a leaf opens its detail. The drill `path` is owned by the parent (App) so it
// can be mirrored into the browser History API — that makes the mobile
// swipe-right / hardware Back gesture walk back up the hierarchy.
const props = defineProps({ path: { type: Array, default: () => [] } })
const emit = defineEmits(['drill', 'select', 'up', 'goto', 'root'])

const PRI_RANK = { P0: 0, P1: 1, P2: 2, P3: 3 }

const currentParentId = computed(() =>
  props.path.length ? props.path[props.path.length - 1] : null,
)
const currentIssue = computed(() =>
  currentParentId.value != null ? store.issueById(currentParentId.value) : null,
)
const crumbs = computed(() =>
  props.path.map((id) => store.issueById(id)).filter(Boolean),
)

const children = computed(() =>
  store.issues
    .filter((i) => (i.parent_id ?? null) === currentParentId.value)
    .sort((a, b) => PRI_RANK[a.priority] - PRI_RANK[b.priority] || a.id - b.id),
)

function childCount(id) {
  return store.issues.filter((i) => i.parent_id === id).length
}

function tap(issue) {
  if (childCount(issue.id) > 0) emit('drill', issue.id)
  else emit('select', issue.id)
}
</script>

<template>
  <div class="mobile-nav">
    <!-- Breadcrumb -->
    <div class="crumbs">
      <button class="crumb" :class="{ active: !crumbs.length }" @click="emit('root')">
        🗂 Epics
      </button>
      <template v-for="(c, idx) in crumbs" :key="c.id">
        <span class="sep">›</span>
        <button
          class="crumb"
          :class="{ active: idx === crumbs.length - 1 }"
          @click="emit('goto', idx)"
        >
          #{{ c.id }}
        </button>
      </template>
    </div>

    <!-- Current parent header (when drilled in) -->
    <div v-if="currentIssue" class="parent-card" @click="emit('select', currentIssue.id)">
      <div class="pc-top">
        <span class="chip" :class="'pri-' + currentIssue.priority">
          {{ currentIssue.priority }}
        </span>
        <span class="chip st" :class="'st-' + currentIssue.status">
          {{ currentIssue.status }}
        </span>
        <span class="spacer"></span>
        <button class="ghost small" @click.stop="emit('up')">↑ up</button>
      </div>
      <div class="pc-title">#{{ currentIssue.id }} {{ currentIssue.title }}</div>
      <div class="pc-hint muted">tap for full details ›</div>
    </div>

    <div v-else class="level-label muted">
      {{ children.length }} epic{{ children.length === 1 ? '' : 's' }} · tap to drill in
    </div>

    <!-- Children as large tap targets -->
    <div class="cards">
      <button v-for="i in children" :key="i.id" class="card" @click="tap(i)">
        <span class="chip" :class="'pri-' + i.priority">{{ i.priority }}</span>
        <div class="card-main">
          <div class="card-title" :class="{ done: i.status === 'done' }">
            {{ i.title }}
          </div>
          <div class="card-meta">
            <span class="mono muted">#{{ i.id }}</span>
            <span class="chip st tiny" :class="'st-' + i.status">{{ i.status }}</span>
            <span v-if="i.blocked_count" class="chip pri-P0 tiny">⛔ {{ i.blocked_count }}</span>
            <span v-else-if="i.actionable" class="chip ready tiny">ready</span>
            <span v-if="i.comment_count" class="muted small">💬 {{ i.comment_count }}</span>
          </div>
        </div>
        <span class="card-right">
          <span v-if="childCount(i.id)" class="drilldown">{{ childCount(i.id) }} ›</span>
          <span v-else class="leaf muted">›</span>
        </span>
      </button>

      <div v-if="!children.length" class="empty muted">
        No sub-issues here.
        <span v-if="currentIssue">Tap the card above for its details.</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mobile-nav {
  padding: 10px 12px 40px;
}
.crumbs {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
  margin-bottom: 12px;
}
.crumb {
  border: none;
  background: transparent;
  color: var(--accent);
  padding: 6px 6px;
  font-size: 14px;
}
.crumb.active {
  color: var(--text);
  font-weight: 600;
}
.sep {
  color: var(--text-dim);
}
.parent-card {
  border: 1px solid var(--accent);
  background: var(--accent-dim);
  border-radius: 12px;
  padding: 12px 14px;
  margin-bottom: 14px;
}
.pc-top {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.pc-top .spacer {
  flex: 1;
}
.pc-title {
  font-size: 17px;
  font-weight: 600;
  line-height: 1.3;
}
.pc-hint {
  font-size: 12px;
  margin-top: 4px;
}
.level-label {
  font-size: 13px;
  margin-bottom: 10px;
}
.cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.card {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  text-align: left;
  border: 1px solid var(--border);
  background: var(--bg-elev);
  border-radius: 12px;
  padding: 14px;
  min-height: 60px;
}
.card:active {
  background: var(--bg-elev2);
}
.card-main {
  flex: 1;
  min-width: 0;
}
.card-title {
  font-size: 16px;
  line-height: 1.3;
  margin-bottom: 5px;
}
.card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.card-right {
  flex-shrink: 0;
  align-self: center;
}
.drilldown {
  font-size: 15px;
  font-weight: 600;
  color: var(--accent);
  white-space: nowrap;
}
.leaf {
  font-size: 18px;
}
.chip.st { border-color: currentColor; }
.chip.ready { color: var(--status-done); border-color: var(--status-done); }
.chip.tiny { font-size: 11px; padding: 0 6px; }
.small { font-size: 12px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.done { text-decoration: line-through; color: var(--text-dim); }
.ghost.small { width: auto; padding: 3px 10px; font-size: 12px; }
.empty {
  text-align: center;
  padding: 30px 10px;
  font-size: 14px;
}
</style>
