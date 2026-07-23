// Reactive client-side store: fetches data, holds it, and subscribes to the
// server's SSE change feed so every view refreshes live.
import { reactive } from 'vue'
import { startRegistration, startAuthentication } from '@simplewebauthn/browser'

async function req(method, url, body, headers) {
  const opts = { method, headers: { ...(headers || {}) }, credentials: 'same-origin' }
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(url, opts)
  if (!res.ok) {
    if (res.status === 401) {
      // Session missing/expired — surface the login screen.
      store.authStatus.auth = true
      store.authStatus.authenticated = false
    }
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = j.detail || detail
    } catch (_) {}
    const e = new Error(detail)
    e.status = res.status
    throw e
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

  // Auth. When `auth` is false the server is open (no login needed).
  authStatus: { auth: false, authenticated: true, is_admin: true, has_passkey: false },
  authError: '',

  get pendingCount() {
    return this.proposals.length
  },

  issueById(id) {
    return this.issues.find((i) => i.id === id)
  },

  // --- Auth ---
  async loadAuthStatus() {
    try {
      this.authStatus = await req('GET', '/api/auth/status')
    } catch (e) {
      // If status itself fails, assume open so the app still tries to load.
      this.authStatus = { auth: false, authenticated: true, is_admin: true }
    }
    return this.authStatus
  },

  async passkeyLogin() {
    this.authError = ''
    try {
      const options = await req('POST', '/api/webauthn/login/begin')
      const assertion = await startAuthentication({ optionsJSON: options })
      await req('POST', '/api/webauthn/login/finish', { credential: assertion })
      await this.loadAuthStatus()
      return true
    } catch (e) {
      this.authError = e.message || 'passkey login failed'
      return false
    }
  },

  async passkeyRegister(token, name) {
    this.authError = ''
    const headers = { Authorization: `Bearer ${token.trim()}` }
    try {
      const options = await req('POST', '/api/webauthn/register/begin', undefined, headers)
      const attestation = await startRegistration({ optionsJSON: options })
      await req(
        'POST',
        '/api/webauthn/register/finish',
        { credential: attestation, name: name || 'passkey' },
        headers,
      )
      // Registered — immediately sign in to establish a session.
      return await this.passkeyLogin()
    } catch (e) {
      this.authError = e.message || 'passkey registration failed'
      return false
    }
  },

  async logout() {
    try {
      await req('POST', '/api/auth/logout')
    } catch (_) {}
    this.authStatus.authenticated = false
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

  clearToasts() {
    this.toasts = []
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
