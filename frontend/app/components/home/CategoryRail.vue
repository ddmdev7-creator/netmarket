<script setup lang="ts">
import { PhSquaresFour } from '@phosphor-icons/vue'
import type { CategoryRead } from '~/types/api'

const props = defineProps<{ categories: CategoryRead[]; activeId: string | null }>()
const emit = defineEmits<{ select: [id: string | null] }>()

// Uniquement les catégories principales : les sous-catégories s'affichent
// en pastilles une fois la catégorie ouverte (voir pages/index.vue).
const roots = computed(() =>
  props.categories.filter((c) => c.parent_id === null).sort((a, b) => a.name.localeCompare(b.name, 'fr')),
)
</script>

<template>
  <nav class="cat-rail" aria-label="Catégories">
    <button
      type="button"
      class="cat-rail__item"
      :class="{ 'cat-rail__item--active': activeId === null }"
      :style="{ '--hue': 220 }"
      @click="emit('select', null)"
    >
      <span class="cat-rail__bubble"><PhSquaresFour :size="26" weight="duotone" /></span>
      <span class="cat-rail__label">Tout</span>
    </button>
    <button
      v-for="category in roots"
      :key="category.id"
      type="button"
      class="cat-rail__item"
      :class="{ 'cat-rail__item--active': activeId === category.id }"
      :style="{ '--hue': categoryIcon(category).hue }"
      @click="emit('select', category.id)"
    >
      <span class="cat-rail__bubble">
        <component :is="categoryIcon(category).icon" :size="26" weight="duotone" />
      </span>
      <span class="cat-rail__label">{{ category.name }}</span>
    </button>
  </nav>
</template>

<style scoped>
.cat-rail {
  display: flex;
  gap: 4px;
  overflow-x: auto;
  scrollbar-width: none;
  padding: 2px 0 4px;
  -webkit-mask-image: linear-gradient(to right, black calc(100% - 24px), transparent 100%);
  mask-image: linear-gradient(to right, black calc(100% - 24px), transparent 100%);
}

.cat-rail::-webkit-scrollbar {
  display: none;
}

.cat-rail__item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  flex: 0 0 74px;
  padding: 4px 2px;
  border: 0;
  background: none;
  cursor: pointer;
  color: var(--color-neutral-300);
}

.cat-rail__bubble {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 58px;
  height: 58px;
  border-radius: 50%;
  background: hsl(var(--hue) 70% var(--tint-bg));
  color: hsl(var(--hue) 60% var(--tint-fg));
  border: 2px solid transparent;
  transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}

.cat-rail__item:hover .cat-rail__bubble {
  transform: translateY(-2px);
}

.cat-rail__item--active .cat-rail__bubble {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-primary-100);
}

.cat-rail__label {
  font-size: 11.5px;
  font-weight: 600;
  line-height: 1.2;
  text-align: center;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-width: 100%;
}

.cat-rail__item--active .cat-rail__label {
  color: var(--color-primary-300);
}

@media (min-width: 960px) {
  .cat-rail {
    gap: 10px;
  }

  .cat-rail__item {
    flex-basis: 92px;
  }

  .cat-rail__bubble {
    width: 68px;
    height: 68px;
  }

  .cat-rail__label {
    font-size: 12.5px;
  }
}
</style>
