<script setup lang="ts">
import { PhClockCounterClockwise, PhMoney } from '@phosphor-icons/vue'
import type { PaymentSettingsRead } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
const toast = useToastStore()

const { data: settings, refresh } = await useAsyncData(
  'admin-payment-settings',
  () => apiFetch<PaymentSettingsRead>('/admin/payment-settings'),
)

const refundDelayHours = ref(String(settings.value?.refund_delay_hours ?? 48))
const saving = ref(false)

const codEnabled = ref(settings.value?.cash_on_delivery_enabled ?? false)
const savingCod = ref(false)
async function toggleCod(value: boolean | null) {
  savingCod.value = true
  try {
    await apiFetch('/admin/payment-settings', { method: 'PATCH', body: { cash_on_delivery_enabled: !!value } })
    codEnabled.value = !!value
    toast.success(value ? 'Paiement à la livraison proposé aux acheteurs.' : 'Paiement à la livraison retiré du checkout.')
  } catch (e) {
    codEnabled.value = !value
    toast.error(apiErrorMessage(e, 'Impossible d’enregistrer ce réglage.'))
  } finally {
    savingCod.value = false
  }
}

async function save() {
  const hours = Number(refundDelayHours.value)
  if (!Number.isInteger(hours) || hours < 0) {
    toast.error('Le délai doit être un nombre d’heures entier, positif ou nul.')
    return
  }
  saving.value = true
  try {
    await apiFetch('/admin/payment-settings', { method: 'PATCH', body: { refund_delay_hours: hours } })
    await refresh()
    toast.success('Réglage enregistré.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible d’enregistrer ce réglage.'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="dashboard-shell">
    <h1 class="text-h6 mb-2">Paiement</h1>
    <p class="text-muted mb-4" style="font-size: 12.5px; max-width: 640px">
      Paiement en ligne (Djomy) : quand un acheteur annule une commande payée en ligne avant qu'un vendeur ne
      commence à la traiter, un remboursement est déclenché automatiquement vers son compte mobile money. Le délai
      ci-dessous est purement informatif — Djomy ne le garantit pas — et sert uniquement à fixer les attentes de
      l'acheteur.
    </p>

    <v-card class="pa-4 mb-4" max-width="420">
      <div class="d-flex align-center ga-2 mb-2">
        <PhMoney :size="20" color="var(--color-primary)" />
        <span style="font-weight: 600">Paiement à la livraison (espèces)</span>
      </div>
      <v-switch
        :model-value="codEnabled"
        color="primary"
        inset
        hide-details
        :loading="savingCod"
        :disabled="savingCod"
        :label="codEnabled ? 'Proposé aux acheteurs' : 'Désactivé — paiement en ligne ou NdjouriBank uniquement'"
        @update:model-value="toggleCod"
      />
      <p class="text-muted mt-2 mb-0" style="font-size: 11.5px">
        Désactivé, les nouvelles commandes se paient en ligne (mobile money, carte) ou avec le solde NdjouriBank :
        aucun livreur ne transporte d'argent. Les commandes déjà passées en espèces vont au bout normalement.
      </p>
    </v-card>

    <v-card class="pa-4" max-width="420">
      <div class="d-flex align-center ga-2 mb-3">
        <PhClockCounterClockwise :size="20" color="var(--color-primary)" />
        <span style="font-weight: 600">Délai de remboursement estimé</span>
      </div>
      <v-text-field
        v-model="refundDelayHours"
        label="Heures"
        inputmode="numeric"
        suffix="h"
        hide-details="auto"
      />
      <p class="text-muted mt-2 mb-0" style="font-size: 11.5px">
        Affiché à l'acheteur juste après l'annulation, tant que le remboursement n'est pas confirmé.
      </p>
      <v-btn color="primary" class="mt-4" :loading="saving" @click="save">Enregistrer</v-btn>
    </v-card>
  </div>
</template>
