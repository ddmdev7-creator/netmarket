<script setup lang="ts">
import { PhImage, PhTruck, PhWarningCircle } from '@phosphor-icons/vue'
import type { OrderRead } from '~/types/api'

definePageMeta({ middleware: 'auth' })

const { apiFetch } = useApi()
const apiBase = useApiBase()

// Pas plus de 4 vignettes par commande — au-delà, "+N" plutôt que de
// surcharger une ligne de liste censée rester un aperçu, pas le détail
// (déjà disponible en ouvrant la commande).
const MAX_THUMBS = 4

function orderItems(order: OrderRead) {
  return order.sub_orders.flatMap((so) => so.items)
}

const { data: orders, pending, error } = await useAsyncData('my-orders', () => apiFetch<OrderRead[]>('/orders'), {
  default: () => [],
})

const tab = ref<'ongoing' | 'done'>('ongoing')

const ongoing = computed(() => orders.value.filter((o) => !['delivered', 'cancelled'].includes(o.status)))
const done = computed(() => orders.value.filter((o) => ['delivered', 'cancelled'].includes(o.status)))
const visible = computed(() => (tab.value === 'ongoing' ? ongoing.value : done.value))

// Un seul délai pour toute la commande (aperçu, pas le détail — voir
// commandes/[id].vue pour le délai par boutique) : la fourchette la plus
// large parmi les sous-commandes pas encore livrées/annulées, même logique
// d'exclusion que sur la page de détail.
function orderDeliveryEstimate(order: OrderRead): string | null {
  const pending = order.sub_orders.filter(
    (so) => so.estimated_delivery_min && so.estimated_delivery_max && !['delivered', 'cancelled'].includes(so.status),
  )
  if (pending.length === 0) return null
  const min = pending.map((so) => so.estimated_delivery_min!).sort()[0]!
  const max = pending.map((so) => so.estimated_delivery_max!).sort().at(-1)!
  return formatDeliveryEstimate(min, max)
}

function vendorCount(order: OrderRead) {
  return order.sub_orders.length
}
function itemCount(order: OrderRead) {
  return order.sub_orders.reduce((sum, so) => sum + so.items.reduce((s, i) => s + i.quantity, 0), 0)
}
function shortId(id: string) {
  return `#GN-${id.slice(0, 5).toUpperCase()}`
}
function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })
}
</script>

<template>
  <!-- Pas de .app-shell ici : layouts/default.vue en fournit déjà un (avec
       app-shell--catalog pour cette route, voir ce fichier) -- un deuxième
       wrapper imbriqué ici replafonnerait à 720px, annulant l'élargissement
       du bandeau du haut. .detail-card (main.css) recentre LE CONTENU en
       une carte détachée, sans replafonner LayoutTopBar avec -- impose son
       propre padding (plus de .pa-4 ici), la marge sous la bottom nav
       mobile vient déjà de .buyer-shell (layouts/default.vue). -->
  <div class="detail-card">
    <h1 class="text-h6 mb-3">Mes commandes</h1>

    <v-btn-toggle v-model="tab" mandatory density="comfortable" divided class="mb-4">
      <v-btn value="ongoing">En cours</v-btn>
      <v-btn value="done">Terminées</v-btn>
    </v-btn-toggle>

    <div v-if="pending">
      <v-skeleton-loader v-for="n in 3" :key="n" type="list-item-two-line" class="mb-2" />
    </div>
    <CommonEmptyState
      v-else-if="error"
      :icon="PhWarningCircle"
      message="Impossible de charger vos commandes. Réessayez plus tard."
    />
    <CommonEmptyState v-else-if="visible.length === 0" message="Aucune commande ici pour le moment." />

    <NuxtLink v-for="order in visible" :key="order.id" :to="`/commandes/${order.id}`" class="order-row">
      <div class="d-flex justify-space-between align-center">
        <span style="font-weight: 600">{{ shortId(order.id) }}</span>
        <StatusBadge :status="order.status" />
      </div>
      <div class="order-thumbs mt-2">
        <div v-for="item in orderItems(order).slice(0, MAX_THUMBS)" :key="item.id" class="order-thumbs__item">
          <img
            v-if="item.product_image"
            :src="resolveImageUrl(item.product_image, apiBase)"
            :alt="item.product_name"
            loading="lazy"
          />
          <PhImage v-else :size="14" weight="light" color="var(--color-neutral-500)" />
        </div>
        <div v-if="orderItems(order).length > MAX_THUMBS" class="order-thumbs__more">
          +{{ orderItems(order).length - MAX_THUMBS }}
        </div>
      </div>
      <div class="text-muted mt-1 text-meta">
        {{ formatDate(order.created_at) }} · {{ itemCount(order) }} article{{ itemCount(order) > 1 ? 's' : '' }} ·
        {{ vendorCount(order) }} boutique{{ vendorCount(order) > 1 ? 's' : '' }}
      </div>
      <div v-if="orderDeliveryEstimate(order)" class="text-meta delivery-estimate mt-1">
        <PhTruck :size="12" weight="bold" />
        Livraison estimée : <strong>{{ orderDeliveryEstimate(order) }}</strong>
      </div>
      <div class="d-flex justify-space-between mt-1">
        <span class="text-muted text-meta">Total</span>
        <span class="text-meta">{{ formatGnf(order.total) }}</span>
      </div>
    </NuxtLink>
  </div>
</template>

<style scoped>
.order-row {
  display: block;
  padding: 12px 0;
  border-bottom: 1px solid var(--color-divider);
  text-decoration: none;
  color: inherit;
}

.order-thumbs {
  display: flex;
  align-items: center;
  gap: 6px;
}

.order-thumbs__item {
  width: 30px;
  height: 30px;
  flex: none;
  border-radius: var(--radius-sm);
  background: var(--color-neutral-800);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.order-thumbs__item img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.order-thumbs__more {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-neutral-400);
}

.delivery-estimate {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--color-neutral-300);
}
</style>
