<script setup lang="ts">
import { PhCaretRight } from '@phosphor-icons/vue'
import type { Component } from 'vue'
import type { ProductRead } from '~/types/api'

/**
 * Rubrique horizontale de l'accueil ("Nouveautés", "Petits prix"…). Les
 * produits sont fournis par la page : elle décide quand les charger (la
 * rubrique "Près de chez vous" dépend d'une position connue côté client).
 */
withDefaults(
  defineProps<{
    title: string
    icon: Component
    hue: number
    products: ProductRead[]
    loading?: boolean
    seeAll?: boolean
  }>(),
  { loading: false, seeAll: true },
)
const emit = defineEmits<{ seeAll: [] }>()
</script>

<template>
  <section class="rail">
    <header class="rail__head">
      <span class="rail__icon" :style="{ '--hue': hue }"><component :is="icon" :size="18" weight="fill" /></span>
      <h2 class="rail__title">{{ title }}</h2>
      <button v-if="seeAll" type="button" class="rail__all" @click="emit('seeAll')">
        Voir tout
        <PhCaretRight :size="14" weight="bold" />
      </button>
    </header>
    <slot name="before" />
    <div class="rail__track">
      <template v-if="loading">
        <v-skeleton-loader v-for="n in 3" :key="n" type="card" class="rail__cell" />
      </template>
      <div v-for="product in products" v-else :key="product.id" class="rail__cell">
        <ProductCard :product="product" />
      </div>
    </div>
  </section>
</template>

<style scoped>
.rail__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.rail__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: hsl(var(--hue) 70% var(--tint-bg));
  color: hsl(var(--hue) 65% var(--tint-fg));
}

.rail__title {
  flex: 1;
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 800;
  margin: 0;
}

.rail__all {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 6px 4px 6px 10px;
  border: 0;
  background: none;
  color: var(--color-primary-300);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.rail__track {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  scroll-snap-type: x proximity;
  scrollbar-width: none;
  /* Déborde jusqu'aux bords de l'écran : la carte coupée à droite signale
     qu'on peut faire défiler. */
  margin: 0 -12px;
  padding: 2px 12px 8px;
  scroll-padding: 0 12px;
}

.rail__track::-webkit-scrollbar {
  display: none;
}

.rail__cell {
  flex: 0 0 166px;
  /* Une photo qui ne charge pas (texte alternatif long) ne doit pas élargir la carte. */
  min-width: 0;
  scroll-snap-align: start;
}

@media (min-width: 960px) {
  .rail__title {
    font-size: 19px;
  }

  .rail__track {
    gap: 16px;
    margin: 0 -32px;
    padding: 2px 32px 10px;
    scroll-padding: 0 32px;
  }

  .rail__cell {
    flex-basis: 220px;
  }
}
</style>
