<script setup lang="ts">
import { PhQrCode } from '@phosphor-icons/vue'
import type { PickupPointManagerSubOrderRead } from '~/types/api'

definePageMeta({ middleware: 'pickup-manager', layout: 'point-retrait' })

const { apiFetch } = useApi()
const toast = useToastStore()

const { data: deliveries, pending, refresh } = await useAsyncData(
  'pickup-manager-deliveries',
  () => apiFetch<PickupPointManagerSubOrderRead[]>('/orders/pickup-point-deliveries'),
  { default: () => [], getCachedData: () => undefined },
)

// Deux étapes distinctes chez le même gestionnaire : réception du colis
// déposé par le livreur, puis remise finale au client — voir
// app/orders/service.py::_allowed_next_statuses côté backend.
const toReceive = computed(() => deliveries.value.filter((so) => so.status === 'shipped'))
const toHandOff = computed(() => deliveries.value.filter((so) => so.status === 'arrived_at_pickup_point'))

const updatingId = ref<string | null>(null)

async function markStatus(subOrder: PickupPointManagerSubOrderRead, status: string) {
  updatingId.value = subOrder.id
  try {
    await apiFetch(`/orders/sub-orders/${subOrder.id}/status`, { method: 'PATCH', body: { status } })
    await refresh()
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de mettre à jour cette sous-commande.'))
  } finally {
    updatingId.value = null
  }
}

// Un seul scanner, un seul handler : le backend détermine lui-même la bonne
// cible (arrivée ou remise) selon l'état actuel de la sous-commande — pas
// besoin de distinguer "quel bouton a ouvert le scan" côté frontend.
const scannerOpen = ref(false)

async function handleDecode(token: string) {
  try {
    const updated = await apiFetch<{ order_id: string; status: string }>('/orders/sub-orders/confirm-delivery', {
      method: 'POST',
      body: { token },
    })
    await refresh()
    const label = updated.status === 'delivered' ? 'Remise confirmée' : 'Réception confirmée'
    toast.success(`${label} — ${shortId(updated.order_id)}.`)
  } catch (e) {
    toast.error(apiErrorMessage(e, 'QR code invalide ou expiré.'))
  }
}

function shortId(orderId: string) {
  return `#GN-${orderId.slice(0, 5).toUpperCase()}`
}
function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="app-shell pa-4" style="padding-bottom: 76px">
    <h1 class="text-h6 mb-3">Mon point de retrait</h1>

    <CommonEmptyState
      v-if="!pending && deliveries.length === 0"
      message="Aucune commande à traiter pour le moment."
    />

    <template v-if="toReceive.length > 0">
      <h2 class="section-title mb-2">À réceptionner</h2>
      <v-card v-for="so in toReceive" :key="so.id" class="mb-3 pa-3">
        <div class="d-flex justify-space-between align-center mb-2">
          <span class="order-code">{{ shortId(so.order_id) }}</span>
          <StatusBadge :status="so.status" />
        </div>
        <div class="text-muted mb-2" style="font-size: 12px">{{ so.shop_name }} · {{ formatDate(so.created_at) }}</div>
        <div v-for="item in so.items" :key="item.id" class="d-flex justify-space-between mb-1" style="font-size: 13px">
          <span
            >{{ item.product_name }}<span v-if="item.variant_label" class="text-muted"> ({{ item.variant_label }})</span> ×
            {{ item.quantity }}</span
          >
        </div>
        <OrderDeliveryDetails
          class="mt-2 mb-1"
          :zone="so.delivery_zone"
          :address="so.delivery_address"
          :instructions="so.delivery_instructions"
          delivery-type="pickup_point"
          :show-party="false"
        />
        <div v-if="so.courier_name" class="text-muted mb-3" style="font-size: 11.5px; padding-left: 23px">
          Livreur : {{ so.courier_name }} · {{ so.courier_phone }}
        </div>

        <v-divider class="mb-3" />

        <div class="d-flex ga-2">
          <v-btn color="primary" size="small" class="flex-grow-1" @click="scannerOpen = true">
            <PhQrCode :size="16" class="mr-1" />
            Scanner le code du livreur
          </v-btn>
          <v-btn
            variant="outlined"
            size="small"
            class="flex-grow-1"
            :loading="updatingId === so.id"
            @click="markStatus(so, 'arrived_at_pickup_point')"
          >
            Marquer reçu
          </v-btn>
        </div>
      </v-card>
    </template>

    <template v-if="toHandOff.length > 0">
      <h2 class="section-title mb-2 mt-4">À remettre au client</h2>
      <v-card v-for="so in toHandOff" :key="so.id" class="mb-3 pa-3">
        <div class="d-flex justify-space-between align-center mb-2">
          <span class="order-code">{{ shortId(so.order_id) }}</span>
          <StatusBadge :status="so.status" />
        </div>
        <div class="text-muted mb-2" style="font-size: 12px">{{ so.shop_name }} · {{ formatDate(so.created_at) }}</div>
        <div v-for="item in so.items" :key="item.id" class="d-flex justify-space-between mb-1" style="font-size: 13px">
          <span
            >{{ item.product_name }}<span v-if="item.variant_label" class="text-muted"> ({{ item.variant_label }})</span> ×
            {{ item.quantity }}</span
          >
        </div>
        <OrderDeliveryDetails
          class="mt-2 mb-1"
          :zone="so.delivery_zone"
          :address="so.delivery_address"
          :instructions="so.delivery_instructions"
          delivery-type="pickup_point"
          :show-party="false"
        />

        <v-divider class="mt-2 mb-3" />

        <div class="d-flex ga-2">
          <v-btn color="primary" size="small" class="flex-grow-1" @click="scannerOpen = true">
            <PhQrCode :size="16" class="mr-1" />
            Scanner le QR du client
          </v-btn>
          <v-btn
            variant="outlined"
            size="small"
            class="flex-grow-1"
            :loading="updatingId === so.id"
            @click="markStatus(so, 'delivered')"
          >
            Marquer remis
          </v-btn>
        </div>
      </v-card>
    </template>

    <VendorQrScannerDialog v-model="scannerOpen" @decode="handleDecode" />
  </div>
</template>

<style scoped>
.order-code {
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 13.5px;
  letter-spacing: 0.01em;
  color: var(--color-primary-300);
}

.section-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--color-primary-300);
  opacity: 0.85;
}
</style>
