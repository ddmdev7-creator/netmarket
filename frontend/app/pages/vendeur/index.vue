<script setup lang="ts">
import {
  PhCaretRight,
  PhCheckCircle,
  PhConfetti,
  PhPackage,
  PhPlus,
  PhReceipt,
  PhTruck,
  PhWallet,
  PhWarning,
  PhWarningCircle,
} from '@phosphor-icons/vue'
import type { Component } from 'vue'
import type { DailyOrderCount, VendorDashboard, VendorRead, VendorStatus, WalletRead } from '~/types/api'

definePageMeta({ middleware: 'vendor', layout: 'vendeur' })

const { apiFetch } = useApi()

// getCachedData: hydrateThenRefetch disables Nuxt's static cross-navigation
// cache. By default useAsyncData reuses whatever it fetched the last time
// this page mounted (nuxtApp.static.data) instead of refetching — so
// switching tabs (dashboard → commandes → dashboard) kept showing the stats
// from before a status change, not after. These numbers move on every
// vendor action, so they must never be served stale.
const alwaysRefetch = { getCachedData: hydrateThenRefetch }

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

// Gains retirables : chargés sans bloquer la page (pas de carte si l'appel échoue).
const walletAvailable = ref(0)
onMounted(async () => {
  try {
    const wallets = await apiFetch<WalletRead[]>('/wallets/mine')
    walletAvailable.value = wallets.find((w) => w.kind === 'vendor')?.balance.available ?? 0
  } catch {
    walletAvailable.value = 0
  }
})

interface TodoCard {
  key: string
  count: number
  title: string
  text: string
  icon: Component
  hue: number
  to: string
  urgent?: boolean
}

// Section « À faire » : ce qui attend une action du vendeur, du plus urgent
// au moins urgent, chaque carte menant directement à la liste filtrée.
const todos = computed<TodoCard[]>(() => {
  const d = dashboard.value
  if (!d) return []
  const plural = (n: number, one: string, many: string) => (n > 1 ? many : one)
  const cards: TodoCard[] = [
    {
      key: 'pending',
      count: d.pending_orders,
      title: plural(d.pending_orders, 'commande à accepter', 'commandes à accepter'),
      text: 'Les acheteurs attendent votre confirmation.',
      icon: PhReceipt,
      hue: 0,
      to: '/vendeur/commandes?status=pending',
      urgent: true,
    },
    {
      key: 'confirmed',
      count: d.confirmed_orders,
      title: plural(d.confirmed_orders, 'commande à préparer', 'commandes à préparer'),
      text: 'Emballez-les puis passez-les « en préparation ».',
      icon: PhPackage,
      hue: 35,
      to: '/vendeur/commandes?status=confirmed',
    },
    {
      key: 'preparing',
      count: d.preparing_orders,
      title: plural(d.preparing_orders, 'colis à expédier', 'colis à expédier'),
      text: 'Trouvez un livreur et remettez-lui le colis.',
      icon: PhTruck,
      hue: 200,
      to: '/vendeur/commandes?status=preparing',
    },
    {
      key: 'out',
      count: d.out_of_stock_products.length,
      title: plural(d.out_of_stock_products.length, 'produit en rupture', 'produits en rupture'),
      text: 'Invisibles à l’achat tant qu’ils ne sont pas réapprovisionnés.',
      icon: PhWarning,
      hue: 355,
      to: '/vendeur/produits?stock=out',
      urgent: true,
    },
    {
      key: 'low',
      count: d.low_stock_products.length,
      title: plural(d.low_stock_products.length, 'produit en stock faible', 'produits en stock faible'),
      text: 'Pensez à réapprovisionner avant la rupture.',
      icon: PhWarningCircle,
      hue: 40,
      to: '/vendeur/produits?stock=low',
    },
  ]
  return cards.filter((c) => c.count > 0)
})

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

    <section v-if="dashboard && vendor?.status === 'approved'" class="todo mb-6" aria-labelledby="todo-title">
      <div class="todo__head">
        <h2 id="todo-title" class="todo__title">À faire</h2>
        <NuxtLink to="/vendeur/produits/nouveau" class="todo__add">
          <PhPlus :size="14" weight="bold" /> Nouveau produit
        </NuxtLink>
      </div>

      <div v-if="todos.length" class="todo__grid">
        <NuxtLink
          v-for="card in todos"
          :key="card.key"
          :to="card.to"
          class="todo-card"
          :class="{ 'todo-card--urgent': card.urgent }"
          :style="{ '--hue': card.hue }"
        >
          <span class="todo-card__icon"><component :is="card.icon" :size="20" weight="duotone" /></span>
          <span class="todo-card__body">
            <span class="todo-card__title"><strong>{{ card.count }}</strong> {{ card.title }}</span>
            <span class="todo-card__text">{{ card.text }}</span>
          </span>
          <PhCaretRight :size="16" class="todo-card__go" />
        </NuxtLink>
      </div>
      <div v-else class="todo__clear">
        <PhConfetti :size="22" weight="duotone" />
        <span><strong>Tout est à jour.</strong> Aucune commande ni aucun produit n'attend d'action.</span>
      </div>

      <NuxtLink v-if="walletAvailable > 0" to="/vendeur/gains" class="todo-card todo-card--money mt-2" style="--hue: 150">
        <span class="todo-card__icon"><PhWallet :size="20" weight="duotone" /></span>
        <span class="todo-card__body">
          <span class="todo-card__title"><strong>{{ formatGnf(walletAvailable) }}</strong> disponibles</span>
          <span class="todo-card__text">Vos gains peuvent être retirés vers votre mobile money.</span>
        </span>
        <PhCaretRight :size="16" class="todo-card__go" />
      </NuxtLink>
      <p v-if="dashboard.shipped_orders" class="todo__note">
        <PhCheckCircle :size="14" weight="fill" />
        {{ dashboard.shipped_orders }} colis en route vers {{ dashboard.shipped_orders > 1 ? 'leurs acheteurs' : 'son acheteur' }}.
      </p>
    </section>

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
            <span class="d-flex align-center ga-1">
              <span class="text-muted">Épuisé</span>
              <PhCaretRight :size="14" color="var(--color-neutral-500)" />
            </span>
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
        <span class="d-flex align-center ga-1">
          <span class="text-muted">{{ p.stock }} en stock</span>
          <PhCaretRight :size="14" color="var(--color-neutral-500)" />
        </span>
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
  align-items: center;
  padding: 8px;
  margin: 0 -8px;
  border-radius: var(--radius-sm);
  border-bottom: 1px solid var(--color-divider);
  text-decoration: none;
  color: inherit;
  font-size: 13px;
  transition: background 0.15s ease;
}

.low-stock-row:hover {
  background: var(--color-neutral-800);
}

.todo__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.todo__title {
  font-family: var(--font-heading);
  font-size: 17px;
  font-weight: 800;
  margin: 0;
}

.todo__add {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 7px 12px;
  border-radius: 999px;
  background: var(--color-primary);
  color: #fff;
  font-size: 12.5px;
  font-weight: 700;
  text-decoration: none;
}

.todo__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 8px;
}

.todo-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  color: inherit;
  text-decoration: none;
  transition: border-color 0.15s ease, transform 0.15s ease;
}

.todo-card:hover {
  border-color: hsl(var(--hue) 60% 50%);
  transform: translateY(-1px);
}

.todo-card--urgent {
  border-left: 4px solid hsl(var(--hue) 70% 52%);
}

.todo-card__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  border-radius: 12px;
  background: hsl(var(--hue) 70% var(--tint-bg));
  color: hsl(var(--hue) 60% var(--tint-fg));
}

.todo-card__body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.todo-card__title {
  font-size: 14px;
  color: var(--color-neutral-200);
}

.todo-card__title strong {
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 800;
}

.todo-card__text {
  font-size: 12px;
  color: var(--color-neutral-400);
}

.todo-card__go {
  flex-shrink: 0;
  color: var(--color-neutral-500);
}

.todo-card--money .todo-card__title strong {
  color: hsl(150 55% var(--tint-fg));
}

.todo__clear {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px;
  border-radius: var(--radius-md);
  background: hsl(150 70% var(--tint-bg-soft));
  color: hsl(150 55% var(--tint-fg));
  font-size: 13px;
}

.todo__clear strong {
  color: var(--color-neutral-200);
}

.todo__note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 10px 0 0;
  font-size: 12.5px;
  color: var(--color-success);
}
</style>
