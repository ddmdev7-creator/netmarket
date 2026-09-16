<script setup lang="ts">
import { PhWarningCircle } from '@phosphor-icons/vue'
import type { DailyOrderCount, VendorDashboard, VendorRead, VendorStatus } from '~/types/api'

definePageMeta({ middleware: 'vendor', layout: 'vendeur' })

const { apiFetch } = useApi()

// getCachedData: () => undefined disables Nuxt's static cross-navigation
// cache. By default useAsyncData reuses whatever it fetched the last time
// this page mounted (nuxtApp.static.data) instead of refetching — so
// switching tabs (dashboard → commandes → dashboard) kept showing the stats
// from before a status change, not after. These numbers move on every
// vendor action, so they must never be served stale.
const alwaysRefetch = { getCachedData: () => undefined }

const { data: vendor } = await useAsyncData('vendor-me', () => apiFetch<VendorRead>('/vendors/me'), alwaysRefetch)
const { data: dashboard, pending } = await useAsyncData(
  'vendor-dashboard',
  () => apiFetch<VendorDashboard>('/vendors/me/dashboard'),
  alwaysRefetch,
)
const { data: timeseries } = await useAsyncData(
  'vendor-orders-timeseries',
  () => apiFetch<DailyOrderCount[]>('/vendors/me/orders-timeseries'),
  { default: () => [], ...alwaysRefetch },
)

const statusMeta: Record<VendorStatus, { label: string; color: string }> = {
  pending: { label: 'En attente de validation', color: 'warning' },
  approved: { label: 'Boutique approuvée', color: 'success' },
  rejected: { label: 'Inscription rejetée', color: 'error' },
  suspended: { label: 'Boutique suspendue', color: 'error' },
}

// Headline figures only — the charts below carry the order-status split and
// the revenue composition with more nuance than a flat number.
const tiles = computed(() => {
  if (!dashboard.value) return []
  const d = dashboard.value
  return [
    { label: 'Commandes totales', value: String(d.total_orders) },
    { label: 'Produits actifs', value: String(d.active_product_count) },
  ]
})
</script>

<template>
  <div class="dashboard-shell">
    <h1 class="text-h6 mb-4">Tableau de bord</h1>

    <template v-if="vendor">
      <div class="d-flex align-center justify-space-between mb-1">
        <span class="text-h6" style="font-size: 17px">{{ vendor.shop_name }}</span>
        <v-chip :color="statusMeta[vendor.status].color" size="small" variant="tonal">
          {{ statusMeta[vendor.status].label }}
        </v-chip>
      </div>
      <div v-if="vendor.zone" class="text-muted mb-4" style="font-size: 12.5px">{{ vendor.zone }}</div>

      <v-alert v-if="vendor.status === 'pending'" type="warning" variant="tonal" density="compact" class="mb-4">
        Ta boutique est en attente de validation par un administrateur. Tu pourras publier des produits une fois
        approuvée.
      </v-alert>
      <v-alert v-else-if="vendor.status === 'rejected'" type="error" variant="tonal" density="compact" class="mb-4">
        Ton inscription a été rejetée. Contacte le support pour plus de détails.
      </v-alert>
      <v-alert v-else-if="vendor.status === 'suspended'" type="error" variant="tonal" density="compact" class="mb-4">
        Ta boutique est suspendue et ne peut plus vendre pour le moment.
      </v-alert>
    </template>

    <div class="stat-grid mb-5">
      <v-skeleton-loader v-if="pending" type="card" class="stat-tile" v-for="n in 2" :key="n" />
      <div v-else v-for="tile in tiles" :key="tile.label" class="stat-tile">
        <div class="stat-tile__value">{{ tile.value }}</div>
        <div class="stat-tile__label">{{ tile.label }}</div>
      </div>
    </div>

    <v-card v-if="dashboard" class="chart-card mb-4" variant="flat">
      <div class="chart-card__title">Commandes par statut</div>
      <VendorChartsOrderStatusBarChart
        :active="dashboard.active_orders"
        :delivered="dashboard.delivered_orders"
        :cancelled="dashboard.cancelled_orders"
      />
    </v-card>

    <v-card v-if="dashboard" class="chart-card mb-4" variant="flat">
      <div class="chart-card__title">Revenu (commandes livrées)</div>
      <VendorChartsRevenueCompositionChart :net="dashboard.net_revenue" :commission="dashboard.commission_due" />
    </v-card>

    <v-card v-if="timeseries?.length" class="chart-card mb-5" variant="flat">
      <div class="chart-card__title">Commandes reçues — 14 derniers jours</div>
      <VendorChartsOrdersTrendChart :points="timeseries" />
    </v-card>

    <v-expansion-panels v-if="dashboard?.out_of_stock_products?.length" class="mb-4">
      <v-expansion-panel>
        <v-expansion-panel-title>
          <div class="d-flex align-center ga-2">
            <PhWarningCircle :size="16" color="var(--color-error, #e5484d)" />
            <span style="font-size: 13px; font-weight: 600">
              Rupture de stock ({{ dashboard.out_of_stock_products.length }})
            </span>
          </div>
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <NuxtLink
            v-for="p in dashboard.out_of_stock_products"
            :key="p.id"
            :to="`/vendeur/produits/${p.id}`"
            class="low-stock-row"
          >
            <span>{{ p.name }}</span>
            <span class="text-muted">Épuisé</span>
          </NuxtLink>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

    <div v-if="dashboard?.low_stock_products?.length">
      <div class="d-flex align-center ga-2 mb-2">
        <PhWarningCircle :size="16" color="var(--color-primary)" />
        <span style="font-size: 13px; font-weight: 600">Stock faible</span>
      </div>
      <NuxtLink
        v-for="p in dashboard.low_stock_products"
        :key="p.id"
        :to="`/vendeur/produits/${p.id}`"
        class="low-stock-row"
      >
        <span>{{ p.name }}</span>
        <span class="text-muted">{{ p.stock }} en stock</span>
      </NuxtLink>
    </div>
  </div>
</template>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
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
  margin-bottom: 12px;
}

.low-stock-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid var(--color-divider);
  text-decoration: none;
  color: inherit;
  font-size: 13px;
}
</style>
