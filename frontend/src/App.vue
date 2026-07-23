<script setup>
import { onMounted, ref, computed } from 'vue'
import { store } from './api.js'
import GraphView from './components/GraphView.vue'
import IssueList from './components/IssueList.vue'
import IssueDetail from './components/IssueDetail.vue'
import KnowledgePanel from './components/KnowledgePanel.vue'
import MobileView from './components/MobileView.vue'

const tab = ref('graph')
const mobileTab = ref('issues')
const selectedId = ref(null)

// Layout: auto by viewport, with a manual override so it can be previewed.
const mq = window.matchMedia('(max-width: 760px)')
const autoMobile = ref(mq.matches)
mq.addEventListener?.('change', (e) => {
  autoMobile.value = e.matches
})
const override = ref(null) // null = auto; true/false = forced
const isMobile = computed(() =>
  override.value === null ? autoMobile.value : override.value,
)
function toggleLayout() {
  override.value = !isMobile.value
}

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
  <!-- ================= MOBILE ================= -->
  <template v-if="isMobile">
    <div class="topbar">
      <span class="brand">🧭 Tracker</span>
      <div class="spacer"></div>
      <button class="layout-toggle" title="Switch to desktop layout" @click="toggleLayout">
        🖥
      </button>
      <div class="conn">
        <span class="dot" :class="{ on: store.connected }"></span>
      </div>
    </div>
    <div v-if="store.error" class="err">⚠ {{ store.error }}</div>
    <div class="mtabs">
      <button :class="{ active: mobileTab === 'issues' }" @click="mobileTab = 'issues'">
        Issues
      </button>
      <button
        :class="{ active: mobileTab === 'knowledge' }"
        @click="mobileTab = 'knowledge'"
      >
        Knowledge
        <span v-if="store.pendingCount" class="badge">{{ store.pendingCount }}</span>
      </button>
    </div>
    <div class="mcontent">
      <MobileView v-if="mobileTab === 'issues'" @select="select" />
      <KnowledgePanel v-else @select="select" />
    </div>
    <IssueDetail
      v-if="selectedId !== null"
      :issue-id="selectedId"
      fullscreen
      @close="closeDetail"
      @select="select"
    />
  </template>

  <!-- ================= DESKTOP ================= -->
  <template v-else>
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
      <button class="layout-toggle" title="Preview mobile layout" @click="toggleLayout">
        📱
      </button>
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
</template>

<style scoped>
.mtabs {
  display: flex;
  gap: 4px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-elev);
  flex-shrink: 0;
}
.mtabs button {
  flex: 1;
  background: transparent;
  border: 1px solid transparent;
  padding: 10px;
  font-size: 15px;
}
.mtabs button.active {
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--accent);
}
.mcontent {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.layout-toggle {
  border: 1px solid var(--border);
  background: var(--bg-elev2);
  font-size: 15px;
  padding: 4px 9px;
  margin-right: 4px;
}
</style>
