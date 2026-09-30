<script setup lang="ts">
import {
  PhBank,
  PhChartLineUp,
  PhClipboardText,
  PhCreditCard,
  PhCurrencyCircleDollar,
  PhFlag,
  PhMapPin,
  PhMapTrifold,
  PhMotorcycle,
  PhPackage,
  PhSparkle,
  PhStorefront,
  PhTag,
  PhTruck,
  PhUserGear,
  PhUsers,
} from '@phosphor-icons/vue'
import type { Component } from 'vue'
import type { AdminAttention } from '~/types/api'

const emit = defineEmits<{ navigate: [] }>()
const route = useRoute()
const { attention, startPolling } = useAdminAttention()
onMounted(startPolling)

interface NavItem {
  to: string
  label: string
  icon: Component
  /** Compteur « à traiter » affiché en pastille. */
  badge?: (a: AdminAttention) => number
  urgent?: boolean
}

// Regroupé par thème : on retrouve un écran par ce qu'on veut faire.
const groups: { title: string; items: NavItem[] }[] = [
  {
    title: 'Pilotage',
    items: [
      { to: '/admin', label: 'Tableau de bord', icon: PhChartLineUp },
      { to: '/admin/livraisons', label: 'Suivi livraisons', icon: PhTruck, badge: (a) => a.unassigned_deliveries, urgent: true },
      { to: '/admin/carte', label: 'Carte', icon: PhMapTrifold },
    ],
  },
  {
    title: 'Ventes',
    items: [
      { to: '/admin/commandes', label: 'Commandes', icon: PhPackage, badge: (a) => a.pending_orders },
      { to: '/admin/vendeurs', label: 'Vendeurs', icon: PhStorefront, badge: (a) => a.pending_vendors, urgent: true },
      { to: '/admin/categories', label: 'Catégories', icon: PhTag },
      { to: '/admin/abonnements', label: 'Abonnements', icon: PhSparkle },
    ],
  },
  {
    title: 'Logistique',
    items: [
      { to: '/admin/livreurs', label: 'Livreurs', icon: PhMotorcycle, badge: (a) => a.pending_couriers, urgent: true },
      { to: '/admin/points-retrait', label: 'Points de retrait', icon: PhMapPin },
      { to: '/admin/gestionnaires', label: 'Gestionnaires', icon: PhUserGear },
      { to: '/admin/candidatures', label: 'Candidatures', icon: PhClipboardText, badge: (a) => a.pending_applications, urgent: true },
      { to: '/admin/frais-livraison', label: 'Frais de livraison', icon: PhCurrencyCircleDollar },
    ],
  },
  {
    title: 'Finances',
    items: [
      { to: '/admin/finance', label: 'Compte principal', icon: PhBank, badge: (a) => a.pending_withdrawals + a.failed_refunds, urgent: true },
      { to: '/admin/paiement', label: 'Paiement', icon: PhCreditCard },
    ],
  },
  {
    title: 'Communauté',
    items: [
      { to: '/admin/utilisateurs', label: 'Utilisateurs', icon: PhUsers },
      { to: '/admin/signalements', label: 'Signalements', icon: PhFlag, badge: (a) => a.pending_reports, urgent: true },
    ],
  },
]

function isActive(to: string) {
  return to === '/admin' ? route.path === '/admin' : route.path.startsWith(to)
}

function badgeOf(item: NavItem) {
  return item.badge && attention.value ? item.badge(attention.value) : 0
}
</script>

<template>
  <nav class="as" aria-label="Administration">
    <div class="as__brand">
      <span class="as__logo">N</span>
      <span class="as__brand-text">
        <strong>NdjouriMarket</strong>
        <span>Administration</span>
      </span>
    </div>

    <div v-for="group in groups" :key="group.title" class="as__group">
      <div class="as__group-title">{{ group.title }}</div>
      <NuxtLink
        v-for="item in group.items"
        :key="item.to"
        :to="item.to"
        class="as__item"
        :class="{ 'is-active': isActive(item.to) }"
        :aria-current="isActive(item.to) ? 'page' : undefined"
        @click="emit('navigate')"
      >
        <component :is="item.icon" :size="19" :weight="isActive(item.to) ? 'fill' : 'regular'" />
        <span class="as__label">{{ item.label }}</span>
        <span v-if="badgeOf(item)" class="as__badge" :class="{ 'as__badge--urgent': item.urgent }">
          {{ badgeOf(item) > 99 ? '99+' : badgeOf(item) }}
        </span>
      </NuxtLink>
    </div>

    <NuxtLink to="/" class="as__market" @click="emit('navigate')">
      <PhStorefront :size="17" /> Visiter le marché
    </NuxtLink>
  </nav>
</template>

<style scoped>
.as {
  display: flex;
  flex-direction: column;
  gap: 2px;
  height: 100%;
  padding: 14px 12px;
  overflow-y: auto;
}

.as__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 8px 16px;
}

.as__logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 11px;
  background: linear-gradient(135deg, var(--color-primary), #4f46e5);
  color: #fff;
  font-family: var(--font-heading);
  font-weight: 800;
  font-size: 18px;
  box-shadow: var(--shadow-glow-primary);
}

.as__brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
}

.as__brand-text strong {
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 800;
}

.as__brand-text span {
  font-size: 11.5px;
  color: var(--color-neutral-400);
}

.as__group {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 10px;
}

.as__group-title {
  padding: 6px 12px 4px;
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-neutral-500);
}

.as__item {
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

.as__item:hover {
  background: var(--color-neutral-800);
  color: var(--color-neutral-200);
}

.as__item.is-active {
  background: color-mix(in srgb, var(--color-primary) 13%, transparent);
  color: var(--color-primary-300);
  font-weight: 700;
}

.as__item.is-active::before {
  content: '';
  position: absolute;
  left: -12px;
  top: 8px;
  bottom: 8px;
  width: 4px;
  border-radius: 0 4px 4px 0;
  background: var(--color-primary);
}

.as__label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.as__badge {
  min-width: 22px;
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--color-neutral-700);
  color: var(--color-neutral-200);
  font-size: 11px;
  font-weight: 800;
  text-align: center;
}

.as__badge--urgent {
  background: var(--color-error);
  color: #fff;
}

.as__market {
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

.as__market:hover {
  background: var(--color-neutral-800);
}
</style>
