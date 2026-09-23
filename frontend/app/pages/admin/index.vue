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
import type { AdminStats, OrderStatus, PaymentMethod, UserRole } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()

// getCachedData: hydrateThenRefetch — ces chiffres bougent à chaque action
// (validation vendeur, commande livrée...), voir vendeur/index.vue pour le
// même raisonnement.
const { data: stats, pending } = await useAsyncData(
  'admin-stats',
  () => apiFetch<AdminStats>('/admin/stats'),
  { getCachedData: hydrateThenRefetch },
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

// --- Graphiques ---------------------------------------------------------------

const days = computed(() => stats.value?.daily_activity ?? [])
const ordersSeries = computed(() => days.value.map((d) => ({ date: d.date, value: d.orders })))
const amountSeries = computed(() => days.value.map((d) => ({ date: d.date, value: d.order_amount })))
const signupSeries = computed(() => days.value.map((d) => ({ date: d.date, value: d.signups })))
const sum = (points: { value: number }[]) => points.reduce((total, p) => total + p.value, 0)

// Montants compacts sur les axes (« 1,2 M »), complets dans l'infobulle.
function compactGnf(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} M`
  if (value >= 1_000) return `${Math.round(value / 1_000)} k`
  return String(value)
}

const statusRows = computed(() =>
  (Object.keys(statusLabels) as OrderStatus[]).map((status) => ({
    key: status,
    label: statusLabels[status],
    value: stats.value?.orders_by_status[status] ?? 0,
    color: statusColors[status],
  })),
)

// Couleurs catégorielles validées (clair/sombre), ordre fixe.
const paymentRows = computed(() =>
  (['cash_on_delivery', 'online', 'wallet'] as PaymentMethod[]).map((method, i) => ({
    key: method,
    label: PAYMENT_METHOD_LABELS[method].short,
    value: stats.value?.orders_by_payment_method[method] ?? 0,
    color: `var(--dash-cat-${i + 1})`,
  })),
)

const roleLabels: Record<UserRole, string> = {
  buyer: 'Acheteurs',
  vendor: 'Vendeurs',
  courier: 'Livreurs',
  pickup_point_manager: 'Gestionnaires de point',
  admin: 'Administrateurs',
}
const roleRows = computed(() =>
  (Object.keys(roleLabels) as UserRole[]).map((role) => ({
    key: role,
    label: roleLabels[role],
    value: stats.value?.users_by_role[role] ?? 0,
  })),
)

const topProductRows = computed(() =>
  (stats.value?.top_products ?? []).map((p) => ({ key: p.product_id, label: p.product_name, value: p.quantity_sold })),
)
const topVendorRows = computed(() =>
  (stats.value?.top_vendors ?? []).map((v) => ({ key: v.vendor_id, label: v.shop_name, value: v.revenue })),
)
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
      <h2 class="section-heading">30 derniers jours</h2>
      <div class="trend-grid mb-4">
        <v-card class="chart-card" variant="flat">
          <div class="chart-card__head">
            <span class="chart-card__title">Commandes par jour</span>
            <span class="chart-card__hero">{{ sum(ordersSeries) }}</span>
          </div>
          <AdminChartsDailyChart :points="ordersSeries" kind="bar" label="Commandes passées par jour, 30 derniers jours" />
        </v-card>
        <v-card class="chart-card" variant="flat">
          <div class="chart-card__head">
            <span class="chart-card__title">Montant commandé par jour</span>
            <span class="chart-card__hero">{{ formatGnf(sum(amountSeries)) }}</span>
          </div>
          <AdminChartsDailyChart
            :points="amountSeries"
            kind="line"
            :format="compactGnf"
            label="Montant des commandes passées par jour, hors annulées, 30 derniers jours"
          />
        </v-card>
        <v-card class="chart-card" variant="flat">
          <div class="chart-card__head">
            <span class="chart-card__title">Inscriptions par jour</span>
            <span class="chart-card__hero">{{ sum(signupSeries) }}</span>
          </div>
          <AdminChartsDailyChart :points="signupSeries" kind="bar" label="Nouveaux comptes par jour, 30 derniers jours" />
        </v-card>
      </div>

      <h2 class="section-heading">Répartitions</h2>
      <div class="panel-grid mb-4">
        <v-card class="chart-card" variant="flat">
          <div class="chart-card__title">Commandes par statut</div>
          <AdminChartsHBarChart :rows="statusRows" show-share label="Commandes par statut" />
        </v-card>
        <v-card class="chart-card" variant="flat">
          <div class="chart-card__title">Moyens de paiement</div>
          <AdminChartsHBarChart :rows="paymentRows" show-share label="Commandes par moyen de paiement" />
        </v-card>
        <v-card class="chart-card" variant="flat">
          <div class="chart-card__title">Utilisateurs par rôle</div>
          <AdminChartsHBarChart :rows="roleRows" label="Utilisateurs par rôle" />
        </v-card>
      </div>

      <h2 class="section-heading">Classements (ventes livrées)</h2>
      <div class="panel-grid panel-grid--two">
        <v-card class="chart-card" variant="flat">
          <div class="chart-card__title">Top 5 produits (quantité vendue)</div>
          <CommonEmptyState v-if="!topProductRows.length" message="Pas encore de ventes." />
          <AdminChartsHBarChart v-else :rows="topProductRows" label="Produits les plus vendus" />
        </v-card>
        <v-card class="chart-card" variant="flat">
          <div class="chart-card__title">Top 5 boutiques (chiffre d'affaires)</div>
          <CommonEmptyState v-if="!topVendorRows.length" message="Pas encore de ventes." />
          <AdminChartsHBarChart v-else :rows="topVendorRows" :format="formatGnf" label="Boutiques au plus fort chiffre d'affaires" />
        </v-card>
      </div>
    </template>
  </div>
</template>

<style scoped>
.dashboard-shell {
  --dash-cat-1: #2a78d6;
  --dash-cat-2: #eb6834;
  --dash-cat-3: #1baf7a;
}

:root[data-theme='dark'] .dashboard-shell {
  --dash-cat-1: #3987e5;
  --dash-cat-2: #d95926;
  --dash-cat-3: #199e70;
}

.section-heading {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-neutral-400);
}

.trend-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 14px;
}

@media (min-width: 1100px) {
  .trend-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

.chart-card__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 18px;
}

.chart-card__head .chart-card__title {
  margin-bottom: 0;
}

.chart-card__hero {
  font-family: var(--font-heading);
  font-size: 18px;
  font-weight: 800;
  color: var(--color-neutral-200);
  font-variant-numeric: tabular-nums;
}

@media (min-width: 1100px) {
  .panel-grid--two {
    grid-template-columns: repeat(2, 1fr);
  }
}

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

</style>
