<script setup>
import { onMounted, onUnmounted, ref, computed, watch } from 'vue'
import { store } from './api.js'
import GraphView from './components/GraphView.vue'
import IssueList from './components/IssueList.vue'
import IssueDetail from './components/IssueDetail.vue'
import KnowledgePanel from './components/KnowledgePanel.vue'
import MobileView from './components/MobileView.vue'
import ActivityFeed from './components/ActivityFeed.vue'
import Toasts from './components/Toasts.vue'
import LoginView from './components/LoginView.vue'

const needsLogin = computed(
  () => store.authStatus.auth && !store.authStatus.authenticated,
)

const tab = ref('graph')
const mobileTab = ref('issues')
const selectedId = ref(null)
// The mobile drill-down path (stack of issue ids). Mirrored into the History
// API so swipe-right / Back walks back up.
const mobilePath = ref([])

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

// --- Desktop detail (no history entanglement) ---
function select(id) {
  selectedId.value = id
}
function closeDetail() {
  selectedId.value = null
}

// --- Mobile navigation backed by the History API ---
// Each forward step (drill in, open a detail) pushes a history entry carrying
// the full nav state; Back/swipe-right pops it and popstate replays the state.
const EMPTY_NAV = { path: [], detail: null }

function applyNav(nav) {
  mobilePath.value = Array.isArray(nav?.path) ? nav.path : []
  selectedId.value = nav?.detail ?? null
}
function pushNav(path, detail) {
  mobilePath.value = path
  selectedId.value = detail
  window.history.pushState({ nav: { path, detail } }, '')
}
function onDrill(id) {
  pushNav([...mobilePath.value, id], null)
}
function onSelectMobile(id) {
  pushNav([...mobilePath.value], id)
}
function onUp() {
  if (mobilePath.value.length || selectedId.value != null) window.history.back()
}
function onGoto(index) {
  const delta = index + 1 - mobilePath.value.length
  if (delta < 0) window.history.go(delta)
}
function onRoot() {
  if (mobilePath.value.length) window.history.go(-mobilePath.value.length)
}
function mobileBack() {
  window.history.back()
}
function selectAny(id) {
  isMobile.value ? onSelectMobile(id) : select(id)
}
function onPopState(e) {
  applyNav(e.state && e.state.nav ? e.state.nav : EMPTY_NAV)
}

// Keep the drill path valid if issues it points at get deleted elsewhere.
watch(
  () => store.issues,
  () => {
    const valid = mobilePath.value.filter((id) => store.issueById(id))
    if (valid.length !== mobilePath.value.length) {
      mobilePath.value = valid
      window.history.replaceState(
        { nav: { path: valid, detail: selectedId.value } },
        '',
      )
    }
  },
)

let started = false
function startApp() {
  if (started) return
  started = true
  store.loadAll()
  store.connect()
}

async function boot() {
  await store.loadAuthStatus()
  if (!needsLogin.value) startApp()
}

// After a successful passkey login, start the live app.
watch(needsLogin, (v) => {
  if (!v) startApp()
})

onMounted(() => {
  window.history.replaceState({ nav: { ...EMPTY_NAV } }, '')
  window.addEventListener('popstate', onPopState)
  boot()
})
onUnmounted(() => window.removeEventListener('popstate', onPopState))
</script>

<template>
  <!-- ================= LOGIN GATE ================= -->
  <LoginView v-if="needsLogin" />

  <template v-else>
  <!-- ================= MOBILE ================= -->
  <template v-if="isMobile">
    <div class="topbar">
      <span class="brand">🧭 Tracker</span>
      <div class="spacer"></div>
      <ActivityFeed @select="onSelectMobile" />
      <button class="layout-toggle" title="Switch to desktop layout" @click="toggleLayout">
        🖥
      </button>
      <button
        v-if="store.authStatus.auth"
        class="layout-toggle"
        title="Log out"
        @click="store.logout()"
      >
        ⎋
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
      <MobileView
        v-if="mobileTab === 'issues'"
        :path="mobilePath"
        @drill="onDrill"
        @select="onSelectMobile"
        @up="onUp"
        @goto="onGoto"
        @root="onRoot"
      />
      <KnowledgePanel v-else @select="onSelectMobile" />
    </div>
    <IssueDetail
      v-if="selectedId !== null"
      :issue-id="selectedId"
      fullscreen
      @close="mobileBack"
      @select="onSelectMobile"
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
      <ActivityFeed @select="select" />
      <button class="layout-toggle" title="Preview mobile layout" @click="toggleLayout">
        📱
      </button>
      <button
        v-if="store.authStatus.auth"
        class="layout-toggle"
        title="Log out"
        @click="store.logout()"
      >
        ⎋
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

  <!-- Live toasts (both layouts) -->
  <Toasts @select="selectAny" />
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
