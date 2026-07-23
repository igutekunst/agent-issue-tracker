// Reactive client-side store: fetches data, holds it, and subscribes to the
// server's SSE change feed so every view refreshes live.
import { reactive } from 'vue'

async function req(method, url, body) {
  const opts = { method, headers: {} }
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(url, opts)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = j.detail || detail
    } catch (_) {}
    throw new Error(detail)
  }
  if (res.status === 204) return null
  const text = await res.text()
  return text ? JSON.parse(text) : null
}

export const store = reactive({
  issues: [],
  dependencies: [],
  knowledge: [],
  proposals: [],
  meta: { statuses: [], priorities: [] },
  connected: false,
  error: '',
  // Bumped on every change event so per-issue views (e.g. comments) can refetch.
  changeVersion: 0,

  // Notifications / activity feed.
  activity: [],
  activityMaxId: 0,
  unread: 0,
  toasts: [],
  osNotify: false,

  get pendingCount() {
    return this.proposals.length
  },

  issueById(id) {
    return this.issues.find((i) => i.id === id)
  },

  async loadAll() {
    try {
      const [graph, knowledge, proposals, meta] = await Promise.all([
        req('GET', '/api/graph'),
        req('GET', '/api/knowledge'),
        req('GET', '/api/knowledge/proposals?status=pending'),
        req('GET', '/api/meta'),
      ])
      this.issues = graph.issues
      this.dependencies = graph.dependencies
      this.knowledge = knowledge
      this.proposals = proposals
      this.meta = meta
      this.error = ''
    } catch (e) {
      this.error = e.message
    }
  },

  connect() {
    const es = new EventSource('/events')
    es.addEventListener('hello', () => {
      this.connected = true
      this.loadAll()
      this.loadActivity(true) // seed the feed without notifying
    })
    es.addEventListener('change', () => {
      this.changeVersion++
      this.loadAll()
      this.loadActivity(false) // notify on anything new
    })
    es.onerror = () => {
      this.connected = false
    }
  },

  async loadActivity(initial = false) {
    let rows
    try {
      rows = await req('GET', '/api/activity?limit=50')
    } catch (e) {
      return
    }
    const fresh = rows.filter((r) => r.id > this.activityMaxId)
    this.activity = rows
    if (rows.length) {
      this.activityMaxId = Math.max(this.activityMaxId, ...rows.map((r) => r.id))
    }
    if (!initial && fresh.length) {
      // fresh is newest-first; emit oldest-first so the newest toast is on top.
      for (const item of fresh.slice().reverse()) {
        this.unread++
        this.toast(item)
        this.maybeOsNotify(item)
      }
    }
  },

  toast(item) {
    const t = { ...item, key: `${item.id}-${this.toasts.length}` }
    this.toasts.push(t)
    setTimeout(() => {
      this.toasts = this.toasts.filter((x) => x.key !== t.key)
    }, 6000)
  },

  dismissToast(key) {
    this.toasts = this.toasts.filter((x) => x.key !== key)
  },

  markActivityRead() {
    this.unread = 0
  },

  async enableOsNotify() {
    if (!('Notification' in window)) return
    const perm = await Notification.requestPermission()
    this.osNotify = perm === 'granted'
  },

  maybeOsNotify(item) {
    if (this.osNotify && document.hidden && 'Notification' in window) {
      new Notification('Agent Issue Tracker', {
        body: item.actor ? `${item.text} · ${item.actor}` : item.text,
      })
    }
  },

  // --- mutations ---
  createIssue(payload) {
    return req('POST', '/api/issues', payload)
  },
  updateIssue(id, payload) {
    return req('PATCH', `/api/issues/${id}`, payload)
  },
  deleteIssue(id) {
    return req('DELETE', `/api/issues/${id}`)
  },
  addDependency(blocker_id, blocked_id) {
    return req('POST', '/api/dependencies', { blocker_id, blocked_id })
  },
  removeDependency(blocker_id, blocked_id) {
    return req(
      'DELETE',
      `/api/dependencies?blocker_id=${blocker_id}&blocked_id=${blocked_id}`,
    )
  },
  getComments(issueId) {
    return req('GET', `/api/issues/${issueId}/comments`)
  },
  addComment(issueId, payload) {
    return req('POST', `/api/issues/${issueId}/comments`, payload)
  },
  deleteComment(commentId) {
    return req('DELETE', `/api/comments/${commentId}`)
  },
  propose(payload) {
    return req('POST', '/api/knowledge/proposals', payload)
  },
  approve(id) {
    return req('POST', `/api/knowledge/proposals/${id}/approve`)
  },
  reject(id) {
    return req('POST', `/api/knowledge/proposals/${id}/reject`)
  },
})
