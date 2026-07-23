<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'
import { store } from '../api.js'

cytoscape.use(dagre)

const emit = defineEmits(['select'])
const el = ref(null)
const showDone = ref(true)
let cy = null

const PRI = { P0: '#f85149', P1: '#ff9f4a', P2: '#d29922', P3: '#6e7681' }
const STATUS = {
  open: '#8b949e',
  in_progress: '#d29922',
  blocked: '#f85149',
  done: '#3fb950',
  cancelled: '#6e7681',
}

function buildElements() {
  const visible = store.issues.filter(
    (i) => showDone.value || (i.status !== 'done' && i.status !== 'cancelled'),
  )
  const ids = new Set(visible.map((i) => i.id))
  const nodes = visible.map((i) => ({
    data: {
      id: 'n' + i.id,
      raw: i.id,
      label: `#${i.id}  ${i.title}`,
      pri: i.priority,
      status: i.status,
      actionable: i.actionable ? 1 : 0,
      parent: i.parent_id && ids.has(i.parent_id) ? 'n' + i.parent_id : undefined,
    },
  }))
  const edges = store.dependencies
    .filter((d) => ids.has(d.blocker_id) && ids.has(d.blocked_id))
    .map((d) => ({
      data: {
        id: `e${d.blocker_id}_${d.blocked_id}`,
        source: 'n' + d.blocker_id,
        target: 'n' + d.blocked_id,
      },
    }))
  return [...nodes, ...edges]
}

function layout() {
  if (!cy) return
  cy.layout({
    name: 'dagre',
    rankDir: 'LR',
    nodeSep: 22,
    rankSep: 70,
    edgeSep: 12,
    padding: 24,
  }).run()
}

function render() {
  if (!cy) return
  cy.json({ elements: buildElements() })
  layout()
}

onMounted(() => {
  cy = cytoscape({
    container: el.value,
    minZoom: 0.2,
    maxZoom: 2.5,
    wheelSensitivity: 0.2,
    style: [
      {
        selector: 'node',
        style: {
          label: 'data(label)',
          color: '#e6edf3',
          'font-size': 12,
          'text-valign': 'center',
          'text-halign': 'center',
          'text-wrap': 'wrap',
          'text-max-width': 170,
          shape: 'round-rectangle',
          width: 'label',
          height: 'label',
          padding: 10,
          'background-color': '#1c2430',
          'border-width': 3,
          'border-color': (n) => STATUS[n.data('status')] || '#8b949e',
        },
      },
      {
        // left accent by priority
        selector: 'node',
        style: {
          'background-gradient-stop-colors': (n) =>
            `${PRI[n.data('pri')]} #1c2430`,
          'background-gradient-stop-positions': '0 6',
          'background-fill': 'linear-gradient',
          'background-gradient-direction': 'to-right',
        },
      },
      {
        selector: 'node:parent',
        style: {
          'background-opacity': 0.08,
          'background-color': '#4c8dff',
          'background-fill': 'solid',
          'border-width': 1,
          'border-color': '#2a3441',
          'border-style': 'dashed',
          label: 'data(label)',
          'text-valign': 'top',
          'text-halign': 'center',
          'font-size': 11,
          color: '#8b949e',
          padding: 16,
        },
      },
      {
        selector: 'node[actionable = 1]',
        style: {
          'border-color': '#3fb950',
          'border-width': 3,
          'overlay-color': '#3fb950',
          'overlay-opacity': 0.06,
          'overlay-padding': 6,
        },
      },
      {
        selector: 'edge',
        style: {
          width: 2,
          'line-color': '#4c8dff',
          'target-arrow-color': '#4c8dff',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          opacity: 0.85,
        },
      },
      {
        selector: 'node:selected',
        style: { 'border-color': '#4c8dff', 'border-width': 4 },
      },
    ],
    elements: buildElements(),
  })
  layout()
  cy.on('tap', 'node', (evt) => {
    const raw = evt.target.data('raw')
    if (raw) emit('select', raw)
  })
})

onBeforeUnmount(() => {
  if (cy) cy.destroy()
  cy = null
})

watch(
  () => [store.issues, store.dependencies, showDone.value],
  () => render(),
  { deep: true },
)
</script>

<template>
  <div class="graph-wrap">
    <div class="graph-toolbar">
      <label class="toggle">
        <input type="checkbox" v-model="showDone" /> show done
      </label>
      <button class="ghost" @click="layout">Re-layout</button>
      <button class="ghost" @click="cy && cy.fit(undefined, 40)">Fit</button>
      <div class="legend">
        <span><i class="sw" style="background:#3fb950"></i>actionable</span>
        <span><i class="sw" style="background:#d29922"></i>in progress</span>
        <span><i class="sw" style="background:#f85149"></i>blocked</span>
        <span class="muted">arrows = blocks · dashed box = parent</span>
      </div>
    </div>
    <div ref="el" class="cy"></div>
    <div v-if="!store.issues.length" class="empty muted">
      No issues yet. Create one with <code>issue add "..."</code>.
    </div>
  </div>
</template>

<style scoped>
.graph-wrap {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
}
.graph-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-elev);
  flex-wrap: wrap;
}
.toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: auto;
  color: var(--text-dim);
  font-size: 13px;
}
.toggle input {
  width: auto;
}
.legend {
  display: flex;
  gap: 14px;
  align-items: center;
  font-size: 12px;
  color: var(--text-dim);
  margin-left: auto;
}
.legend span {
  display: flex;
  align-items: center;
  gap: 5px;
}
.sw {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  display: inline-block;
}
.cy {
  flex: 1;
  min-height: 0;
}
.empty {
  position: absolute;
  top: 60%;
  left: 0;
  right: 0;
  text-align: center;
}
code {
  background: var(--bg-elev2);
  padding: 1px 5px;
  border-radius: 4px;
}
</style>
