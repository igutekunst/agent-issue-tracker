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
function click(item) {
  const id = issueRef(item)
  if (id != null) emit('select', id)
  store.dismissToast(item.key)
}
</script>

<template>
  <div class="toasts">
    <div
      v-for="t in store.toasts"
      :key="t.key"
      class="toast"
      :class="{ clickable: issueRef(t) != null }"
      @click="click(t)"
    >
      <div class="ttext">{{ t.text }}</div>
      <div v-if="t.actor" class="tactor">{{ t.actor }}</div>
      <button class="tclose" @click.stop="store.dismissToast(t.key)">✕</button>
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
  gap: 8px;
  max-width: 340px;
}
.toast {
  position: relative;
  background: var(--bg-elev);
  border: 1px solid var(--accent);
  border-left-width: 3px;
  border-radius: 8px;
  padding: 10px 30px 10px 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  animation: slidein 0.18s ease-out;
}
.toast.clickable {
  cursor: pointer;
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
  position: absolute;
  top: 6px;
  right: 6px;
  border: none;
  background: transparent;
  color: var(--text-dim);
  font-size: 12px;
  padding: 2px 5px;
  width: auto;
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
