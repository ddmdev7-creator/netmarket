<script setup lang="ts">
import { PhChartBar, PhGear, PhPackage, PhStorefront } from '@phosphor-icons/vue'

const navItems = [
  { to: '/vendeur', label: 'Tableau de bord', icon: PhChartBar },
  { to: '/vendeur/produits', label: 'Produits', icon: PhPackage },
  { to: '/vendeur/commandes', label: 'Commandes', icon: PhStorefront },
  { to: '/vendeur/boutique', label: 'Boutique', icon: PhGear },
]
</script>

<template>
  <nav class="bottom-nav">
    <NuxtLink
      v-for="item in navItems"
      :key="item.to"
      :to="item.to"
      class="bottom-nav__item"
      exact-active-class="bottom-nav__item--active"
    >
      <component :is="item.icon" :size="20" />
      <span>{{ item.label }}</span>
    </NuxtLink>
  </nav>
</template>

<style scoped>
.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 100%;
  max-width: 480px;
  display: flex;
  border-top: 1px solid var(--color-divider);
  background: var(--color-neutral-900);
  box-shadow: var(--shadow-dock);
  padding: 8px 4px calc(10px + env(safe-area-inset-bottom, 0px));
  z-index: 10;
}

.bottom-nav__item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  font-size: 10.5px;
  color: var(--color-neutral-500);
  text-decoration: none;
  padding: 2px 0;
}

.bottom-nav__item--active {
  color: var(--color-primary);
}
</style>
