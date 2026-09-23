<script setup lang="ts">
import { PhImage } from '@phosphor-icons/vue'
import type { OrderRead, OrderStatus, Page } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
const apiBase = useApiBase()
const pageSize = 20

const statusFilter = ref<OrderStatus | 'all'>('all')
const statusOptions: { value: OrderStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'Toutes' },
  { value: 'pending', label: 'En attente' },
  { value: 'confirmed', label: 'Confirmée' },
  { value: 'preparing', label: 'En préparation' },
  { value: 'shipped', label: 'Expédiée' },
  { value: 'delivered', label: 'Livrée' },
  { value: 'cancelled', label: 'Annulée' },
]

const page = ref(1)
const emptyPage: Page<OrderRead> = { items: [], total: 0, page: 1, page_size: pageSize, pages: 0 }

const {
  data: ordersPage,
  pending,
  refresh,
} = await useAsyncData(
  'admin-orders',
  () =>
    apiFetch<Page<OrderRead>>('/admin/orders', {
      query: { page: page.value, page_size: pageSize, status: statusFilter.value === 'all' ? undefined : statusFilter.value },
    }),
  { default: () => emptyPage, getCachedData: hydrateThenRefetch },
)

watch([page, statusFilter], () => refresh())

const orders = computed(() => ordersPage.value?.items ?? [])
const pageCount = computed(() => Math.max(1, ordersPage.value?.pages ?? 1))

function orderItems(order: OrderRead) {
  return order.sub_orders.flatMap((so) => so.items)
}

function shortId(orderId: string) {
  return `#GN-${orderId.slice(0, 5).toUpperCase()}`
}
function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="dashboard-shell">
    <h1 class="text-h6 mb-4">Toutes les commandes</h1>

    <v-select
      v-model="statusFilter"
      :items="statusOptions"
      item-title="label"
      item-value="value"
      label="Statut"
      density="compact"
      variant="outlined"
      hide-details
      class="mb-4 filter-select"
    />

    <div v-if="pending" class="orders-grid">
      <v-skeleton-loader v-for="n in 6" :key="n" type="card" />
    </div>
    <CommonEmptyState v-else-if="orders.length === 0" message="Aucune commande." />

    <div v-else class="orders-grid">
      <NuxtLink v-for="order in orders" :key="order.id" :to="`/admin/commandes/${order.id}`" class="order-card">
        <div class="d-flex justify-space-between align-center mb-2">
          <span class="order-code">{{ shortId(order.id) }}</span>
          <StatusBadge :status="order.status" />
        </div>
        <div class="text-muted mb-3" style="font-size: 12px">{{ formatDate(order.created_at) }}</div>

        <div class="order-thumbs mb-3">
          <div v-for="item in orderItems(order).slice(0, 4)" :key="item.id" class="order-thumbs__item">
            <img
              v-if="item.product_image"
              :src="resolveImageUrl(item.product_image, apiBase)"
              :alt="item.product_name"
              loading="lazy"
            />
            <PhImage v-else :size="18" weight="light" color="var(--color-neutral-500)" />
          </div>
          <div v-if="orderItems(order).length > 4" class="order-thumbs__more">
            +{{ orderItems(order).length - 4 }}
          </div>
        </div>

        <div v-for="so in order.sub_orders" :key="so.id" class="d-flex justify-space-between mb-1" style="font-size: 13px">
          <span class="text-muted">{{ so.shop_name }}</span>
          <StatusBadge :status="so.status" />
        </div>

        <v-divider class="my-2" />

        <div class="d-flex justify-space-between align-center" style="font-size: 13px">
          <span class="text-muted">
            {{ PAYMENT_METHOD_LABELS[order.payment_method].paid }}
            · {{ order.payment_status ?? '—' }}
          </span>
          <span class="order-amount">{{ formatGnf(order.total) }}</span>
        </div>
      </NuxtLink>
    </div>

    <v-pagination v-if="pageCount > 1" v-model="page" :length="pageCount" density="compact" class="mt-4" />
  </div>
</template>

<style scoped>
.filter-select {
  max-width: 280px;
}

/* Même logique que les autres listes admin/vendeur redesignées : une seule
   colonne pleine largeur devient illisible sur un grand écran (cartes
   étirées sur toute la largeur de .dashboard-shell), donc plusieurs
   colonnes dès que la place le permet, auto-fill plutôt qu'un nombre fixe. */
.orders-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

@media (min-width: 720px) {
  .orders-grid {
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  }
}

.order-card {
  display: block;
  padding: 14px;
  border-radius: var(--radius-lg);
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  box-shadow: var(--shadow-sm);
  text-decoration: none;
  color: inherit;
  transition: box-shadow 0.15s ease, transform 0.15s ease;
}

.order-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
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
  color: var(--color-primary-300);
}

.order-thumbs {
  display: flex;
  align-items: center;
  gap: 6px;
}

.order-thumbs__item {
  width: 40px;
  height: 40px;
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
</style>
