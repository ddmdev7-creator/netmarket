<script setup lang="ts">
import {
  PhChartBar,
  PhGear,
  PhMapPinLine,
  PhPackage,
  PhReceipt,
  PhCrown,
  PhStorefront,
  PhWallet,
} from '@phosphor-icons/vue'
import type { Component } from 'vue'
import type { VendorDashboard, VendorRead } from '~/types/api'

const emit = defineEmits<{ navigate: [] }>()
const auth = useAuthStore()
const route = useRoute()
const { apiFetch } = useApi()

// Nom de la boutique et compteurs « à traiter » (commandes à confirmer ou à
// préparer, produits en rupture) — rafraîchis à chaque navigation.
const vendor = ref<VendorRead | null>(null)
const dashboard = ref<VendorDashboard | null>(null)
async function refresh() {
  try {
    ;[vendor.value, dashboard.value] = await Promise.all([
      vendor.value ? Promise.resolve(vendor.value) : apiFetch<VendorRead>('/vendors/me'),
      apiFetch<VendorDashboard>('/vendors/me/dashboard'),
    ])
  } catch {
    // Pastilles facultatives : la navigation reste utilisable sans elles.
  }
}
onMounted(refresh)
watch(() => route.path, refresh)

interface NavItem {
  to: string
  label: string
  icon: Component
  badge?: number
  urgent?: boolean
}

// "Mon point de retrait" n'apparaît que pour un vendeur dont la boutique EST
// aussi un point de retrait (voir PickupPoint.vendor_id côté backend) — son
// compte habituel donne alors aussi accès à cet espace, sans rôle séparé.
const groups = computed<{ title: string; items: NavItem[] }[]>(() => {
  const d = dashboard.value
  const toHandle = d ? d.pending_orders + d.confirmed_orders + d.preparing_orders : 0
  const outOfStock = d?.out_of_stock_products.length ?? 0
  return [
    {
      title: 'Ma boutique',
      items: [
        { to: '/vendeur', label: 'Tableau de bord', icon: PhChartBar },
        { to: '/vendeur/commandes', label: 'Commandes', icon: PhReceipt, badge: toHandle, urgent: (d?.pending_orders ?? 0) > 0 },
        { to: '/vendeur/produits', label: 'Produits', icon: PhPackage, badge: outOfStock, urgent: false },
      ],
    },
    {
      title: 'Gestion',
      items: [
        { to: '/vendeur/gains', label: 'Mes gains', icon: PhWallet },
        { to: '/vendeur/boutique', label: 'Réglages', icon: PhGear },
        { to: '/vendeur/abonnement', label: 'Abonnement', icon: PhCrown },
        ...(auth.user?.is_pickup_point_manager
          ? [{ to: '/point-retrait', label: 'Mon point de retrait', icon: PhMapPinLine }]
          : []),
      ],
    },
  ]
})

function isActive(to: string) {
  return to === '/vendeur' ? route.path === '/vendeur' : route.path.startsWith(to)
}

const initials = computed(() =>
  (vendor.value?.shop_name ?? 'Boutique')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join(''),
)
</script>

<template>
  <nav class="vs" aria-label="Espace vendeur">
    <div class="vs__brand">
      <span class="vs__logo">{{ initials }}</span>
      <span class="vs__brand-text">
        <strong>{{ vendor?.shop_name ?? 'Ma boutique' }}</strong>
        <span>Espace vendeur</span>
      </span>
    </div>

    <div v-for="group in groups" :key="group.title" class="vs__group">
      <div class="vs__group-title">{{ group.title }}</div>
      <NuxtLink
        v-for="item in group.items"
        :key="item.to"
        :to="item.to"
        class="vs__item"
        :class="{ 'is-active': isActive(item.to) }"
        :aria-current="isActive(item.to) ? 'page' : undefined"
        @click="emit('navigate')"
      >
        <component :is="item.icon" :size="19" :weight="isActive(item.to) ? 'fill' : 'regular'" />
        <span class="vs__label">{{ item.label }}</span>
        <span v-if="item.badge" class="vs__badge" :class="{ 'vs__badge--urgent': item.urgent }">
          {{ item.badge > 99 ? '99+' : item.badge }}
        </span>
      </NuxtLink>
    </div>

    <NuxtLink to="/" class="vs__market" @click="emit('navigate')">
      <PhStorefront :size="17" /> Visiter le marché
    </NuxtLink>
  </nav>
</template>

<style scoped>
.vs {
  display: flex;
  flex-direction: column;
  gap: 2px;
  height: 100%;
  padding: 14px 12px;
  overflow-y: auto;
}

.vs__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 8px 16px;
}

.vs__logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  border-radius: 12px;
  background: linear-gradient(135deg, hsl(152 68% 42%), hsl(190 70% 42%));
  color: #fff;
  font-family: var(--font-heading);
  font-weight: 800;
  font-size: 15px;
}

.vs__brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.2;
}

.vs__brand-text strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-heading);
  font-size: 15px;
  font-weight: 800;
}

.vs__brand-text span {
  font-size: 11.5px;
  color: var(--color-neutral-400);
}

.vs__group {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 10px;
}

.vs__group-title {
  padding: 6px 12px 4px;
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-neutral-500);
}

.vs__item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 12px;
  border-radius: 10px;
  color: var(--color-neutral-300);
  text-decoration: none;
  font-size: 13.5px;
  font-weight: 500;
  transition: background 0.15s ease, color 0.15s ease;
}

.vs__item:hover {
  background: var(--color-neutral-800);
  color: var(--color-neutral-200);
}

.vs__item.is-active {
  background: color-mix(in srgb, var(--color-primary) 13%, transparent);
  color: var(--color-primary-300);
  font-weight: 700;
}

.vs__item.is-active::before {
  content: '';
  position: absolute;
  left: -12px;
  top: 8px;
  bottom: 8px;
  width: 4px;
  border-radius: 0 4px 4px 0;
  background: var(--color-primary);
}

.vs__label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.vs__badge {
  min-width: 22px;
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--color-neutral-700);
  color: var(--color-neutral-200);
  font-size: 11px;
  font-weight: 800;
  text-align: center;
}

.vs__badge--urgent {
  background: var(--color-error);
  color: #fff;
}

.vs__market {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: auto;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px dashed var(--color-divider-strong);
  color: var(--color-primary-300);
  font-size: 13px;
  font-weight: 700;
  text-decoration: none;
}

.vs__market:hover {
  background: var(--color-neutral-800);
}
</style>
