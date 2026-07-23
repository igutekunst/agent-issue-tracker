<script setup>
import { ref } from 'vue'
import { store } from '../api.js'
import { renderMarkdown as md } from '../markdown.js'

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
          <div class="diff-block old" v-if="p.current_value !== null">
            <span class="lbl">current</span>
            <div class="val markdown-body" v-html="md(p.current_value)"></div>
          </div>
          <div class="diff-block new" v-if="p.operation === 'set'">
            <span class="lbl">proposed</span>
            <div class="val markdown-body" v-html="md(p.proposed_value)"></div>
          </div>
          <div class="diff-block del" v-else>
            <span class="lbl">proposed</span>
            <div class="val">(delete this key)</div>
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
      <div v-if="store.knowledge.length" class="entries">
        <div v-for="k in store.knowledge" :key="k.key" class="entry">
          <div class="entry-head">
            <span class="mono key">{{ k.key }}</span>
            <span class="muted small">{{ k.updated_at.replace('T', ' ') }}</span>
          </div>
          <div class="val markdown-body" v-html="md(k.value)"></div>
        </div>
      </div>
      <p v-else class="muted">No approved entries yet.</p>
    </section>

    <section class="propose">
      <h3>Propose a change</h3>
      <div class="pform">
        <input v-model="draft.key" placeholder="key (e.g. deploy.url)" class="mono" />
        <textarea
          v-model="draft.value"
          placeholder="value — markdown supported (headings, lists, code, links…)"
          rows="5"
        ></textarea>
        <input v-model="draft.note" placeholder="note (why this change?)" />
        <button class="primary" @click="propose">Propose</button>
      </div>
      <p class="muted small">
        Values can be long and use markdown. Even changes you make here enter the
        approval queue — nothing mutates the store without an explicit approval.
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
  gap: 8px;
  margin: 8px 0;
}
.diff-block {
  border-radius: 6px;
  border: 1px solid var(--border);
  padding: 8px 10px;
}
.diff-block .lbl {
  display: block;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  color: var(--text-dim);
  margin-bottom: 4px;
}
.diff-block .val {
  font-size: 13px;
  word-break: break-word;
}
.diff-block.old {
  background: #f8514914;
  border-color: #f8514955;
}
.diff-block.old .lbl { color: #ffb0ab; }
.diff-block.new {
  background: #3fb95014;
  border-color: #3fb95055;
}
.diff-block.new .lbl { color: #96f0a8; }
.diff-block.del {
  background: #f8514914;
  border-color: #f8514955;
}
.note {
  font-size: 13px;
  color: var(--text-dim);
  margin: 6px 0;
}
.pactions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.pactions button { width: auto; }
.entries {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.entry {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-elev);
  padding: 10px 12px;
}
.entry-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}
.entry .key { font-size: 13px; }
.entry .val { font-size: 13.5px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.small { font-size: 12px; }
.pform {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pform button { width: auto; align-self: flex-start; white-space: nowrap; }
</style>
