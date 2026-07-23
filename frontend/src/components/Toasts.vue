<script setup>
import { store } from '../api.js'

const emit = defineEmits(['select'])

function issueRef(item) {
  if (item.kind === 'issue' || item.kind === 'comment') {
    const id = parseInt(item.ref, 10)
    return Number.isNaN(id) ? null : id
  }
  return null
}

// Clicking a notification dismisses it (and jumps to the issue if it has one).
function click(item) {
  const id = issueRef(item)
  if (id != null) emit('select', id)
  store.dismissToast(item.key)
}
</script>

<template>
  <div v-if="store.toasts.length" class="toasts">
    <button
      v-if="store.toasts.length > 1"
      class="clear-all"
      @click="store.clearToasts()"
    >
      Clear all ✕
    </button>
    <div
      v-for="t in store.toasts"
      :key="t.key"
      class="toast"
      :class="{ clickable: issueRef(t) != null }"
      @click="click(t)"
    >
      <div class="tbody">
        <div class="ttext">{{ t.text }}</div>
        <div v-if="t.actor" class="tactor">{{ t.actor }}</div>
      </div>
      <button class="tclose" title="Dismiss" @click.stop="store.dismissToast(t.key)">
        ✕
      </button>
    </div>
  </div>
</template>

<style scoped>
.toasts {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 80;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  max-width: 340px;
}
.clear-all {
  border: 1px solid var(--border);
  background: var(--bg-elev2);
  color: var(--text-dim);
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 6px;
}
.clear-all:hover {
  color: var(--text);
  border-color: var(--accent);
}
.toast {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
  background: var(--bg-elev);
  border: 1px solid var(--accent);
  border-left-width: 3px;
  border-radius: 8px;
  padding: 10px 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  animation: slidein 0.18s ease-out;
}
.toast.clickable {
  cursor: pointer;
}
.tbody {
  flex: 1;
  min-width: 0;
}
.ttext {
  font-size: 13px;
  line-height: 1.35;
}
.tactor {
  font-size: 12px;
  color: var(--accent);
  font-weight: 600;
  margin-top: 2px;
}
.tclose {
  flex-shrink: 0;
  border: none;
  background: transparent;
  color: var(--text-dim);
  font-size: 12px;
  padding: 2px 4px;
  width: auto;
  line-height: 1;
}
.tclose:hover {
  color: var(--text);
}
@keyframes slidein {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
