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
      :class="{ 'bottom-nav__item--active': isActive(item.to) }"
      :aria-current="isActive(item.to) ? 'page' : undefined"
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
/* Pleine largeur de l'écran (téléphone comme tablette) ; les onglets sont
   recentrés sur une largeur confortable plutôt que d'être étirés. */
.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  justify-content: center;
  border-top: 1px solid var(--color-divider);
  background: color-mix(in srgb, var(--color-neutral-900) 92%, transparent);
  backdrop-filter: saturate(160%) blur(12px);
  -webkit-backdrop-filter: saturate(160%) blur(12px);
  box-shadow: var(--shadow-dock);
  padding: 6px 8px calc(8px + env(safe-area-inset-bottom, 0px));
  z-index: 10;
}

/* Remplacée par la navigation de LayoutTopBar sur ordinateur (voir TopBar.vue). */
@media (min-width: 960px) {
  .bottom-nav {
    display: none;
  }
}

.bottom-nav__item {
  flex: 1;
  max-width: 120px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-neutral-500);
  text-decoration: none;
  padding: 2px 0;
}

.bottom-nav__item--active {
  color: var(--color-primary-300);
}

/* Pastille derrière l'icône active (façon onglets Material). */
.bottom-nav__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 30px;
  border-radius: 999px;
  transition: background 0.2s ease;
}

.bottom-nav__item--active .bottom-nav__icon {
  background: var(--color-primary-100);
}

/* Tablette : icône et libellé côte à côte, onglets plus larges. */
@media (min-width: 600px) {
  .bottom-nav {
    padding-top: 8px;
  }

  .bottom-nav__item {
    flex-direction: row;
    justify-content: center;
    gap: 6px;
    max-width: 150px;
    padding: 0;
    font-size: 13px;
  }

  .bottom-nav__icon {
    width: auto;
    height: auto;
    background: none !important;
  }

  .bottom-nav__item--active {
    border-radius: 999px;
    background: var(--color-primary-100);
    padding: 8px 12px;
  }
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
