<script setup>
import { ref } from 'vue'
import { store } from '../api.js'

const draft = ref({ key: '', value: '', note: '' })

async function propose() {
  if (!draft.value.key.trim() || !draft.value.value.trim()) return
  try {
    await store.propose({ ...draft.value, author: 'human', operation: 'set' })
    draft.value = { key: '', value: '', note: '' }
  } catch (e) {
    store.error = e.message
  }
}

async function approve(id) {
  try {
    await store.approve(id)
  } catch (e) {
    store.error = e.message
  }
}
async function reject(id) {
  try {
    await store.reject(id)
  } catch (e) {
    store.error = e.message
  }
}
</script>

<template>
  <div class="kb-wrap">
    <h2>Knowledge base</h2>
    <p class="muted intro">
      A key/value store agents read freely but can only change with your approval.
      Agents run <code>issue kb propose &lt;key&gt; &lt;value&gt;</code>; changes land
      here for review.
    </p>

    <section v-if="store.proposals.length" class="pending">
      <h3>⏳ Pending approval ({{ store.proposals.length }})</h3>
      <div v-for="p in store.proposals" :key="p.id" class="proposal">
        <div class="phead">
          <span class="chip op" :class="p.operation">{{ p.operation }}</span>
          <span class="mono key">{{ p.key }}</span>
          <span class="muted by">— {{ p.author }}</span>
        </div>
        <div class="diff">
          <div class="diff-row" v-if="p.current_value !== null">
            <span class="lbl old">current</span>
            <span class="val old">{{ p.current_value }}</span>
          </div>
          <div class="diff-row" v-if="p.operation === 'set'">
            <span class="lbl new">proposed</span>
            <span class="val new">{{ p.proposed_value }}</span>
          </div>
          <div class="diff-row" v-else>
            <span class="lbl del">proposed</span>
            <span class="val del">(delete this key)</span>
          </div>
        </div>
        <p v-if="p.note" class="note">📝 {{ p.note }}</p>
        <div class="pactions">
          <button class="approve" @click="approve(p.id)">✓ Approve</button>
          <button class="ghost danger" @click="reject(p.id)">✕ Reject</button>
        </div>
      </div>
    </section>

    <section class="approved">
      <h3>Approved values</h3>
      <table v-if="store.knowledge.length">
        <thead>
          <tr><th>key</th><th>value</th><th>updated</th></tr>
        </thead>
        <tbody>
          <tr v-for="k in store.knowledge" :key="k.key">
            <td class="mono">{{ k.key }}</td>
            <td class="val-cell">{{ k.value }}</td>
            <td class="muted mono small">{{ k.updated_at.replace('T', ' ') }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">No approved entries yet.</p>
    </section>

    <section class="propose">
      <h3>Propose a change</h3>
      <div class="pform">
        <input v-model="draft.key" placeholder="key (e.g. deploy.url)" class="mono" />
        <input v-model="draft.value" placeholder="value" />
        <input v-model="draft.note" placeholder="note (why?)" />
        <button class="primary" @click="propose">Propose</button>
      </div>
      <p class="muted small">
        Even changes you make here enter the approval queue — nothing mutates the
        store without an explicit approval.
      </p>
    </section>
  </div>
</template>

<style scoped>
.kb-wrap {
  padding: 16px 22px 40px;
  max-width: 820px;
}
h2 { font-size: 18px; margin: 4px 0 6px; }
h3 {
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--text-dim);
  margin: 22px 0 10px;
}
.intro { margin-top: 0; }
code {
  background: var(--bg-elev2);
  padding: 1px 5px;
  border-radius: 4px;
}
.proposal {
  background: var(--bg-elev);
  border: 1px solid var(--status-in_progress);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 10px;
}
.phead {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.chip.op { border-color: currentColor; }
.chip.op.set { color: var(--status-done); }
.chip.op.delete { color: var(--status-blocked); }
.key { font-weight: 600; }
.diff {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin: 6px 0;
}
.diff-row {
  display: flex;
  gap: 10px;
  align-items: baseline;
}
.lbl {
  width: 68px;
  flex-shrink: 0;
  font-size: 11px;
  text-align: right;
  color: var(--text-dim);
}
.val {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
  padding: 2px 8px;
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-word;
}
.val.old { background: #f8514922; text-decoration: line-through; color: #ffb0ab; }
.val.new { background: #3fb95022; color: #96f0a8; }
.val.del { background: #f8514922; color: #ffb0ab; }
.note {
  font-size: 13px;
  color: var(--text-dim);
  margin: 6px 0;
}
.pactions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.pactions button { width: auto; }
table {
  width: 100%;
  border-collapse: collapse;
}
th {
  text-align: left;
  color: var(--text-dim);
  font-weight: 600;
  font-size: 12px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}
td {
  padding: 7px 8px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}
.val-cell { white-space: pre-wrap; word-break: break-word; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.small { font-size: 12px; }
.pform {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 8px;
  align-items: center;
}
.pform input:nth-child(1) { grid-column: 1; }
.pform button { width: auto; white-space: nowrap; }
</style>
