<script setup lang="ts">
/**
 * QR de remise d'un colis (client, ou livreur au dépôt en point de retrait).
 * Le code est opaque (« NDJ:… », aucune information lisible) et change toutes
 * les 60 s : il est redemandé au serveur à chaque renouvellement — voir
 * backend app/orders/handoff.py. Une photo ou une capture d'écran devient
 * donc inutilisable au bout d'une minute ou deux.
 */
import QRCode from 'qrcode'
import type { HandoffCodeRead } from '~/types/api'

const props = defineProps<{ subOrderId: string }>()

const { apiFetch } = useApi()
const dataUrl = ref('')
const secondsLeft = ref(0)
const failed = ref(false)
let renewTimer: ReturnType<typeof setTimeout> | undefined
let tickTimer: ReturnType<typeof setInterval> | undefined

async function load() {
  clearTimeout(renewTimer)
  try {
    const handoff = await apiFetch<HandoffCodeRead>(`/orders/sub-orders/${props.subOrderId}/handoff-code`)
    // Noir sur blanc quel que soit le thème : les lecteurs se fient au contraste brut.
    dataUrl.value = await QRCode.toDataURL(handoff.code, {
      margin: 1,
      width: 240,
      color: { dark: '#000000', light: '#ffffff' },
    })
    failed.value = false
    secondsLeft.value = handoff.expires_in
    // Petit délai après le changement de créneau côté serveur.
    renewTimer = setTimeout(load, (handoff.expires_in + 1) * 1000)
  } catch {
    failed.value = true
    renewTimer = setTimeout(load, 5000)
  }
}

// Revenu sur l'onglet après une pause : le code affiché peut être périmé.
function onVisibility() {
  if (!document.hidden) load()
}

onMounted(() => {
  load()
  tickTimer = setInterval(() => {
    if (secondsLeft.value > 0) secondsLeft.value -= 1
  }, 1000)
  document.addEventListener('visibilitychange', onVisibility)
})

onBeforeUnmount(() => {
  clearTimeout(renewTimer)
  clearInterval(tickTimer)
  document.removeEventListener('visibilitychange', onVisibility)
})

watch(() => props.subOrderId, load)
</script>

<template>
  <div class="qr-wrap">
    <div class="qr-card">
      <img v-if="dataUrl" :src="dataUrl" alt="QR code de remise du colis" width="190" height="190" />
      <v-progress-circular v-else indeterminate color="primary" size="32" />
    </div>
    <div class="qr-meta">
      <template v-if="failed">Connexion perdue — nouvel essai…</template>
      <template v-else-if="dataUrl">Se renouvelle dans {{ secondsLeft }} s</template>
    </div>
  </div>
</template>

<style scoped>
.qr-wrap {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.qr-card {
  width: 214px;
  height: 214px;
  background: #fff;
  border-radius: var(--radius-md);
  padding: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.qr-meta {
  font-size: 12px;
  color: var(--color-neutral-400);
  font-variant-numeric: tabular-nums;
}
</style>
