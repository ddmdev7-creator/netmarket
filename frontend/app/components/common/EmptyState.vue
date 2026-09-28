<script setup lang="ts">
import { PhPackage } from '@phosphor-icons/vue'
import type { RouteLocationRaw } from 'vue-router'

/**
 * État vide : pastille illustrée, titre facultatif, explication, et
 * éventuellement l'action qui permet d'en sortir (« Découvrir les produits »).
 */
withDefaults(
  defineProps<{
    message: string
    icon?: object
    title?: string
    hue?: number
    actionLabel?: string
    actionTo?: RouteLocationRaw
  }>(),
  { icon: () => PhPackage, hue: 220, title: undefined, actionLabel: undefined, actionTo: undefined },
)
</script>

<template>
  <div class="empty-state">
    <span class="empty-state__bubble" :style="{ '--hue': hue }">
      <component :is="icon" :size="32" weight="duotone" />
    </span>
    <h2 v-if="title" class="empty-state__title">{{ title }}</h2>
    <p class="empty-state__message">{{ message }}</p>
    <v-btn v-if="actionLabel && actionTo" color="primary" :to="actionTo" class="mt-2">{{ actionLabel }}</v-btn>
    <slot />
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 40px 16px;
}

.empty-state__bubble {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 68px;
  height: 68px;
  margin-bottom: 12px;
  border-radius: 50%;
  background: hsl(var(--hue) 70% var(--tint-bg));
  color: hsl(var(--hue) 60% var(--tint-fg));
}

.empty-state__title {
  font-family: var(--font-heading);
  font-size: 17px;
  font-weight: 800;
  margin: 0 0 4px;
}

.empty-state__message {
  max-width: 340px;
  margin: 0;
  font-size: 13.5px;
  line-height: 1.45;
  color: var(--color-neutral-400);
}
</style>
