<script setup lang="ts">
import { PhCheckCircle, PhQrCode } from '@phosphor-icons/vue'
import type { CourierDetailRead, CourierSubOrderRead } from '~/types/api'

definePageMeta({ middleware: 'courier', layout: 'livreur' })

const { apiFetch } = useApi()
const toast = useToastStore()
const { locating, locate } = useGeolocation()

const { data: deliveries, pending, refresh } = await useAsyncData(
  'courier-deliveries',
  () => apiFetch<CourierSubOrderRead[]>('/orders/courier-deliveries'),
  { default: () => [], getCachedData: () => undefined },
)

const { data: myCourier } = await useAsyncData(
  'courier-me-availability',
  () => apiFetch<CourierDetailRead>('/couriers/me'),
  { getCachedData: () => undefined },
)
const isOnline = ref(false)
const togglingAvailability = ref(false)
watch(myCourier, (c) => { if (c) isOnline.value = c.is_online }, { immediate: true })

async function toggleAvailability(value: boolean) {
  togglingAvailability.value = true
  try {
    let position: { latitude: number; longitude: number } | null = null
    if (value) {
      try {
        position = await locate()
      } catch (e) {
        // Erreur de géolocalisation (message déjà en français, voir
        // useGeolocation) — distincte d'une erreur API, pas de fallback
        // générique à appliquer ici.
        toast.error(e instanceof Error ? e.message : 'Impossible de récupérer ta position.')
        isOnline.value = false
        return
      }
    }

    const updated = await apiFetch<CourierDetailRead>('/couriers/me/availability', {
      method: 'PATCH',
      body: value ? { is_online: true, latitude: position!.latitude, longitude: position!.longitude } : { is_online: false },
    })
    isOnline.value = updated.is_online
    if (value) toast.success('Tu es maintenant disponible pour recevoir des livraisons.')
  } catch (e) {
    isOnline.value = !value // repli visuel : l'appel a échoué, le switch ne doit pas rester sur la valeur non confirmée
    toast.error(apiErrorMessage(e, 'Impossible de mettre à jour ta disponibilité.'))
  } finally {
    togglingAvailability.value = false
  }
}

const updatingId = ref<string | null>(null)

async function markDelivered(subOrder: CourierSubOrderRead) {
  updatingId.value = subOrder.id
  try {
    await apiFetch<CourierSubOrderRead>(`/orders/sub-orders/${subOrder.id}/status`, {
      method: 'PATCH',
      body: { status: 'delivered' },
    })
    await refresh()
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de mettre à jour cette livraison.'))
  } finally {
    updatingId.value = null
  }
}

const scannerOpen = ref(false)

async function handleDecode(token: string) {
  try {
    const updated = await apiFetch<CourierSubOrderRead>('/orders/sub-orders/confirm-delivery', {
      method: 'POST',
      body: { token },
    })
    await refresh()
    toast.success(`Livraison confirmée — ${shortId(updated.order_id)}.`)
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
  <!-- Pas de .app-shell ici : layouts/livreur.vue en fournit déjà un (avec
       app-shell--catalog, voir ce fichier) -- un deuxième wrapper imbriqué
       ici replafonnerait à 720px, annulant l'élargissement du bandeau du
       haut. .detail-card (main.css) recentre LE CONTENU en une carte
       détachée, sans replafonner LayoutTopBar avec -- impose son propre
       padding (plus de .pa-4 ici). Chaque livraison est un bloc séparé par
       une ligne (comme les boutiques d'une commande sur commandes/[id].vue)
       plutôt qu'une v-card imbriquée dans la carte détachée, pour éviter un
       effet "carte dans la carte". -->
  <div class="detail-card">
    <div class="d-flex justify-space-between align-center mb-1">
      <div class="d-flex align-center ga-2">
        <h1 class="text-h6 mb-0">Mes livraisons</h1>
        <v-chip v-if="myCourier?.status === 'approved'" size="x-small" color="success" variant="tonal">
          <PhCheckCircle :size="12" weight="fill" class="mr-1" />
          Approuvé
        </v-chip>
      </div>
      <div class="d-flex align-center ga-2">
        <span class="text-muted text-meta">{{ isOnline ? 'Disponible' : 'Indisponible' }}</span>
        <v-switch
          :model-value="isOnline"
          color="primary"
          density="compact"
          hide-details
          :loading="togglingAvailability || locating"
          :disabled="togglingAvailability || locating"
          @update:model-value="toggleAvailability"
        />
      </div>
    </div>

    <v-alert v-if="myCourier && myCourier.status !== 'approved'" type="warning" variant="tonal" density="compact" class="mb-3">
      <template v-if="myCourier.status === 'pending'">Ton profil est en cours de vérification par un administrateur.</template>
      <template v-else-if="myCourier.status === 'rejected'">Ton profil a été rejeté{{ myCourier.admin_note ? ` — ${myCourier.admin_note}` : '' }}.</template>
      <template v-else>Ton compte est suspendu.</template>
    </v-alert>

    <CommonEmptyState v-if="!pending && deliveries.length === 0" message="Aucune livraison assignée pour le moment." />

    <div v-for="so in deliveries" :key="so.id" class="mb-6">
      <div class="d-flex justify-space-between align-center mb-2">
        <span class="order-code">{{ shortId(so.order_id) }}</span>
        <StatusBadge :status="so.status" />
      </div>
      <div class="text-muted mb-2 text-meta">{{ so.shop_name }} · {{ formatDate(so.created_at) }}</div>

      <div v-for="item in so.items" :key="item.id" class="d-flex justify-space-between mb-1 text-body">
        <span
          >{{ item.product_name }}<span v-if="item.variant_label" class="text-muted"> ({{ item.variant_label }})</span> ×
          {{ item.quantity }}</span
        >
      </div>

      <OrderDeliveryDetails
        class="mt-3 mb-3"
        :zone="so.delivery_zone"
        :address="so.delivery_address"
        :instructions="so.delivery_instructions"
        :delivery-type="so.delivery_type"
        :recipient-name="so.recipient_name"
        :recipient-phone="so.recipient_phone"
        :pickup-point-contacts="so.pickup_point_contacts"
        :note="so.delivery_type === 'pickup_point' ? 'À déposer sur place — le client viendra le récupérer.' : null"
      />

      <template v-if="so.status === 'shipped' && so.delivery_type === 'pickup_point'">
        <div v-if="so.pickup_dropoff_token" class="d-flex flex-column align-center mb-3">
          <p class="text-muted mb-2 text-meta">Le gestionnaire du point scanne ce code à la réception</p>
          <OrderDeliveryQrCode :token="so.pickup_dropoff_token" />
        </div>
        <p class="text-muted mb-0 text-center text-meta">
          C'est le gestionnaire du point de retrait qui confirme la réception — rien à faire ici de votre côté.
        </p>
      </template>

      <div v-else-if="so.status === 'shipped'" class="d-flex ga-2">
        <v-btn color="primary" size="small" class="flex-grow-1" @click="scannerOpen = true">
          <PhQrCode :size="16" class="mr-1" />
          Scanner pour confirmer
        </v-btn>
        <v-btn
          variant="outlined"
          size="small"
          class="flex-grow-1"
          :loading="updatingId === so.id"
          @click="markDelivered(so)"
        >
          Marquer livrée
        </v-btn>
      </div>

      <v-divider class="mt-4" />
    </div>

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
</style>
