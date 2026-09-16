<script setup lang="ts">
import type { OrderRead, OrderStatus, Page } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()
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
  { default: () => emptyPage, getCachedData: () => undefined },
)

watch([page, statusFilter], () => refresh())

const orders = computed(() => ordersPage.value?.items ?? [])
const pageCount = computed(() => Math.max(1, ordersPage.value?.pages ?? 1))

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
      class="mb-4"
    />

    <CommonEmptyState v-if="!pending && orders.length === 0" message="Aucune commande." />

    <v-card v-for="order in orders" :key="order.id" class="mb-3 pa-3">
      <div class="d-flex justify-space-between align-center mb-2">
        <span style="font-weight: 600">{{ shortId(order.id) }}</span>
        <StatusBadge :status="order.status" />
      </div>
      <div class="text-muted mb-2" style="font-size: 12px">{{ formatDate(order.created_at) }}</div>

      <div v-for="so in order.sub_orders" :key="so.id" class="d-flex justify-space-between mb-1" style="font-size: 13px">
        <span>{{ so.shop_name }}</span>
        <span class="text-muted">{{ so.status }}</span>
      </div>

      <v-divider class="my-2" />

      <div class="d-flex justify-space-between align-center" style="font-size: 13px">
        <span class="text-muted">
          {{ order.payment_method === 'cash_on_delivery' ? 'Paiement à la livraison' : order.payment_method }}
          · {{ order.payment_status ?? '—' }}
        </span>
        <span style="font-weight: 600">{{ formatGnf(order.total) }}</span>
      </div>
    </v-card>

    <v-pagination v-if="pageCount > 1" v-model="page" :length="pageCount" density="compact" class="mt-4" />
  </div>
</template>
