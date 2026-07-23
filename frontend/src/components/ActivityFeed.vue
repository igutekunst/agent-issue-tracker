<script setup>
import { ref } from 'vue'
import { store } from '../api.js'

const emit = defineEmits(['select'])
const open = ref(false)

function toggle() {
  open.value = !open.value
  if (open.value) store.markActivityRead()
}
function close() {
  open.value = false
}

function issueRef(item) {
  if (item.kind === 'issue' || item.kind === 'comment') {
    const id = parseInt(item.ref, 10)
    return Number.isNaN(id) ? null : id
  }
  return null
}
function clickItem(item) {
  const id = issueRef(item)
  if (id != null) {
    emit('select', id)
    close()
  }
}

function ago(ts) {
  const then = new Date(ts).getTime()
  const s = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}
</script>

<template>
  <div class="feed">
    <button class="bell" :class="{ has: store.unread }" title="Activity" @click="toggle">
      🔔
      <span v-if="store.unread" class="ubadge">{{ store.unread > 99 ? '99+' : store.unread }}</span>
    </button>

    <template v-if="open">
      <div class="scrim" @click="close"></div>
      <div class="panel">
        <div class="panel-head">
          <strong>Activity</strong>
          <button class="ghost tiny" @click="close">✕</button>
        </div>

        <div class="items">
          <div
            v-for="item in store.activity"
            :key="item.id"
            class="item"
            :class="{ clickable: issueRef(item) != null }"
            @click="clickItem(item)"
          >
            <div class="itext">{{ item.text }}</div>
            <div class="imeta">
              <span v-if="item.actor" class="actor">{{ item.actor }}</span>
              <span v-if="item.actor" class="sepdot">·</span>
              <span class="muted">{{ ago(item.ts) }}</span>
            </div>
          </div>
          <div v-if="!store.activity.length" class="empty muted">No activity yet.</div>
        </div>

        <div class="panel-foot">
          <button
            v-if="!store.osNotify"
            class="ghost small"
            @click="store.enableOsNotify()"
          >
            🔔 Enable desktop notifications
          </button>
          <span v-else class="muted small">✓ Desktop notifications on</span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.feed {
  position: relative;
  display: flex;
  align-items: center;
}
.bell {
  position: relative;
  border: 1px solid var(--border);
  background: var(--bg-elev2);
  font-size: 15px;
  padding: 4px 9px;
}
.bell.has {
  border-color: var(--accent);
}
.ubadge {
  position: absolute;
  top: -7px;
  right: -7px;
  background: var(--status-blocked);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  border-radius: 9px;
  padding: 0 5px;
  line-height: 16px;
  min-width: 16px;
  text-align: center;
}
.scrim {
  position: fixed;
  inset: 0;
  z-index: 60;
}
.panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 340px;
  max-width: 92vw;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
  z-index: 61;
  overflow: hidden;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
}
.items {
  overflow-y: auto;
  flex: 1;
}
.item {
  padding: 9px 12px;
  border-bottom: 1px solid var(--border);
}
.item.clickable {
  cursor: pointer;
}
.item.clickable:hover {
  background: var(--bg-elev2);
}
.itext {
  font-size: 13px;
  line-height: 1.35;
}
.imeta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
  font-size: 12px;
}
.actor {
  color: var(--accent);
  font-weight: 600;
}
.sepdot {
  color: var(--text-dim);
}
.empty {
  padding: 24px 12px;
  text-align: center;
}
.panel-foot {
  padding: 8px 12px;
  border-top: 1px solid var(--border);
}
.tiny {
  padding: 1px 7px;
  font-size: 11px;
  width: auto;
}
.small {
  font-size: 12px;
  width: auto;
}
</style>
