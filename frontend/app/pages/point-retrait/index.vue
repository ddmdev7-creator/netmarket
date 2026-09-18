<script setup lang="ts">
import { PhMagnifyingGlass, PhMapPinLine, PhQrCode } from '@phosphor-icons/vue'
import type { PickupPointManagerSubOrderRead } from '~/types/api'

definePageMeta({ middleware: 'pickup-manager', layout: 'point-retrait' })

const { apiFetch } = useApi()
const toast = useToastStore()

const { data: deliveries, pending, refresh } = await useAsyncData(
  'pickup-manager-deliveries',
  () => apiFetch<PickupPointManagerSubOrderRead[]>('/orders/pickup-point-deliveries'),
  { default: () => [], getCachedData: () => undefined },
)

// Retrouver un colis par son code, sa boutique ou l'emplacement de stockage
// déjà noté — le nombre de colis en attente chez un point actif peut vite
// rendre la liste longue à parcourir à l'œil.
const search = ref('')
const visibleDeliveries = computed(() => {
  const query = search.value.trim().toLowerCase()
  if (!query) return deliveries.value
  return deliveries.value.filter((so) =>
    [shortId(so.order_id), so.shop_name, so.storage_location ?? '']
      .join(' ')
      .toLowerCase()
      .includes(query),
  )
})

// Deux étapes distinctes chez le même gestionnaire : réception du colis
// déposé par le livreur, puis remise finale au client — voir
// app/orders/service.py::_allowed_next_statuses côté backend.
const toReceive = computed(() => visibleDeliveries.value.filter((so) => so.status === 'shipped'))
const toHandOff = computed(() => visibleDeliveries.value.filter((so) => so.status === 'arrived_at_pickup_point'))

// Édition de l'emplacement de stockage — état local par sous-commande, ne
// s'écrase pas au refetch une fois modifié (voir storageLocationFor), pour
// ne pas perdre une saisie en cours si un scan déclenche un refresh entre-temps.
const storageLocationDrafts = ref<Record<string, string>>({})
const savingStorageLocationId = ref<string | null>(null)

function storageLocationFor(subOrder: PickupPointManagerSubOrderRead) {
  if (!(subOrder.id in storageLocationDrafts.value)) {
    storageLocationDrafts.value[subOrder.id] = subOrder.storage_location ?? ''
  }
  return storageLocationDrafts.value[subOrder.id]
}

async function saveStorageLocation(subOrder: PickupPointManagerSubOrderRead) {
  const value = (storageLocationDrafts.value[subOrder.id] ?? '').trim()
  savingStorageLocationId.value = subOrder.id
  try {
    await apiFetch(`/orders/sub-orders/${subOrder.id}/storage-location`, {
      method: 'PATCH',
      body: { storage_location: value || null },
    })
    await refresh()
    toast.success('Emplacement enregistré.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'enregistrer l'emplacement."))
  } finally {
    savingStorageLocationId.value = null
  }
}

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

    <v-text-field
      v-if="deliveries.length > 0"
      v-model="search"
      placeholder="Rechercher par code, boutique ou emplacement…"
      density="compact"
      variant="outlined"
      hide-details
      clearable
      class="mb-4"
    >
      <template #prepend-inner>
        <PhMagnifyingGlass :size="16" color="var(--color-neutral-500)" />
      </template>
    </v-text-field>

    <CommonEmptyState
      v-if="!pending && deliveries.length === 0"
      message="Aucune commande à traiter pour le moment."
    />
    <CommonEmptyState
      v-else-if="!pending && visibleDeliveries.length === 0"
      message="Aucun colis ne correspond à cette recherche."
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

        <div class="d-flex align-center ga-2 mb-3">
          <PhMapPinLine :size="15" color="var(--color-primary)" />
          <v-text-field
            :model-value="storageLocationFor(so)"
            placeholder="Emplacement (ex: Étagère B3)"
            density="compact"
            variant="outlined"
            hide-details
            class="flex-grow-1"
            @update:model-value="(v) => (storageLocationDrafts[so.id] = v)"
          />
          <v-btn
            size="small"
            variant="tonal"
            :loading="savingStorageLocationId === so.id"
            @click="saveStorageLocation(so)"
          >
            OK
          </v-btn>
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

        <div class="storage-highlight mb-2">
          <PhMapPinLine :size="16" color="var(--color-primary)" />
          <span v-if="so.storage_location" class="storage-highlight__value">{{ so.storage_location }}</span>
          <span v-else class="storage-highlight__value text-muted">Emplacement non renseigné</span>
        </div>
        <div class="d-flex align-center ga-2 mb-3">
          <v-text-field
            :model-value="storageLocationFor(so)"
            placeholder="Emplacement (ex: Étagère B3)"
            density="compact"
            variant="outlined"
            hide-details
            class="flex-grow-1"
            @update:model-value="(v) => (storageLocationDrafts[so.id] = v)"
          />
          <v-btn
            size="small"
            variant="tonal"
            :loading="savingStorageLocationId === so.id"
            @click="saveStorageLocation(so)"
          >
            OK
          </v-btn>
        </div>

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

/* Ce que le gestionnaire vient chercher en premier sur une carte "à
   remettre" — mis en évidence plutôt que noyé dans le reste des détails,
   voir OrderDeliveryDetails juste en dessous pour l'adresse/les instructions. */
.storage-highlight {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: var(--color-primary-800);
  width: fit-content;
}

.storage-highlight__value {
  font-weight: 700;
  font-size: 13.5px;
  color: var(--color-primary-100);
}
</style>
