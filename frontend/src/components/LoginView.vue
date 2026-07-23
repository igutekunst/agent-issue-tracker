<script setup>
import { ref } from 'vue'
import { store } from '../api.js'

const busy = ref(false)
const showEnroll = ref(false)
const token = ref('')
const passkeyName = ref('')

async function signIn() {
  busy.value = true
  await store.passkeyLogin()
  busy.value = false
}
async function enroll() {
  if (!token.value.trim()) return
  busy.value = true
  const ok = await store.passkeyRegister(token.value, passkeyName.value)
  busy.value = false
  if (ok) {
    token.value = ''
    passkeyName.value = ''
  }
}
</script>

<template>
  <div class="login-wrap">
    <div class="card">
      <div class="brand">🧭 Agent Issue Tracker</div>
      <p class="sub muted">This tracker is protected. Sign in to continue.</p>

      <button
        v-if="store.authStatus.has_passkey"
        class="primary big"
        :disabled="busy"
        @click="signIn"
      >
        🔑 Sign in with passkey
      </button>

      <p v-if="!store.authStatus.has_passkey" class="muted note">
        No passkey is registered yet. Enroll this device with your bootstrap /
        admin token.
      </p>

      <button
        v-if="store.authStatus.has_passkey"
        class="ghost link"
        @click="showEnroll = !showEnroll"
      >
        {{ showEnroll ? 'Hide' : 'Enroll another device' }}
      </button>

      <div v-if="showEnroll || !store.authStatus.has_passkey" class="enroll">
        <label>Admin / bootstrap token
          <input
            v-model="token"
            type="password"
            placeholder="it_…"
            autocomplete="off"
            @keyup.enter="enroll"
          />
        </label>
        <label>Passkey name (optional)
          <input v-model="passkeyName" placeholder="e.g. my-laptop" @keyup.enter="enroll" />
        </label>
        <button class="primary" :disabled="busy || !token.trim()" @click="enroll">
          Register this device as a passkey
        </button>
      </div>

      <p v-if="store.authError" class="err">⚠ {{ store.authError }}</p>
    </div>
  </div>
</template>

<style scoped>
.login-wrap {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.card {
  width: 100%;
  max-width: 380px;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 26px 24px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5);
}
.brand {
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 6px;
}
.sub {
  margin: 0 0 18px;
  font-size: 13px;
}
.big {
  width: 100%;
  padding: 12px;
  font-size: 15px;
}
.note {
  font-size: 13px;
  margin: 0 0 14px;
}
.link {
  display: block;
  margin: 12px auto 0;
  background: transparent;
  border: none;
  color: var(--accent);
  font-size: 13px;
  width: auto;
}
.enroll {
  margin-top: 16px;
  border-top: 1px solid var(--border);
  padding-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.enroll label {
  display: block;
  font-size: 12px;
  color: var(--text-dim);
}
.enroll input {
  margin-top: 5px;
}
.enroll button {
  width: 100%;
}
.err {
  color: var(--status-blocked);
  font-size: 13px;
  margin-top: 14px;
}
</style>
