<script setup lang="ts">
import { PhCaretDown, PhImage, PhMagnifyingGlass, PhMotorcycle, PhQrCode } from '@phosphor-icons/vue'
import type { CourierRead, OrderStatus, VehicleType, VendorSubOrderRead } from '~/types/api'

definePageMeta({ middleware: 'vendor', layout: 'vendeur' })

const { apiFetch } = useApi()
const toast = useToastStore()
const route = useRoute()
const router = useRouter()
const apiBase = useApiBase()

// getCachedData: hydrateThenRefetch disables Nuxt's static cross-navigation
// cache — without it, switching tabs in the vendor bottom nav and coming
// back here re-mounts the page but silently reuses the stale pre-transition
// list instead of refetching (see app/pages/vendeur/index.vue for the same fix).
const { data: subOrders, pending, refresh } = await useAsyncData(
  'vendor-sub-orders',
  () => apiFetch<VendorSubOrderRead[]>('/orders/sub-orders'),
  { default: () => [], getCachedData: hydrateThenRefetch },
)

const { data: couriers } = await useAsyncData(
  'vendor-couriers',
  () => apiFetch<CourierRead[]>('/couriers'),
  { default: () => [] },
)

const courierOptions = computed(() =>
  couriers.value.map((c) => ({ title: `${c.full_name ?? c.phone} (${c.vehicle_type})`, value: c.id })),
)

const assigningId = ref<string | null>(null)
const courierSelection = ref<Record<string, string | null>>({})

function courierSelectionFor(subOrder: VendorSubOrderRead) {
  if (!(subOrder.id in courierSelection.value)) {
    courierSelection.value[subOrder.id] = subOrder.courier_id
  }
  return courierSelection.value[subOrder.id]
}

async function assignCourier(subOrder: VendorSubOrderRead) {
  const courierId = courierSelection.value[subOrder.id] ?? null
  assigningId.value = subOrder.id
  try {
    await apiFetch<VendorSubOrderRead>(`/orders/sub-orders/${subOrder.id}/courier`, {
      method: 'PATCH',
      body: { courier_id: courierId },
    })
    await refresh()
    toast.success('Livreur assigné.')
  } catch (e) {
    toast.error(apiErrorMessage(e, "Impossible d'assigner ce livreur."))
  } finally {
    assigningId.value = null
  }
}

// Recherche par proximité (voir POST /orders/sub-orders/{id}/dispatch) —
// remplace le choix manuel comme chemin principal ; celui-ci reste
// disponible en repli (showManualAssign) au cas où la recherche automatique
// ne trouve personne, la boutique n'a pas encore de position, etc.
const vehicleFilterOptions = [
  { title: "N'importe quel engin", value: null },
  { title: 'Moto', value: 'moto' },
  { title: 'Taxi', value: 'taxi' },
  { title: 'Voiture', value: 'voiture' },
]
const dispatchVehicleFilter = ref<Record<string, VehicleType | null>>({})
const dispatchingId = ref<string | null>(null)
const showManualAssign = ref<Record<string, boolean>>({})

function vehicleFilterFor(subOrder: VendorSubOrderRead) {
  if (!(subOrder.id in dispatchVehicleFilter.value)) {
    dispatchVehicleFilter.value[subOrder.id] = null
  }
  return dispatchVehicleFilter.value[subOrder.id]
}

async function startDispatch(subOrder: VendorSubOrderRead) {
  dispatchingId.value = subOrder.id
  try {
    await apiFetch<VendorSubOrderRead>(`/orders/sub-orders/${subOrder.id}/dispatch`, {
      method: 'POST',
      body: { vehicle_type: dispatchVehicleFilter.value[subOrder.id] ?? undefined },
    })
    await refresh()
    toast.success('Recherche lancée — le livreur le plus proche a été notifié.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de lancer la recherche.'))
  } finally {
    dispatchingId.value = null
  }
}

// Rafraîchit dès que le dispatch aboutit (livreur trouvé) ou échoue (aucun
// livreur) — ces deux notifications arrivent en push pendant que la page est
// ouverte (voir app/notifications/service.py::notify_delivery_request_accepted
// et notify_delivery_no_courier_found côté backend).
const notifications = useNotificationStore()
watch(
  () => notifications.items[0],
  (latest) => {
    if (latest && (latest.type === 'delivery_request_accepted' || latest.type === 'delivery_no_courier_found')) {
      refresh()
    }
  },
)

type StatusFilter = OrderStatus | 'all' | 'todo'
// « À traiter » : ce qui attend une action du vendeur (confirmer, préparer, expédier).
// Colis non retiré : trouver un livreur pour le retour, puis le réceptionner.
const TODO_STATUSES: OrderStatus[] = ['pending', 'confirmed', 'preparing', 'return_pending', 'returning']
const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'todo', label: 'À traiter' },
  { value: 'all', label: 'Toutes' },
  { value: 'pending', label: 'En attente' },
  { value: 'confirmed', label: 'Confirmée' },
  { value: 'preparing', label: 'En préparation' },
  { value: 'shipped', label: 'Expédiée' },
  { value: 'arrived_at_pickup_point', label: 'Arrivée au point' },
  { value: 'delivered', label: 'Livrée' },
  { value: 'return_pending', label: 'Retour à organiser' },
  { value: 'returning', label: 'Retour en cours' },
  { value: 'returned', label: 'Rendue' },
  { value: 'cancelled', label: 'Annulée' },
]

// Arrivée depuis une notification ("commande reçue") : on force le filtre à
// "Toutes" (la commande neuve est "pending", déjà couvert, mais évite toute
// surprise si un jour le lien pointe vers une commande à un autre stade) et
// on scroll jusqu'à sa carte une fois la liste chargée.
const highlightOrderId = route.query.highlight as string | undefined
// ?status=… : arrivée depuis une carte « À faire » du tableau de bord.
const statusFilter = ref<StatusFilter>(
  typeof route.query.status === 'string' && !highlightOrderId ? (route.query.status as OrderStatus) : highlightOrderId ? 'all' : 'todo',
)
// Rien à traiter à l'arrivée : on montre tout plutôt qu'une liste vide.
watch(
  subOrders,
  (list) => {
    if (statusFilter.value === 'todo' && list.length && !list.some((so) => TODO_STATUSES.includes(so.status))) {
      statusFilter.value = 'all'
    }
  },
  { immediate: true },
)
const search = ref('')

watch(
  subOrders,
  async (list) => {
    if (!highlightOrderId || list.length === 0) return
    await nextTick()
    document.getElementById(`sub-order-${highlightOrderId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    router.replace({ query: {} })
  },
  { immediate: true },
)

const statusCounts = computed(() => {
  const counts: Record<string, number> = { all: subOrders.value.length, todo: 0 }
  for (const so of subOrders.value) {
    counts[so.status] = (counts[so.status] ?? 0) + 1
    if (TODO_STATUSES.includes(so.status)) counts.todo! += 1
  }
  return counts
})

const visible = computed(() => {
  const query = search.value.trim().toLowerCase()
  return subOrders.value.filter((so) => {
    if (statusFilter.value === 'todo' && !TODO_STATUSES.includes(so.status)) return false
    if (statusFilter.value !== 'all' && statusFilter.value !== 'todo' && so.status !== statusFilter.value) return false
    if (!query) return true
    return (
      shortId(so.order_id).toLowerCase().includes(query) ||
      so.items.some((item) => item.product_name.toLowerCase().includes(query))
    )
  })
})

// Mirrors backend app/orders/service.py::_ALLOWED_TRANSITIONS — the vendor
// only ever drives what happens before the parcel leaves their hands
// (accepter, préparer, expédier, annuler). Once expédiée, the vendor no
// longer has any action here : confirming receipt/remise is exclusively the
// livreur's (livraison à domicile) or the point de retrait manager's
// (retrait) job — see update_sub_order_status's is_owner_vendor guard.
const ACTIONS: Record<OrderStatus, { label: string; to: OrderStatus; color: string; variant?: 'outlined' }[]> = {
  pending: [
    { label: 'Confirmer', to: 'confirmed', color: 'primary' },
    { label: 'Refuser', to: 'cancelled', color: 'error', variant: 'outlined' },
  ],
  confirmed: [
    { label: 'Mettre en préparation', to: 'preparing', color: 'primary' },
    { label: 'Annuler', to: 'cancelled', color: 'error', variant: 'outlined' },
  ],
  preparing: [{ label: 'Marquer expédiée', to: 'shipped', color: 'primary' }],
  shipped: [],
  arrived_at_pickup_point: [],
  return_pending: [],
  returning: [],
  returned: [],
  delivered: [],
  cancelled: [],
}

function actionsFor(so: VendorSubOrderRead) {
  return ACTIONS[so.status]
}

// Ce que le vendeur voit une fois qu'il n'a plus la main — purement
// informatif, pour qu'il comprenne qui doit agir ensuite plutôt que de se
// demander pourquoi il n'y a plus de bouton.
function waitingMessage(so: VendorSubOrderRead): string | null {
  if (so.status === 'shipped') {
    return so.delivery_type === 'pickup_point'
      ? 'En attente de dépôt au point de retrait par le livreur.'
      : 'En attente de confirmation de livraison par le livreur.'
  }
  if (so.status === 'arrived_at_pickup_point') {
    return 'En attente de remise au client par le gestionnaire du point de retrait.'
  }
  if (so.status === 'return_pending') {
    return so.courier_name
      ? `${so.courier_name} va récupérer le colis au point de retrait pour vous le rapporter.`
      : "Le client n'a pas retiré sa commande : trouvez un livreur ci-dessus pour la rapporter. Le retour est à sa charge, pas à la vôtre."
  }
  if (so.status === 'returned') return 'Colis rendu : les articles sont revenus en stock.'
  return null
}

// Un colis ne peut pas être marqué expédié sans livreur assigné pour le
// transporter (voir app/orders/service.py::update_sub_order_status, qui
// rejette la transition côté backend) — désactivé ici en plus pour ne pas
// laisser le vendeur cliquer dans le vide.
function isActionDisabled(so: VendorSubOrderRead, action: { to: OrderStatus }) {
  return action.to === 'shipped' && !so.courier_id
}

// --- Retour d'un colis non retiré : réception par scan du QR du livreur ---
const scannerOpen = ref(false)
async function receiveReturn(code: string) {
  try {
    await apiFetch('/orders/sub-orders/confirm-delivery', { method: 'POST', body: { code } })
    await refresh()
    toast.success('Colis réceptionné : les articles sont revenus en stock.')
  } catch (e) {
    toast.error(apiErrorMessage(e, 'QR code invalide ou expiré.'))
  }
}

const updatingId = ref<string | null>(null)

async function transition(subOrder: VendorSubOrderRead, to: OrderStatus) {
  updatingId.value = subOrder.id
  try {
    await apiFetch<VendorSubOrderRead>(`/orders/sub-orders/${subOrder.id}/status`, {
      method: 'PATCH',
      body: { status: to },
    })
    await refresh()
  } catch (e) {
    toast.error(apiErrorMessage(e, 'Impossible de mettre à jour cette commande.'))
  } finally {
    updatingId.value = null
  }
}

// Commandes terminées (livrées, annulées) : carte repliée, détails à la demande.
const isClosed = (so: VendorSubOrderRead) => ['delivered', 'cancelled', 'returned'].includes(so.status)
const expanded = ref<Record<string, boolean>>({})
const showDetails = (so: VendorSubOrderRead) => !isClosed(so) || !!expanded.value[so.id]

function shortId(orderId: string) {
  return `#GN-${orderId.slice(0, 5).toUpperCase()}`
}
function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="dashboard-shell">
    <div class="vo-head mb-3">
      <div>
        <h1 class="text-h6 mb-0">Commandes</h1>
        <p class="text-muted mb-0" style="font-size: 13px">
          <template v-if="statusCounts.todo">{{ statusCounts.todo }} commande{{ statusCounts.todo > 1 ? 's' : '' }} attend{{ statusCounts.todo > 1 ? 'ent' : '' }} votre action.</template>
          <template v-else>Rien à traiter pour le moment.</template>
        </p>
      </div>
      <v-text-field
        v-model="search"
        placeholder="Rechercher par code ou produit…"
        density="compact"
        variant="outlined"
        hide-details
        clearable
        class="vo-search"
      >
        <template #prepend-inner><PhMagnifyingGlass :size="16" color="var(--color-neutral-500)" /></template>
      </v-text-field>
    </div>

    <div class="status-filters mb-4">
      <button
        v-for="f in STATUS_FILTERS"
        :key="f.value"
        type="button"
        class="status-filter"
        :class="{ 'status-filter--active': statusFilter === f.value }"
        @click="statusFilter = f.value"
      >
        {{ f.label }}
        <span class="status-filter__count">{{ statusCounts[f.value] ?? 0 }}</span>
      </button>
    </div>

    <CommonEmptyState v-if="!pending && visible.length === 0" message="Aucune commande ici pour le moment." />

    <div class="sub-order-grid">
    <v-card
      v-for="so in visible"
      :id="`sub-order-${so.order_id}`"
      :key="so.id"
      class="vo-card pa-4"
      :class="[`vo-card--${so.status}`, { 'sub-order-card--highlight': so.order_id === highlightOrderId }]"
    >
      <div class="d-flex justify-space-between align-center ga-2 mb-1">
        <OrderNumber :id="so.order_id" />
        <StatusBadge :status="so.status" />
      </div>
      <div class="d-flex justify-space-between align-center mb-3 text-muted" style="font-size: 12px">
        <span>{{ formatDate(so.created_at) }} · {{ so.delivery_type === 'pickup_point' ? 'Point de retrait' : 'Domicile' }}</span>
        <strong class="order-amount">{{ formatGnf(so.amount) }}</strong>
      </div>

      <div v-for="item in so.items" :key="item.id" class="order-item-row mb-2">
        <NuxtLink :to="`/produits/${item.product_id}`" class="order-item-row__thumb">
          <img
            v-if="item.product_image"
            :src="resolveImageUrl(item.product_image, apiBase, 160)"
            :alt="item.product_name"
            loading="lazy"
          />
          <PhImage v-else :size="22" weight="light" color="var(--color-neutral-500)" />
        </NuxtLink>
        <span class="order-item-row__label" style="font-size: 13px"
          >{{ item.product_name }}<span v-if="item.variant_label" class="text-muted"> ({{ item.variant_label }})</span> ×
          {{ item.quantity }}</span
        >
        <span style="font-size: 13px">{{ formatGnf(item.unit_price * item.quantity) }}</span>
      </div>

      <button v-if="isClosed(so)" type="button" class="vo-toggle" @click="expanded[so.id] = !expanded[so.id]">
        {{ expanded[so.id] ? 'Masquer les détails' : 'Voir les détails' }}
        <PhCaretDown :size="13" :style="{ transform: expanded[so.id] ? 'rotate(180deg)' : '' }" />
      </button>

      <template v-if="showDetails(so)">
      <OrderDeliveryDetails
        class="mt-3 mb-3"
        :zone="so.delivery_zone"
        :address="so.delivery_address"
        :instructions="so.delivery_instructions"
        :delivery-type="so.delivery_type"
        :recipient-name="so.recipient_name"
        :recipient-phone="so.recipient_phone"
        :pickup-point-contacts="so.pickup_point_contacts"
        :note="so.delivery_type === 'pickup_point' ? 'Le client viendra le récupérer en personne.' : null"
      />

      <p
        v-if="so.estimated_delivery_min && so.estimated_delivery_max && !['delivered', 'cancelled'].includes(so.status)"
        class="text-muted mb-3"
        style="font-size: 11.5px"
      >
        Estimation annoncée au client :
        <strong>{{ formatDeliveryEstimate(so.estimated_delivery_min, so.estimated_delivery_max) }}</strong>
      </p>

      <div v-if="!['delivered', 'cancelled', 'returned'].includes(so.status)" class="courier-assign mb-3">
        <div class="d-flex align-center ga-1 mb-1">
          <PhMotorcycle :size="15" color="var(--color-primary)" />
          <span class="field-label mb-0">Livreur</span>
        </div>

        <!-- Déjà assigné (recherche réussie ou choix manuel) — rien d'autre à faire. -->
        <div v-if="so.courier_name" class="text-muted" style="font-size: 12.5px">
          Assigné à {{ so.courier_name }} · {{ so.courier_phone }}
        </div>

        <!-- Recherche en cours : offre envoyée à un livreur, en attente de sa réponse. -->
        <div v-else-if="so.dispatch_offered_courier_id" class="d-flex align-center ga-2" style="font-size: 12.5px">
          <v-progress-circular indeterminate size="16" width="2" color="primary" />
          <span class="text-muted">En attente de réponse de {{ so.dispatch_offered_courier_name }}…</span>
        </div>

        <!-- Rien en cours : recherche automatique par proximité, choix manuel en repli. -->
        <template v-else>
          <div class="d-flex ga-2 mb-1">
            <v-select
              :model-value="vehicleFilterFor(so)"
              :items="vehicleFilterOptions"
              density="compact"
              variant="outlined"
              hide-details
              class="flex-grow-1"
              @update:model-value="(v) => (dispatchVehicleFilter[so.id] = v)"
            />
            <v-btn size="small" color="primary" :loading="dispatchingId === so.id" @click="startDispatch(so)">
              <PhMagnifyingGlass :size="14" class="mr-1" />
              Chercher un livreur
            </v-btn>
          </div>

          <button type="button" class="manual-assign-toggle" @click="showManualAssign[so.id] = !showManualAssign[so.id]">
            {{ showManualAssign[so.id] ? 'Masquer le choix manuel' : 'Ou choisir manuellement' }}
          </button>

          <div v-if="showManualAssign[so.id]" class="d-flex ga-2 mt-2">
            <v-select
              :model-value="courierSelectionFor(so)"
              :items="courierOptions"
              placeholder="Non assigné"
              density="compact"
              variant="outlined"
              hide-details
              clearable
              class="flex-grow-1"
              @update:model-value="(v) => (courierSelection[so.id] = v)"
            />
            <v-btn
              size="small"
              variant="tonal"
              :loading="assigningId === so.id"
              :disabled="courierSelectionFor(so) === (so.courier_id ?? null)"
              @click="assignCourier(so)"
            >
              OK
            </v-btn>
          </div>
        </template>
      </div>

      <v-divider class="mb-2" />

      <div class="d-flex justify-space-between mb-3" style="font-size: 13px">
        <span class="text-muted">Commission NdjouriMarket</span>
        <span>− {{ formatGnf(so.commission) }}</span>
      </div>
      </template>
      <div class="d-flex justify-space-between mb-3" style="font-size: 13px">
        <span class="text-muted">Taille du colis</span>
        <span>
          {{ parcelSizeLabel(so.parcel_size) }}
          <em v-if="so.declared_parcel_size && so.parcel_size !== so.declared_parcel_size" class="text-muted">
            (corrigée par le point, déclarée {{ so.declared_parcel_size }})
          </em>
        </span>
      </div>
      <div v-if="so.vendor_delivery_fee" class="d-flex justify-space-between mb-3 offered-line">
        <span>Retrait offert au client (prélevé à la livraison)</span>
        <strong>− {{ formatGnf(so.vendor_delivery_fee) }}</strong>
      </div>

      <div v-if="actionsFor(so).length" class="d-flex flex-column ga-1">
        <div class="d-flex ga-2">
          <v-btn
            v-for="action in actionsFor(so)"
            :key="action.to"
            :color="action.color"
            :variant="action.variant"
            size="small"
            class="flex-grow-1"
            :loading="updatingId === so.id"
            :disabled="isActionDisabled(so, action)"
            @click="transition(so, action.to)"
          >
            {{ action.label }}
          </v-btn>
        </div>
        <span v-if="actionsFor(so).some((a) => isActionDisabled(so, a))" class="text-muted" style="font-size: 11px">
          Assignez un livreur ci-dessus avant de pouvoir marquer cette commande expédiée.
        </span>
      </div>
      <div v-else-if="so.status === 'returning'" class="return-receive">
        <span>{{ so.courier_name ?? 'Le livreur' }} vous rapporte le colis : scannez son QR code à la réception.</span>
        <v-btn color="primary" size="small" @click="scannerOpen = true">
          <PhQrCode :size="16" class="mr-1" />
          Scanner le livreur
        </v-btn>
      </div>
      <p v-else-if="waitingMessage(so)" class="text-muted mb-0" style="font-size: 12px">
        {{ waitingMessage(so) }}
      </p>
    </v-card>
    </div>

    <VendorQrScannerDialog v-model="scannerOpen" @decode="receiveReturn" />
  </div>
</template>

<style scoped>
.vo-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.vo-search {
  flex: 1 1 260px;
  max-width: 420px;
}

.vo-card {
  margin-bottom: 14px;
  border-left: 4px solid var(--vo-accent, var(--color-divider));
}

.vo-card--pending { --vo-accent: hsl(38 90% 52%); }
.vo-card--confirmed,
.vo-card--preparing { --vo-accent: var(--color-primary); }
.vo-card--shipped,
.vo-card--arrived_at_pickup_point { --vo-accent: hsl(265 70% 60%); }
.vo-card--return_pending,
.vo-card--returning { --vo-accent: hsl(30 85% 52%); }

.return-receive {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: hsl(30 90% var(--tint-bg-soft, 17%));
  color: hsl(30 70% var(--tint-fg));
  font-size: 12.5px;
}
.vo-card--delivered { --vo-accent: hsl(150 60% 45%); }
.vo-card--cancelled { --vo-accent: var(--color-neutral-600); }

.vo-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--color-primary-300);
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
}

.offered-line {
  padding: 8px 10px;
  border-radius: var(--radius-md);
  background: hsl(150 70% var(--tint-bg));
  color: hsl(150 55% var(--tint-fg));
  font-size: 12.5px;
}

/* Une seule colonne pleine largeur reste illisible passé 960px (cartes
   étirées sur près de 1400px, voir .dashboard-shell) — sur grand écran, les
   commandes se répartissent plutôt sur plusieurs colonnes, chacune bornée à
   une largeur de carte confortable, sans jamais dépendre d'un nombre de
   colonnes fixe (auto-fill s'adapte à la largeur réelle disponible). */
.sub-order-grid {
  display: grid;
  grid-template-columns: 1fr;
  align-items: start;
  gap: 0;
}

@media (min-width: 960px) {
  .sub-order-grid {
    grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
    gap: 0 16px;
  }
}

.order-item-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 34px lisait mal les détails du produit (tissu, couleur exacte...) dont un
   vendeur a justement besoin pour préparer la bonne commande — remonté à une
   taille qui reste une vignette (pas une photo pleine) mais où le produit
   reste identifiable au premier coup d'œil. */
.order-item-row__thumb {
  width: 48px;
  height: 48px;
  flex: none;
  border-radius: var(--radius-sm);
  background: var(--color-neutral-800);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

@media (min-width: 960px) {
  .order-item-row__thumb {
    width: 60px;
    height: 60px;
  }
}

.order-item-row__thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.order-item-row__label {
  flex: 1 1 auto;
  min-width: 0;
}

.manual-assign-toggle {
  display: inline-flex;
  align-items: center;
  background: none;
  border: none;
  color: var(--color-primary-300);
  font-size: 12px;
  font-weight: 600;
  padding: 0;
  cursor: pointer;
}

.sub-order-card--highlight {
  outline: 2px solid var(--color-primary);
  animation: highlight-fade 2.5s ease-out 1;
}

@keyframes highlight-fade {
  0% {
    /* --color-accent-900 référencé ici auparavant n'a jamais existé comme
       token — cette règle utilisait donc toujours son fallback blanc, déjà
       peu visible et désormais invisible sur fond clair. */
    background: rgba(10, 102, 245, 0.1);
  }
  100% {
    background: transparent;
  }
}

.status-filters {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: none;
}
.status-filters::-webkit-scrollbar {
  display: none;
}

.status-filter {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  color: var(--color-neutral-300);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.status-filter--active {
  border-color: var(--color-primary);
  background: var(--color-primary-800);
  color: var(--color-primary-100);
}

.status-filter__count {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 999px;
  padding: 1px 6px;
  font-size: 10.5px;
}

.status-filter--active .status-filter__count {
  background: rgba(0, 0, 0, 0.25);
}

.order-code {
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 13.5px;
  letter-spacing: 0.01em;
  color: var(--color-primary-300);
}

.order-amount {
  font-family: var(--font-heading);
  font-weight: 700;
  font-size: 15px;
  color: var(--color-primary-300);
}
</style>
