<script setup lang="ts">
import { PhArrowLeft, PhSparkle } from '@phosphor-icons/vue'
import type { SubscriptionPlanRead, SubscriptionStatus, VendorSubscriptionRead } from '~/types/api'

definePageMeta({ middleware: 'vendor', layout: 'vendeur' })

const { apiFetch } = useApi()
const toast = useToastStore()

const alwaysRefetch = { getCachedData: () => undefined }

const { data: plans } = await useAsyncData(
  'subscription-plans',
  () => apiFetch<SubscriptionPlanRead[]>('/subscriptions/plans'),
  { default: () => [], ...alwaysRefetch },
)
const { data: subscription, refresh } = await useAsyncData(
  'vendor-subscription-me',
  () => apiFetch<VendorSubscriptionRead | null>('/subscriptions/me'),
  alwaysRefetch,
)

const statusMeta: Record<SubscriptionStatus, { label: string; color: string }> = {
  pending: { label: 'En attente de confirmation', color: 'warning' },
  active: { label: 'Actif', color: 'success' },
  expired: { label: 'Expiré', color: 'error' },
  cancelled: { label: 'Annulé', color: 'error' },
}

const isPremium = computed(() => subscription.value?.status === 'active')
const hasPending = computed(() => subscription.value?.status === 'pending')

const subscribingId = ref<string | null>(null)

async function subscribe(plan: SubscriptionPlanRead) {
  subscribingId.value = plan.id
  try {
    subscription.value = await apiFetch<VendorSubscriptionRead>('/subscriptions/subscribe', {
      method: 'POST',
      body: { plan_id: plan.id },
    })
    toast.success('Demande envoyée — en attente de confirmation du paiement.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'envoyer cette demande d'abonnement."))
  } finally {
    subscribingId.value = null
  }
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })
}
</script>

<template>
  <div class="app-shell pa-4" style="padding-bottom: 76px">
    <h1 class="text-h6 mb-4">Abonnement premium</h1>

    <v-card v-if="subscription" class="pa-3 mb-4" variant="flat">
      <div class="d-flex justify-space-between align-center mb-1">
        <span style="font-weight: 600">{{ subscription.plan.name }}</span>
        <v-chip :color="statusMeta[subscription.status].color" size="small" variant="tonal">
          {{ statusMeta[subscription.status].label }}
        </v-chip>
      </div>
      <div v-if="subscription.expires_at" class="text-muted" style="font-size: 12.5px">
        {{ subscription.status === 'active' ? 'Valide jusqu\'au' : 'Expiré le' }} {{ formatDate(subscription.expires_at) }}
      </div>
      <v-alert v-if="hasPending" type="warning" variant="tonal" density="compact" class="mt-3">
        Envoie le paiement via mobile money puis contacte le support — un administrateur confirmera ton abonnement.
      </v-alert>
    </v-card>

    <v-alert v-if="isPremium" type="success" variant="tonal" density="compact" class="mb-4">
      <div class="d-flex align-center ga-2">
        <PhSparkle :size="16" />
        <span>Tu peux améliorer tes photos produit avec l'IA (fond blanc, recadrage, netteté) depuis le formulaire produit.</span>
      </div>
    </v-alert>

    <p class="text-muted mb-3" style="font-size: 12.5px">
      Abonne-toi pour améliorer automatiquement tes photos produit : suppression du fond, recadrage sur le produit,
      agrandissement et retouche couleur.
    </p>

    <v-card v-for="plan in plans" :key="plan.id" class="pa-3 mb-3" variant="flat">
      <div class="d-flex justify-space-between align-center mb-1">
        <span style="font-weight: 600">{{ plan.name }}</span>
        <span style="font-size: 14px; font-weight: 600">{{ plan.price_gnf.toLocaleString('fr-FR') }} GNF</span>
      </div>
      <div class="text-muted mb-3" style="font-size: 12.5px">{{ plan.duration_days }} jours</div>
      <v-btn
        color="primary"
        block
        size="small"
        :disabled="hasPending || isPremium"
        :loading="subscribingId === plan.id"
        @click="subscribe(plan)"
      >
        S'abonner
      </v-btn>
    </v-card>

    <v-divider class="my-2" />
    <NuxtLink to="/vendeur/boutique" class="list-item">
      <PhArrowLeft :size="18" color="var(--color-neutral-400)" />
      <span>Retour aux réglages de la boutique</span>
    </NuxtLink>
  </div>
</template>

<style scoped>
.list-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 13px 0;
  font-size: 13.5px;
  text-decoration: none;
  color: inherit;
}
</style>
