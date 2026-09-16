<script setup lang="ts">
import type { AdminStats, OrderStatus } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()

// getCachedData: () => undefined — ces chiffres bougent à chaque action
// (validation vendeur, commande livrée...), voir vendeur/index.vue pour le
// même raisonnement.
const { data: stats, pending } = await useAsyncData(
  'admin-stats',
  () => apiFetch<AdminStats>('/admin/stats'),
  { getCachedData: () => undefined },
)

const tiles = computed(() => {
  if (!stats.value) return []
  const s = stats.value
  return [
    { label: 'Boutiques', value: String(s.total_vendors) },
    { label: 'En attente de validation', value: String(s.pending_vendors) },
    { label: 'Produits', value: String(s.total_products) },
    { label: 'Commandes', value: String(s.total_orders) },
    { label: 'Ventes (livrées)', value: formatGnf(s.total_sales) },
    { label: 'Commission (livrée)', value: formatGnf(s.total_commission) },
  ]
})

const statusLabels: Record<OrderStatus, string> = {
  pending: 'En attente',
  confirmed: 'Confirmée',
  preparing: 'En préparation',
  shipped: 'Expédiée',
  arrived_at_pickup_point: 'Arrivée au point de retrait',
  delivered: 'Livrée',
  cancelled: 'Annulée',
}
</script>

<template>
  <div class="dashboard-shell">
    <h1 class="text-h6 mb-4">Statistiques plateforme</h1>

    <div class="stat-grid mb-5">
      <v-skeleton-loader v-if="pending" type="card" class="stat-tile" v-for="n in 6" :key="n" />
      <div v-else v-for="tile in tiles" :key="tile.label" class="stat-tile">
        <div class="stat-tile__value">{{ tile.value }}</div>
        <div class="stat-tile__label">{{ tile.label }}</div>
      </div>
    </div>

    <template v-if="stats">
      <v-card class="chart-card mb-4" variant="flat">
        <div class="chart-card__title">Commandes par statut</div>
        <div v-for="status in Object.keys(statusLabels) as OrderStatus[]" :key="status" class="status-row">
          <span>{{ statusLabels[status] }}</span>
          <span style="font-weight: 600">{{ stats.orders_by_status[status] ?? 0 }}</span>
        </div>
      </v-card>

      <v-card class="chart-card mb-4" variant="flat">
        <div class="chart-card__title">Top 5 produits (quantité vendue)</div>
        <CommonEmptyState v-if="stats.top_products.length === 0" message="Pas encore de ventes." />
        <div v-for="p in stats.top_products" :key="p.product_id" class="status-row">
          <span>{{ p.product_name }}</span>
          <span style="font-weight: 600">{{ p.quantity_sold }}</span>
        </div>
      </v-card>

      <v-card class="chart-card mb-5" variant="flat">
        <div class="chart-card__title">Top 5 boutiques (chiffre d'affaires)</div>
        <CommonEmptyState v-if="stats.top_vendors.length === 0" message="Pas encore de ventes." />
        <div v-for="v in stats.top_vendors" :key="v.vendor_id" class="status-row">
          <span>{{ v.shop_name }}</span>
          <span style="font-weight: 600">{{ formatGnf(v.revenue) }}</span>
        </div>
      </v-card>
    </template>
  </div>
</template>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

@media (min-width: 768px) {
  .stat-grid {
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
  }
}

@media (min-width: 1200px) {
  .stat-grid {
    grid-template-columns: repeat(6, 1fr);
  }
}

.stat-tile {
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  padding: 12px;
}

.stat-tile__value {
  font-family: var(--font-heading);
  font-size: 17px;
  font-weight: 700;
}

.stat-tile__label {
  font-size: 11px;
  color: var(--color-neutral-400);
  margin-top: 2px;
}

.chart-card {
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  box-shadow: var(--shadow-sm);
  padding: 14px;
}

.chart-card__title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--color-neutral-300);
  margin-bottom: 10px;
}

.status-row {
  display: flex;
  justify-content: space-between;
  padding: 7px 0;
  border-bottom: 1px solid var(--color-divider);
  font-size: 13px;
}

.status-row:last-child {
  border-bottom: none;
}
</style>
