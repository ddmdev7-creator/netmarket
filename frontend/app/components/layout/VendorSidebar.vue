<script setup lang="ts">
import { PhChartBar, PhGear, PhPackage, PhStorefront } from '@phosphor-icons/vue'

const emit = defineEmits<{ navigate: [] }>()

const navItems = [
  { to: '/vendeur', label: 'Tableau de bord', icon: PhChartBar },
  { to: '/vendeur/produits', label: 'Produits', icon: PhPackage },
  { to: '/vendeur/commandes', label: 'Commandes', icon: PhStorefront },
  { to: '/vendeur/boutique', label: 'Boutique', icon: PhGear },
]
</script>

<template>
  <nav class="vendor-sidebar">
    <div class="vendor-sidebar__title">Espace vendeur</div>
    <NuxtLink
      v-for="item in navItems"
      :key="item.to"
      :to="item.to"
      class="vendor-sidebar__item"
      exact-active-class="vendor-sidebar__item--active"
      @click="emit('navigate')"
    >
      <component :is="item.icon" :size="19" />
      <span>{{ item.label }}</span>
    </NuxtLink>
  </nav>
</template>

<style scoped>
.vendor-sidebar {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px;
  height: 100%;
}

.vendor-sidebar__title {
  font-family: var(--font-heading);
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-neutral-500);
  padding: 10px 12px 14px;
}

.vendor-sidebar__item {
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

.vendor-sidebar__item:hover {
  background: var(--color-neutral-800);
}

.vendor-sidebar__item--active {
  /* color-mix plutôt qu'un token -100 fixe : reste correct dans les deux
     thèmes (voir la même remarque sur AdminSidebar.vue). */
  background: color-mix(in srgb, var(--color-primary) 14%, transparent);
  color: var(--color-primary);
  font-weight: 700;
}
</style>
