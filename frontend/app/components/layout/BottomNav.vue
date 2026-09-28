<script setup lang="ts">
import { PhHeart, PhHouse, PhShoppingCart, PhPackage, PhUser } from '@phosphor-icons/vue'

const cartStore = useCartStore()
const route = useRoute()

function isActive(to: string) {
  return to === '/' ? route.path === '/' : route.path.startsWith(to)
}

const navItems = [
  { to: '/', label: 'Accueil', icon: PhHouse },
  { to: '/favoris', label: 'Favoris', icon: PhHeart },
  { to: '/panier', label: 'Panier', icon: PhShoppingCart },
  { to: '/commandes', label: 'Commandes', icon: PhPackage },
  { to: '/profil', label: 'Profil', icon: PhUser },
]
</script>

<template>
  <nav class="bottom-nav">
    <NuxtLink
      v-for="item in navItems"
      :key="item.to"
      :to="item.to"
      class="bottom-nav__item"
      active-class="bottom-nav__item--active"
    >
      <span :key="item.to === '/panier' ? cartStore.bumpTick : 0" class="bottom-nav__icon" :class="{ 'is-bump': item.to === '/panier' && cartStore.bumpTick > 0 }">
        <v-badge
          v-if="item.to === '/panier' && cartStore.itemCount > 0"
          :content="cartStore.itemCount"
          color="primary"
          offset-x="-2"
          offset-y="-2"
        >
          <component :is="item.icon" :size="22" :weight="isActive(item.to) ? 'fill' : 'regular'" />
        </v-badge>
        <component :is="item.icon" v-else :size="22" :weight="isActive(item.to) ? 'fill' : 'regular'" />
      </span>
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

/* Remplacée par la navigation horizontale de LayoutTopBar sur desktop
   (voir TopBar.vue) -- même seuil que .app-shell. */
@media (min-width: 960px) {
  .bottom-nav {
    display: none;
  }
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

.bottom-nav__icon {
  display: inline-flex;
}

.bottom-nav__icon.is-bump {
  animation: cart-bump 0.5s cubic-bezier(0.3, 1.6, 0.5, 1);
}

@keyframes cart-bump {
  30% {
    transform: scale(1.35) translateY(-3px);
  }
  100% {
    transform: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .bottom-nav__icon.is-bump {
    animation: none;
  }
}
</style>
