<script setup lang="ts">
import { PhBank, PhChartBar, PhClipboardText, PhCreditCard, PhCurrencyCircleDollar, PhFlag, PhMapPin, PhMapTrifold, PhMotorcycle, PhPackage, PhSparkle, PhStorefront, PhTag, PhTruck, PhUsers } from '@phosphor-icons/vue'

const emit = defineEmits<{ navigate: [] }>()

const navItems = [
  { to: '/admin', label: 'Statistiques', icon: PhChartBar },
  { to: '/admin/utilisateurs', label: 'Utilisateurs', icon: PhUsers },
  { to: '/admin/vendeurs', label: 'Vendeurs', icon: PhStorefront },
  { to: '/admin/abonnements', label: 'Abonnements', icon: PhSparkle },
  { to: '/admin/livreurs', label: 'Livreurs', icon: PhMotorcycle },
  { to: '/admin/commandes', label: 'Commandes', icon: PhPackage },
  { to: '/admin/livraisons', label: 'Suivi livraisons', icon: PhTruck },
  { to: '/admin/carte', label: 'Carte', icon: PhMapTrifold },
  { to: '/admin/points-retrait', label: 'Points retrait', icon: PhMapPin },
  { to: '/admin/candidatures', label: 'Candidatures points', icon: PhClipboardText },
  { to: '/admin/frais-livraison', label: 'Frais livraison', icon: PhCurrencyCircleDollar },
  { to: '/admin/finance', label: 'Compte principal', icon: PhBank },
  { to: '/admin/paiement', label: 'Paiement', icon: PhCreditCard },
  { to: '/admin/signalements', label: 'Signalements', icon: PhFlag },
  { to: '/admin/categories', label: 'Catégories', icon: PhTag },
]
</script>

<template>
  <nav class="admin-sidebar">
    <div class="admin-sidebar__title">Administration</div>
    <NuxtLink
      v-for="item in navItems"
      :key="item.to"
      :to="item.to"
      class="admin-sidebar__item"
      exact-active-class="admin-sidebar__item--active"
      @click="emit('navigate')"
    >
      <component :is="item.icon" :size="19" />
      <span>{{ item.label }}</span>
    </NuxtLink>
  </nav>
</template>

<style scoped>
.admin-sidebar {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px;
  height: 100%;
}

.admin-sidebar__title {
  font-family: var(--font-heading);
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-neutral-500);
  padding: 10px 12px 14px;
}

.admin-sidebar__item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  color: var(--color-neutral-300);
  text-decoration: none;
  font-size: 13.5px;
  font-weight: 500;
}

.admin-sidebar__item:hover {
  background: var(--color-neutral-800);
}

.admin-sidebar__item--active {
  /* color-mix plutôt que --color-primary-100 : ce token n'est pas redéfini
     en thème sombre (voir main.css) et resterait un bleu clair illisible
     en fond de pastille sur fond sombre. color-mix reste relatif à
     --color-primary, donc correct dans les deux thèmes. */
  background: color-mix(in srgb, var(--color-primary) 14%, transparent);
  color: var(--color-primary);
  font-weight: 700;
}
</style>
