<script setup lang="ts">
import type { SubscriptionStatus, VendorSubscriptionRead } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
const toast = useToastStore()

const tab = ref<SubscriptionStatus>('pending')
const tabs: { value: SubscriptionStatus; label: string }[] = [
  { value: 'pending', label: 'En attente' },
  { value: 'active', label: 'Actifs' },
  { value: 'expired', label: 'Expirés' },
  { value: 'cancelled', label: 'Annulés' },
]

const { data: subscriptions, pending, refresh } = await useAsyncData(
  'admin-subscriptions',
  () => apiFetch<VendorSubscriptionRead[]>('/admin/subscriptions', { query: { status: tab.value } }),
  { default: () => [], getCachedData: () => undefined },
)
watch(tab, () => refresh())

const statusMeta: Record<SubscriptionStatus, { label: string; color: string }> = {
  pending: { label: 'En attente', color: 'warning' },
  active: { label: 'Actif', color: 'success' },
  expired: { label: 'Expiré', color: 'error' },
  cancelled: { label: 'Annulé', color: 'error' },
}

// Même logique que admin/vendeurs : la liste courante ne montre que l'onglet
// actif, donc après une action on la retire localement plutôt que de la
// re-classer.
const updatingId = ref<string | null>(null)

async function act(subscription: VendorSubscriptionRead, action: 'confirm' | 'cancel') {
  updatingId.value = subscription.id
  try {
    await apiFetch(`/admin/subscriptions/${subscription.id}/${action}`, { method: 'POST' })
    subscriptions.value = subscriptions.value.filter((s) => s.id !== subscription.id)
    toast.success(action === 'confirm' ? 'Abonnement confirmé.' : 'Abonnement annulé.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de mettre à jour cet abonnement.'))
  } finally {
    updatingId.value = null
  }
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })
}
</script>

<template>
  <div class="dashboard-shell">
    <h1 class="text-h6 mb-4">Abonnements vendeurs</h1>

    <v-btn-toggle v-model="tab" mandatory density="comfortable" divided class="mb-4 flex-wrap">
      <v-btn v-for="t in tabs" :key="t.value" :value="t.value" size="small">{{ t.label }}</v-btn>
    </v-btn-toggle>

    <CommonEmptyState v-if="!pending && subscriptions.length === 0" message="Aucun abonnement dans cette catégorie." />

    <v-card v-for="subscription in subscriptions" :key="subscription.id" class="mb-3 pa-3">
      <div class="d-flex justify-space-between align-center mb-1">
        <span style="font-weight: 600">{{ subscription.plan.name }}</span>
        <v-chip :color="statusMeta[subscription.status].color" size="small" variant="tonal">
          {{ statusMeta[subscription.status].label }}
        </v-chip>
      </div>
      <div class="text-muted mb-3" style="font-size: 12.5px">
        {{ subscription.plan.price_gnf.toLocaleString('fr-FR') }} GNF — {{ subscription.plan.duration_days }} jours
        <template v-if="subscription.expires_at">
          · expire le {{ formatDate(subscription.expires_at) }}
        </template>
      </div>

      <div v-if="subscription.status === 'pending'" class="d-flex ga-2">
        <v-btn
          color="primary"
          size="small"
          class="flex-grow-1"
          :loading="updatingId === subscription.id"
          @click="act(subscription, 'confirm')"
        >
          Confirmer le paiement
        </v-btn>
        <v-btn
          color="error"
          variant="outlined"
          size="small"
          class="flex-grow-1"
          :loading="updatingId === subscription.id"
          @click="act(subscription, 'cancel')"
        >
          Annuler
        </v-btn>
      </div>
      <v-btn
        v-else-if="subscription.status === 'active'"
        color="error"
        variant="outlined"
        size="small"
        block
        :loading="updatingId === subscription.id"
        @click="act(subscription, 'cancel')"
      >
        Annuler
      </v-btn>
    </v-card>
  </div>
</template>
