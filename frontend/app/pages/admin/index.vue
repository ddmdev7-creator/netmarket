<script setup lang="ts">
import {
  PhArrowsClockwise,
  PhBank,
  PhClipboardText,
  PhFlag,
  PhMotorcycle,
  PhTruck,
  PhWarningCircle,
  PhCheckCircle,
  PhClock,
  PhCurrencyCircleDollar,
  PhPackage,
  PhPercent,
  PhShoppingCart,
  PhStorefront,
} from '@phosphor-icons/vue'
import type { TodoItem } from '~/components/common/TodoCards.vue'
import type { AdminStats, OrderStatus, PaymentMethod, UserRole } from '~/types/api'

definePageMeta({ middleware: 'admin', layout: 'admin' })

const { apiFetch } = useApi()

// getCachedData: hydrateThenRefetch — ces chiffres bougent à chaque action
// (validation vendeur, commande livrée...), voir vendeur/index.vue pour le
// même raisonnement.
const auth = useAuthStore()
const { attention, refresh: refreshAttention } = useAdminAttention()
onMounted(refreshAttention)

const greeting = computed(() => {
  const hour = new Date().getHours()
  const name = auth.user?.first_name
  return `${hour < 18 ? 'Bonjour' : 'Bonsoir'}${name ? ` ${name}` : ''}`
})
const today = new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })

// Section « À traiter » : chaque carte mène à l'écran concerné.
const todos = computed<TodoItem[]>(() => {
  const a = attention.value
  if (!a) return []
  const plural = (n: number, one: string, many: string) => (n > 1 ? many : one)
  const items: TodoItem[] = [
    { key: 'deliveries', count: a.unassigned_deliveries, title: plural(a.unassigned_deliveries, 'colis sans livreur', 'colis sans livreur'), text: 'Confirmés mais personne pour les transporter.', icon: PhTruck, hue: 355, urgent: true, to: '/admin/livraisons' },
    { key: 'vendors', count: a.pending_vendors, title: plural(a.pending_vendors, 'boutique à valider', 'boutiques à valider'), text: 'Inscriptions de vendeurs en attente.', icon: PhStorefront, hue: 260, urgent: true, to: '/admin/vendeurs' },
    { key: 'couriers', count: a.pending_couriers, title: plural(a.pending_couriers, 'livreur à vérifier', 'livreurs à vérifier'), text: 'Pièces et engin à contrôler.', icon: PhMotorcycle, hue: 25, urgent: true, to: '/admin/livreurs' },
    { key: 'applications', count: a.pending_applications, title: plural(a.pending_applications, 'candidature de point', 'candidatures de point'), text: 'Dossiers de points de retrait à examiner.', icon: PhClipboardText, hue: 200, to: '/admin/candidatures' },
    { key: 'withdrawals', count: a.pending_withdrawals, title: plural(a.pending_withdrawals, 'retrait à valider', 'retraits à valider'), text: 'Demandes de retrait des bénéficiaires.', icon: PhBank, hue: 150, to: '/admin/finance' },
    { key: 'refunds', count: a.failed_refunds, title: plural(a.failed_refunds, 'remboursement échoué', 'remboursements échoués'), text: 'À reprendre manuellement avec l’acheteur.', icon: PhWarningCircle, hue: 0, urgent: true, to: '/admin/finance' },
    { key: 'reports', count: a.pending_reports, title: plural(a.pending_reports, 'signalement', 'signalements'), text: 'Produits ou avis signalés par les utilisateurs.', icon: PhFlag, hue: 38, to: '/admin/signalements' },
    { key: 'orders', count: a.pending_orders, title: plural(a.pending_orders, 'commande en attente', 'commandes en attente'), text: 'Pas encore confirmées par leur vendeur.', icon: PhShoppingCart, hue: 215, to: '/admin/commandes' },
  ]
  return items.filter((i) => (i.count ?? 0) > 0)
})

const { data: stats, pending, refresh: refreshStats } = await useAsyncData(
  'admin-stats',
  () => apiFetch<AdminStats>('/admin/stats'),
  { getCachedData: hydrateThenRefetch },
)

const tiles = computed(() => {
  if (!stats.value) return []
  const s = stats.value
  return [
    { label: 'Ventes livrées', value: formatGnf(s.total_sales), icon: PhCurrencyCircleDollar, hue: 150, hero: true },
    { label: 'Commission encaissée', value: formatGnf(s.total_commission), icon: PhPercent, hue: 260, hero: true },
    { label: 'Commandes', value: String(s.total_orders), icon: PhShoppingCart, hue: 215 },
    { label: 'Produits en ligne', value: String(s.total_products), icon: PhPackage, hue: 30 },
    { label: 'Boutiques approuvées', value: `${s.approved_vendors} / ${s.total_vendors}`, icon: PhCheckCircle, hue: 170 },
    { label: 'Boutiques en attente', value: String(s.pending_vendors), icon: PhClock, hue: 38 },
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
    <header class="dash-head">
      <div>
        <h1 class="text-h6 mb-0">{{ greeting }}</h1>
        <p class="dash-head__date">{{ today }} · vue d'ensemble de la plateforme</p>
      </div>
      <v-btn variant="tonal" color="primary" :loading="pending" @click="refreshStats(); refreshAttention()">
        <PhArrowsClockwise :size="16" class="mr-1" /> Actualiser
      </v-btn>
    </header>

    <section class="mb-6" aria-labelledby="todo-title">
      <h2 id="todo-title" class="section-heading">À traiter</h2>
      <CommonTodoCards :items="todos" empty-text="Rien en attente : tout est traité." />
    </section>

    <h2 class="section-heading">Indicateurs clés</h2>
    <div class="stat-grid mb-6">
      <v-skeleton-loader v-if="pending" type="card" class="stat-tile" v-for="n in 6" :key="n" />
      <div
        v-else
        v-for="tile in tiles"
        :key="tile.label"
        class="stat-tile"
        :class="{ 'stat-tile--hero': tile.hero }"
        :style="{ '--hue': tile.hue }"
      >
        <div class="stat-tile__icon"><component :is="tile.icon" :size="20" weight="duotone" /></div>
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
  margin: 0 0 12px;
  font-size: 12px;
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

.dash-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 22px;
}

.dash-head__date {
  margin: 4px 0 0;
  font-size: 13.5px;
  color: var(--color-neutral-400);
}

.dash-head__date::first-letter {
  text-transform: uppercase;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

@media (min-width: 768px) {
  .stat-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 14px;
  }
}

.stat-tile {
  position: relative;
  overflow: hidden;
  padding: 16px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-sm);
}

/* Montants phares : dégradé de la teinte de la tuile. */
.stat-tile--hero {
  grid-column: span 2;
  border-color: hsl(var(--hue) 60% 50% / 0.3);
  background: linear-gradient(135deg, hsl(var(--hue) 70% var(--tint-bg-soft)), var(--color-neutral-900));
}

.stat-tile__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  margin-bottom: 12px;
  border-radius: 12px;
  background: hsl(var(--hue) 70% var(--tint-bg));
  color: hsl(var(--hue) 60% var(--tint-fg));
}

.stat-tile__value {
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stat-tile--hero .stat-tile__value {
  font-size: 26px;
  color: hsl(var(--hue) 60% var(--tint-fg));
}

.stat-tile__label {
  margin-top: 2px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--color-neutral-400);
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
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  padding: 18px;
}

.chart-card__title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--color-neutral-300);
  margin-bottom: 10px;
}

</style>
