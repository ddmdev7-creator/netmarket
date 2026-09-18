<script setup lang="ts">
import {
  PhCheckCircle,
  PhClock,
  PhCurrencyCircleDollar,
  PhPackage,
  PhPercent,
  PhShoppingCart,
  PhStorefront,
} from '@phosphor-icons/vue'
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
    { label: 'Boutiques', value: String(s.total_vendors), icon: PhStorefront, tone: 'primary' },
    { label: 'Boutiques approuvées', value: String(s.approved_vendors), icon: PhCheckCircle, tone: 'success' },
    { label: 'En attente de validation', value: String(s.pending_vendors), icon: PhClock, tone: 'accent' },
    { label: 'Produits', value: String(s.total_products), icon: PhPackage, tone: 'primary' },
    { label: 'Commandes', value: String(s.total_orders), icon: PhShoppingCart, tone: 'primary' },
    { label: 'Ventes (livrées)', value: formatGnf(s.total_sales), icon: PhCurrencyCircleDollar, tone: 'accent' },
    { label: 'Commission (livrée)', value: formatGnf(s.total_commission), icon: PhPercent, tone: 'success' },
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

// Même intention de couleurs que StatusBadge.vue (components/StatusBadge.vue),
// traduite en valeurs CSS directement puisqu'il ne s'agit pas ici d'un v-chip.
const statusColors: Record<OrderStatus, string> = {
  pending: 'var(--color-neutral-400)',
  confirmed: 'var(--color-primary)',
  preparing: 'var(--color-primary)',
  shipped: 'var(--color-primary-300)',
  arrived_at_pickup_point: 'var(--color-accent)',
  delivered: 'var(--color-success)',
  cancelled: 'var(--color-error)',
}
</script>

<template>
  <div class="dashboard-shell">
    <h1 class="text-h6 mb-4">Statistiques plateforme</h1>

    <div class="stat-grid mb-5">
      <v-skeleton-loader v-if="pending" type="card" class="stat-tile" v-for="n in 7" :key="n" />
      <div v-else v-for="tile in tiles" :key="tile.label" class="stat-tile">
        <div class="stat-tile__icon" :class="`stat-tile__icon--${tile.tone}`">
          <component :is="tile.icon" :size="18" weight="bold" />
        </div>
        <div class="stat-tile__value">{{ tile.value }}</div>
        <div class="stat-tile__label">{{ tile.label }}</div>
      </div>
    </div>

    <template v-if="stats">
      <div class="panel-grid">
        <v-card class="chart-card" variant="flat">
          <div class="chart-card__title">Commandes par statut</div>
          <div v-for="status in Object.keys(statusLabels) as OrderStatus[]" :key="status" class="status-row">
            <span class="d-flex align-center ga-2">
              <span class="status-dot" :style="{ backgroundColor: statusColors[status] }" />
              {{ statusLabels[status] }}
            </span>
            <span style="font-weight: 700">{{ stats.orders_by_status[status] ?? 0 }}</span>
          </div>
        </v-card>

        <v-card class="chart-card" variant="flat">
          <div class="chart-card__title">Top 5 produits (quantité vendue)</div>
          <CommonEmptyState v-if="stats.top_products.length === 0" message="Pas encore de ventes." />
          <div v-for="(p, i) in stats.top_products" :key="p.product_id" class="status-row">
            <span class="d-flex align-center ga-2">
              <span class="rank-badge">{{ i + 1 }}</span>
              {{ p.product_name }}
            </span>
            <span style="font-weight: 700">{{ p.quantity_sold }}</span>
          </div>
        </v-card>

        <v-card class="chart-card" variant="flat">
          <div class="chart-card__title">Top 5 boutiques (chiffre d'affaires)</div>
          <CommonEmptyState v-if="stats.top_vendors.length === 0" message="Pas encore de ventes." />
          <div v-for="(v, i) in stats.top_vendors" :key="v.vendor_id" class="status-row">
            <span class="d-flex align-center ga-2">
              <span class="rank-badge">{{ i + 1 }}</span>
              {{ v.shop_name }}
            </span>
            <span style="font-weight: 700">{{ formatGnf(v.revenue) }}</span>
          </div>
        </v-card>
      </div>
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
    grid-template-columns: repeat(4, 1fr);
  }
}

.stat-tile {
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  padding: 14px;
}

.stat-tile__icon {
  width: 34px;
  height: 34px;
  border-radius: 999px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 10px;
}

.stat-tile__icon--primary {
  background: color-mix(in srgb, var(--color-primary) 14%, transparent);
  color: var(--color-primary);
}

.stat-tile__icon--success {
  background: color-mix(in srgb, var(--color-success) 16%, transparent);
  color: var(--color-success);
}

.stat-tile__icon--accent {
  background: color-mix(in srgb, var(--color-accent) 16%, transparent);
  color: var(--color-accent);
}

.stat-tile__value {
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 700;
}

.stat-tile__label {
  font-size: 11px;
  color: var(--color-neutral-400);
  margin-top: 2px;
}

.panel-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 14px;
}

@media (min-width: 1100px) {
  .panel-grid {
    grid-template-columns: repeat(3, 1fr);
    align-items: start;
  }
}

.chart-card {
  background: var(--color-neutral-900);
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
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
  align-items: center;
  justify-content: space-between;
  padding: 7px 0;
  border-bottom: 1px solid var(--color-divider);
  font-size: 13px;
}

.status-row:last-child {
  border-bottom: none;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
}

.rank-badge {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--color-neutral-800);
  color: var(--color-neutral-400);
  font-size: 10.5px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
}
</style>
