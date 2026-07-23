<script setup>
import { onMounted, ref } from 'vue'
import { store } from './api.js'
import GraphView from './components/GraphView.vue'
import IssueList from './components/IssueList.vue'
import IssueDetail from './components/IssueDetail.vue'
import KnowledgePanel from './components/KnowledgePanel.vue'

const tab = ref('graph')
const selectedId = ref(null)

function select(id) {
  selectedId.value = id
}
function closeDetail() {
  selectedId.value = null
}

onMounted(() => {
  store.loadAll()
  store.connect()
})
</script>

<template>
  <div class="topbar">
    <span class="brand">🧭 Agent Issue Tracker</span>
    <div class="tabs">
      <button class="tab" :class="{ active: tab === 'graph' }" @click="tab = 'graph'">
        Graph
      </button>
      <button class="tab" :class="{ active: tab === 'list' }" @click="tab = 'list'">
        Issues
      </button>
      <button
        class="tab"
        :class="{ active: tab === 'knowledge' }"
        @click="tab = 'knowledge'"
      >
        Knowledge
        <span v-if="store.pendingCount" class="badge">{{ store.pendingCount }}</span>
      </button>
    </div>
    <div class="spacer"></div>
    <div class="conn">
      <span class="dot" :class="{ on: store.connected }"></span>
      {{ store.connected ? 'live' : 'offline' }}
    </div>
  </div>

  <div v-if="store.error" class="err">⚠ {{ store.error }}</div>

  <div class="main">
    <div class="content">
      <GraphView v-if="tab === 'graph'" @select="select" />
      <IssueList v-else-if="tab === 'list'" @select="select" />
      <KnowledgePanel v-else-if="tab === 'knowledge'" />
    </div>
    <IssueDetail
      v-if="selectedId !== null"
      :issue-id="selectedId"
      @close="closeDetail"
      @select="select"
    />
  </div>
</template>
