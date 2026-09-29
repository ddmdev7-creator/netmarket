<script setup lang="ts">
import type { Component } from 'vue'

/**
 * Navigation des espaces livreur et point de retrait : barre du bas pleine
 * largeur sur téléphone et tablette (même rendu que BottomNav.vue), dock
 * flottant centré sur ordinateur.
 */
const props = defineProps<{ items: { to: string; label: string; icon: Component; badge?: number }[] }>()

const route = useRoute()
const rootPath = computed(() => props.items[0]?.to ?? '/')
function isActive(to: string) {
  return to === rootPath.value ? route.path === to : route.path.startsWith(to)
}
</script>

<template>
  <nav class="space-nav">
    <NuxtLink
      v-for="item in items"
      :key="item.to"
      :to="item.to"
      class="space-nav__item"
      :class="{ 'space-nav__item--active': isActive(item.to) }"
      :aria-current="isActive(item.to) ? 'page' : undefined"
    >
      <span class="space-nav__icon">
        <component :is="item.icon" :size="22" :weight="isActive(item.to) ? 'fill' : 'regular'" />
        <span v-if="item.badge" class="space-nav__badge">{{ item.badge > 9 ? '9+' : item.badge }}</span>
      </span>
      <span>{{ item.label }}</span>
    </NuxtLink>
  </nav>
</template>

<style scoped>
.space-nav {
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

.space-nav__item {
  flex: 1;
  max-width: 120px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 2px 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-neutral-500);
  text-decoration: none;
}

.space-nav__item--active {
  color: var(--color-primary-300);
}

.space-nav__icon {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 30px;
  border-radius: 999px;
  transition: background 0.2s ease;
}

.space-nav__item--active .space-nav__icon {
  background: var(--color-primary-100);
}

.space-nav__badge {
  position: absolute;
  top: -2px;
  right: 8px;
  min-width: 17px;
  padding: 0 4px;
  border-radius: 999px;
  background: var(--color-error);
  color: #fff;
  font-size: 10px;
  font-weight: 800;
  line-height: 17px;
  text-align: center;
}

@media (min-width: 600px) {
  .space-nav {
    padding-top: 8px;
  }

  .space-nav__item {
    flex-direction: row;
    justify-content: center;
    gap: 6px;
    max-width: 160px;
    padding: 0;
    font-size: 13px;
  }

  .space-nav__icon {
    width: auto;
    height: auto;
    background: none !important;
  }

  .space-nav__badge {
    top: -6px;
    right: -10px;
  }

  .space-nav__item--active {
    padding: 8px 14px;
    border-radius: 999px;
    background: var(--color-primary-100);
  }
}

/* Ordinateur : dock flottant plutôt qu'une barre collée au bas de l'écran. */
@media (min-width: 960px) {
  .space-nav {
    left: 50%;
    right: auto;
    bottom: 18px;
    transform: translateX(-50%);
    gap: 4px;
    padding: 6px;
    border: 1px solid var(--color-divider);
    border-radius: 999px;
    box-shadow: var(--shadow-lg);
  }

  .space-nav__item {
    flex: none;
    max-width: none;
    padding: 8px 16px;
    border-radius: 999px;
  }

  .space-nav__item:hover:not(.space-nav__item--active) {
    background: var(--color-neutral-800);
  }
}
</style>
